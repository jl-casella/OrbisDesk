// SPDX-License-Identifier: GPL-3.0-or-later
// S4: installing a game of the user's library (docs/STEAM_S4.md).
// The depot choice is Playden's SelectDepots (Windows, the account's licenses, English, the public
// branch, 64-bit over 32-bit). The download is S2's, proven on the console, grown into an installer:
//   - several depots merged into one folder, a later depot's file replacing an earlier one's;
//   - four workers, each with its own CdnClient (its own curl handles);
//   - resumable without a journal: files are sized up front, and a chunk whose bytes are already in
//     place (their SHA-1 is the chunk's) is not fetched again, so a stopped install carries on;
//   - every file's SHA-1 checked against the manifest at the end;
//   - a record of what was installed (.orbisdesk-install.json) written only when everything passed.
// Then the game's executable: its PE machine, whether the game ships steam_api(64).dll and whether
// the executable carries SteamStub's .bind section (DRM this project can't run).
// Logs: counts, sizes and error categories; no app, depot or file names (they name the user's games).
#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "steam/backend/app_info.h"
#include "steam/backend/cm_client.h"
#include "steam/session_store.h"

namespace orbisdesk {

using NoteFn = void (*)(const char*, ...);

// A Windows launch entry of the game, as Steam's appinfo gives it, for OrbisDesk to start the game.
struct Launch {
  std::string executable;   // game-relative, '/' separators
  std::string arguments;    // Windows command-line text, as Steam passes it
  std::string working_dir;  // game-relative; empty: the game folder, as Steam starts it
  std::string description;  // Steam's label for a non-default entry; empty for the default
  std::string type;         // Steam's launch type ("default", "option1", ... or empty)
};

// What the installed executable of a launch entry is.
struct LaunchCheck {
  bool present = false;     // the merged depots have the file
  bool pe = false;          // it read as a PE image
  std::string arch;         // "x86", "x64", "other" or "" when not read
  bool steamstub = false;   // SteamStub's .bind section: DRM OrbisDesk can't run
};

struct InstallPlan {
  std::uint32_t app = 0;
  std::string name;
  std::string install_dir;  // the app's installdir, for the record
  std::vector<playden::steam::DepotInfo> depots;
  std::string language;                // the content language the depots were chosen for
  std::vector<std::string> languages;  // the ones the game's own depots carry; empty when none is localised
  std::uint64_t install_bytes = 0;
  std::uint64_t download_bytes = 0;
  std::vector<Launch> launches;  // Steam's eligible Windows entries, default first
  std::string executable;  // the first entry's executable (game-relative), empty when none
  std::string failure;     // why there is no plan (user-facing, hw_text's letters)
};

// Chooses the depots of `app` for this account, in content `language` (Steam's name, "spanish"; empty
// is English). Playden falls back to English, then to the first language listed, when the game doesn't
// carry the one asked for: plan->language says which it got. dlc_apps: the appinfo of the app's DLC
// Steam described. False with plan->failure when nothing can be installed.
bool PlanInstall(const playden::steam::AppInfo& app, const std::vector<playden::steam::AppInfo>& dlc_apps,
                 const playden::steam::AcquisitionResult& licenses, const std::string& language, NoteFn note,
                 InstallPlan* plan);

struct InstallProgress {
  std::atomic<std::uint64_t> total_bytes{0};  // the merged files' bytes
  std::atomic<std::uint64_t> done_bytes{0};   // chunks in place, fetched or found
  std::atomic<std::uint64_t> fetched_bytes{0};  // compressed bytes fetched from Steam in this run
  std::atomic<std::uint64_t> reused_bytes{0};   // chunks already on disk with the right SHA-1
  std::atomic<std::uint32_t> files_total{0};
  std::atomic<std::uint32_t> files_done{0};
  std::atomic<int> phase{0};  // 0 preparing, 1 downloading, 2 checking the executable
};

struct InstallResult {
  bool ok = false;
  bool canceled = false;
  std::string failure;  // user-facing, hw_text's letters
  std::uint32_t files = 0, verified = 0, failed = 0, links = 0;
  std::uint64_t bytes = 0, fetched = 0, reused = 0, ms = 0;
  std::string arch;  // the first entry's: "x86", "x64" or "" when the executable wasn't read
  bool steam_api = false;
  bool steamstub = false;  // the first entry's
  std::vector<Launch> launches;              // plan.launches with the paths' case as installed
  std::vector<LaunchCheck> checks;           // one per launches entry
  std::vector<std::string> steam_api_paths;  // game-relative paths of steam_api.dll / steam_api64.dll
};

// The free space of the file system holding `path` (measured at its nearest existing folder), for an
// unprivileged writer. A measurement that fails or reads implausibly is ok=false with its cause, never
// a number: 01.08 took a failed one for a full drive (free=0 on a console with ~149 GB free).
struct FreeSpace {
  bool ok = false;
  std::uint64_t bytes = 0;
  std::string detail;  // what was measured and how it went, for the log
};
FreeSpace MeasureFreeSpace(const std::string& path);

// The PE machine and SteamStub's .bind section of an executable, read through `read` (bytes, size,
// offset; false when they can't be read). check->pe says whether it read as a PE image.
bool ParsePe(const std::function<bool(std::uint8_t*, std::size_t, std::uint64_t)>& read, LaunchCheck* check);

// What RunInstall can start from (steam_install.cpp): the depot keys, servers, manifests and the
// executables' chunks the precheck fetched.
struct Prepared;

// SteamStub before the download: the depot manifests, then only the chunks under each listed
// executable's headers and section table (the first chunk, as a rule). Nothing is written to disk.
// Detection only: nothing here removes or works around the DRM.
struct Precheck {
  bool ran = false;        // at least one executable was read as a PE image
  bool steamstub = false;  // every executable read has SteamStub's .bind section (no shortcut could be made)
  std::string arch;        // the first executable's, "" when not read
  std::uint64_t fetched = 0;        // compressed chunk bytes fetched
  std::vector<LaunchCheck> checks;  // one per distinct executable Steam lists (up to four)
  std::string failure;              // why it didn't run (user-facing, hw_text's letters)
  std::shared_ptr<Prepared> prepared;  // for RunInstall, which then fetches none of it again
};
Precheck PrecheckExecutables(const std::string& ca, playden::steam::CmClient& cm, const playden::StoredSession& session,
                             const InstallPlan& plan, const std::atomic<bool>& cancel, NoteFn note);

// Installs `plan` into `root` (created when missing). Runs on the caller's thread; `cancel` stops it
// between chunks, leaving what is in place for the next run. Without a free space measurement the
// install stops before writing, unless `unmeasured_ok` (the user said to go on); a drive that fills up
// then stops it with its own failure (ENOSPC). `precheck`: the precheck of this plan, whose keys,
// manifests and chunks are used instead of fetching them again (may be null).
InstallResult RunInstall(const std::string& ca, playden::steam::CmClient& cm, const playden::StoredSession& session,
                         const InstallPlan& plan, const std::string& root, const std::atomic<bool>& cancel,
                         bool unmeasured_ok, InstallProgress* progress, NoteFn note, const Precheck* precheck = nullptr);

// Whether `root` holds a finished install (its record).
bool Installed(const std::string& root);

// What a finished install's record says, for the game's page.
struct InstalledRecord {
  int format = 0;  // 2 from 01.11; 0 for 01.08..01.10's records (no launches or steam_api paths)
  std::string language;
  std::string executable, arch;
  bool steamstub = false;
  bool steam_api = false;
  std::vector<std::string> steam_api_paths;
  std::uint64_t bytes = 0;
};
bool ReadInstallRecord(const std::string& root, InstalledRecord* record);

// Whether a file or folder exists, by opening it read-only. Not access(): in this title's libc it fails
// for every path, existing or not (S4 01.09 on the console walked /data/orbisdesk/steam-games/<app> up
// to "/" while the install was writing there, and S3 showed its notice on every run).
bool PathExists(const std::string& path);

// Deletes an installed (or partly downloaded) game's folder. Everything else goes first and the install
// record last, so a removal that stops halfway still shows the game as installed and can be repeated.
// A symbolic link is removed, never followed (O_NOFOLLOW): nothing outside `root` is touched. Not
// stat(): the SDK's struct stat is not the kernel's.
struct UninstallResult {
  bool ok = false;           // the folder is gone
  std::uint64_t files = 0;   // files and links removed
  std::uint64_t folders = 0;
  std::uint64_t failures = 0;
  int first_errno = 0;
  std::string first_failure;  // the path (relative to root) of the first failure
};
// `progress` is called every few hundred files with the files removed so far (may be null).
UninstallResult RemoveGameFolder(const std::string& root, NoteFn note, void (*progress)(std::uint64_t files));

}  // namespace orbisdesk
