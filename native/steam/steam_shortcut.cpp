// SPDX-License-Identifier: GPL-3.0-or-later
// S5's game shortcuts (steam_shortcut.h).
#include "steam_shortcut.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdint>
#include <string>

namespace orbisdesk {
namespace {

#ifdef STEAM_HOST
// a host run writes into a folder of its own, laid out as the prefix
constexpr char kPrefix[] = "wine-prefix";
#else
constexpr char kPrefix[] = "/data/wine-prefix";
#endif
constexpr char kDesktop[] = "/drive_c/users/orbis/Desktop";
constexpr char kStartMenu[] = "/drive_c/ProgramData/Microsoft/Windows/Start Menu/Programs/Steam";

// [MS-SHLLINK]: the link CLSID and the LinkFlags make-start-menu.py sets
constexpr unsigned char kLinkClsid[16] = {0x01, 0x14, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
                                          0xc0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46};
enum : std::uint32_t {
  kHasLinkInfo = 0x2, kHasName = 0x4, kHasWorkingDir = 0x10, kHasArguments = 0x20, kHasIconLocation = 0x40,
  kIsUnicode = 0x80
};

void Put16(std::string& out, std::uint32_t value) {
  out.push_back(static_cast<char>(value & 0xff));
  out.push_back(static_cast<char>((value >> 8) & 0xff));
}
void Put32(std::string& out, std::uint32_t value) {
  for (int i = 0; i < 4; ++i) out.push_back(static_cast<char>((value >> (8 * i)) & 0xff));
}

// UTF-8 to UTF-16LE code units; an invalid byte becomes U+FFFD.
std::u16string Utf16(const std::string& text) {
  std::u16string out;
  for (std::size_t i = 0; i < text.size();) {
    const auto c = static_cast<unsigned char>(text[i]);
    std::uint32_t code = 0xfffd;
    std::size_t length = 1;
    if (c < 0x80) code = c;
    else if ((c & 0xe0) == 0xc0 && i + 1 < text.size()) code = (c & 0x1f) << 6 | (text[i + 1] & 0x3f), length = 2;
    else if ((c & 0xf0) == 0xe0 && i + 2 < text.size())
      code = (c & 0x0f) << 12 | (text[i + 1] & 0x3f) << 6 | (text[i + 2] & 0x3f), length = 3;
    else if ((c & 0xf8) == 0xf0 && i + 3 < text.size())
      code = (c & 0x07) << 18 | (text[i + 1] & 0x3f) << 12 | (text[i + 2] & 0x3f) << 6 | (text[i + 3] & 0x3f), length = 4;
    i += length;
    if (code >= 0x10000) {
      code -= 0x10000;
      out.push_back(static_cast<char16_t>(0xd800 | (code >> 10)));
      out.push_back(static_cast<char16_t>(0xdc00 | (code & 0x3ff)));
    } else {
      out.push_back(static_cast<char16_t>(code));
    }
  }
  return out;
}

// StringData: a count of UTF-16 code units, then the units
void PutString(std::string& out, const std::string& text) {
  const auto units = Utf16(text);
  Put16(out, static_cast<std::uint32_t>(units.size()));
  for (const auto unit : units) Put16(out, unit);
}

bool Ascii(const std::string& text) {
  for (const unsigned char c : text)
    if (c < 0x20 || c > 0x7e) return false;
  return true;
}

// The game's name as a file name: no Windows-reserved characters or controls, at most 80 bytes.
std::string FileName(const std::string& name, std::uint32_t app) {
  std::string out;
  for (const unsigned char c : name) {
    if (c < 0x20 || c == 0x7f || std::string("\\/:*?\"<>|").find(static_cast<char>(c)) != std::string::npos) out += ' ';
    else out += static_cast<char>(c);
  }
  while (!out.empty() && (out.back() == ' ' || out.back() == '.')) out.pop_back();
  while (!out.empty() && out.front() == ' ') out.erase(out.begin());
  if (out.size() > 80) {
    out.resize(80);
    while (!out.empty() && (static_cast<unsigned char>(out.back()) & 0xc0) == 0x80) out.pop_back();  // a cut UTF-8 tail
    if (!out.empty() && static_cast<unsigned char>(out.back()) >= 0xc0) out.pop_back();
  }
  return out.empty() ? "Steam " + std::to_string(app) : out;
}

bool MakeFolders(const std::string& path) {
  for (std::size_t slash = path.find('/', 1); slash != std::string::npos; slash = path.find('/', slash + 1)) {
    const std::string dir = path.substr(0, slash);
    if (mkdir(dir.c_str(), 0777) && errno != EEXIST) return false;
  }
  return true;
}

bool Write(const std::string& path, const std::string& bytes) {
  if (!MakeFolders(path)) return false;
  const std::string temporary = path + ".tmp";
  const int fd = open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd < 0) return false;
  const bool ok = write(fd, bytes.data(), bytes.size()) == static_cast<ssize_t>(bytes.size()) && fsync(fd) == 0;
  close(fd);
  if (!ok || rename(temporary.c_str(), path.c_str())) {
    unlink(temporary.c_str());
    return false;
  }
  return true;
}

}  // namespace

std::string GameWindowsPath(std::uint32_t app, const std::string& relative) {
  std::string path = "Z:\\orbisdesk\\steam-games\\" + std::to_string(app);
  if (!relative.empty()) path += "\\" + relative;
  for (auto& c : path)
    if (c == '/') c = '\\';
  return path;
}

std::string ShortcutBytes(const std::string& target, const std::string& description, const std::string& arguments,
                          const std::string& working_dir) {
  const std::uint32_t flags = kHasLinkInfo | kHasName | kHasWorkingDir | kHasIconLocation | kIsUnicode |
                              (arguments.empty() ? 0 : kHasArguments);
  std::string out;
  Put32(out, 0x4c);
  out.append(reinterpret_cast<const char*>(kLinkClsid), sizeof(kLinkClsid));
  Put32(out, flags);
  Put32(out, 0x20);              // FILE_ATTRIBUTE_ARCHIVE
  out.append(24, '\0');          // creation, access and write times
  Put32(out, 0);                 // file size
  Put32(out, 0);                 // icon index
  Put32(out, 1);                 // SW_SHOWNORMAL
  Put16(out, 0);                 // hot key
  Put16(out, 0);                 // reserved
  Put32(out, 0);
  Put32(out, 0);
  // LinkInfo with VolumeIDAndLocalBasePath: a fixed-disk volume and the ANSI target
  std::string volume;
  Put32(volume, 17);  // VolumeIDSize
  Put32(volume, 3);   // DRIVE_FIXED
  Put32(volume, 0);   // serial
  Put32(volume, 16);  // label offset
  volume.push_back('\0');
  const std::string base = target + '\0', suffix(1, '\0');
  const std::uint32_t header = 0x1c, volume_at = header, base_at = volume_at + static_cast<std::uint32_t>(volume.size()),
                      suffix_at = base_at + static_cast<std::uint32_t>(base.size()),
                      size = suffix_at + static_cast<std::uint32_t>(suffix.size());
  Put32(out, size);
  Put32(out, header);
  Put32(out, 1);  // VolumeIDAndLocalBasePath
  Put32(out, volume_at);
  Put32(out, base_at);
  Put32(out, 0);  // no network relative link
  Put32(out, suffix_at);
  out += volume + base + suffix;
  PutString(out, description);
  PutString(out, working_dir);
  if (!arguments.empty()) PutString(out, arguments);
  PutString(out, target);  // icon: the program's own, icon 0
  Put32(out, 0);           // terminal extra-data block
  return out;
}

std::string SourceLanguageArguments(const std::string& root, const Launch& launch, const std::string& language) {
  if (language.empty() || language == "english") return "";
  if (launch.arguments.find("-language") != std::string::npos) return "";  // Steam's own entry chose one
  const auto slash = launch.executable.rfind('/');
  const std::string folder = slash == std::string::npos ? std::string() : launch.executable.substr(0, slash + 1);
  if (!PathExists(root + "/" + folder + "bin/engine.dll")) return "";
  return "-language " + language;
}

ShortcutResult WriteGameShortcuts(std::uint32_t app, const std::string& name, const InstallResult& result,
                                  const std::string& root, const std::string& language) {
  ShortcutResult shortcut;
  const std::string prefix = kPrefix;
  shortcut.prefix = PathExists(prefix + "/drive_c");
  if (!shortcut.prefix) {
    shortcut.skipped = "no OrbisDesk prefix";
    return shortcut;
  }
  bool steamstub = false;  // an entry was skipped for SteamStub alone
  for (std::size_t i = 0; i < result.launches.size() && i < result.checks.size(); ++i) {
    const auto& launch = result.launches[i];
    const auto& check = result.checks[i];
    if (check.present && check.pe && check.steamstub) steamstub = true;
    if (!check.present || !check.pe || check.steamstub) continue;
    const std::string target = GameWindowsPath(app, launch.executable);
    const std::string folder = GameWindowsPath(app, launch.working_dir);
    if (!Ascii(target) || !Ascii(folder)) {
      shortcut.skipped = "non-ASCII path";  // LinkInfo's local base path is ANSI
      continue;
    }
    const std::string file = FileName(name, app) + ".lnk";
    std::string arguments = launch.arguments;
    shortcut.language_arguments = SourceLanguageArguments(root, launch, language);
    if (!shortcut.language_arguments.empty())
      arguments += (arguments.empty() ? "" : " ") + shortcut.language_arguments;
    const std::string bytes = ShortcutBytes(target, name, arguments, folder);
    if (Write(prefix + kDesktop + "/" + file, bytes)) shortcut.desktop = file;
    if (Write(prefix + kStartMenu + "/" + file, bytes)) shortcut.start = file;
    if (shortcut.desktop.empty() && shortcut.start.empty()) shortcut.skipped = "write failed errno=" + std::to_string(errno);
    else shortcut.skipped.clear();
    return shortcut;
  }
  if (shortcut.skipped.empty()) shortcut.skipped = steamstub ? "steamstub" : "no usable launch entry";
  return shortcut;
}

ShortcutRemoval RemoveGameShortcuts(std::uint32_t app, const std::string& name) {
  ShortcutRemoval removal;
  const std::string prefix = kPrefix;
  removal.prefix = PathExists(prefix + "/drive_c");
  const std::string file = FileName(name, app) + ".lnk";
  // the LinkInfo's ANSI target: Z:\orbisdesk\steam-games\<app>\...
  const std::string ours = GameWindowsPath(app, "") + "\\";
  const auto remove = [&](const std::string& path) -> std::string {
    const int fd = open(path.c_str(), O_RDONLY);
    if (fd < 0) {
      if (errno == ENOENT) return "absent";
      if (!removal.error) removal.error = errno;
      return "unreadable";
    }
    std::string bytes;
    char buffer[4096];
    ssize_t got;
    while (bytes.size() < (1u << 20) && (got = read(fd, buffer, sizeof(buffer))) > 0) bytes.append(buffer, static_cast<std::size_t>(got));
    close(fd);
    if (bytes.find(ours) == std::string::npos) return "not_ours";
    if (unlink(path.c_str())) {
      if (!removal.error) removal.error = errno;
      return "failed";
    }
    return "removed";
  };
  removal.desktop = remove(prefix + kDesktop + "/" + file);
  removal.start = remove(prefix + kStartMenu + "/" + file);
  return removal;
}

}  // namespace orbisdesk
