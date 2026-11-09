// SPDX-License-Identifier: GPL-3.0-or-later
// S5: gbe_fork (LGPL-3, github.com/Detanup01/gbe_fork, release-2026_09_27) in place of a game's
// steam_api, per game and reversible (docs/STEAM_S5.md). Without the Steam client, a game's own
// steam_api.dll closes it or asks for Steam; gbe_fork answers the game itself.
// Enabling, for each steam_api.dll / steam_api64.dll of the install record:
//   1. the game's DLL is renamed to <name>.orig (kept, never overwritten);
//   2. gbe_fork's DLL of the same name (x86 or x64 build) is copied in;
//   3. beside it, steam_settings/ gets steam_appid.txt, configs.user.ini (a generic player name and
//      the install's language: no account data) and steam_interfaces.txt, the interface versions the
//      original DLL names (gbe_fork's generate_interfaces, ported).
// .orbisdesk-gbe.txt lists what was written. Restoring deletes exactly that and renames the .orig
// files back.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace orbisdesk {

using EmuNoteFn = void (*)(const char*, ...);

// Where the title carries gbe_fork's DLLs: <prefix>x86-steam_api.dll and <prefix>x64-steam_api64.dll, flat,
// as create-gp4 declares no folders under assets/misc.
#if defined(STEAM_HOST)
inline constexpr char kEmuAssets[] = "gbe/gbe-";
#elif defined(STEAM_UI_HOSTED)
inline constexpr char kEmuAssets[] = "/data/wine-prefix/drive_c/orbis/steam/gbe-";  // OrbisDesk's C:\orbis\steam
#else
inline constexpr char kEmuAssets[] = "/app0/assets/misc/gbe-";
#endif

bool EmulatorEnabled(const std::string& root);

// steam_api_paths: game-relative, as the install record lists them. language: Steam's name
// ("english"). False with `failure` (user-facing) when it couldn't; what was done is undone.
bool EnableEmulator(const std::string& root, std::uint32_t app, const std::vector<std::string>& steam_api_paths,
                    const std::string& language, EmuNoteFn note, std::string* failure);
bool RestoreEmulator(const std::string& root, EmuNoteFn note, std::string* failure);

// gbe_fork's generate_interfaces over a DLL's bytes: the interface version names, one per line.
std::string SteamInterfaces(const std::string& dll_bytes);

// configs.user.ini's text with [user::general] language= set (gbe_fork answers GetCurrentGameLanguage and
// GetSteamUILanguage with it).
std::string SetUserLanguage(const std::string& ini, const std::string& language);

}  // namespace orbisdesk
