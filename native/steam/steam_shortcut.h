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
};

// Source engine games (an engine DLL in bin/ beside the executable) take their interface language from
// `-language <name>` on the command line; without it they follow Steam's. Steam isn't running inside
// OrbisDesk, so a game installed in another language than English gets it on its shortcut: W292's
// Portal 2, installed in Spanish with gbe_fork on, still started in English. Empty for English, for
// other games, and when Steam's entry already has -language.
std::string SourceLanguageArguments(const std::string& root, const Launch& launch, const std::string& language);

// The Windows path of a file of an installed game, as OrbisDesk's guests see it.
std::string GameWindowsPath(std::uint32_t app, const std::string& relative);

// Writes the shortcuts of the first usable launch entry of an installed game (present, a PE, no
// SteamStub). `name` is the game's name, for the file and the description. `root`: the game's folder;
// `language`: its installed content language (SourceLanguageArguments).
ShortcutResult WriteGameShortcuts(std::uint32_t app, const std::string& name, const InstallResult& result,
                                  const std::string& root, const std::string& language);

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
                          const std::string& working_dir);

}  // namespace orbisdesk
