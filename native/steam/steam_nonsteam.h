// SPDX-License-Identifier: GPL-3.0-or-later
// Non-Steam games in Big Picture (docs/STEAM_BIG_PICTURE.md, 2026-11-25): Windows games already on the console
// that Steam didn't install, kept in OrbisDesk's own list and started with Play like a Steam game. This file
// holds what needs no screen: the saved list, the ids, Windows <-> console paths, an exe's kind and name,
// a shortcut's target, the search for games on the console, folder listings and the store search for a cover.
// Nothing here is sent to the Steam account. Logs carry counts only, never a game, a path or a name.
#pragma once

#include <cstdint>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace orbisdesk {

struct NonSteamGame {
  std::uint32_t id = 0;   // NonSteamId(program)
  std::string name;
  std::string program;    // Windows path of the exe
  std::string folder;     // Windows path it starts in
  std::string options;    // launch options
  std::string cover;      // "store:<app>", "file", "plain", "" (none chosen yet)
  std::uint64_t added = 0;  // unix seconds
  bool named = false;     // the user typed the name: the cover search looks for it alone
};

// Ids with the top bit set: never a Steam app id, so covers, favorites and played lists can't collide.
std::uint32_t NonSteamId(const std::string& program);
inline bool IsNonSteamId(std::uint32_t id) { return (id & 0x80000000u) != 0; }

// The list (0600, written to a temporary file and renamed). A missing file is an empty list.
std::vector<NonSteamGame> LoadNonSteamGames(const std::string& path);
bool SaveNonSteamGames(const std::string& path, const std::vector<NonSteamGame>& games);

// Where the console keeps what Windows sees: C: the Wine prefix's drive_c, Z: /data, D: to K: the USB drives.
struct NonSteamRoots {
  std::string drive_c;            // "/data/wine-prefix/drive_c"
  std::string z;                  // "/data"
  std::vector<std::string> usb;   // "/mnt/usb0" ... "/mnt/usb7" (D: ...)
};
NonSteamRoots& Roots();           // the console's by default; the host test sets its own
std::string WindowsToUnix(const std::string& windows);  // "" when no drive maps it
std::string UnixToWindows(const std::string& unix_path);
// the folder part of a Windows path ("C:\Games\X\x.exe" -> "C:\Games\X")
std::string WindowsFolder(const std::string& windows);
std::string WindowsBasename(const std::string& windows);

// An exe's machine and the name it carries (ProductName, else FileDescription, from its version resource).
struct ExeInfo {
  bool pe = false;
  std::string arch;     // "x86", "x64", "other"
  std::string product;  // UTF-8, "" when none
};
ExeInfo ReadExeInfo(const std::string& unix_path);

// A .lnk's target ([MS-SHLLINK]: LinkInfo's local base path, else the relative path), arguments and folder.
struct LinkTarget {
  bool ok = false;
  std::string target, arguments, folder;  // Windows paths as the link has them
};
LinkTarget ReadLink(const std::string& unix_path);
LinkTarget ParseLink(const std::string& bytes);

// Setup, uninstall, updater, crash reporter and redistributable programs: never offered as a game.
bool ExcludedProgram(const std::string& file_name);

// Games found on the console: Desktop and Start shortcuts first (their target, arguments and folder), then
// exes one or two folders deep under Program Files, Program Files (x86), C:\Games and each USB drive's top
// and Games folder. Programs already listed in `known` (lower-case Windows paths) or under one of
// `skip_unix` (Steam games' folders) are left out.
struct Candidate {
  std::string name, program, folder, options, arch;
  bool shortcut = false;
};
std::vector<Candidate> FindNonSteamGames(const std::set<std::string>& known, const std::vector<std::string>& skip_unix);

// A folder for the browser: sub-folders, then files whose extension is in `extensions` (".exe" or ".jpg"...),
// both by name; hidden names left out.
struct FolderEntry {
  std::string name;
  bool folder = false;
  std::uint64_t bytes = 0;
};
bool ListFolder(const std::string& unix_path, const std::vector<std::string>& extensions, std::vector<FolderEntry>* out);

// Steam's public store search (no account, no key), for a cover by name: apps only, best first.
std::string StoreSearchUrl(const std::string& name);
std::vector<std::pair<std::uint32_t, std::string>> ParseStoreSearch(const std::string& body);
// The same search on api.steampowered.com (IStoreQueryService/SearchSuggestions), the host the covers already
// reach: app ids, best first.
std::string StoreSuggestUrl(const std::string& name);
std::vector<std::uint32_t> ParseStoreSuggest(const std::string& body);
// What to search the store for, best first: the name without trademark signs, bracketed parts and edition
// words, the part before a subtitle, then the program's folder (hardware 2026-11-25: a game named with an
// edition the store doesn't carry matched nothing). At most five, no repeats. `named`: the user typed the name,
// so the terms come from it alone, the program's folder left out (it is what the user corrected).
std::vector<std::string> StoreSearchTerms(const std::string& name, const std::string& program, bool named = false);
// Whether `found` (a store's or an article's name) is the game called `name` (hardware 2026-11-26: "Need for Speed
// Underground 2", not on Steam, took the cover of another game's DLC). Words compared without case, signs or
// punctuation, II..X read as numbers, "the a an of and" ignored. The sequel numbers (1..99) are the same, and
// either the words are the same but for edition words and years, or `found` is `name`'s title without the
// subtitle after its last " - " or ":" and adds only edition words or years. The app type is checked elsewhere
// (Covers::StoreArt::type).
bool StoreNameMatches(const std::string& name, const std::string& found);
// The game's name, else (when the user didn't type the name) the program's folder as StoreSearchTerms takes it.
bool CoverNameMatches(const std::string& name, const std::string& program, bool named, const std::string& found);

// The cover when Steam's store has none (hardware 2026-11-26: a game Steam doesn't sell): English Wikipedia's
// article image for a single video game, by the open MediaWiki API (no key; PCGamingWiki answers automated
// clients with a Cloudflare challenge). An article counts when its short description names one video game (not a
// franchise, series or list) and its title, without a bracketed part, is the game's by CoverNameMatches. Only
// https images on upload.wikimedia.org. Best first.
struct WikiCover {
  std::string title;
  std::string image;  // the original image's URL
  int width = 0, height = 0;
};
std::string WikipediaSearchUrl(const std::string& term);
std::vector<WikiCover> ParseWikipediaCovers(const std::string& body, const std::string& name, const std::string& program,
                                            bool named);
// Wikimedia asks automated clients to name themselves
constexpr char kWikimediaUserAgent[] = "OrbisDesk/1.0 (PlayStation 4 homebrew; non-Steam game covers)";

// a name that has no characters the list or the screens can't carry (tabs, line breaks, the UI's marks)
std::string CleanName(const std::string& name);
std::string LowerAscii(std::string text);

}  // namespace orbisdesk
