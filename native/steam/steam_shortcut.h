// SPDX-License-Identifier: GPL-3.0-or-later
// S5: a shortcut to an installed game in OrbisDesk's Explorer (docs/STEAM_S5.md).
// OrbisDesk's Wine prefix is /data/wine-prefix and its Z: drive is /data (platform/ps4/pw_wine_fs.c),
// so a game in /data/orbisdesk/steam-games/<app>/ is Z:\orbisdesk\steam-games\<app>\ to its guests.
// Explorer shows the .lnk files of the Desktop folder and of the Start menu as launchers (W168, W169,
// W045); a .lnk dropped there needs no change to OrbisDesk. The .lnk format is the one
// tools/make-start-menu.py writes: [MS-SHLLINK] with a LinkInfo local base path, description, working
// folder, arguments and icon.
#pragma once

#include <string>

#include "steam_install.h"

namespace orbisdesk {

struct ShortcutResult {
  bool prefix = false;  // OrbisDesk's prefix exists on this console
  std::string desktop;  // the .lnk written to the Desktop (empty: none)
  std::string start;    // the .lnk written to the Start menu's Programs/Steam (empty: none)
  std::string skipped;  // why none was written
  std::string language_arguments;  // what was added to the entry's arguments for the language, if anything
  bool failed = false;
  bool launcher = false;  // a SteamStub game's: steam-open.exe --play <app> (kLauncherImage)
};

// A SteamStub game's shortcut starts C:\orbis\steam-open.exe --play <app> (native/steam/orbis_steam_open.c), which
// runs the launch plan the Steam client keeps for the game (Z:\orbisdesk\steam\launch\<app>.plan): what Play would
// start, the game or gbe_fork's ColdClient loader, decided when the plan is written.
constexpr char kLauncherImage[] = "C:\\orbis\\steam-open.exe";
constexpr char kLauncherFolder[] = "C:\\orbis";
std::string LauncherArguments(std::uint32_t app);

// Source engine games (an engine DLL in bin/ beside the executable) take their interface language from
// `-language <name>` on the command line; without it they follow Steam's. Steam isn't running inside
// OrbisDesk, so a game installed in another language than English gets it on its shortcut: W292's
// Portal 2, installed in Spanish with gbe_fork on, still started in English. Empty for English, for
// other games, and when Steam's entry already has -language.
std::string SourceLanguageArguments(const std::string& root, const Launch& launch, const std::string& language);

// The Windows path of a file of an installed game, as OrbisDesk's guests see it.
std::string GameWindowsPath(std::uint32_t app, const std::string& relative);

// The launch entry a game's shortcut starts: the first one present, a PE and without SteamStub, whose
// Windows paths are ASCII (a .lnk's LinkInfo path is ANSI). Big Picture's Play starts the same entry the same
// way: image, arguments (with SourceLanguageArguments) and working folder.
struct LaunchEntry {
  bool ok = false;
  std::size_t index = 0;
  std::string image;      // Windows path of the executable
  std::string arguments;  // Steam's arguments plus the language's
  std::string directory;  // Windows path of the working folder
  std::string language_arguments;
  std::string skipped;    // why there is none: "steamstub", "non-ASCII path", "no usable launch entry"
};
// allow_steamstub: a SteamStub entry is usable too (Big Picture's full emulation, which starts it through
// gbe_fork's ColdClient loader; the shortcut never does)
LaunchEntry ChooseLaunchEntry(const std::vector<Launch>& launches, const std::vector<LaunchCheck>& checks,
                              const std::string& root, const std::string& language, bool allow_steamstub = false);

// Writes the shortcuts of the first usable launch entry of an installed game (present, a PE, no
// SteamStub); when every entry has SteamStub, the launcher's (ShortcutResult::launcher). `name` is the game's name, for the file and the description. `root`: the game's folder;
// `language`: its installed content language (SourceLanguageArguments).
// through_launcher: the game's launch mode starts it through gbe_fork's ColdClient loader (Big Picture's launch
// modes), so its shortcut is the launcher's whatever SteamStub says.
ShortcutResult WriteGameShortcuts(std::uint32_t app, const std::string& name, const InstallResult& result,
                                  const std::string& root, const std::string& language, const std::string& previous_root = "",
                                  bool through_launcher = false);

// Removes the game's shortcuts WriteGameShortcuts made (an uninstall). A .lnk of the same name that
// doesn't point into this game's folder is the user's own and stays. Each state is "removed",
// "absent", "not_ours", "unreadable" or "failed".
struct ShortcutRemoval {
  bool prefix = false;
  std::string desktop, start;
  int error = 0;  // errno of the first failure
};
ShortcutRemoval RemoveGameShortcuts(std::uint32_t app, const std::string& name);

// The .lnk bytes, for a test.
std::string ShortcutBytes(const std::string& target, const std::string& description, const std::string& arguments,
                          const std::string& working_dir, const std::string& icon = "");

}  // namespace orbisdesk
