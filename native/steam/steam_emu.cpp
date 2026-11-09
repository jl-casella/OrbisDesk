// SPDX-License-Identifier: GPL-3.0-or-later
// S5's gbe_fork switch (steam_emu.h). SteamInterfaces is a port of gbe_fork's
// tools/generate_interfaces/generate_interfaces.cpp (LGPL-3.0, release-2026_09_27): the same
// patterns, in the same order, and the same SteamClient017 rule.
#include "steam_emu.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>

#include "steam_install.h"

namespace orbisdesk {
namespace {

constexpr char kMarker[] = ".orbisdesk-gbe.txt";

bool ReadFile(const std::string& path, std::string* out) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) return false;
  char buffer[65536];
  for (;;) {
    const ssize_t got = read(fd, buffer, sizeof(buffer));
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) {
      close(fd);
      return false;
    }
    if (got == 0) break;
    out->append(buffer, static_cast<std::size_t>(got));
  }
  close(fd);
  return true;
}

bool WriteFile(const std::string& path, const std::string& bytes) {
  const std::string temporary = path + ".tmp";
  const int fd = open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd < 0) return false;
  std::size_t done = 0;
  while (done < bytes.size()) {
    const ssize_t put = write(fd, bytes.data() + done, bytes.size() - done);
    if (put < 0 && errno == EINTR) continue;
    if (put <= 0) break;
    done += static_cast<std::size_t>(put);
  }
  const bool ok = done == bytes.size() && fsync(fd) == 0;
  close(fd);
  if (!ok || rename(temporary.c_str(), path.c_str())) {
    unlink(temporary.c_str());
    return false;
  }
  return true;
}

std::string Folder(const std::string& relative) {
  const auto slash = relative.rfind('/');
  return slash == std::string::npos ? std::string() : relative.substr(0, slash + 1);
}

std::string Base(const std::string& relative) {
  const auto slash = relative.rfind('/');
  std::string base = slash == std::string::npos ? relative : relative.substr(slash + 1);
  for (auto& c : base)
    if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
  return base;
}

// The marker: "v1", then "dll\t<path>" for each replaced DLL and "file\t<path>" / "dir\t<path>" for
// what was written beside it, all game-relative, in the order they were made.
struct Marker {
  std::vector<std::pair<std::string, std::string>> entries;
  std::string Text() const {
    std::string text = "v1\n";
    for (const auto& [kind, path] : entries) text += kind + "\t" + path + "\n";
    return text;
  }
  bool Parse(const std::string& text) {
    std::size_t at = 0;
    bool first = true;
    while (at < text.size()) {
      const auto end = text.find('\n', at);
      const std::string line = text.substr(at, end == std::string::npos ? std::string::npos : end - at);
      at = end == std::string::npos ? text.size() : end + 1;
      if (first) {
        if (line != "v1") return false;
        first = false;
        continue;
      }
      if (line.empty()) continue;
      const auto tab = line.find('\t');
      if (tab == std::string::npos) return false;
      const std::string kind = line.substr(0, tab), path = line.substr(tab + 1);
      if ((kind != "dll" && kind != "file" && kind != "dir") || path.empty() || path[0] == '/' ||
          path.find("..") != std::string::npos)
        return false;
      entries.emplace_back(kind, path);
    }
    return !first;
  }
};

}  // namespace

// configs.user.ini with `language=` in [user::general] set to `language`: the line replaced where it is,
// added at the end of the section, or the section added at the end. Other lines are kept as they are.
std::string SetUserLanguage(const std::string& ini, const std::string& language) {
  std::vector<std::string> lines;
  for (std::size_t at = 0; at < ini.size();) {
    const auto end = ini.find('\n', at);
    lines.push_back(ini.substr(at, end == std::string::npos ? std::string::npos : end - at));
    at = end == std::string::npos ? ini.size() : end + 1;
  }
  auto trimmed = [](std::string text) {
    while (!text.empty() && (text.back() == '\r' || text.back() == ' ' || text.back() == '\t')) text.pop_back();
    std::size_t start = 0;
    while (start < text.size() && (text[start] == ' ' || text[start] == '\t')) ++start;
    return text.substr(start);
  };
  const std::string wanted = "language=" + language;
  bool in_section = false, set = false;
  std::size_t section_end = lines.size();  // where a missing key goes: the line after the section's last
  bool section_found = false;
  for (std::size_t i = 0; i < lines.size(); ++i) {
    const std::string line = trimmed(lines[i]);
    if (!line.empty() && line[0] == '[') {
      in_section = line == "[user::general]";
      if (in_section) {
        section_found = true;
        section_end = i + 1;
      }
      continue;
    }
    if (!in_section) continue;
    if (!line.empty()) section_end = i + 1;
    const auto equals = line.find('=');
    if (equals != std::string::npos && trimmed(line.substr(0, equals)) == "language") {
      lines[i] = wanted;
      set = true;
    }
  }
  if (!set) {
    if (section_found) {
      lines.insert(lines.begin() + static_cast<std::ptrdiff_t>(section_end), wanted);
    } else {
      if (!lines.empty() && !trimmed(lines.back()).empty()) lines.push_back("");
      lines.push_back("[user::general]");
      lines.push_back(wanted);
    }
  }
  std::string out;
  for (const auto& line : lines) out += line + "\n";
  return out;
}

// gbe_fork's patterns are all a literal, most followed by \d+, so a literal search does what its
// std::regex scan does (leftmost, non-overlapping, greedy digits) without it: on the PS4, libc++'s
// regex took about 40 s for one steam_api.dll (W291) while the page sat unchanged.
std::string SteamInterfaces(const std::string& dll_bytes) {
  struct Pattern {
    const char* literal;
    bool digits;
  };
  static const Pattern kPatterns[] = {
      {"STEAMAPPS_INTERFACE_VERSION", true}, {"SteamApps", true}, {"STEAMAPPLIST_INTERFACE_VERSION", true},
      {"STEAMAPPTICKET_INTERFACE_VERSION", true}, {"SteamClient", true}, {"STEAMCONTROLLER_INTERFACE_VERSION", false},
      {"SteamController", true}, {"SteamFriends", true}, {"SteamGameServerStats", true}, {"SteamGameCoordinator", true},
      {"SteamGameServer", true}, {"STEAMHTMLSURFACE_INTERFACE_VERSION_", true}, {"STEAMHTTP_INTERFACE_VERSION", true},
      {"SteamInput", true}, {"STEAMINVENTORY_INTERFACE_V", true}, {"SteamMatchMakingServers", true},
      {"SteamMatchMaking", true}, {"SteamMatchGameSearch", true}, {"SteamParties", true},
      {"STEAMMUSIC_INTERFACE_VERSION", true}, {"STEAMMUSICREMOTE_INTERFACE_VERSION", true},
      {"SteamNetworkingMessages", true}, {"SteamNetworkingSockets", true}, {"SteamNetworkingUtils", true},
      {"SteamNetworking", true}, {"STEAMPARENTALSETTINGS_INTERFACE_VERSION", true},
      {"STEAMREMOTEPLAY_INTERFACE_VERSION", true}, {"STEAMREMOTESTORAGE_INTERFACE_VERSION", true},
      {"STEAMSCREENSHOTS_INTERFACE_VERSION", true}, {"STEAMTIMELINE_INTERFACE_V", true},
      {"STEAMUGC_INTERFACE_VERSION", true}, {"SteamUser", true}, {"STEAMUSERSTATS_INTERFACE_VERSION", true},
      {"SteamUtils", true}, {"STEAMVIDEO_INTERFACE_V", true}, {"STEAMUNIFIEDMESSAGES_INTERFACE_VERSION", true},
      {"SteamMasterServerUpdater", true},
  };
  std::string out;
  for (const auto& pattern : kPatterns) {
    const std::string literal = pattern.literal;
    std::vector<std::string> matches;
    std::size_t at = 0;
    for (;;) {
      const std::size_t found = dll_bytes.find(literal, at);
      if (found == std::string::npos) break;
      std::size_t end = found + literal.size();
      if (pattern.digits)
        while (end < dll_bytes.size() && dll_bytes[end] >= '0' && dll_bytes[end] <= '9') ++end;
      if (pattern.digits && end == found + literal.size()) {
        at = found + 1;  // no digits: no match here
        continue;
      }
      matches.push_back(dll_bytes.substr(found, end - found));
      at = end;
    }
    // newer SDKs keep only SteamClient() among the legacy exports, and it returns SteamClient017
    if (literal == "SteamClient" && matches.size() > 1 &&
        std::find(matches.begin(), matches.end(), "SteamClient017") != matches.end())
      matches.erase(std::remove_if(matches.begin(), matches.end(), [](const std::string& m) { return m != "SteamClient017"; }),
                    matches.end());
    for (const auto& match : matches) out += match + "\n";
  }
  return out;
}

bool EmulatorEnabled(const std::string& root) { return PathExists(root + "/" + kMarker); }

bool RestoreEmulator(const std::string& root, EmuNoteFn note, std::string* failure) {
  std::string text;
  Marker marker;
  if (!ReadFile(root + "/" + kMarker, &text) || !marker.Parse(text)) {
    note("PWSTEAM emu restore marker=unreadable");
    *failure = "THE EMULATOR RECORD WAS NOT FOUND.";
    return false;
  }
  int restored = 0, removed = 0, problems = 0;
  // files first, then folders (deepest last made first), then the DLLs
  for (auto it = marker.entries.rbegin(); it != marker.entries.rend(); ++it) {
    const std::string path = root + "/" + it->second;
    if (it->first == "file") {
      if (unlink(path.c_str()) && errno != ENOENT) ++problems;
      else ++removed;
    } else if (it->first == "dir") {
      rmdir(path.c_str());  // only when empty: the game may have put its own files there
    }
  }
  for (const auto& [kind, relative] : marker.entries) {
    if (kind != "dll") continue;
    const std::string path = root + "/" + relative, original = path + ".orig";
    if (!PathExists(original)) {
      ++problems;
      continue;
    }
    unlink(path.c_str());
    if (rename(original.c_str(), path.c_str())) ++problems;
    else ++restored;
  }
  note("PWSTEAM emu restore dlls=%d files=%d problems=%d", restored, removed, problems);
  if (problems) {
    *failure = "NOT EVERYTHING COULD BE RESTORED. VERIFYING THE GAME FROM THE LIST REPAIRS IT.";
    return false;
  }
  unlink((root + "/" + kMarker).c_str());
  return true;
}

bool EnableEmulator(const std::string& root, std::uint32_t app, const std::vector<std::string>& steam_api_paths,
                    const std::string& language, EmuNoteFn note, std::string* failure) {
  if (EmulatorEnabled(root)) {
    note("PWSTEAM emu enable already=1");
    return true;
  }
  if (steam_api_paths.empty()) {
    *failure = "THE GAME HAS NO STEAM API: THE EMULATOR IS NOT NEEDED.";
    return false;
  }
  // each step is logged with the milliseconds since the switch was pressed; paths stay out of the
  // log (they can name the game), so the DLLs are numbered
  const auto started = std::chrono::steady_clock::now();
  auto ms = [&] {
    return static_cast<long long>(
        std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - started).count());
  };
  note("PWSTEAM emu enable start dlls=%zu", steam_api_paths.size());
  Marker marker;
  auto undo = [&](const char* step, const char* text) {
    note("PWSTEAM emu enable failed step=%s errno=%d ms=%lld", step, errno, ms());
    // what was done so far, recorded for RestoreEmulator
    WriteFile(root + "/" + kMarker, marker.Text());
    std::string ignored;
    RestoreEmulator(root, note, &ignored);
    *failure = text;
    return false;
  };
  const std::string wanted_language = language.empty() ? std::string("english") : language;
  const std::string user_ini = "[user::general]\naccount_name=OrbisDesk\nlanguage=" + wanted_language + "\n";
  std::size_t index = 0;
  for (const auto& relative : steam_api_paths) {
    ++index;
    const std::string base = Base(relative);
    const bool x64 = base == "steam_api64.dll";
    std::string emulator, original;
    if (!ReadFile(std::string(kEmuAssets) + (x64 ? "x64-steam_api64.dll" : "x86-steam_api.dll"), &emulator) ||
        emulator.size() < 4096)
      return undo("asset", "THE EMULATOR IS NOT IN THIS VERSION.");
    const std::string path = root + "/" + relative;
    std::string current;
    if (!ReadFile(path, &current)) return undo("read", "COULD NOT READ THE GAME STEAM API.");
    note("PWSTEAM emu enable dll=%zu/%zu step=read arch=%s game_bytes=%zu emulator_bytes=%zu ms=%lld", index,
         steam_api_paths.size(), x64 ? "x64" : "x86", current.size(), emulator.size(), ms());
    if (PathExists(path + ".orig")) {
      // a .orig without a marker (a run stopped halfway): safe only when it is the game's DLL again
      // beside it (a verification put it back) or beside gbe_fork's (the copy had finished)
      if (!ReadFile(path + ".orig", &original))
        return undo("orig_read", "COULD NOT READ THE SAVED STEAM API.");
      if (current == original) {
        unlink((path + ".orig").c_str());
        note("PWSTEAM emu enable stale_orig=same_as_game");
      } else if (current == emulator) {
        note("PWSTEAM emu enable stale_orig=emulator_in_place");
        marker.entries.emplace_back("dll", relative);
      } else {
        return undo("orig_exists", "A SAVED STEAM API DOES NOT MATCH THE GAME. NOTHING WAS CHANGED.");
      }
    } else {
      original = current;
    }
    if (current != emulator) {
      if (rename(path.c_str(), (path + ".orig").c_str())) return undo("rename", "COULD NOT SAVE THE ORIGINAL STEAM API.");
      marker.entries.emplace_back("dll", relative);
      if (!WriteFile(path, emulator)) return undo("copy", "COULD NOT COPY THE EMULATOR.");
      note("PWSTEAM emu enable dll=%zu step=copied ms=%lld", index, ms());
    } else {
      note("PWSTEAM emu enable dll=%zu step=already_emulator ms=%lld", index, ms());
    }
    const std::string folder = Folder(relative) + "steam_settings";
    if (!mkdir((root + "/" + folder).c_str(), 0777)) marker.entries.emplace_back("dir", folder);
    else if (errno != EEXIST) return undo("mkdir", "COULD NOT CREATE THE EMULATOR SETTINGS.");
    const std::string interfaces = SteamInterfaces(original);
    std::size_t lines = 0;
    for (const char c : interfaces) lines += c == '\n';
    note("PWSTEAM emu enable dll=%zu step=interfaces lines=%zu ms=%lld", index, lines, ms());
    const std::pair<const char*, std::string> files[] = {
        {"/steam_appid.txt", std::to_string(app) + "\n"},
        {"/configs.user.ini", user_ini},
        {"/steam_interfaces.txt", interfaces},
    };
    for (const auto& [name, bytes] : files) {
      if (std::string(name) == "/steam_interfaces.txt" && bytes.empty()) continue;  // a newer SDK: none needed
      const std::string file = folder + name;
      if (PathExists(root + "/" + file)) {
        // a file already there is left alone (the game's, or one an interrupted switch left: W291's
        // run stopped after writing them and before its record), except the language of
        // configs.user.ini: it is the language the user chose, and the old file kept W292's Portal 2
        // in English
        if (std::string(name) == "/configs.user.ini") {
          std::string old_text;
          const char* state = "unreadable";
          if (ReadFile(root + "/" + file, &old_text)) {
            const std::string new_text = SetUserLanguage(old_text, wanted_language);
            state = new_text == old_text ? "same" : WriteFile(root + "/" + file, new_text) ? "updated" : "write_failed";
          }
          note("PWSTEAM emu enable dll=%zu step=language file=existing state=%s language=%s", index, state,
               wanted_language.c_str());
          if (std::string(state) == "write_failed") return undo("language", "COULD NOT WRITE THE EMULATOR LANGUAGE.");
        }
        continue;
      }
      if (!WriteFile(root + "/" + file, bytes)) return undo("settings", "COULD NOT WRITE THE EMULATOR SETTINGS.");
      marker.entries.emplace_back("file", file);
      if (std::string(name) == "/configs.user.ini")
        note("PWSTEAM emu enable dll=%zu step=language file=new language=%s", index, wanted_language.c_str());
    }
    note("PWSTEAM emu enable dll=%zu step=settings ms=%lld", index, ms());
  }
  if (!WriteFile(root + "/" + kMarker, marker.Text())) return undo("marker", "COULD NOT SAVE THE EMULATOR RECORD.");
  note("PWSTEAM emu enable done dlls=%zu entries=%zu ms=%lld", steam_api_paths.size(), marker.entries.size(), ms());
  return true;
}

}  // namespace orbisdesk
