// SPDX-License-Identifier: GPL-3.0-or-later
// Included inside steam_client.cpp's namespace before the install pages: Big Picture's saved settings, the
// native calls it may use, and the download that runs in the background (docs/STEAM_BIG_PICTURE.md).

#if defined(STEAM_HOST)
#define ORBIS_DIR "."
#else
#define ORBIS_DIR "/data/orbisdesk"
#endif
// read by native/wine_hardware.c before Wine starts: "mode=desktop" or "mode=bigpicture"
constexpr char kStartupFile[] = ORBIS_DIR "/startup.ini";
constexpr char kFavoritesFile[] = DATA_DIR "/favorites.txt";
constexpr char kPlayedFile[] = DATA_DIR "/played.txt";
constexpr char kInstallLocationFile[] = DATA_DIR "/install-location.txt";
constexpr char kArtDir[] = DATA_DIR "/art";
// platform/ps4/pw_shell_open.h: Explorer's launch bridge (Z:\orbisdesk\process-p014\title-launch)
constexpr char kTitleLaunchDir[] = ORBIS_DIR "/process-p014";

// native/wine_hardware.c and native/hw_overlay.c, inside OrbisDesk's title; weak, so the standalone title and
// the host link without them
extern "C" int pw_hw_bigpicture_boot(void) __attribute__((weak));
extern "C" const char* pw_hw_restart_mode(const char* mode) __attribute__((weak));
extern "C" void pw_hw_close_title(void) __attribute__((weak));
extern "C" int pw_hw_open_programs(void) __attribute__((weak));

bool InOrbisDesk() {
#ifdef STEAM_UI_HOSTED
  return true;
#else
  return false;
#endif
}
bool BigPictureBoot() { return pw_hw_bigpicture_boot && pw_hw_bigpicture_boot(); }

std::string FirstLine(const std::string& path) {
  std::string text;
  int error = 0;
  if (!ReadAll(path, &text, &error)) return "";
  const auto end = text.find_first_of("\r\n");
  return end == std::string::npos ? text : text.substr(0, end);
}

bool StartupBigPicture() {
  std::string text;
  int error = 0;
  if (!ReadAll(kStartupFile, &text, &error)) return false;
  return text.find("mode=bigpicture") != std::string::npos;
}
bool SaveStartupMode(bool bigpicture) {
  const bool ok = WriteText(kStartupFile, bigpicture ? "mode=bigpicture\n" : "mode=desktop\n", 0644);
  note("PWSTEAM bigpicture startup_mode=%s saved=%d", bigpicture ? "bigpicture" : "desktop", ok);
  return ok;
}

std::set<std::uint32_t> LoadFavorites() {
  std::set<std::uint32_t> out;
  std::string text;
  int error = 0;
  if (!ReadAll(kFavoritesFile, &text, &error)) return out;
  for (std::size_t at = 0; at < text.size();) {
    const auto end = text.find('\n', at);
    const auto line = text.substr(at, end == std::string::npos ? std::string::npos : end - at);
    if (!line.empty()) out.insert(static_cast<std::uint32_t>(strtoul(line.c_str(), nullptr, 10)));
    if (end == std::string::npos) break;
    at = end + 1;
  }
  out.erase(0);
  return out;
}
void SaveFavorites(const std::set<std::uint32_t>& favorites) {
  std::string text;
  for (auto app : favorites) text += std::to_string(app) + "\n";
  if (!WriteText(kFavoritesFile, text, 0600)) note("PWSTEAM bigpicture favorites saved=0 errno=%d", errno);
}

// app -> the last time Play started it
std::map<std::uint32_t, std::uint64_t> LoadPlayed() {
  std::map<std::uint32_t, std::uint64_t> out;
  std::string text;
  int error = 0;
  if (!ReadAll(kPlayedFile, &text, &error)) return out;
  for (std::size_t at = 0; at < text.size();) {
    const auto end = text.find('\n', at);
    unsigned long app = 0;
    unsigned long long when = 0;
    if (sscanf(text.c_str() + at, "%lu %llu", &app, &when) == 2 && app) out[static_cast<std::uint32_t>(app)] = when;
    if (end == std::string::npos) break;
    at = end + 1;
  }
  return out;
}
void SavePlayed(const std::map<std::uint32_t, std::uint64_t>& played) {
  std::string text;
  for (const auto& [app, when] : played) text += std::to_string(app) + " " + std::to_string(when) + "\n";
  if (!WriteText(kPlayedFile, text, 0600)) note("PWSTEAM bigpicture played saved=0 errno=%d", errno);
}

// the drive new installs go to without asking: a GameStorage id ("internal" or a USB library's), empty: ask
std::string DefaultStorageId() { return FirstLine(kInstallLocationFile); }
bool SaveDefaultStorageId(const std::string& id) {
  const bool ok = WriteText(kInstallLocationFile, id.empty() ? "" : id + "\n", 0600);
  note("PWSTEAM bigpicture install_location=%s saved=%d", id.empty() ? "ask" : id == "internal" ? "internal" : "usb", ok);
  return ok;
}
// the default drive, prepared, when one is set and present
bool DefaultInstallStorage(orbisdesk::GameStorage* storage) {
  const std::string id = DefaultStorageId();
  if (id.empty()) return false;
  for (auto& volume : orbisdesk::GameStorages()) {
    if (volume.id != id) continue;
    std::string error;
    *storage = volume;
    if (orbisdesk::PrepareGameStorage(storage, &error)) return true;
    note("PWSTEAM bigpicture default_location prepare=0");
    return false;
  }
  note("PWSTEAM bigpicture default_location present=0");
  return false;
}

// ---- the download in the background ----
// One install at a time, as the client always did: after its plan and the user's go-ahead it runs on a thread
// of its own while the screens stay usable (Big Picture only; the text client kept its progress page). Its
// result is shown once it ends.
struct Download {
  std::uint32_t app = 0;
  std::string name, root, drive;
  orbisdesk::GameStorage storage;
  orbisdesk::InstallPlan plan;
  orbisdesk::Precheck precheck;
  bool again = false, unmeasured_ok = false, emulator = false;
  std::atomic<bool> cancel{false}, done{false};
  orbisdesk::InstallProgress progress;
  orbisdesk::InstallResult result;
  std::string page;  // the result page's text, once done
  std::thread runner;
  // the speed over the last few seconds
  std::uint64_t window_fetched = 0;
  std::chrono::steady_clock::time_point window_start = std::chrono::steady_clock::now();
  double rate = 0;
  bool fetching = false;
  void Sample() {
    const auto now = std::chrono::steady_clock::now();
    const auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - window_start).count();
    if (ms < 3000) return;
    const auto fetched = progress.fetched_bytes.load();
    rate = static_cast<double>(fetched - window_fetched) * 1000.0 / static_cast<double>(ms);
    fetching = fetched != window_fetched;
    window_fetched = fetched;
    window_start = now;
  }
  int Permille() const {
    const auto total = progress.total_bytes.load(), placed = progress.done_bytes.load();
    return total ? static_cast<int>(std::min<std::uint64_t>(1000, placed * 1000 / total)) : 0;
  }
};
std::unique_ptr<Download> download;
bool background_installs = false;  // set while Big Picture's screens run

struct FinishedDownload {
  std::uint32_t app = 0;
  std::string name, detail;
  bool ok = false;
};
std::vector<FinishedDownload> finished_downloads;

bool DownloadRunning() { return download && !download->done.load(); }
bool DownloadingApp(std::uint32_t app) { return download && download->app == app && !download->done.load(); }

void StartDownload(Context& context, const playden::StoredSession& session, const Game& game,
                   orbisdesk::InstallPlan plan, const std::string& root, const orbisdesk::GameStorage& storage,
                   bool unmeasured_ok, bool again, orbisdesk::Precheck precheck, bool emulator);
