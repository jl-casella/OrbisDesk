// SPDX-License-Identifier: GPL-3.0-or-later
// Non-Steam games: the list, paths, exe and shortcut reading, the search on the console (steam_nonsteam.h).
#include "steam_nonsteam.h"

#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <map>
#include <set>

#include "steam/backend/json.h"

namespace orbisdesk {
namespace {

bool IsDir(const std::string& path) {
  struct stat st{};
  return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}
bool IsFile(const std::string& path, std::uint64_t* bytes = nullptr) {
  struct stat st{};
  if (stat(path.c_str(), &st) != 0 || !S_ISREG(st.st_mode)) return false;
  if (bytes) *bytes = static_cast<std::uint64_t>(st.st_size);
  return true;
}

std::vector<std::string> Names(const std::string& dir) {
  std::vector<std::string> names;
  DIR* listing = opendir(dir.c_str());
  if (!listing) return names;
  while (dirent* entry = readdir(listing)) {
    const std::string name = entry->d_name;
    if (name != "." && name != "..") names.push_back(name);
    if (names.size() >= 4096) break;
  }
  closedir(listing);
  return names;
}

bool EndsWith(const std::string& text, const std::string& end) {
  return text.size() >= end.size() && LowerAscii(text.substr(text.size() - end.size())) == end;
}

std::string Escape(const std::string& text) {
  std::string out;
  for (const char c : text) {
    if (c == '\\') out += "\\\\";
    else if (c == '\t') out += "\\t";
    else if (c == '\n') out += "\\n";
    else if (c == '\r') out += "\\r";
    else out += c;
  }
  return out;
}

std::string Unescape(const std::string& text) {
  std::string out;
  for (std::size_t i = 0; i < text.size(); ++i) {
    if (text[i] != '\\' || i + 1 == text.size()) {
      out += text[i];
      continue;
    }
    const char c = text[++i];
    out += c == 't' ? '\t' : c == 'n' ? '\n' : c == 'r' ? '\r' : c;
  }
  return out;
}

std::vector<std::string> SplitTabs(const std::string& line) {
  std::vector<std::string> fields;
  std::string field;
  for (const char c : line) {
    if (c == '\t') fields.push_back(field), field.clear();
    else field += c;
  }
  fields.push_back(field);
  return fields;
}

void AppendUtf8(std::string* out, std::uint32_t cp) {
  if (cp < 0x80) *out += static_cast<char>(cp);
  else if (cp < 0x800) *out += static_cast<char>(0xc0 | (cp >> 6)), *out += static_cast<char>(0x80 | (cp & 0x3f));
  else if (cp < 0x10000)
    *out += static_cast<char>(0xe0 | (cp >> 12)), *out += static_cast<char>(0x80 | ((cp >> 6) & 0x3f)),
        *out += static_cast<char>(0x80 | (cp & 0x3f));
  else
    *out += static_cast<char>(0xf0 | (cp >> 18)), *out += static_cast<char>(0x80 | ((cp >> 12) & 0x3f)),
        *out += static_cast<char>(0x80 | ((cp >> 6) & 0x3f)), *out += static_cast<char>(0x80 | (cp & 0x3f));
}

// UTF-16LE (count units, or up to a NUL when count is npos) to UTF-8
std::string Utf16(const std::string& data, std::size_t at, std::size_t count) {
  std::string out;
  for (std::size_t i = 0; i < count && at + 2 * i + 1 < data.size(); ++i) {
    std::uint32_t unit = static_cast<std::uint8_t>(data[at + 2 * i]) | static_cast<std::uint8_t>(data[at + 2 * i + 1]) << 8;
    if (!unit) break;
    if (unit >= 0xd800 && unit < 0xdc00 && at + 2 * i + 3 < data.size()) {
      const std::uint32_t low = static_cast<std::uint8_t>(data[at + 2 * i + 2]) | static_cast<std::uint8_t>(data[at + 2 * i + 3]) << 8;
      if (low >= 0xdc00 && low < 0xe000) {
        unit = 0x10000 + ((unit - 0xd800) << 10) + (low - 0xdc00);
        ++i;
      }
    }
    AppendUtf8(&out, unit);
  }
  return out;
}

std::string Latin1(const std::string& data, std::size_t at, std::size_t count) {
  std::string out;
  for (std::size_t i = 0; i < count && at + i < data.size(); ++i) {
    const auto c = static_cast<std::uint8_t>(data[at + i]);
    if (!c) break;
    AppendUtf8(&out, c);
  }
  return out;
}

std::uint32_t U16(const std::string& d, std::size_t at) {
  return at + 2 <= d.size() ? static_cast<std::uint8_t>(d[at]) | static_cast<std::uint8_t>(d[at + 1]) << 8 : 0;
}
std::uint32_t U32(const std::string& d, std::size_t at) {
  return at + 4 <= d.size() ? U16(d, at) | U16(d, at + 2) << 16 : 0;
}

bool ReadAt(int fd, std::uint64_t offset, std::size_t size, std::string* out) {
  out->assign(size, '\0');
  std::size_t done = 0;
  while (done < size) {
    const ssize_t got = pread(fd, &(*out)[done], size - done, static_cast<off_t>(offset + done));
    if (got <= 0) break;
    done += static_cast<std::size_t>(got);
  }
  out->resize(done);
  return done == size;
}

// the value of a VS_VERSIONINFO string (UTF-16LE key) in a version resource
std::string VersionString(const std::string& block, const char* key) {
  std::string wide;
  for (const char* k = key; *k; ++k) wide += *k, wide += '\0';
  wide += std::string(2, '\0');
  for (std::size_t at = block.find(wide); at != std::string::npos; at = block.find(wide, at + 2)) {
    if (at < 6 || at % 2) continue;
    const std::size_t value_units = U16(block, at - 4);
    std::size_t value = at + wide.size();
    value = (value + 3) & ~static_cast<std::size_t>(3);
    if (!value_units || value >= block.size()) continue;
    std::string text = Utf16(block, value, value_units);
    while (!text.empty() && (text.back() == ' ' || text.back() == '\0')) text.pop_back();
    while (!text.empty() && text.front() == ' ') text.erase(text.begin());
    if (!text.empty()) return text;
  }
  return "";
}

// one case-insensitive step down a path: the console's file systems keep case, Windows paths don't
std::string Resolve(const std::string& base, const std::string& relative) {
  std::string path = base;
  std::string part;
  auto step = [&](const std::string& name) {
    if (name.empty() || name == ".") return true;
    if (name == "..") {
      const auto slash = path.find_last_of('/');
      if (slash != std::string::npos && slash > 0) path.resize(slash);
      return true;
    }
    std::string next = path + "/" + name;
    struct stat st{};
    if (stat(next.c_str(), &st) == 0) {
      path = next;
      return true;
    }
    const std::string lower = LowerAscii(name);
    for (const auto& entry : Names(path))
      if (LowerAscii(entry) == lower) {
        path += "/" + entry;
        return true;
      }
    path = next;  // absent: kept as asked, so the caller sees it doesn't exist
    return false;
  };
  for (const char c : relative) {
    if (c == '\\' || c == '/') step(part), part.clear();
    else part += c;
  }
  step(part);
  return path;
}

std::string Stem(const std::string& file) {
  const auto dot = file.find_last_of('.');
  return dot == std::string::npos ? file : file.substr(0, dot);
}

bool UnderAny(const std::string& unix_path, const std::vector<std::string>& roots) {
  for (const auto& root : roots)
    if (!root.empty() && unix_path.compare(0, root.size(), root) == 0 &&
        (unix_path.size() == root.size() || unix_path[root.size()] == '/'))
      return true;
  return false;
}

}  // namespace

std::string LowerAscii(std::string text) {
  for (auto& c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return text;
}

std::string CleanName(const std::string& name) {
  std::string out;
  for (const char c : name) {
    const auto u = static_cast<unsigned char>(c);
    out += (u < 0x20 || u == 0x7f) ? ' ' : c;
  }
  while (!out.empty() && out.back() == ' ') out.pop_back();
  while (!out.empty() && out.front() == ' ') out.erase(out.begin());
  return out.size() > 120 ? out.substr(0, 120) : out;
}

std::uint32_t NonSteamId(const std::string& program) {
  std::uint32_t hash = 0x811c9dc5u;
  for (const char c : LowerAscii(program)) hash = (hash ^ static_cast<std::uint8_t>(c == '/' ? '\\' : c)) * 0x01000193u;
  return hash | 0x80000000u;
}

std::vector<NonSteamGame> LoadNonSteamGames(const std::string& path) {
  std::vector<NonSteamGame> games;
  FILE* file = fopen(path.c_str(), "rb");
  if (!file) return games;
  std::string text;
  char chunk[4096];
  for (std::size_t got; (got = fread(chunk, 1, sizeof(chunk), file)) > 0 && text.size() < (4u << 20);) text.append(chunk, got);
  fclose(file);
  std::size_t start = 0;
  std::set<std::uint32_t> seen;
  while (start < text.size()) {
    auto end = text.find('\n', start);
    if (end == std::string::npos) end = text.size();
    const std::string line = text.substr(start, end - start);
    start = end + 1;
    if (line.empty() || line[0] == '#') continue;
    const auto f = SplitTabs(line);
    if (f.size() < 7) continue;
    NonSteamGame game;
    game.added = strtoull(f[1].c_str(), nullptr, 10);
    game.name = CleanName(Unescape(f[2]));
    game.program = Unescape(f[3]);
    game.folder = Unescape(f[4]);
    game.options = Unescape(f[5]);
    game.cover = Unescape(f[6]);
    game.named = f.size() > 7 && f[7] == "1";  // a later column: lists without it read as not named
    if (game.program.size() < 4 || game.name.empty()) continue;
    game.id = NonSteamId(game.program);  // from the program, whatever the line says
    if (!seen.insert(game.id).second) continue;
    games.push_back(std::move(game));
  }
  return games;
}

bool SaveNonSteamGames(const std::string& path, const std::vector<NonSteamGame>& games) {
  std::string text = "# OrbisDesk non-Steam games 1: id, added, name, program, folder, options, cover, named\n";
  for (const auto& g : games)
    text += std::to_string(g.id) + "\t" + std::to_string(g.added) + "\t" + Escape(g.name) + "\t" + Escape(g.program) + "\t" +
            Escape(g.folder) + "\t" + Escape(g.options) + "\t" + Escape(g.cover) + "\t" + (g.named ? "1" : "0") + "\n";
  const std::string temp = path + ".tmp";
  const int fd = open(temp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0) return false;
  std::size_t done = 0;
  bool ok = true;
  while (ok && done < text.size()) {
    const ssize_t wrote = write(fd, text.data() + done, text.size() - done);
    if (wrote <= 0) ok = false;
    else done += static_cast<std::size_t>(wrote);
  }
  ok = ok && fsync(fd) == 0;
  close(fd);
  if (!ok || rename(temp.c_str(), path.c_str()) != 0) {
    unlink(temp.c_str());
    return false;
  }
  return true;
}

NonSteamRoots& Roots() {
  static NonSteamRoots roots = [] {
    NonSteamRoots r;
    r.drive_c = "/data/wine-prefix/drive_c";
    r.z = "/data";
    for (int i = 0; i < 8; ++i) r.usb.push_back("/mnt/usb" + std::to_string(i));
    return r;
  }();
  return roots;
}

std::string WindowsToUnix(const std::string& windows) {
  if (windows.size() < 2 || windows[1] != ':') return "";
  const char letter = static_cast<char>(std::toupper(static_cast<unsigned char>(windows[0])));
  std::string base;
  if (letter == 'C') base = Roots().drive_c;
  else if (letter == 'Z') base = Roots().z;
  else if (letter >= 'D' && letter < 'D' + static_cast<int>(Roots().usb.size())) base = Roots().usb[static_cast<std::size_t>(letter - 'D')];
  if (base.empty()) return "";
  return Resolve(base, windows.substr(2));
}

std::string UnixToWindows(const std::string& unix_path) {
  auto under = [&](const std::string& root, char letter) -> std::string {
    if (root.empty() || unix_path.compare(0, root.size(), root) != 0) return "";
    if (unix_path.size() > root.size() && unix_path[root.size()] != '/') return "";
    std::string rest = unix_path.substr(root.size());
    for (auto& c : rest)
      if (c == '/') c = '\\';
    return std::string(1, letter) + ":" + (rest.empty() ? "\\" : rest);
  };
  std::string out = under(Roots().drive_c, 'C');
  for (std::size_t i = 0; out.empty() && i < Roots().usb.size(); ++i) out = under(Roots().usb[i], static_cast<char>('D' + i));
  if (out.empty()) out = under(Roots().z, 'Z');
  return out;
}

std::string WindowsFolder(const std::string& windows) {
  const auto slash = windows.find_last_of("\\/");
  if (slash == std::string::npos) return windows;
  return slash == 2 ? windows.substr(0, 3) : windows.substr(0, slash);
}

std::string WindowsBasename(const std::string& windows) {
  const auto slash = windows.find_last_of("\\/");
  return slash == std::string::npos ? windows : windows.substr(slash + 1);
}

ExeInfo ReadExeInfo(const std::string& unix_path) {
  ExeInfo info;
  const int fd = open(unix_path.c_str(), O_RDONLY);
  if (fd < 0) return info;
  std::string head;
  ReadAt(fd, 0, 4096, &head);
  const std::uint32_t pe = U32(head, 0x3c);
  if (head.size() < 64 || head.compare(0, 2, "MZ") != 0 || pe + 24 > head.size() || head.compare(pe, 4, std::string("PE\0\0", 4)) != 0) {
    close(fd);
    return info;
  }
  info.pe = true;
  const std::uint32_t machine = U16(head, pe + 4);
  info.arch = machine == 0x14c ? "x86" : machine == 0x8664 ? "x64" : "other";
  const std::uint32_t sections = U16(head, pe + 6), optional_size = U16(head, pe + 20);
  const std::size_t optional = pe + 24;
  const std::uint32_t magic = U16(head, optional);
  const std::size_t directories = optional + (magic == 0x20b ? 112 : 96);
  const std::uint32_t resource_rva = U32(head, directories + 2 * 8);
  std::string table;
  if (resource_rva && sections && sections < 96 && ReadAt(fd, optional + optional_size, sections * 40u, &table)) {
    for (std::uint32_t s = 0; s < sections; ++s) {
      const std::size_t at = s * 40u;
      const std::uint32_t va = U32(table, at + 12), raw_size = U32(table, at + 16), raw = U32(table, at + 20);
      const std::uint32_t vsize = std::max(U32(table, at + 8), raw_size);
      if (resource_rva < va || resource_rva >= va + vsize) continue;
      std::string res;
      const std::uint32_t size = std::min<std::uint32_t>(raw_size, 16u << 20);
      if (!ReadAt(fd, raw + (resource_rva - va), size - std::min(size, resource_rva - va), &res)) break;
      // root: RT_VERSION (16); then its first name, its first language, the data entry
      auto find = [&](std::size_t dir, std::uint32_t id, bool first) -> std::uint32_t {
        const std::uint32_t named = U16(res, dir + 12), ids = U16(res, dir + 14);
        for (std::uint32_t e = 0; e < named + ids && e < 512; ++e) {
          const std::size_t entry = dir + 16 + e * 8u;
          if (first || (e >= named && U32(res, entry) == id)) return U32(res, entry + 4);
        }
        return 0;
      };
      const std::uint32_t types = find(0, 16, false);
      if (!(types & 0x80000000u)) break;
      const std::uint32_t names = find(types & 0x7fffffffu, 0, true);
      if (!(names & 0x80000000u)) break;
      const std::uint32_t data = find(names & 0x7fffffffu, 0, true);
      if (data & 0x80000000u) break;
      const std::uint32_t data_rva = U32(res, data), data_size = U32(res, data + 4);
      if (data_rva < resource_rva || data_rva - resource_rva >= res.size()) break;
      const std::string block = res.substr(data_rva - resource_rva, std::min<std::size_t>(data_size, 1u << 20));
      info.product = VersionString(block, "ProductName");
      if (info.product.empty()) info.product = VersionString(block, "FileDescription");
      break;
    }
  }
  close(fd);
  info.product = CleanName(info.product);
  return info;
}

LinkTarget ParseLink(const std::string& d) {
  LinkTarget link;
  if (d.size() < 0x4c || U32(d, 0) != 0x4c) return link;
  const std::uint32_t flags = U32(d, 0x14);
  std::size_t at = 0x4c;
  if (flags & 0x1) at += 2 + U16(d, at);  // LinkTargetIDList
  std::string base;
  if (flags & 0x2) {  // LinkInfo
    const std::uint32_t size = U32(d, at), header = U32(d, at + 4), info_flags = U32(d, at + 8);
    if (size < 0x1c || at + size > d.size()) return link;
    if (info_flags & 1) {
      const bool wide = header >= 0x24 && U32(d, at + 28);
      base = wide ? Utf16(d, at + U32(d, at + 28), 4096) : Latin1(d, at + U32(d, at + 16), 4096);
      if (wide && U32(d, at + 32)) base += Utf16(d, at + U32(d, at + 32), 4096);
      else if (U32(d, at + 24)) base += Latin1(d, at + U32(d, at + 24), 4096);
    }
    at += size;
  }
  const bool unicode = flags & 0x80;
  auto string_data = [&]() {
    const std::size_t count = U16(d, at);
    std::string text = unicode ? Utf16(d, at + 2, count) : Latin1(d, at + 2, count);
    at += 2 + count * (unicode ? 2 : 1);
    return text;
  };
  std::string name, relative;
  if (flags & 0x4) name = string_data();
  if (flags & 0x8) relative = string_data();
  if (flags & 0x10) link.folder = string_data();
  if (flags & 0x20) link.arguments = string_data();
  link.target = base.empty() ? relative : base;
  link.ok = !link.target.empty() && at <= d.size();
  return link;
}

LinkTarget ReadLink(const std::string& unix_path) {
  LinkTarget link;
  FILE* file = fopen(unix_path.c_str(), "rb");
  if (!file) return link;
  std::string bytes(65536, '\0');
  bytes.resize(fread(&bytes[0], 1, bytes.size(), file));
  fclose(file);
  link = ParseLink(bytes);
  // a relative target is from the link's own folder
  if (link.ok && !(link.target.size() > 2 && link.target[1] == ':')) {
    const std::string here = UnixToWindows(unix_path.substr(0, unix_path.find_last_of('/')));
    link.target = here.empty() ? "" : here + "\\" + link.target;
    link.ok = !link.target.empty();
  }
  return link;
}

bool ExcludedProgram(const std::string& file_name) {
  static const char* const kWords[] = {"setup",   "unins",    "install", "update",  "patch",  "crash",  "report",
                                       "redist",  "vcredist", "dxsetup", "directx", "dotnet", "config", "helper",
                                       "regist",  "activat",  "cleanup", "prereq",  "oalinst", "physx", "touchup",
                                       "repair",  "support",  "server",  "dedicated", "cefprocess", "webhelper",
                                       "uploader", "feedback", "eula"};
  const std::string lower = LowerAscii(file_name);
  if (!EndsWith(lower, ".exe")) return true;
  for (const char* word : kWords)
    if (lower.find(word) != std::string::npos) return true;
  return false;
}

std::vector<Candidate> FindNonSteamGames(const std::set<std::string>& known, const std::vector<std::string>& skip_unix) {
  std::vector<Candidate> found;
  std::set<std::string> seen = known;
  std::set<std::string> shortcut_folders;  // a game a shortcut already found is not offered again by its folder
  auto take = [&](Candidate c, const std::string& unix_program) {
    const std::string key = LowerAscii(c.program);
    if (seen.count(key) || UnderAny(unix_program, skip_unix)) return;
    if (!c.folder.empty() && UnderAny(WindowsToUnix(c.folder), skip_unix)) return;
    seen.insert(key);
    c.name = CleanName(c.name);
    if (!c.name.empty()) found.push_back(std::move(c));
  };
  const auto& roots = Roots();
  // 1: shortcuts (Desktop and Start), as the user sees them; OrbisDesk's own Steam folder is left out
  std::vector<std::pair<std::string, int>> link_dirs = {
      {roots.drive_c + "/users/orbis/Desktop", 0},
      {roots.drive_c + "/users/Public/Desktop", 0},
      {roots.drive_c + "/ProgramData/Microsoft/Windows/Start Menu/Programs", 2},
      {roots.drive_c + "/users/orbis/AppData/Roaming/Microsoft/Windows/Start Menu/Programs", 2}};
  std::vector<std::pair<std::string, int>> pending = link_dirs;
  int looked = 0;
  while (!pending.empty() && looked < 400) {
    const auto [dir, depth] = pending.back();
    pending.pop_back();
    for (const auto& name : Names(dir)) {
      const std::string path = dir + "/" + name;
      if (IsDir(path)) {
        if (depth > 0 && LowerAscii(name) != "steam" && LowerAscii(name) != "orbisdesk") pending.push_back({path, depth - 1});
        continue;
      }
      if (!EndsWith(name, ".lnk")) continue;
      ++looked;
      const auto link = ReadLink(path);
      if (!link.ok || ExcludedProgram(WindowsBasename(link.target))) continue;
      const std::string program = WindowsToUnix(link.target);
      if (program.empty() || !IsFile(program)) continue;
      const auto exe = ReadExeInfo(program);
      if (!exe.pe) continue;
      Candidate c;
      c.name = Stem(name);
      c.program = UnixToWindows(program);
      c.folder = link.folder.empty() ? WindowsFolder(c.program) : link.folder;
      c.options = link.arguments;
      c.arch = exe.arch;
      c.shortcut = true;
      shortcut_folders.insert(LowerAscii(WindowsFolder(c.program)));
      take(std::move(c), program);
    }
  }
  // 2: game folders: one candidate per folder, its largest exe that names itself (else its largest)
  std::vector<std::string> bases = {roots.drive_c + "/Program Files", roots.drive_c + "/Program Files (x86)",
                                    roots.drive_c + "/Games"};
  for (const auto& usb : roots.usb) {
    if (!IsDir(usb)) continue;
    bases.push_back(usb);
    bases.push_back(Resolve(usb, "Games"));
  }
  static const char* const kSkipFolders[] = {"steam games", "steam-games", "windows", "orbis", "common files",
                                             "internet explorer", "windows nt", "windowspowershell", "windows media player",
                                             "microsoft", "microsoft.net", "steam", "games", "system volume information",
                                             "$recycle.bin", "orbisdesk", "wine-prefix", "wine"};
  for (const auto& base : bases) {
    if (!IsDir(base)) continue;
    for (const auto& folder : Names(base)) {
      const std::string lower = LowerAscii(folder);
      bool skip = folder[0] == '.';
      for (const char* s : kSkipFolders) skip = skip || lower == s || (lower.rfind("microsoft", 0) == 0);
      const std::string game_dir = base + "/" + folder;
      if (skip || !IsDir(game_dir) || UnderAny(game_dir, skip_unix)) continue;
      std::string best;
      std::uint64_t best_bytes = 0;
      bool best_named = false;
      ExeInfo best_info;
      auto consider = [&](const std::string& dir) {
        for (const auto& name : Names(dir)) {
          std::uint64_t bytes = 0;
          if (ExcludedProgram(name) || !IsFile(dir + "/" + name, &bytes)) continue;
          const auto exe = ReadExeInfo(dir + "/" + name);
          if (!exe.pe) continue;
          const bool named = !exe.product.empty();
          if (best.empty() || (named && !best_named) || (named == best_named && bytes > best_bytes)) {
            best = dir + "/" + name, best_bytes = bytes, best_named = named, best_info = exe;
          }
        }
      };
      consider(game_dir);
      for (const auto& sub : Names(game_dir))
        if (IsDir(game_dir + "/" + sub)) consider(game_dir + "/" + sub);
      if (best.empty()) continue;
      Candidate c;
      c.program = UnixToWindows(best);
      c.folder = WindowsFolder(c.program);
      c.name = best_info.product.empty() ? folder : best_info.product;
      c.arch = best_info.arch;
      if (shortcut_folders.count(LowerAscii(c.folder))) continue;
      take(std::move(c), best);
    }
  }
  return found;
}

bool ListFolder(const std::string& unix_path, const std::vector<std::string>& extensions, std::vector<FolderEntry>* out) {
  out->clear();
  if (!IsDir(unix_path)) return false;
  std::vector<FolderEntry> folders, files;
  for (const auto& name : Names(unix_path)) {
    if (name[0] == '.') continue;
    const std::string path = unix_path + "/" + name;
    FolderEntry entry;
    entry.name = name;
    if (IsDir(path)) {
      entry.folder = true;
      folders.push_back(entry);
      continue;
    }
    bool wanted = false;
    for (const auto& ext : extensions) wanted = wanted || EndsWith(name, ext);
    if (wanted && IsFile(path, &entry.bytes)) files.push_back(entry);
  }
  auto by_name = [](const FolderEntry& a, const FolderEntry& b) { return LowerAscii(a.name) < LowerAscii(b.name); };
  std::sort(folders.begin(), folders.end(), by_name);
  std::sort(files.begin(), files.end(), by_name);
  *out = folders;
  out->insert(out->end(), files.begin(), files.end());
  return true;
}

std::string StoreSearchUrl(const std::string& name) {
  static const char hex[] = "0123456789ABCDEF";
  std::string term;
  for (const unsigned char c : name) {
    if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') term += static_cast<char>(c);
    else term += '%', term += hex[c >> 4], term += hex[c & 15];
  }
  return "https://store.steampowered.com/api/storesearch/?term=" + term + "&l=english&cc=US";
}

std::string StoreSuggestUrl(const std::string& name) {
  std::string quoted;
  for (const char c : name) {
    if (c == '"' || c == '\\') quoted += '\\';
    quoted += c;
  }
  const std::string input = "{\"search_term\":\"" + quoted +
                            "\",\"max_results\":10,\"context\":{\"language\":\"english\",\"country_code\":\"US\"},"
                            "\"filters\":{\"type_filters\":{\"include_apps\":true}}}";
  static const char hex[] = "0123456789ABCDEF";
  std::string encoded;
  for (const unsigned char c : input) {
    if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') encoded += static_cast<char>(c);
    else encoded += '%', encoded += hex[c >> 4], encoded += hex[c & 15];
  }
  return "https://api.steampowered.com/IStoreQueryService/SearchSuggestions/v1?input_json=" + encoded;
}

std::vector<std::uint32_t> ParseStoreSuggest(const std::string& body) {
  std::vector<std::uint32_t> apps;
  const auto root = playden::steam::json::Parse(body);
  if (!root || !root->is_object()) return apps;
  const auto* response = root->Find("response");
  const auto* ids = response && response->is_object() ? response->Find("ids") : nullptr;
  if (!ids || !ids->is_array()) return apps;
  for (const auto& item : ids->array()) {
    const auto* app = item.is_object() ? item.Find("appid") : nullptr;
    const auto id = app ? app->AsUint64() : std::nullopt;
    if (id && *id && *id < 0x80000000u) apps.push_back(static_cast<std::uint32_t>(*id));
    if (apps.size() >= 8) break;
  }
  return apps;
}

namespace {
// the program's folder as a name: the folder, or its parent when the folder is a bin, game or system one
std::string FolderTerm(const std::string& program) {
  std::string folder = WindowsBasename(WindowsFolder(program));
  static const char* const kGeneric[] = {"bin", "binaries", "win32", "win64", "x86", "x64", "game", "games", "system", "exe", "pc"};
  for (const char* generic : kGeneric)
    if (LowerAscii(folder) == generic) folder = WindowsBasename(WindowsFolder(WindowsFolder(program)));
  std::string term;
  if (folder.size() > 2 && folder[1] != ':')
    for (const char c : folder) term += (c == '_' || c == '.') ? ' ' : c;
  return term;
}
}  // namespace

std::vector<std::string> StoreSearchTerms(const std::string& name, const std::string& program, bool named) {
  std::vector<std::string> terms;
  auto squeeze = [](std::string text) {
    std::string out;
    for (const char c : text) {
      if (c == ' ' && (out.empty() || out.back() == ' ')) continue;
      out += c;
    }
    while (!out.empty() && (out.back() == ' ' || out.back() == '-' || out.back() == ':')) out.pop_back();
    return out;
  };
  auto add = [&](const std::string& term) {
    const std::string t = squeeze(term);
    if (t.size() < 3 || terms.size() >= 5) return;
    for (const auto& have : terms)
      if (LowerAscii(have) == LowerAscii(t)) return;
    terms.push_back(t);
  };
  // the name with the signs, brackets and separators the store search trips on taken out
  std::string plain;
  int depth = 0;
  for (std::size_t i = 0; i < name.size(); ++i) {
    const char c = name[i];
    if (c == '(' || c == '[') ++depth;
    else if ((c == ')' || c == ']') && depth) --depth;
    else if (depth) continue;
    else if (!name.compare(i, 3, "\xe2\x84\xa2") || !name.compare(i, 2, "\xc2\xae") || !name.compare(i, 2, "\xc2\xa9")) {
      i += name[i] == '\xe2' ? 2 : 1;  // TM, (R), (C): dropped, the spaces around them stay
    } else if (c == '_' || c == '.') plain += ' ';
    else plain += c;
  }
  plain = squeeze(plain);
  const std::string folder_term = named ? std::string() : FolderTerm(program);
  // a one-word name is usually the exe's own ("speed2"), which finds other games: the folder goes first
  if (plain.find(' ') == std::string::npos) add(folder_term);
  add(plain);
  // without edition words at the end ("Black Edition", "GOTY", "Complete")
  static const char* const kEditions[] = {"edition", "goty", "game of the year", "complete", "deluxe", "gold", "platinum",
                                          "collector's", "collectors", "special", "definitive", "ultimate", "anniversary",
                                          "director's cut", "enhanced", "remastered", "black", "limited", "premium", "pc"};
  std::string trimmed = plain;
  for (bool cut = true; cut;) {
    cut = false;
    const std::string lower = LowerAscii(trimmed);
    for (const char* word : kEditions) {
      const std::string w = std::string(" ") + word;
      if (lower.size() > w.size() && lower.compare(lower.size() - w.size(), w.size(), w) == 0) {
        trimmed = squeeze(trimmed.substr(0, trimmed.size() - w.size()));
        cut = true;
        break;
      }
    }
  }
  add(trimmed);
  // the title before its subtitle: the longer cut first
  for (const char* sep : {" - ", ":"}) {
    const auto at = trimmed.find(sep);
    if (at != std::string::npos && at >= 3) add(trimmed.substr(0, at));
  }
  add(folder_term);
  return terms;
}

std::vector<std::pair<std::uint32_t, std::string>> ParseStoreSearch(const std::string& body) {
  std::vector<std::pair<std::uint32_t, std::string>> apps;
  const auto root = playden::steam::json::Parse(body);
  if (!root || !root->is_object()) return apps;
  const auto* items = root->Find("items");
  if (!items || !items->is_array()) return apps;
  for (const auto& item : items->array()) {
    if (!item.is_object()) continue;
    const auto* type = item.Find("type");
    const auto* id = item.Find("id");
    const auto* name = item.Find("name");
    if (!type || !type->is_string() || type->text() != "app" || !id) continue;
    const auto app = id->AsUint64();
    if (!app || !*app || *app >= 0x80000000u) continue;
    apps.push_back({static_cast<std::uint32_t>(*app), name && name->is_string() ? CleanName(name->text()) : ""});
    if (apps.size() >= 8) break;
  }
  return apps;
}

namespace {
// a name's words for StoreNameMatches: lower case ASCII, apostrophes dropped, anything else not a letter or
// digit (signs such as TM included) a break; II..X as numbers; the small words left out
std::vector<std::string> NameWords(const std::string& text) {
  static const char* const kRoman[] = {"ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"};
  static const char* const kSmall[] = {"the", "a", "an", "of", "and"};
  std::vector<std::string> words;
  std::string word;
  auto flush = [&] {
    if (word.empty()) return;
    for (std::size_t i = 0; i < sizeof(kRoman) / sizeof(kRoman[0]); ++i)
      if (word == kRoman[i]) word = std::to_string(i + 2);
    bool small = false;
    for (const char* s : kSmall) small = small || word == s;
    if (!small) words.push_back(word);
    word.clear();
  };
  for (const unsigned char c : text) {
    if (c == '\'') continue;
    if (c < 0x80 && std::isalnum(c)) word += static_cast<char>(std::tolower(c));
    else flush();
  }
  flush();
  return words;
}

bool IsNumber(const std::string& word) {
  return !word.empty() && std::all_of(word.begin(), word.end(), [](unsigned char c) { return std::isdigit(c); });
}
}  // namespace

bool StoreNameMatches(const std::string& name, const std::string& found) {
  // words a store or an article adds or leaves out of the same game's name
  static const std::set<std::string> kEdition = {"edition", "goty", "game", "year", "complete", "deluxe", "gold", "platinum",
                                                 "collectors", "special", "definitive", "ultimate", "anniversary", "directors",
                                                 "cut", "enhanced", "remastered", "black", "limited", "premium", "pc", "version"};
  const auto mine = NameWords(name), theirs = NameWords(found);
  if (mine.empty() || theirs.empty()) return false;
  const std::set<std::string> have(mine.begin(), mine.end()), other(theirs.begin(), theirs.end());
  auto sequels = [](const std::set<std::string>& words) {
    std::set<std::string> out;
    for (const auto& word : words)
      if (IsNumber(word) && word.size() <= 2 && word != "0") out.insert(word);
    return out;
  };
  if (sequels(have) != sequels(other)) return false;  // Underground is not Underground 2, nor II the first
  auto spare = [&](const std::set<std::string>& from, const std::set<std::string>& than) {
    for (const auto& word : from)
      if (!than.count(word) && !kEdition.count(word) && !(IsNumber(word) && word.size() == 4)) return false;
    return true;  // every word `from` has beyond `than` is an edition's or a year
  };
  if (spare(other, have) && spare(have, other)) return true;  // the same name, editions and years aside
  // or the found name is the title without the subtitle after the last " - " or ":", and adds nothing
  std::string title = name;
  for (const char* sep : {" - ", ":"}) {
    const auto at = title.rfind(sep);
    if (at != std::string::npos && at > 0) {
      title.resize(at);
      break;
    }
  }
  const auto main = NameWords(title);
  if (main.empty() || main.size() == mine.size()) return false;
  for (const auto& word : main)
    if (!other.count(word)) return false;
  return spare(other, have);
}

bool CoverNameMatches(const std::string& name, const std::string& program, bool named, const std::string& found) {
  if (StoreNameMatches(name, found)) return true;
  const std::string folder = named ? std::string() : FolderTerm(program);
  return !folder.empty() && StoreNameMatches(folder, found);
}

std::string WikipediaSearchUrl(const std::string& term) {
  static const char hex[] = "0123456789ABCDEF";
  std::string encoded;
  for (const unsigned char c : term) {
    if (std::isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') encoded += static_cast<char>(c);
    else encoded += '%', encoded += hex[c >> 4], encoded += hex[c & 15];
  }
  return "https://en.wikipedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=0&gsrlimit=5"
         "&prop=pageimages%7Cdescription&piprop=original&pilicense=any&gsrsearch=" + encoded;
}

std::vector<WikiCover> ParseWikipediaCovers(const std::string& body, const std::string& game_name,
                                            const std::string& program, bool named) {
  std::vector<std::pair<std::int64_t, WikiCover>> found;
  const auto root = playden::steam::json::Parse(body);
  const auto* query = root && root->is_object() ? root->Find("query") : nullptr;
  const auto* pages = query && query->is_object() ? query->Find("pages") : nullptr;
  if (!pages || !pages->is_object()) return {};
  for (const auto& [key, page] : pages->object()) {
    (void)key;
    if (!page.is_object()) continue;
    const auto* title = page.Find("title");
    const auto* description = page.Find("description");
    const auto* original = page.Find("original");
    const auto* index = page.Find("index");
    if (!title || !title->is_string() || !description || !description->is_string() || !original || !original->is_object())
      continue;
    const std::string what = LowerAscii(description->text());
    if (what.find("video game") == std::string::npos) continue;
    bool group = false;
    for (const char* word : {"franchise", "series", "list", "compilation", "character", "company", "developer"})
      group = group || what.find(word) != std::string::npos;
    if (group) continue;
    // "Need for Speed (2015 video game)": the bracketed part says what the page is, not the game's name
    std::string name = title->text();
    const auto bracket = name.find(" (");
    if (bracket != std::string::npos) name.resize(bracket);
    if (!CoverNameMatches(game_name, program, named, name)) continue;
    const auto* source = original->Find("source");
    if (!source || !source->is_string()) continue;
    const std::string url = source->text();
    if (url.rfind("https://upload.wikimedia.org/", 0) != 0 || url.find("..") != std::string::npos) continue;
    WikiCover cover;
    cover.title = title->text();
    cover.image = url;
    const auto* width = original->Find("width");
    const auto* height = original->Find("height");
    const auto w = width ? width->AsUint64() : std::nullopt;
    const auto h = height ? height->AsUint64() : std::nullopt;
    cover.width = w && *w < 100000 ? static_cast<int>(*w) : 0;
    cover.height = h && *h < 100000 ? static_cast<int>(*h) : 0;
    const auto rank = index ? index->AsUint64() : std::nullopt;
    found.push_back({rank ? static_cast<std::int64_t>(*rank) : 1000, std::move(cover)});
  }
  std::stable_sort(found.begin(), found.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
  std::vector<WikiCover> covers;
  for (auto& item : found) covers.push_back(std::move(item.second));
  return covers;
}

}  // namespace orbisdesk
