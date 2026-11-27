// SPDX-License-Identifier: GPL-3.0-or-later
// Included inside steam_client.cpp's namespace after the install and uninstall pages: Steam Big Picture's
// controller (docs/STEAM_BIG_PICTURE.md). It fills steam_bp.h's views from the library and the console, draws
// them (steam_ui_begin/end), and turns the pad into the actions the text client had (install, verify, language,
// emulator, move, uninstall, sign out) plus Play, which starts a game exactly as its Desktop shortcut does,
// through Explorer. Logs carry events and counts, never a game or the account.

#ifdef STEAM_UI_HOSTED
#include <orbis/Rtc.h>
#endif
std::string Clock() {
  int hour = -1, minute = 0;
#ifdef STEAM_UI_HOSTED
  // the console's local time (the C library's clock is not it: native/wine_hardware.c W047)
  TimeTable now;
  memset(&now, 0, sizeof(now));
  if (!sceRtcGetCurrentClockLocalTime(&now)) hour = now.hour, minute = now.minute;
#else
  const time_t now = time(nullptr);
  struct tm local;
  if (localtime_r(&now, &local)) hour = local.tm_hour, minute = local.tm_min;
#endif
  if (hour < 0) return "";
  char text[8];
  snprintf(text, sizeof(text), "%02d:%02d", hour, minute);
  return text;
}

std::string Percent(int permille) { return std::to_string(permille / 10) + "%"; }

// ---- the download ----
void StartDownload(Context& context, const playden::StoredSession& session, const Game& game,
                   orbisdesk::InstallPlan plan, const std::string& root, const orbisdesk::GameStorage& storage,
                   bool unmeasured_ok, bool again, orbisdesk::Precheck precheck, bool emulator) {
  download = std::make_unique<Download>();
  Download* d = download.get();
  d->app = game.app;
  d->name = game.name;
  d->root = root;
  d->storage = storage;
  d->drive = DriveShort(storage);
  d->plan = std::move(plan);
  d->precheck = std::move(precheck);
  d->again = again;
  d->unmeasured_ok = unmeasured_ok;
  d->emulator = emulator;
  // its own copy: the shell replaces the library when the background load comes back
  auto g = std::make_shared<const Game>(game);
  note("PWSTEAM download start again=%d background=1", again);
  d->runner = std::thread([d, g, &context, &session] {
    const orbisdesk::GameStorage where = d->storage;
    d->result = orbisdesk::RunInstall(context.ca, *context.cm, session, d->plan, d->root, d->cancel, d->unmeasured_ok,
                                      &d->progress, note, d->again ? nullptr : &d->precheck,
                                      [where] { return orbisdesk::GameStorageAvailable(where); });
    d->page = FinishInstall(*g, d->plan, d->root, d->storage, d->result, d->emulator);
    note("PWSTEAM download end ok=%d canceled=%d", d->result.ok, d->result.canceled);
    d->done = true;
    steam_ui_poke();
  });
}

// An ended download: counted, listed under Downloads, and (`show`) its result page until O.
bool CollectDownload(Installs* installs, bool show) {
  if (!download || !download->done.load()) return false;
  download->runner.join();
  const auto& result = download->result;
  if (result.ok) ++installs->ok;
  else if (result.canceled) ++installs->paused;
  else ++installs->failed;
  FinishedDownload finished;
  finished.app = download->app;
  finished.name = download->name;
  finished.ok = result.ok;
  finished.detail = result.ok ? "INSTALLED ON " + download->drive + " \xc2\xb7 SHORTCUTS ON THE DESKTOP AND IN START"
                    : result.canceled ? "PAUSED \xc2\xb7 THE NEXT INSTALL RESUMES IT"
                                      : "NOT INSTALLED \xc2\xb7 " + result.failure;
  if (!result.canceled) finished_downloads.insert(finished_downloads.begin(), finished);
  const std::string page = download->page;
  download.reset();
  if (show) {
    steam_ui_show((page + PAGE_FOOTER "O: BACK").c_str(), nullptr);
    steam_ui_wait(STEAM_UI_CIRCLE);
  }
  return true;
}

// Stops the download (what it fetched stays, the next install resumes it) and waits for its thread.
void PauseDownload(Installs* installs) {
  if (!download) return;
  download->cancel = true;
  steam_ui_show(("DOWNLOADS\n" + download->name + "\nPAUSING THE DOWNLOAD...").c_str(), nullptr);
  while (!download->done.load()) std::this_thread::sleep_for(std::chrono::milliseconds(100));
  CollectDownload(installs, false);
}

// ---- the shell ----
struct GameInfo {
  bool installed = false, offline = false, external = false, paused = false;
  std::string letter, drive_short, drive_name, library;
  std::uint64_t bytes = 0;
};

struct Shell {
  Shell(Context& c, const playden::StoredSession& s, Library& l, Installs* i)
      : context(c), session(s), library(l), installs(i) {}
  Context& context;
  const playden::StoredSession& session;
  Library& library;  // replaced when the background load comes back (TakeLibraryRefresh)
  Installs* installs;
  bool big_picture = false;
  int tab = bp::kHome;
  int home_shelf = 0, home_index[2] = {0, 0};
  int lib_view = 1, lib_index = 0, sort = 0;
  bool lib_views_focus = false;
  int dl_selected = 0;
  int st_drive = 0, st_game = 0;
  bool st_games_focus = false;
  int set_row = 0;
  std::set<std::uint32_t> favorites;
  std::map<std::uint32_t, std::uint64_t> played;
  orbisdesk::Covers covers;
  std::map<std::uint32_t, GameInfo> info;
  std::vector<orbisdesk::GameStorage> drives;
  bool drives_loaded = false;
  // a game Play started that is still in front (the client came back over it)
  std::uint32_t running_app = 0;
  unsigned running_token = 0;
  int running_baseline = 0;
  // the non-Steam list changed: joined again to the library between screens (MergeNonSteam)
  bool nonsteam_dirty = false;
};

void RefreshGame(Shell& shell, const Game& game) {
  GameInfo info;
  if (game.non_steam) {
    // installed by definition; offline when its program (its drive) isn't there
    info.installed = true;
    const std::string program = orbisdesk::WindowsToUnix(game.ns.program);
    info.offline = program.empty() || !orbisdesk::PathExists(program);
    info.letter = game.ns.program.size() >= 2 ? Upper(game.ns.program.substr(0, 2)) : "";
    info.external = !info.letter.empty() && info.letter != "C:" && info.letter != "Z:";
    if (info.letter == "C:") info.drive_short = "C: Windows", info.drive_name = "C: Windows";
    else if (info.letter == "Z:") info.drive_short = "Z: Internal", info.drive_name = "Internal storage";
    else if (info.external) {
      info.drive_short = info.letter + " USB " + std::to_string(info.letter[0] - 'D');
      info.drive_name = info.offline ? info.letter + " (not connected)" : info.drive_short.substr(3);
    }
    shell.info[game.app] = info;
    return;
  }
  info.installed = orbisdesk::KnownInstalledGame(game.app);
  const std::string root = GameRoot(game.app);
  if (info.installed) {
    orbisdesk::GameStorage storage;
    const bool present = orbisdesk::StorageForGame(root, &storage);
    info.offline = !present || !orbisdesk::GameLocationAvailable(game.app);
    const std::string windows = orbisdesk::StorageWindowsPath(root, "");
    info.letter = windows.size() >= 2 ? windows.substr(0, 2) : "";
    info.external = info.letter != "Z:" && !info.letter.empty();
    if (present) {
      info.drive_short = DriveShort(storage);
      info.drive_name = DriveName(storage);
      info.library = storage.library;
    } else {
      info.drive_short = info.letter + " USB";
      info.drive_name = info.letter.empty() ? "a USB drive" : info.letter + " (not connected)";
    }
    orbisdesk::InstalledRecord record;
    if (!info.offline && orbisdesk::ReadInstallRecord(root, &record)) info.bytes = record.bytes;
  } else {
    info.paused = orbisdesk::PathExists(root + "/" + kLanguageFile);
  }
  shell.info[game.app] = info;
}

void Refresh(Shell& shell) {
  const auto start = std::chrono::steady_clock::now();
  for (const auto& game : shell.library.games) RefreshGame(shell, game);
  int installed = 0, offline = 0;
  for (const auto& [app, info] : shell.info) installed += info.installed, offline += info.offline;
  trace_note("PWSTEAM bigpicture refresh games=%zu installed=%d offline=%d ms=%lld", shell.library.games.size(), installed, offline,
       static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count()));
}

void LoadDrives(Shell& shell) {
  shell.drives = orbisdesk::GameStorages();
  shell.drives_loaded = true;
  trace_note("PWSTEAM bigpicture drives=%zu", shell.drives.size());
}

const GameInfo& Info(Shell& shell, const Game& game) {
  auto found = shell.info.find(game.app);
  if (found == shell.info.end()) {
    RefreshGame(shell, game);
    found = shell.info.find(game.app);
  }
  return found->second;
}

bp::Cover CoverFor(Shell& shell, const Game& game) {
  const auto& info = Info(shell, game);
  bp::Cover cover;
  cover.app = game.app;
  cover.name = game.name;
  cover.art = shell.covers.Get(game.app);
  cover.installed = info.installed;
  cover.offline = info.installed && info.offline;
  if (info.installed && info.external) cover.drive = info.letter;
  if (DownloadingApp(game.app)) cover.progress = download->Permille();
  cover.favorite = shell.favorites.count(game.app) != 0;
  cover.non_steam = game.non_steam;
  return cover;
}

bp::Frame FrameFor(Shell& shell, int tab) {
  (void)shell;
  bp::Frame frame;
  frame.tab = tab;
  frame.clock = Clock();
  if (download) {
    frame.download_name = download->name;
    frame.download_permille = download->Permille();
  }
  return frame;
}

std::vector<const Game*> Sorted(Shell& shell, std::vector<const Game*> games) {
  if (shell.sort == 1)
    std::stable_sort(games.begin(), games.end(), [](const Game* a, const Game* b) { return a->windows_bytes > b->windows_bytes; });
  else if (shell.sort == 2)
    std::stable_sort(games.begin(), games.end(), [&](const Game* a, const Game* b) {
      const auto pa = shell.played.find(a->app), pb = shell.played.find(b->app);
      return (pa == shell.played.end() ? 0 : pa->second) > (pb == shell.played.end() ? 0 : pb->second);
    });
  return games;
}
const char* SortName(int sort) { return sort == 1 ? "SIZE" : sort == 2 ? "LAST PLAYED" : "NAME A\xe2\x80\x93Z"; }

// the library's views: Installed, All games, Not installed, Favorites, then one per drive holding games
struct LibraryViews {
  std::vector<std::string> names;
  std::vector<std::vector<const Game*>> games;
  int separator = -1;
};
LibraryViews Views(Shell& shell) {
  LibraryViews views;
  views.names = {"Installed", "All games", "Not installed", "Favorites"};
  views.games.resize(4);
  std::map<std::string, std::vector<const Game*>> drives;
  std::vector<const Game*> non_steam;
  for (const auto& game : shell.library.games) {
    const auto& info = Info(shell, game);
    views.games[1].push_back(&game);
    views.games[info.installed ? 0 : 2].push_back(&game);
    if (shell.favorites.count(game.app)) views.games[3].push_back(&game);
    if (info.installed && !info.drive_short.empty()) drives[info.drive_short].push_back(&game);
    if (game.non_steam) non_steam.push_back(&game);
  }
  // the Non-Steam view once one game is added
  if (!non_steam.empty()) {
    views.names.push_back("Non-Steam");
    views.games.push_back(non_steam);
  }
  views.separator = drives.empty() ? -1 : static_cast<int>(views.names.size());
  for (auto& [name, games] : drives) {
    views.names.push_back(name);
    views.games.push_back(games);
  }
  for (auto& list : views.games) list = Sorted(shell, list);
  return views;
}

bool AddTileShown(Shell& shell, const LibraryViews& views) {
  if (!InOrbisDesk() || shell.lib_view >= static_cast<int>(views.names.size())) return false;
  const auto& name = views.names[static_cast<std::size_t>(shell.lib_view)];
  return shell.lib_view == 1 || name == "Non-Steam";
}

// the Home shelves: what was played last (else what is installed, else the library), and what is installed
struct HomeShelves {
  std::string first_title;
  std::vector<const Game*> first, second;
};
HomeShelves Shelves(Shell& shell) {
  HomeShelves shelves;
  for (const auto& game : shell.library.games)
    if (Info(shell, game).installed) shelves.second.push_back(&game);
  shelves.first = shelves.second;
  std::stable_sort(shelves.first.begin(), shelves.first.end(), [&](const Game* a, const Game* b) {
    const auto pa = shell.played.find(a->app), pb = shell.played.find(b->app);
    return (pa == shell.played.end() ? 0 : pa->second) > (pb == shell.played.end() ? 0 : pb->second);
  });
  if (download) {
    // the game downloading comes first
    for (const auto& game : shell.library.games)
      if (game.app == download->app && !Info(shell, game).installed) shelves.first.insert(shelves.first.begin(), &game);
  }
  shelves.first_title = "CONTINUE PLAYING";
  if (shelves.first.empty()) {
    shelves.first_title = "IN YOUR LIBRARY";
    for (const auto& game : shell.library.games) {
      if (shelves.first.size() >= 20) break;
      shelves.first.push_back(&game);
    }
  }
  if (shelves.first.size() > 20) shelves.first.resize(20);
  return shelves;
}

bp::HomeView HomeViewFor(Shell& shell, const HomeShelves& shelves) {
  bp::HomeView view;
  view.frame = FrameFor(shell, bp::kHome);
  view.first_title = shelves.first_title;
  for (const auto* game : shelves.first) view.first.push_back(CoverFor(shell, *game));
  for (const auto* game : shelves.second) view.second.push_back(CoverFor(shell, *game));
  view.shelf = shell.home_shelf;
  view.index = shell.home_index[shell.home_shelf];
  view.empty_second = shell.library.games.empty() ? "THIS ACCOUNT HAS NO GAMES WITH WINDOWS CONTENT."
                                                  : "NO GAME IS INSTALLED YET. OPEN ONE FROM THE LIBRARY TO INSTALL IT.";
  view.big_picture = shell.big_picture;
  return view;
}

// ---- a modal message and a yes/no question, over the current screen ----
bool Confirm(const std::string& label, const std::string& title, const std::string& text, const std::string& yes,
             const std::string& no, bool warn, int focus = 0) {
  for (;;) {
    Present([&](bp::Painter& p) {
      bp::MessageView view;
      view.label = label;
      view.title = title;
      view.text = text;
      view.warn = warn;
      view.buttons = {yes, no};
      view.focus = focus;
      view.hints = {{bp::kCross, "", focus == 0 ? yes : no}, {bp::kNoButton, bp::kLeftRight, "CHOOSE"}, {bp::kCircle, "", no}};
      bp::DrawMessage(p, view);
    });
    const unsigned button = steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_LEFT | STEAM_UI_RIGHT);
    if (button == STEAM_UI_LEFT || button == STEAM_UI_RIGHT) focus = 1 - focus;
    else return button == STEAM_UI_CROSS && focus == 0;
  }
}

void Splash(const std::string& what) {
  Present([&](bp::Painter& p) { bp::DrawSplash(p, what); });
}

// ---- Play: the game's launch entry through Explorer's bridge (platform/ps4/pw_shell_open.h) ----
int LaunchReply(unsigned token, unsigned* value) {
  std::string text;
  int error = 0;
  if (!ReadAll(std::string(kTitleLaunchDir) + "/title-launch-reply", &text, &error)) return 0;
  unsigned got_token = 0, got_value = 0;
  char word[16] = {0};
  if (sscanf(text.c_str(), "%u %15s %u", &got_token, word, &got_value) < 2 || got_token != token) return 0;
  *value = got_value;
  if (!strcmp(word, "started")) return 1;
  if (!strcmp(word, "ended")) return 2;
  if (!strcmp(word, "failed")) return -1;
  return 0;
}

bool LaunchThroughExplorer(const orbisdesk::LaunchEntry& entry, unsigned* token) {
  const std::string dir = kTitleLaunchDir;
  mkdir(dir.c_str(), 0777);
  unlink((dir + "/title-launch-reply").c_str());
  std::string hex;
  if (!RandomHex(4, &hex)) hex = std::to_string(time(nullptr));
  *token = static_cast<unsigned>(strtoul(hex.c_str(), nullptr, 16) & 0x7fffffffu) | 1u;
  // the lines Explorer reads: image, command line, folder, token (UTF-8)
  const std::string command = "\"" + entry.image + "\"" + (entry.arguments.empty() ? "" : " " + entry.arguments);
  const std::string text = entry.image + "\n" + command + "\n" + entry.directory + "\n" + std::to_string(*token) + "\n";
  const std::string temp = dir + "/title-launch.tmp";
  const int fd = open(temp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0) return false;
  const bool written = write(fd, text.data(), text.size()) == static_cast<ssize_t>(text.size()) && fsync(fd) == 0;
  close(fd);
  chmod(temp.c_str(), 0666);
  return written && !rename(temp.c_str(), (dir + "/title-launch").c_str());
}

int OpenPrograms() { return pw_hw_open_programs ? pw_hw_open_programs() : -1; }

// ---- the prefix's Steam registration (2026-11-25) ----
// A game's own Steam emulator writes itself into the prefix as Steam (HKCU Valve\Steam, ActiveProcess's client DLL,
// steam://) and leaves SteamAppId set for whatever starts next; on hardware AC2's SteamStub then opened GTA IV's
// repack launcher. C:\orbis\steam-open.exe --register (native/steam/orbis_steam_open.c) puts OrbisDesk back:
// itself as Steam's executable and steam:// handler, ActiveProcess with no running client (OrbisDesk has no Windows
// Steam client), the Steam variables cleared. Run through Explorer's bridge when the client opens and before Play.
constexpr char kRegistryResult[] = DATA_DIR "/registry-owner.txt";

void ClaimSteamRegistration(std::uint32_t app, bool wait) {
  if (!InOrbisDesk()) return;
  orbisdesk::LaunchEntry entry;
  entry.ok = true;
  entry.image = "C:\\orbis\\steam-open.exe";
  entry.arguments = "--register " + std::to_string(app);
  entry.directory = "C:\\orbis";
  unlink(kRegistryResult);
  unsigned token = 0;
  if (!LaunchThroughExplorer(entry, &token)) {
    note("PWSTEAM registry request_write=0 errno=%d", errno);
    return;
  }
  if (!wait) {
    trace_note("PWSTEAM registry request=sent wait=0");
    return;
  }
  // Explorer's watcher looks twice a second; the helper only writes a few keys
  int state = 0;
  unsigned value = 0;
  for (int waited = 0; waited < 80; ++waited) {
    state = LaunchReply(token, &value);
    if (state == 2 || state < 0) break;
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  std::string result;
  int error = 0;
  if (state == 2 && ReadAll(kRegistryResult, &result, &error)) {
    while (!result.empty() && (result.back() == '\n' || result.back() == '\r')) result.pop_back();
    note("PWSTEAM registry %s", result.c_str());  // owners and counts only (orbis_steam_open.c)
  } else {
    note("PWSTEAM registry state=%d value=%u result=%d", state, value, state == 2);
  }
}

// While the game Play started is in front: the client hidden, the game with the pad. Back when the game and
// whatever it started have ended (a launcher may end before its game: the title's list of open programs
// says), or when the overlay menu or Start asks for Steam. True when the game has ended.
bool WaitForGame(Shell& shell) {
  steam_ui_hide();
  const auto start = std::chrono::steady_clock::now();
  bool seen = false;
  int quiet_ms = 0;
  bool ended = false;
  for (;;) {
    steam_ui_wait_for(0, 250);
    if (steam_ui_show_requested()) break;
    if (!CollectDownload(shell.installs, false)) {
    }
    const int programs = OpenPrograms();
    unsigned value = 0;
    const int state = LaunchReply(shell.running_token, &value);
    if (programs > shell.running_baseline) seen = true;
    bool gone;
    if (programs < 0) gone = state == 2;                                  // no list: Explorer's word
    else if (!seen) gone = state == 2 && programs <= shell.running_baseline;  // never listed: Explorer's word, checked
    else gone = programs <= shell.running_baseline;
    quiet_ms = gone ? quiet_ms + 250 : 0;
    if (quiet_ms >= 1500) {
      ended = true;
      break;
    }
  }
  const auto seconds = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - start).count();
  note("PWSTEAM play %s seconds=%lld seen=%d", ended ? "ended" : "shown_over_game", static_cast<long long>(seconds), seen);
  if (ended) shell.running_app = 0;
  steam_ui_unhide();
  return ended;
}

// What a start through Explorer came to: started, ended, how long it ran, and Explorer's last reply value (the
// exit code once it ended).
struct LaunchOutcome {
  bool started = false, ended = false;
  long long seconds = 0;
  int state = 0;
  unsigned value = 0;
};
LaunchOutcome LaunchAndWait(Shell& shell, const Game& game, const orbisdesk::LaunchEntry& entry);

// ---- full emulation for SteamStub games (the approved review of 2026-11-25) ----
// SteamStub looks for a running Steam client; OrbisDesk's is native. Opted in per game, Play starts the game
// through gbe_fork's ColdClient loader (C:\orbis\steam\coldclient, tools/build-steam-hosted.py), whose experimental
// steamclient.dll the game then loads itself through ActiveProcess, which the loader sets while it runs. No
// remote injection. An additional per-EXE opt-in loads a guarded startup addon before the entry point.
// It changes memory only; it never rewrites the EXE. Experimental: it may not start, and other launchers a
// game needs (Ubisoft, Rockstar) are not provided.
constexpr char kColdClientFile[] = ".orbisdesk-coldclient.txt";  // in the game's folder: the choice and the last run
#ifdef STEAM_HOST
constexpr char kColdClientDir[] = "wine-prefix/drive_c/orbis/steam/coldclient";
#else
constexpr char kColdClientDir[] = "/data/wine-prefix/drive_c/orbis/steam/coldclient";
#endif
constexpr char kColdClientWindows[] = "C:\\orbis\\steam\\coldclient";

struct ColdClientState {
  bool on = false;
  long long last_seconds = -1;
  unsigned last_code = 0;
};

ColdClientState ReadColdClient(const std::string& root) {
  ColdClientState state;
  std::string text;
  int error = 0;
  if (!ReadAll(root + "/" + kColdClientFile, &text, &error)) return state;
  state.on = text.rfind("on", 0) == 0;
  const auto seconds = text.find("last_seconds=");
  if (seconds != std::string::npos) state.last_seconds = strtoll(text.c_str() + seconds + 13, nullptr, 10);
  const auto code = text.find("last_code=");
  if (code != std::string::npos) state.last_code = static_cast<unsigned>(strtoul(text.c_str() + code + 10, nullptr, 10));
  return state;
}

bool WriteColdClient(const std::string& root, const ColdClientState& state) {
  if (!state.on && state.last_seconds < 0) return !unlink((root + "/" + kColdClientFile).c_str()) || errno == ENOENT;
  std::string text = state.on ? "on\n" : "off\n";
  if (state.last_seconds >= 0)
    text += "last_seconds=" + std::to_string(state.last_seconds) + "\nlast_code=" + std::to_string(state.last_code) + "\n";
  return WriteText(root + "/" + kColdClientFile, text, 0644);
}

bool HasSteamStub(const orbisdesk::InstalledRecord& record) {
  if (record.steamstub) return true;
  for (const auto& check : record.checks)
    if (check.present && check.pe && check.steamstub) return true;
  return false;
}

// a second launcher the game's folder shows it needs (its DLLs, two folders deep): "Ubisoft", "Rockstar" or ""
std::string SecondLauncher(const std::string& root) {
  std::vector<std::pair<std::string, int>> pending = {{root, 2}};
  int looked = 0;
  std::vector<orbisdesk::FolderEntry> entries;
  while (!pending.empty() && looked < 2000) {
    const auto [dir, depth] = pending.back();
    pending.pop_back();
    if (!orbisdesk::ListFolder(dir, {".dll"}, &entries)) continue;
    for (const auto& entry : entries) {
      ++looked;
      const std::string lower = orbisdesk::LowerAscii(entry.name);
      if (lower.rfind("ubiorbitapi", 0) == 0 || lower.rfind("uplay_r1", 0) == 0 || lower.rfind("upc_r", 0) == 0)
        return "Ubisoft";
      if (lower.rfind("socialclub", 0) == 0 || lower == "paul.dll") return "Rockstar";
      if (entry.folder && depth > 0) pending.push_back({dir + "/" + entry.name, depth - 1});
    }
  }
  return "";
}

bool ColdClientFilesReady() {
  for (const char* name : {"steamclient.dll", "steamclient64.dll", "steamclient_loader_x86.exe", "steamclient_loader_x64.exe"})
    if (!orbisdesk::PathExists(std::string(kColdClientDir) + "/" + name)) return false;
  return true;
}

// The loader's ini for a start of `game_entry` (Play writes it for each start; a shortcut's launch plan keeps one).
std::string ColdClientIni(std::uint32_t app, const orbisdesk::LaunchEntry& game_entry) {
  return "# OrbisDesk: written for each start of a game with full emulation (native/steam/steam_bigpicture.inc.cpp)\r\n"
         "[SteamClient]\r\nExe=" + game_entry.image + "\r\nExeRunDir=" + game_entry.directory + "\r\nExeCommandLine=" +
         game_entry.arguments + "\r\nAppId=" + std::to_string(app) +
         "\r\nSteamClientDll=steamclient.dll\r\nSteamClient64Dll=steamclient64.dll\r\n"
         "[Injection]\r\nForceInjectSteamClient=0\r\nForceInjectGameOverlayRenderer=0\r\nDllsToInjectFolder=\r\n"
         "IgnoreInjectionError=1\r\nIgnoreLoaderArchDifference=1\r\n"
         "[Persistence]\r\nMode=0\r\n[Debug]\r\nResumeByDebugger=0\r\n";
}

// the loader that matches the architecture of the game's entry
std::string ColdClientLoaderImage(const orbisdesk::InstalledRecord& record, const orbisdesk::LaunchEntry& game_entry) {
  const std::string arch = game_entry.index < record.checks.size() ? record.checks[game_entry.index].arch : record.arch;
  return std::string(kColdClientWindows) + (arch == "x64" ? "\\steamclient_loader_x64.exe" : "\\steamclient_loader_x86.exe");
}

// The loader's ini for this start, and the loader that matches the exe's architecture; false when it can't be set up.
bool SetUpColdClient(const Game& game, const orbisdesk::InstalledRecord& record, const orbisdesk::LaunchEntry& game_entry,
                     orbisdesk::LaunchEntry* loader) {
  const std::string arch = game_entry.index < record.checks.size() ? record.checks[game_entry.index].arch : record.arch;
  const bool x64 = arch == "x64";
  const std::string ini = ColdClientIni(game.app, game_entry);
  const bool files = ColdClientFilesReady();
  const bool wrote = files && WriteText(std::string(kColdClientDir) + "/ColdClientLoader.ini", ini, 0644);
  note("PWSTEAM coldclient setup app=%u arch=%s files=%d ini=%d", game.app, x64 ? "x64" : "x86", files, wrote);
  if (!wrote) return false;
  loader->ok = true;
  loader->index = game_entry.index;
  loader->image = ColdClientLoaderImage(record, game_entry);
  loader->arguments.clear();  // the game's own are in the ini
  loader->directory = kColdClientWindows;
  return true;
}

// ---- each installed game's launch plan (2026-11-26) ----
// What Play would start now, decided here as PlayGame decides it (full emulation, the
// loader that matches the exe), for C:\orbis\steam-open.exe (native/steam/orbis_steam_open.c): a SteamStub game's
// shortcut runs --play <app> (orbisdesk::kLauncherImage), and Steam's URL steam://run/<app>//<args>, which a game's
// launcher opens to have Steam start the game (hardware 2026-11-26: Rockstar's for GTA IV), runs it with the URL's
// arguments. Written for every installed game when the client opens (RefreshAllLaunchPlans), and for one when it is
// installed, before each Play, when its emulation changes, after a move, and by Create shortcuts; a file is
// rewritten only when it changes.
constexpr char kLaunchPlanDir[] = DATA_DIR "/launch";

struct LaunchPlan {
  bool ok = false;
  orbisdesk::LaunchEntry start;  // the program, its arguments and folder
  std::string ini;               // with full emulation: the loader's ini
  std::string message;           // when the game can't start from its shortcut
};

LaunchPlan PlanLaunch(std::uint32_t app, const orbisdesk::InstalledRecord& record, const std::string& root) {
  LaunchPlan plan;
  const auto cold = ReadColdClient(root);
  const bool full_emulation = cold.on;  // the game's launch mode (LaunchModeMenu), SteamStub or not
  if (record.steamstub && !full_emulation) {
    plan.message = "This game has SteamStub DRM. Choose a full emulation launch mode on its page in Steam Big Picture "
                   "(Triangle), then start it again.";
    return plan;
  }
  const auto entry = orbisdesk::ChooseLaunchEntry(record.launches, record.checks, root, record.language, full_emulation);
  if (!entry.ok) {
    plan.message = "There is no Windows executable to start (" + entry.skipped + ").";
    return plan;
  }
  if (!full_emulation) {
    plan.ok = true;
    plan.start = entry;
    return plan;
  }
  if (!ColdClientFilesReady()) {
    plan.message = "Full emulation could not be set up: its files are missing from C:\\orbis\\steam. Update OrbisDesk.";
    return plan;
  }
  plan.ok = true;
  plan.ini = ColdClientIni(app, entry);
  plan.start.ok = true;
  plan.start.image = ColdClientLoaderImage(record, entry);
  plan.start.directory = kColdClientWindows;
  return plan;
}

void RefreshLaunchPlan(std::uint32_t app) {
  const std::string base = std::string(kLaunchPlanDir) + "/" + std::to_string(app);
  const std::string root = GameRoot(app);
  orbisdesk::InstalledRecord record;
  if (root.empty() || !orbisdesk::ReadInstallRecord(root, &record)) {
    unlink((base + ".plan").c_str());
    unlink((base + ".ini").c_str());
    return;
  }
  const auto plan = PlanLaunch(app, record, root);
  mkdir(kLaunchPlanDir, 0777);
  // written only when it differs: the client writes every game's at each open
  auto same = [](const std::string& path, const std::string& text) {
    std::string have;
    int error = 0;
    return ReadAll(path, &have, &error) && have == text;
  };
  bool ini = !plan.ini.empty();
  if (ini) ini = same(base + ".ini", plan.ini) || WriteText(base + ".ini", plan.ini, 0644);
  else unlink((base + ".ini").c_str());
  std::string text;
  if (plan.ok && (plan.ini.empty() || ini)) {
    const std::string command =
        "\"" + plan.start.image + "\"" + (plan.start.arguments.empty() ? "" : " " + plan.start.arguments);
    text = "state=ok\nimage=" + plan.start.image + "\ncommand=" + command + "\ndirectory=" + plan.start.directory +
           "\nini=" + (ini ? "1" : "0") + "\n";
  } else {
    text = "state=blocked\nmessage=" + (plan.ok ? std::string("The loader settings could not be saved.") : plan.message) + "\n";
  }
  if (same(base + ".plan", text)) return;
  const bool saved = WriteText(base + ".plan", text, 0644);
  note("PWSTEAM launch_plan app=%u state=%s coldclient=%d saved=%d", app, plan.ok ? "ok" : "blocked", !plan.ini.empty(), saved);
}

void RefreshAllLaunchPlans(const Library& library) {
  if (!InOrbisDesk()) return;
  int installed = 0;
  for (const auto& game : library.games) {
    if (game.non_steam || !orbisdesk::KnownInstalledGame(game.app)) continue;
    ++installed;
    RefreshLaunchPlan(game.app);
  }
  trace_note("PWSTEAM launch_plans installed=%d", installed);
}

// ---- Settings: Create shortcuts (2026-11-26) ----
// OrbisDesk installed again over kept games leaves them without their Desktop and Start menu links; this writes them
// for every installed Steam game at once, as an install does (WriteGameShortcuts, the SteamStub games' launch plans
// too), instead of a Verify per game. A link of the same name is replaced; nothing else of the game is touched.
void CreateAllShortcuts(Shell& shell) {
  if (!Confirm("CREATE SHORTCUTS", "Create shortcuts",
               "Every installed Steam game gets its shortcut on the Desktop and in Start \xc2\xbb Programs \xc2\xbb Steam "
               "again. A shortcut with the same name is replaced; the games' files are not changed.",
               "CREATE", "CANCEL", false, 0))
    return;
  Splash("CREATING SHORTCUTS");
  int games = 0, made = 0, launchers = 0, none = 0, failed = 0;
  bool prefix = true;
  for (const auto& game : shell.library.games) {
    if (game.non_steam) continue;
    const std::string root = GameRoot(game.app);
    orbisdesk::InstalledRecord record;
    if (root.empty() || !orbisdesk::ReadInstallRecord(root, &record)) continue;
    ++games;
    orbisdesk::InstallResult installed;
    installed.ok = true;
    installed.launches = record.launches;
    installed.checks = record.checks;
    const auto links = orbisdesk::WriteGameShortcuts(game.app, game.name, installed, root, record.language, "",
                                                     ReadColdClient(root).on);
    if (!links.prefix) {
      prefix = false;
      break;
    }
    RefreshLaunchPlan(game.app);
    if (!links.desktop.empty() || !links.start.empty()) {
      ++made;
      launchers += links.launcher;
    } else if (links.failed) {
      ++failed;
    } else {
      ++none;
    }
  }
  note("PWSTEAM shortcuts_all games=%d made=%d launchers=%d none=%d failed=%d prefix=%d", games, made, launchers, none,
       failed, prefix);
  std::string page = "CREATE SHORTCUTS\n";
  if (!prefix) page += "ORBISDESK IS NOT INSTALLED ON THIS CONSOLE: NO SHORTCUT WAS MADE.";
  else if (!games) page += "NO STEAM GAME IS INSTALLED ON THIS CONSOLE OR ITS CONNECTED DRIVES.";
  else {
    page += std::to_string(made) + " OF " + std::to_string(games) + " INSTALLED GAMES HAVE THEIR SHORTCUTS AGAIN.";
    if (none) page += "\n" WARN_LINE + std::to_string(none) + " HAVE NO WINDOWS EXECUTABLE A SHORTCUT CAN START.";
    if (failed) page += "\n" WARN_LINE + std::to_string(failed) + " COULD NOT BE WRITTEN.";
  }
  StorageMessage(page);
}

// ---- launch modes (the approved review of 2026-11-26) ----
// Triangle on an installed Steam game's page chooses how Play, its Desktop and Start shortcuts (steam-open --play) and
// steam://run start it: Direct (the game's own Steam files), the Steam API emulator (gbe_fork's steam_api), full
// emulation (gbe_fork's ColdClient loader). The mode is the game's
// own state, the emulator's record and the ColdClient choice in its folder, so a game keeps the mode it had; the
// recommended one is only marked. The user's choice is also written to kLaunchModeFile in the game's folder, which
// moves with it. Nothing here gets past an online ownership check (Rockstar's launcher checks GTA IV's with Valve).
enum LaunchMode { kModeDirect = 0, kModeApi = 1, kModeCold = 2, kModeCount = 3 };
constexpr char kLaunchModeFile[] = ".orbisdesk-launch-mode.txt";
const char* const kModeNames[] = {"direct", "api", "coldclient"};
const char* const kModeLabels[] = {"Direct", "Steam API emulator", "Full emulation (ColdClient)"};

int CurrentLaunchMode(const std::string& root) {
  const auto cold = ReadColdClient(root);
  if (cold.on) return kModeCold;
  return orbisdesk::EmulatorEnabled(root) ? kModeApi : kModeDirect;
}

bool ApiEmulatorPossible(const orbisdesk::InstalledRecord& record) {
  return record.format >= 2 && !record.steam_api_paths.empty();
}

// SteamStub: full emulation; Steam API: the emulator; else Direct
int RecommendedLaunchMode(const orbisdesk::InstalledRecord& record) {
  if (HasSteamStub(record)) return kModeCold;
  if (record.steam_api && ApiEmulatorPossible(record)) return kModeApi;
  return kModeDirect;
}

bool UserChoseLaunchMode(const std::string& root) { return orbisdesk::PathExists(root + "/" + kLaunchModeFile); }

void NoteLaunchMode(std::uint32_t app, const std::string& root, const orbisdesk::InstalledRecord& record) {
  trace_note("PWSTEAM launch_mode app=%u mode=%s recommended=%s source=%s", app, kModeNames[CurrentLaunchMode(root)],
       kModeNames[RecommendedLaunchMode(record)], UserChoseLaunchMode(root) ? "user" : "default");
}

// why `mode` can't apply to the game, "" when it can
std::string LaunchModeUnavailable(int mode, const std::string& root, const orbisdesk::InstalledRecord& record) {
  if (mode == kModeApi) {
    if (ApiEmulatorPossible(record) || orbisdesk::EmulatorEnabled(root)) return "";
    return record.steam_api && record.format < 2 ? "VERIFY THE GAME FIRST" : "THE GAME HAS NO STEAM_API.DLL";
  }
  if (mode == kModeCold) {
    if (!orbisdesk::ChooseLaunchEntry(record.launches, record.checks, root, record.language, true).ok)
      return "NO WINDOWS EXECUTABLE TO START";
    if (!ColdClientFilesReady()) return "COLDCLIENT FILES MISSING";
  }
  return "";
}

// for steam_client.cpp's shortcuts: the game's mode starts it through the ColdClient loader
bool ColdClientOn(const std::string& root) { return ReadColdClient(root).on; }

bool LaunchModeMenu(const Game& game, const bp::GameView& page, const orbisdesk::InstalledRecord& record);

// After a start from Play: the last run on the page, and, when the game closed within 30 s, a word and the way to
// another launch mode (every mode, the approved review's decision 4).
void AfterPlay(Shell& shell, const Game& game, const std::string& root, const orbisdesk::InstalledRecord& record,
               const LaunchOutcome& outcome) {
  auto state = ReadColdClient(root);
  state.last_seconds = outcome.seconds;
  state.last_code = outcome.state == 2 ? outcome.value : 0;
  WriteColdClient(root, state);
  const int mode = CurrentLaunchMode(root);
  note("PWSTEAM play ended mode=%s started=%d ended=%d reply=%d code=%u seconds=%lld", kModeNames[mode], outcome.started,
       outcome.ended, outcome.state, outcome.value, outcome.seconds);
  if (!outcome.started || !outcome.ended || outcome.seconds >= 30) return;
  int focus = 0;
  for (;;) {
    Present([&](bp::Painter& p) {
      bp::MessageView view;
      view.label = "LAUNCH MODE \xc2\xb7 " + Upper(kModeLabels[mode]);
      view.warn = true;
      view.title = game.name + " closed";
      // a loader's exit code is not the game's (host Wine: a game ending with 7 left the loader's 0), so none
      view.text = "It ran " + std::to_string(outcome.seconds) +
                  " seconds. That usually means the game, or a launcher it needs, refused to go on in this mode. Another "
                  "launch mode may get further; OrbisDesk's log has the details for this run.";
      view.buttons = {"OK", "CHOOSE ANOTHER MODE"};
      view.focus = focus;
      view.hints = {{bp::kNoButton, bp::kLeftRight, "CHOOSE"}, {bp::kCross, "", "SELECT"}, {bp::kCircle, "", "OK"}};
      bp::DrawMessage(p, view);
    });
    const unsigned button = steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_LEFT | STEAM_UI_RIGHT);
    if (button == STEAM_UI_LEFT || button == STEAM_UI_RIGHT) focus = 1 - focus;
    else if (button == STEAM_UI_CIRCLE || focus == 0) return;
    else {
      trace_note("PWSTEAM launch_mode menu from=short_run app=%u", game.app);
      LaunchModeMenu(game, has_picker_backdrop ? picker_backdrop : bp::GameView{}, record);
      (void)shell;
      return;
    }
  }
}

void PlayGame(Shell& shell, const Game& game) {
  if (game.non_steam) {
    const std::string program = orbisdesk::WindowsToUnix(game.ns.program);
    if (program.empty() || !orbisdesk::PathExists(program)) {
      StorageMessage("PLAY\n" + game.name + "\nTHE PROGRAM IS NOT ON THE CONSOLE NOW. RECONNECT ITS DRIVE, OR EDIT THE GAME.");
      return;
    }
    orbisdesk::LaunchEntry entry;
    entry.ok = true;
    entry.image = game.ns.program;
    entry.arguments = game.ns.options;
    entry.directory = game.ns.folder.empty() ? orbisdesk::WindowsFolder(game.ns.program) : game.ns.folder;
    LaunchAndWait(shell, game, entry);
    return;
  }
  const std::string root = GameRoot(game.app);
  orbisdesk::InstalledRecord record;
  if (!orbisdesk::ReadInstallRecord(root, &record)) {
    StorageMessage("PLAY\n" + game.name + "\nTHE GAME'S INSTALL RECORD COULD NOT BE READ. VERIFY IT WITH VERIFY AND UPDATE.");
    return;
  }
  RefreshLaunchPlan(game.app);  // its shortcut and steam://run start what this Play does
  const bool full_emulation = ReadColdClient(root).on;  // the game's launch mode
  if (record.steamstub && !full_emulation) {
    StorageMessage("PLAY\n" + game.name + "\n" WARN_LINE "STEAMSTUB DRM: TRIANGLE ON THE GAME'S PAGE CHOOSES A FULL "
                   "EMULATION LAUNCH MODE (EXPERIMENTAL).");
    return;
  }
  const auto entry = orbisdesk::ChooseLaunchEntry(record.launches, record.checks, root, record.language, full_emulation);
  if (!entry.ok) {
    note("PWSTEAM play no_entry reason=%s", entry.skipped.c_str());
    StorageMessage("PLAY\n" + game.name + "\nTHERE IS NO WINDOWS EXECUTABLE TO START: " + Upper(entry.skipped) + ".");
    return;
  }
  if (!full_emulation) {
    AfterPlay(shell, game, root, record, LaunchAndWait(shell, game, entry));
    return;
  }
  orbisdesk::LaunchEntry loader;
  if (!SetUpColdClient(game, record, entry, &loader)) {
    StorageMessage("PLAY\n" + game.name + "\nFULL EMULATION COULD NOT BE SET UP: ITS FILES ARE MISSING FROM C:\\ORBIS\\STEAM. "
                   "UPDATE ORBISDESK.");
    return;
  }
  AfterPlay(shell, game, root, record, LaunchAndWait(shell, game, loader));
}

// Starts `entry` through Explorer and stays out of the way until the game ends.
LaunchOutcome LaunchAndWait(Shell& shell, const Game& game, const orbisdesk::LaunchEntry& entry) {
  LaunchOutcome outcome;
  if (!InOrbisDesk()) {
    StorageMessage("PLAY\n" + game.name + "\nGAMES START INSIDE ORBISDESK, FROM ITS STEAM CLIENT OR THE GAME'S SHORTCUT.");
    return outcome;
  }
  // the prefix names OrbisDesk as Steam again, whatever a game's emulator wrote since
  ClaimSteamRegistration(game.non_steam ? 0 : game.app, true);
  const int baseline = OpenPrograms();
  unsigned token = 0;
  Splash("STARTING " + Upper(game.name));
  if (!LaunchThroughExplorer(entry, &token)) {
    note("PWSTEAM play request_write=0 errno=%d", errno);
    StorageMessage("PLAY\n" + game.name + "\nTHE START REQUEST COULD NOT BE WRITTEN.");
    return outcome;
  }
  const auto launched = std::chrono::steady_clock::now();
  // Explorer's watcher looks twice a second
  int state = 0;
  unsigned value = 0;
  for (int waited = 0; waited < 150 && !(state = LaunchReply(token, &value)); ++waited)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  note("PWSTEAM play reply state=%d value=%u programs_before=%d language_args=%d", state, value, baseline,
       !entry.language_arguments.empty());
  outcome.state = state;
  outcome.value = value;
  if (state == 0) {
    StorageMessage("PLAY\n" + game.name + "\nTHE DESKTOP DID NOT ANSWER THE START REQUEST. TRY AGAIN IN A MOMENT.");
    return outcome;
  }
  if (state < 0) {
    StorageMessage("PLAY\n" + game.name + "\nWINDOWS COULD NOT START THE GAME: ERROR " + std::to_string(value) + ".");
    return outcome;
  }
  outcome.started = true;
  shell.played[game.app] = static_cast<std::uint64_t>(time(nullptr));
  SavePlayed(shell.played);
  shell.running_app = game.app;
  shell.running_token = token;
  shell.running_baseline = baseline < 0 ? 0 : baseline;
  outcome.ended = WaitForGame(shell);
  outcome.seconds = std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now() - launched).count();
  unsigned ended_value = 0;
  const int ended_state = LaunchReply(token, &ended_value);
  if (ended_state) outcome.state = ended_state, outcome.value = ended_value;
  return outcome;
}

// ---- the game page ----
enum Action { kPlay, kResumeGame, kInstall, kVerify, kMove, kLanguage, kUninstall, kCheckDrives, kResumeMove,
              kPauseDownload, kResumeDownload };

bool ExeRunning(const orbisdesk::InstalledRecord& record) {
  if (!pw_hw_steam_exe_running) return false;
  for (const auto& launch : record.launches) {
    const auto slash = launch.executable.find_last_of("/\\");
    const auto name = launch.executable.substr(slash == std::string::npos ? 0 : slash + 1);
    if (pw_hw_steam_exe_running(name.c_str())) return true;
  }
  return false;
}

void ToggleEmulator(const Game& game, const std::string& root, const orbisdesk::InstalledRecord& record) {
  const bool emulator = orbisdesk::EmulatorEnabled(root);
  if (!(record.format >= 2 && !record.steam_api_paths.empty()) && !emulator) return;
  // the switch reads and writes the game's DLLs: say so at once, so the page doesn't sit unchanged
  steam_ui_show(("STEAM API EMULATOR\n" + game.name + "\n" +
                 (emulator ? "RESTORING THE ORIGINAL STEAM API..." : "TURNING ON THE EMULATOR...") + "\n").c_str(),
                nullptr);
  trace_note("PWSTEAM emu %s pressed", emulator ? "restore" : "enable");
  std::string failure;
  const bool ok = emulator ? orbisdesk::RestoreEmulator(root, note, &failure)
                           : orbisdesk::EnableEmulator(root, game.app, record.steam_api_paths, record.language, note, &failure);
  note("PWSTEAM emu %s ok=%d", emulator ? "restore" : "enable", ok);
  if (!ok) StorageMessage("STEAM API EMULATOR\n" + game.name + "\n" + failure);
}

// What each mode does, under the menu.
std::string LaunchModeText(int mode, bool stub) {
  switch (mode) {
    case kModeDirect:
      return stub ? "Direct starts the game's own exe. Its SteamStub DRM looks for a running Steam client, which OrbisDesk "
                    "doesn't have, so Play stays off in this mode."
                  : "Direct starts the game's own exe with its own Steam files, as a PC without Steam would.";
    case kModeApi:
      return "Steam API emulator: gbe_fork's steam_api.dll in place of the game's, so it starts without a Steam client. "
             "The game's own DLL is kept and comes back when another mode is chosen.";
    default:
      return "Full emulation starts the game through gbe_fork's ColdClient loader with its own steamclient.dll. It is not "
             "Steam: online features, achievements and other launchers (Ubisoft, Rockstar, EA) are not provided.";
  }
}

// Triangle on an installed Steam game's page. True when the mode changed.
bool LaunchModeMenu(const Game& game, const bp::GameView& page, const orbisdesk::InstalledRecord& record) {
  const std::string root = GameRoot(game.app);
  auto cold = ReadColdClient(root);
  const bool stub = HasSteamStub(record);
  const int current = CurrentLaunchMode(root), recommended = RecommendedLaunchMode(record);
  std::string why[kModeCount];
  for (int mode = 0; mode < kModeCount; ++mode) why[mode] = LaunchModeUnavailable(mode, root, record);
  NoteLaunchMode(game.app, root, record);
  int selected = current;
  for (;;) {
    bp::ChoiceView view;
    view.backdrop = page;
    view.label = "LAUNCH MODE";
    view.title = game.name;
    for (int mode = 0; mode < kModeCount; ++mode) {
      bp::ChoiceRow row;
      row.label = kModeLabels[mode];
      row.disabled = !why[mode].empty() && mode != current;
      if (!why[mode].empty()) row.value = why[mode];
      else if (mode == kModeDirect && stub) row.value = "STEAMSTUB: PLAY STAYS OFF", row.warn = true;
      else if (mode == kModeDirect) row.value = "THE GAME'S OWN STEAM FILES";
      if (mode == recommended) row.marks.push_back({"RECOMMENDED", 0});
      if (mode == current) row.marks.push_back({"CURRENT", 1});
      if (mode >= kModeCold && why[mode].empty()) row.marks.push_back({"EXPERIMENTAL", 2});
      view.rows.push_back(row);
    }
    view.selected = selected;
    view.text = LaunchModeText(selected, stub) +
                (selected == recommended ? " Recommended for this game." : "") +
                " Play, its Desktop and Start shortcuts and Steam links use the mode chosen here.";
    view.hints = {{bp::kNoButton, bp::kUpDown, "CHOOSE"}, {bp::kCross, "", "USE"}, {bp::kCircle, "", "BACK"}};
    Present([&](bp::Painter& p) { bp::DrawChoice(p, view); });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_CROSS | STEAM_UI_CIRCLE);
    if (button == STEAM_UI_CIRCLE) return false;
    if (button == STEAM_UI_UP || button == STEAM_UI_DOWN) {
      const int step = button == STEAM_UI_UP ? kModeCount - 1 : 1;
      do selected = (selected + step) % kModeCount;
      while (view.rows[static_cast<std::size_t>(selected)].disabled);
      continue;
    }
    if (selected == current) return false;
    if (!why[selected].empty()) continue;
    if (selected == kModeCold && !cold.on) {
      const std::string other = SecondLauncher(root);
      std::string text = stub ? "This game is protected by SteamStub. Full emulation gives it gbe_fork's Steam client, "
                                "which may let it start, or may not."
                              : "Full emulation gives the game gbe_fork's Steam client through the ColdClient loader, "
                                "which may let it start, or may not.";
      if (other == "Rockstar")
        text += " This game also starts Rockstar's launcher, which checks ownership with Steam's servers: an emulator "
                "can't pass that check, so it will probably stop there. Only an offline mode of the launcher, if it "
                "offers one, might go on.";
      else if (!other.empty())
        text += " This game also needs " + other + "'s launcher, which doesn't work on OrbisDesk yet: it will probably "
                                                   "stop there.";
      else
        text += " Other launchers or DRM the game needs are not provided.";
      if (recommended != selected)
        text += std::string(" ") + kModeLabels[recommended] + " stays recommended for this game.";
      text += " Triangle switches back at any time.";
      if (!Confirm("FULL EMULATION \xc2\xb7 EXPERIMENTAL", game.name, text, "USE FULL EMULATION", "CANCEL", true, 1))
        continue;
    }
    // one emulation at a time: the API emulator only in its own mode. A restore that fails doesn't block the change:
    // the record goes, and Verify puts Steam's files back (as for Verify itself since 04.89)
    const bool api_on = orbisdesk::EmulatorEnabled(root);
    if (selected != kModeApi && api_on) {
      steam_ui_show(("LAUNCH MODE\n" + game.name + "\nRESTORING THE ORIGINAL STEAM API...\n").c_str(), nullptr);
      std::string failure;
      if (!orbisdesk::RestoreEmulator(root, note, &failure)) {
        const bool forgot = orbisdesk::ForgetEmulator(root);
        note("PWSTEAM launch_mode restore_failed forgot=%d", forgot);
        StorageMessage("LAUNCH MODE\n" + game.name + "\n" + failure +
                       (forgot ? " THE MODE CHANGES ANYWAY; VERIFY & UPDATE PUTS STEAM'S FILES BACK." : ""));
        if (!forgot) return false;
      }
    }
    if (selected == kModeApi && !api_on) {
      ToggleEmulator(game, root, record);
      if (!orbisdesk::EmulatorEnabled(root)) return false;  // it said why
    }
    const bool want = selected >= kModeCold;
    if (want != cold.on) {
      const auto previous = cold;
      cold.on = want;
      const bool saved = WriteColdClient(root, cold);
      note("PWSTEAM coldclient set on=%d app=%u saved=%d second_launcher=%d", want, game.app, saved,
           want && !SecondLauncher(root).empty());
      if (!saved) {
        const bool state_restored = WriteColdClient(root, previous);
        note("PWSTEAM coldclient save_failed state_restored=%d", state_restored);
        StorageMessage("FULL EMULATION\n" + game.name + "\nTHE CHOICE COULD NOT BE SAVED IN THE GAME'S FOLDER.");
      }
    }
    // the choice, kept in the game's folder; then the plan and the shortcuts follow it
    const bool written = WriteText(root + "/" + kLaunchModeFile, std::string(kModeNames[selected]) + "\n", 0644);
    RefreshLaunchPlan(game.app);
    orbisdesk::InstallResult installed;
    installed.ok = true;
    installed.launches = record.launches;
    installed.checks = record.checks;
    const auto links =
        orbisdesk::WriteGameShortcuts(game.app, game.name, installed, root, record.language, "", ReadColdClient(root).on);
    note("PWSTEAM launch_mode set app=%u mode=%s saved=%d shortcut_launcher=%d", game.app, kModeNames[selected], written,
         links.launcher);
    NoteLaunchMode(game.app, root, record);
    return true;
  }
}

std::string ArchName(const std::string& arch) {
  return arch == "x86" ? "32-bit" : arch == "x64" ? "64-bit" : arch.empty() ? "not read" : arch;
}

std::string Basename(const std::string& path) {
  const auto slash = path.find_last_of("/\\");
  return slash == std::string::npos ? path : path.substr(slash + 1);
}

#include "steam_nonsteam_ui.inc.cpp"

// the page's view and the action behind each button
bp::GameView GameViewFor(Shell& shell, const Game& game, std::vector<Action>* actions, orbisdesk::InstalledRecord* out_record) {
  bp::GameView view;
  view.frame = FrameFor(shell, bp::kLibrary);
  view.cover = CoverFor(shell, game);
  const auto& info = Info(shell, game);
  const std::string root = GameRoot(game.app);
  orbisdesk::InstalledRecord record;
  const bool readable = info.installed && !info.offline && orbisdesk::ReadInstallRecord(root, &record);
  if (out_record) *out_record = record;
  const bool other_download = DownloadRunning() && !DownloadingApp(game.app);
  actions->clear();
  auto add = [&](const std::string& label, Action action, bool disabled = false) {
    view.buttons.push_back(label);
    view.disabled.push_back(disabled);
    actions->push_back(action);
  };
  const std::string where = info.drive_name.empty() ? "THIS CONSOLE" : Upper(info.drive_name);
  if (orbisdesk::PendingGameMove(game.app)) {
    view.state = bp::kMovePending;
    view.status = "A MOVE WAS INTERRUPTED \xc2\xb7 CROSS RESUMES IT";
    add("RESUME MOVE", kResumeMove);
    view.note = "The original files stay where they were until the copy is checked.";
  } else if (DownloadingApp(game.app)) {
    view.state = bp::kDownloading;
    download->Sample();
    const int permille = download->Permille();
    view.progress = permille;
    view.status = download->cancel.load() ? "PAUSING..."
                  : download->progress.phase.load() == 0 ? "DOWNLOADING \xc2\xb7 PREPARING..."
                  : "DOWNLOADING \xc2\xb7 " + Percent(permille) +
                        (download->fetching ? " \xc2\xb7 " + Size(static_cast<std::uint64_t>(download->rate)) + "/S" : "");
    add("PAUSE DOWNLOAD", kPauseDownload, download->cancel.load());
    view.facts = {{"INSTALL SIZE", Size(download->plan.install_bytes)},
                  {"INSTALL TO", orbisdesk::StorageWindowsPath(download->root, "")},
                  {"LANGUAGE", LanguageName(download->plan.language.empty() ? "english" : download->plan.language)}};
    view.note = "The download goes on while you use the rest of Steam or the desktop. Pausing keeps what was downloaded.";
  } else if (info.installed && info.offline) {
    view.state = bp::kOffline;
    view.cover.offline = true;
    view.status = "RECONNECT " + where + " TO PLAY, MOVE OR UPDATE THIS GAME";
    add("CHECK DRIVES AGAIN", kCheckDrives);
    view.note = "The game's files stay on the drive. Its shortcuts point to " + info.letter +
                ", so they work again once the drive is back.";
    view.note_warn = true;
  } else if (info.installed) {
    const bool running = (shell.running_app == game.app) || (readable && ExeRunning(record));
    const bool stub = readable && HasSteamStub(record);
    const auto cold = readable ? ReadColdClient(root) : ColdClientState{};
    const auto entry = orbisdesk::ChooseLaunchEntry(record.launches, record.checks, root, record.language, cold.on);
    if (running) {
      view.state = bp::kRunning;
      view.status = "RUNNING \xc2\xb7 STARTED FROM STEAM";
      add(shell.running_app == game.app ? "RESUME GAME" : "RUNNING", kResumeGame, shell.running_app != game.app);
      add("VERIFY & UPDATE", kVerify, true);
      add("MOVE", kMove, true);
      add("UNINSTALL", kUninstall, true);
      view.note = "Close the game before verifying, moving or uninstalling it. The overlay menu's Steam entry brings "
                  "this page back over a running game.";
    } else {
      view.state = bp::kInstalled;
      view.status = "INSTALLED ON " + where + (InOrbisDesk() && entry.ok ? "  \xc2\xb7  CROSS TO PLAY" : "");
      if (InOrbisDesk()) add("PLAY", kPlay, !entry.ok);
      add("VERIFY & UPDATE", kVerify, other_download);
      add("MOVE", kMove);
      add("LANGUAGE", kLanguage, other_download);
      add("UNINSTALL", kUninstall);
      if (cold.on) {
        view.status_chip = "COLDCLIENT \xc2\xb7 EXPERIMENTAL";
        view.note = "Play starts the game through gbe_fork's ColdClient loader with its own Steam client. "
                    "Experimental: it may not start, and other launchers this game needs are not provided.";
      } else if (stub) {
        view.note = "SteamStub DRM: this exe looks for a running Steam client, which OrbisDesk doesn't have. Triangle "
                    "chooses a full emulation launch mode, an experimental way that may let it start.";
        view.note_warn = true;
      } else if (entry.ok) {
        view.note = "Play opens " + Basename(entry.image) +
                    " through the desktop, the same as its Desktop shortcut. The game takes the screen; Big Picture "
                    "comes back when it closes.";
      } else {
        view.note = "No Windows executable of this game can be started: " + entry.skipped + ".";
        view.note_warn = true;
      }
    }
    view.chip = info.drive_name.empty() ? "" : Upper(info.drive_name);
    view.facts.push_back({"SIZE", Size(readable ? record.bytes : info.bytes)});
    view.facts.push_back({"LOCATION", orbisdesk::StorageWindowsPath(root, "")});
    if (readable && !record.executable.empty())
      view.facts.push_back({"STARTS", Basename(entry.ok ? entry.image : record.executable) + " \xc2\xb7 " +
                                          ArchName(entry.ok && entry.index < record.checks.size() ? record.checks[entry.index].arch : record.arch) +
                                          (cold.on && entry.ok ? " \xc2\xb7 through the ColdClient loader" : "")});
    view.facts.push_back({"LANGUAGE", LanguageName(record.language.empty() ? "english" : record.language)});
    if (readable) {
      const int mode = CurrentLaunchMode(root), recommended = RecommendedLaunchMode(record);
      std::string value = kModeLabels[mode];
      if (mode != recommended && UserChoseLaunchMode(root))
        value += std::string("  \xc2\xb7  YOUR CHOICE \xc2\xb7 RECOMMENDED: ") + Upper(kModeLabels[recommended]);
      else if (mode == recommended)
        value += "  \xc2\xb7  RECOMMENDED";
      view.facts.push_back({"LAUNCH MODE", value + "  \xc2\xb7  TRIANGLE CHANGES IT"});
      if (cold.last_seconds >= 0)
        view.facts.push_back({"LAST RUN", "Closed after " + std::to_string(cold.last_seconds) + " s"});
    }
  } else {
    view.state = info.paused ? bp::kPaused : bp::kNotInstalled;
    view.status = info.paused ? "PAUSED \xc2\xb7 CROSS RESUMES THE DOWNLOAD"
                              : "NOT INSTALLED  \xc2\xb7  NEEDS " + Size(game.windows_bytes) + "  \xc2\xb7  CROSS TO INSTALL";
    add(info.paused ? "RESUME DOWNLOAD" : "INSTALL", info.paused ? kResumeDownload : kInstall, other_download);
    add("LANGUAGE", kLanguage, other_download);
    const std::string id = DefaultStorageId();
    std::string to = "Asks every time  \xc2\xb7  SETTINGS CHANGES IT";
    if (!id.empty()) {
      to = id == "internal" ? "Z: Internal" : "The default USB drive";
      for (const auto& drive : shell.drives)
        if (drive.id == id) to = DriveShort(drive);
    }
    view.facts = {{"INSTALL SIZE", Size(game.windows_bytes)}, {"INSTALL TO", to}, {"LANGUAGE", LanguageName(SteamLanguage())},
                  {"WINDOWS", "Windows depots found for this account"}};
    view.note = other_download ? download->name + " is downloading. One download at a time."
                               : "Installing makes a shortcut on the desktop and in Start, and Play here starts it.";
  }
  // the hints follow the state
  if (view.state == bp::kInstalled) {
    view.hints = {{bp::kCross, "", InOrbisDesk() ? "PLAY" : "VERIFY"}, {bp::kNoButton, bp::kLeftRight, "ACTIONS"},
                  {bp::kNoButton, "R1", "MOVE"}, {bp::kSquare, "", "LANGUAGE"}};
    if (readable) view.hints.push_back({bp::kTriangle, "", "LAUNCH MODE"});
    view.hints.push_back({bp::kNoButton, "OPTIONS", "UNINSTALL"});
    view.hints.push_back({bp::kCircle, "", "BACK"});
  } else {
    view.hints = {{bp::kCross, "", view.buttons.empty() ? "" : view.buttons[0]}};
    if (view.buttons.size() > 1) view.hints.push_back({bp::kNoButton, bp::kLeftRight, "ACTIONS"});
    if (view.state == bp::kNotInstalled || view.state == bp::kPaused) view.hints.push_back({bp::kSquare, "", "LANGUAGE"});
    view.hints.push_back({bp::kCircle, "", "BACK"});
  }
  return view;
}

void GameScreen(Shell& shell, const Game& game) {
  if (game.non_steam) {
    NonSteamScreen(shell, game);
    return;
  }
  int focus = 0;
  trace_note("PWSTEAM bigpicture game_page open");
  for (;;) {
    if (CollectDownload(shell.installs, true)) RefreshGame(shell, game);
    std::vector<Action> actions;
    orbisdesk::InstalledRecord record;
    bp::GameView view = GameViewFor(shell, game, &actions, &record);
    if (focus >= static_cast<int>(actions.size())) focus = 0;
    view.focus = focus;
    picker_backdrop = view;
    has_picker_backdrop = true;
    Present([&](bp::Painter& p) { bp::DrawGame(p, view); });
    const unsigned button =
        steam_ui_wait_for(STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE | STEAM_UI_SQUARE | STEAM_UI_OPTIONS |
                              STEAM_UI_R1 | STEAM_UI_LEFT | STEAM_UI_RIGHT,
                          DownloadingApp(game.app) ? 500 : 1000);
    if (!button) continue;
    if (button == STEAM_UI_CIRCLE) break;
    if (button == STEAM_UI_LEFT || button == STEAM_UI_RIGHT) {
      const int n = static_cast<int>(actions.size());
      if (n) focus = (focus + (button == STEAM_UI_RIGHT ? 1 : n - 1)) % n;
      continue;
    }
    Action action;
    if (button == STEAM_UI_CROSS) {
      if (actions.empty() || view.disabled[static_cast<std::size_t>(focus)]) continue;
      action = actions[static_cast<std::size_t>(focus)];
    } else if (button == STEAM_UI_SQUARE) {
      if (view.state != bp::kInstalled && view.state != bp::kNotInstalled && view.state != bp::kPaused) continue;
      action = kLanguage;
    } else if (button == STEAM_UI_R1) {
      if (view.state != bp::kInstalled) continue;
      action = kMove;
    } else if (button == STEAM_UI_OPTIONS) {
      if (view.state != bp::kInstalled) continue;
      action = kUninstall;
    } else {  // triangle: the launch mode
      if (view.state != bp::kInstalled || record.app != game.app) continue;
      LaunchModeMenu(game, view, record);
      continue;
    }
    switch (action) {
      case kPlay: PlayGame(shell, game); break;
      case kResumeGame: WaitForGame(shell); break;
      case kInstall:
      case kResumeDownload:
      case kVerify:
        InstallGame(shell.context, shell.session, shell.library, game, shell.installs, "", false);
        break;
      case kLanguage: InstallGame(shell.context, shell.session, shell.library, game, shell.installs, "", true); break;
      case kMove:
        if (MoveGame(game)) {
          RefreshGame(shell, game);
          PlayGame(shell, game);
        }
        break;
      case kResumeMove: MoveGame(game); break;
      case kUninstall:
        if (UninstallGame(game, record)) focus = 0;
        break;
      case kCheckDrives: break;
      case kPauseDownload:
        if (download) download->cancel = true;
        break;
    }
    RefreshGame(shell, game);
    shell.drives_loaded = false;
  }
  has_picker_backdrop = false;
}

// ---- the power menu and leaving ----
enum ShellExit { kStay, kLeave, kSignOut };

// Restarts the title into `mode` ("desktop" or "bigpicture"); returns only when that failed.
void RestartInto(Shell& shell, const char* mode) {
  if (!pw_hw_restart_mode) {
    StorageMessage("RESTART\nTHIS ORBISDESK CANNOT SWITCH MODES. UPDATE IT.");
    return;
  }
  if (DownloadRunning()) PauseDownload(shell.installs);
  Splash(!strcmp(mode, "desktop") ? "OPENING THE DESKTOP" : "OPENING STEAM BIG PICTURE");
  // the library still loading in the background: stopped before the title restarts under it
  JoinLibraryRefresh(true);
  note("PWSTEAM bigpicture restart to=%s", mode);
  const char* reply = pw_hw_restart_mode(mode);
  note("PWSTEAM bigpicture restart failed reply=%s", reply ? reply : "(none)");
  StorageMessage(std::string("RESTART\nORBISDESK COULD NOT RESTART.\n") + (reply ? reply : ""));
}

// A game still in front: close it with the switch, go back to it, or stay. 0 cancel, 1 go on, 2 back to the game.
int GameStillRunning(Shell& shell, const std::string& label, const std::string& action, const HomeShelves& shelves) {
  const int programs = OpenPrograms();
  if (programs <= 0) return 1;
  std::string name = "A program";
  for (const auto& game : shell.library.games)
    if (game.app == shell.running_app) name = game.name;
  int selected = 1;  // the safe choice
  for (;;) {
    Present([&](bp::Painter& p) {
      bp::MenuView view;
      view.home = HomeViewFor(shell, shelves);
      view.home.shelf = -1;
      view.right_panel = false;
      view.label = label;
      view.title = name + " is still running";
      view.text = "OrbisDesk restarts, which closes the game. Progress the game hasn't saved is lost.";
      view.rows = {action, "RETURN TO THE GAME", "CANCEL"};
      view.selected = selected;
      view.hints = {{bp::kNoButton, bp::kUpDown, "CHOOSE"}, {bp::kCross, "", "CONFIRM"}, {bp::kCircle, "", "CANCEL"}};
      bp::DrawMenu(p, view);
    });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_CROSS | STEAM_UI_CIRCLE);
    if (button == STEAM_UI_UP && selected > 0) --selected;
    else if (button == STEAM_UI_DOWN && selected < 2) ++selected;
    else if (button == STEAM_UI_CIRCLE) return 0;
    else if (button == STEAM_UI_CROSS) return selected == 0 ? 1 : selected == 1 ? 2 : 0;
  }
}

// Leaving the client with a download running pauses it, after the user agrees.
bool LeaveWithDownload(Shell& shell) {
  if (!DownloadRunning()) return true;
  if (!Confirm("DOWNLOADS", download->name + " is downloading",
               "Leaving Steam pauses the download. What was downloaded stays, and the next install resumes it.",
               "PAUSE AND LEAVE", "STAY", false, 1))
    return false;
  PauseDownload(shell.installs);
  return true;
}

ShellExit PowerMenu(Shell& shell) {
  const HomeShelves shelves = Shelves(shell);
  std::vector<std::string> rows;
  std::vector<int> icons;
  enum { kExitDesktop, kBackToDesktop, kCloseTitle, kExitClient, kCancel };
  std::vector<int> ids;
  if (InOrbisDesk() && shell.big_picture) rows.push_back("Exit to desktop"), icons.push_back(SD_ICON_MONITOR), ids.push_back(kExitDesktop);
  if (InOrbisDesk() && !shell.big_picture) rows.push_back("Back to the desktop"), icons.push_back(SD_ICON_MONITOR), ids.push_back(kBackToDesktop);
  if (InOrbisDesk()) rows.push_back("Close OrbisDesk"), icons.push_back(SD_ICON_POWER), ids.push_back(kCloseTitle);
  if (!InOrbisDesk()) rows.push_back("Exit"), icons.push_back(SD_ICON_POWER), ids.push_back(kExitClient);
  rows.push_back("Cancel"), icons.push_back(-1), ids.push_back(kCancel);
  int selected = 0;
  for (;;) {
    Present([&](bp::Painter& p) {
      bp::MenuView view;
      view.home = HomeViewFor(shell, shelves);
      view.home.frame.power_focus = true;
      view.home.shelf = -1;
      view.label = "POWER";
      view.rows = rows;
      view.icons = icons;
      view.selected = selected;
      view.note = InOrbisDesk() ? "Close OrbisDesk goes back to the PS4 home screen." : "";
      view.hints = {{bp::kNoButton, bp::kUpDown, "CHOOSE"}, {bp::kCross, "", "SELECT"}, {bp::kCircle, "", "CLOSE"}};
      bp::DrawMenu(p, view);
    });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_OPTIONS);
    if (button == STEAM_UI_UP && selected > 0) --selected;
    else if (button == STEAM_UI_DOWN && selected + 1 < static_cast<int>(rows.size())) ++selected;
    else if (button == STEAM_UI_CIRCLE || button == STEAM_UI_OPTIONS) return kStay;
    else if (button == STEAM_UI_CROSS) {
      const int id = ids[static_cast<std::size_t>(selected)];
      note("PWSTEAM bigpicture power choice=%d", id);
      if (id == kCancel) return kStay;
      if (id == kBackToDesktop || id == kExitClient) return LeaveWithDownload(shell) ? kLeave : kStay;
      if (id == kExitDesktop) {
        const int go = GameStillRunning(shell, "EXIT TO DESKTOP", "CLOSE THE GAME AND EXIT TO DESKTOP", shelves);
        if (go == 2) {
          WaitForGame(shell);
          return kStay;
        }
        if (go == 1) RestartInto(shell, "desktop");
        return kStay;
      }
      if (id == kCloseTitle) {
        if (!Confirm("POWER", "Close OrbisDesk",
                     "OrbisDesk closes and the PS4 home screen comes back. Open programs close without saving" +
                         std::string(DownloadRunning() ? " and the download pauses." : "."),
                     "CLOSE ORBISDESK", "CANCEL", true, 1))
          return kStay;
        if (DownloadRunning()) PauseDownload(shell.installs);
        note("PWSTEAM bigpicture close_title");
        if (pw_hw_close_title) pw_hw_close_title();
        StorageMessage("POWER\nORBISDESK COULD NOT CLOSE ITSELF. USE THE PS BUTTON.");
        return kStay;
      }
    }
  }
}

// O on a tab: inside the desktop it closes the client; in Big Picture it is the power menu
ShellExit Back(Shell& shell) {
  if (shell.big_picture) return PowerMenu(shell);
  return LeaveWithDownload(shell) ? kLeave : kStay;
}

// ---- the tabs ----
void DrawTab(Shell& shell) {
  switch (shell.tab) {
    case bp::kHome: {
      const auto shelves = Shelves(shell);
      auto view = HomeViewFor(shell, shelves);
      const int n = static_cast<int>(shell.home_shelf == 0 ? shelves.first.size() : shelves.second.size());
      if (shell.home_index[shell.home_shelf] >= n) shell.home_index[shell.home_shelf] = n ? n - 1 : 0;
      view.index = shell.home_index[shell.home_shelf];
      Present([&](bp::Painter& p) { bp::DrawHome(p, view); });
      break;
    }
    case bp::kLibrary: {
      const auto views = Views(shell);
      if (shell.lib_view >= static_cast<int>(views.names.size())) shell.lib_view = 1;
      bp::LibraryView view;
      view.frame = FrameFor(shell, bp::kLibrary);
      std::size_t non_steam = 0;
      for (const auto& game : shell.library.games) non_steam += game.non_steam;
      view.subtitle = std::to_string(shell.library.games.size() - non_steam) + " GAMES WITH WINDOWS CONTENT \xc2\xb7 " +
                      std::to_string(shell.library.owned) + " OWNED" +
                      (non_steam ? " \xc2\xb7 " + std::to_string(non_steam) + " NON-STEAM" : "");
      view.add_tile = AddTileShown(shell, views);
      for (std::size_t i = 0; i < views.names.size(); ++i)
        view.views.push_back({views.names[i], static_cast<int>(views.games[i].size())});
      view.separator = views.separator;
      view.view = shell.lib_view;
      view.views_focus = shell.lib_views_focus;
      const auto& list = views.games[static_cast<std::size_t>(shell.lib_view)];
      const int cells = static_cast<int>(list.size()) + (view.add_tile ? 1 : 0);
      if (shell.lib_index >= cells) shell.lib_index = cells ? cells - 1 : 0;
      // covers for the twelve shown only
      const int first = std::max(0, shell.lib_index / 6 - 1) * 6;
      for (int i = 0; i < static_cast<int>(list.size()); ++i) {
        if (i >= first && i < first + 12) view.games.push_back(CoverFor(shell, *list[static_cast<std::size_t>(i)]));
        else {
          bp::Cover cover;
          cover.app = list[static_cast<std::size_t>(i)]->app;
          cover.name = list[static_cast<std::size_t>(i)]->name;
          view.games.push_back(cover);
        }
      }
      view.index = shell.lib_index;
      view.sort = SortName(shell.sort);
      view.empty = shell.lib_view == 0   ? "NO GAME IS INSTALLED YET."
                   : shell.lib_view == 3 ? "NO FAVORITES YET. SQUARE ON A GAME MAKES IT ONE."
                   : shell.lib_view == 2 ? "EVERY GAME IS INSTALLED."
                                         : "NO GAMES WITH WINDOWS CONTENT.";
      Present([&](bp::Painter& p) { bp::DrawLibrary(p, view); });
      break;
    }
    case bp::kDownloads: {
      bp::DownloadsView view;
      view.frame = FrameFor(shell, bp::kDownloads);
      int paused = 0;
      if (download) {
        download->Sample();
        view.active = true;
        for (const auto& game : shell.library.games)
          if (game.app == download->app) view.current.cover = CoverFor(shell, game);
        view.current.name = download->name;
        view.current.detail = "TO " + download->drive + " \xc2\xb7 " + orbisdesk::StorageWindowsPath(download->root, "");
        view.permille = download->Permille();
        const auto total = download->progress.total_bytes.load(), placed = download->progress.done_bytes.load();
        const int phase = download->progress.phase.load();
        view.percent_line = phase == 0 ? "PREPARING..." : phase == 2 ? "CHECKING THE EXECUTABLE..."
                            : Percent(view.permille) + "  \xc2\xb7  " + Size(placed) + " OF " + Size(total);
        if (download->fetching && download->rate > 0) {
          const auto left = total > placed ? total - placed : 0;
          const auto minutes = static_cast<std::uint64_t>(static_cast<double>(left) / download->rate / 60.0) + 1;
          view.speed_line = Size(static_cast<std::uint64_t>(download->rate)) + "/S  \xc2\xb7  ABOUT " + std::to_string(minutes) +
                            " MIN LEFT";
        } else if (phase == 1) {
          view.speed_line = "VERIFYING WHAT IS ALREADY ON THE CONSOLE";
        }
        if (download->cancel.load()) view.state_line = "PAUSING...";
        else if (download->done.load()) view.state_line = "FINISHING...";
      }
      for (const auto& game : shell.library.games) {
        const auto& info = Info(shell, game);
        if (!info.paused || DownloadingApp(game.app)) continue;
        view.paused.push_back({CoverFor(shell, game), game.name, "PAUSED", "CROSS RESUMES WHERE IT STOPPED"});
        ++paused;
      }
      for (const auto& f : finished_downloads) view.finished.push_back({bp::Cover{}, f.name, f.detail, ""});
      view.subtitle = std::string(download ? "1 ACTIVE" : "NONE ACTIVE") + " \xc2\xb7 " + std::to_string(paused) + " PAUSED";
      const int rows = (view.active ? 1 : 0) + static_cast<int>(view.paused.size() + view.finished.size());
      if (shell.dl_selected >= rows) shell.dl_selected = rows ? rows - 1 : 0;
      view.selected = shell.dl_selected;
      Present([&](bp::Painter& p) { bp::DrawDownloads(p, view); });
      break;
    }
    case bp::kStorage: {
      if (!shell.drives_loaded) LoadDrives(shell);
      bp::StorageView view;
      view.frame = FrameFor(shell, bp::kStorage);
      int installed = 0;
      for (const auto& [app, info] : shell.info) installed += info.installed;
      view.subtitle = std::to_string(shell.drives.size()) + (shell.drives.size() == 1 ? " DRIVE" : " DRIVES") + " \xc2\xb7 " +
                      std::to_string(installed) + " GAMES INSTALLED";
      if (shell.st_drive >= static_cast<int>(shell.drives.size())) shell.st_drive = 0;
      std::vector<std::vector<const Game*>> games(shell.drives.size());
      for (std::size_t d = 0; d < shell.drives.size(); ++d)
        for (const auto& game : shell.library.games) {
          const auto& info = Info(shell, game);
          if (info.installed && !info.offline && info.library == shell.drives[d].library) games[d].push_back(&game);
        }
      for (std::size_t d = 0; d < shell.drives.size(); ++d)
        view.drives.push_back({DriveShort(shell.drives[d]), static_cast<int>(games[d].size())});
      view.drive = shell.st_drive;
      view.games_focus = shell.st_games_focus;
      if (!shell.drives.empty()) {
        const auto& drive = shell.drives[static_cast<std::size_t>(shell.st_drive)];
        const auto& list = games[static_cast<std::size_t>(shell.st_drive)];
        view.name = DriveName(drive);
        if (!drive.id.empty() && drive.id == DefaultStorageId()) view.chip = "DEFAULT INSTALL LOCATION";
        view.paths = orbisdesk::StorageWindowsPath(drive.library, "") + " \xc2\xb7 " + drive.library;
        std::uint64_t steam = 0;
        for (const auto* game : list) {
          const auto bytes = Info(shell, *game).bytes;
          steam += bytes;
          view.games.push_back({game->name, Size(bytes)});
        }
        const auto total = drive.free.total_bytes, free = drive.free.bytes;
        if (drive.free.ok && total) {
          const auto used = total > free ? total - free : 0;
          view.steam_permille = static_cast<int>(std::min<std::uint64_t>(1000, steam * 1000 / total));
          view.other_permille = static_cast<int>(std::min<std::uint64_t>(1000, (used > steam ? used - steam : 0) * 1000 / total));
          view.other_label = "OTHER FILES " + Size(used > steam ? used - steam : 0);
          view.free_label = Size(free) + " FREE OF " + Size(total);
        } else {
          view.other_label = "OTHER FILES UNKNOWN";
          view.free_label = drive.free.ok ? Size(free) + " FREE" : "FREE SPACE UNKNOWN";
        }
        view.steam_label = "STEAM GAMES " + Size(steam);
        if (shell.st_game >= static_cast<int>(list.size())) shell.st_game = list.empty() ? 0 : static_cast<int>(list.size()) - 1;
        view.game = shell.st_game;
        view.note = drive.external ? "Unplugging this drive marks its games DRIVE OFFLINE until it is back. Nothing is forgotten."
                                   : "The console's own storage. Square makes a drive the default install location.";
      }
      Present([&](bp::Painter& p) { bp::DrawStorage(p, view); });
      break;
    }
    case bp::kSettings: {
      if (!shell.drives_loaded) LoadDrives(shell);
      bp::SettingsView view;
      view.frame = FrameFor(shell, bp::kSettings);
      view.subtitle = shell.session.account_name.empty() ? "SIGNED IN" : "SIGNED IN AS " + shell.session.account_name;
      const std::string id = DefaultStorageId();
      std::string location = "ASK EVERY TIME";
      if (!id.empty()) {
        location = id == "internal" ? "Z: INTERNAL" : "USB DRIVE (NOT CONNECTED)";
        for (const auto& drive : shell.drives)
          if (drive.id == id) location = Upper(DriveShort(drive));
      }
      std::vector<int> kinds;  // 0 startup, 1 location, 2 language, 3 switch, 4 account, 5 non-Steam, 6 shortcuts
      if (InOrbisDesk()) {
        view.rows.push_back({"Start OrbisDesk in", StartupBigPicture() ? "STEAM BIG PICTURE" : "DESKTOP", true, false});
        kinds.push_back(0);
      }
      view.rows.push_back({"Install location", location, true, false});
      kinds.push_back(1);
      view.rows.push_back({"Steam language", LanguageName(SteamLanguage()), false, false});
      kinds.push_back(2);
      if (InOrbisDesk()) {
        view.rows.push_back({shell.big_picture ? "Exit to desktop" : "Restart in Steam Big Picture", "CROSS", false, true});
        kinds.push_back(3);
        view.rows.push_back({"Add a non-Steam game", "CROSS", false, true});
        kinds.push_back(5);
        view.rows.push_back({"Create shortcuts", "CROSS", false, true});
        kinds.push_back(6);
      }
      view.rows.push_back({"Steam account", shell.session.account_name.empty() ? "SIGN OUT" : shell.session.account_name, false, false});
      kinds.push_back(4);
      if (shell.set_row >= static_cast<int>(view.rows.size())) shell.set_row = 0;
      view.selected = shell.set_row;
      switch (kinds[static_cast<std::size_t>(shell.set_row)]) {
        case 0:
          if (StartupBigPicture()) {
            view.lead = "OrbisDesk opens Steam Big Picture when it starts.";
            view.detail = "The desktop is one step away under Exit to desktop. If Big Picture can't open, OrbisDesk "
                          "starts the desktop instead.";
          } else {
            view.lead = "OrbisDesk opens the Windows desktop when it starts.";
            view.detail = "Big Picture stays in Start, and the Desktop's \"Open Steam Client\" keeps working over the desktop.";
          }
          view.saved = "Applies from the next start. Saved on the console in /data/orbisdesk/startup.ini.";
          break;
        case 1:
          view.lead = "Where new installs go.";
          view.detail = "Ask every time shows the drives for each install. With a drive chosen, installs go there without "
                        "asking while it is connected; when it is not, the drives are shown.";
          break;
        case 2:
          view.lead = "The language new installs ask Steam for.";
          view.detail = "A game without it installs in English. An installed game keeps its own: Language on its page changes it.";
          break;
        case 3:
          view.lead = shell.big_picture ? "OrbisDesk restarts into the Windows desktop." : "OrbisDesk restarts into Steam Big Picture.";
          view.detail = "Open programs close. The startup setting above doesn't change.";
          break;
        case 5:
          view.lead = "Add a Windows game already on the console to the library.";
          view.detail = "Games found in Desktop and Start shortcuts and in game folders are listed, or browse for the exe. "
                        "The list stays on this console; nothing is sent to Steam.";
          break;
        case 6:
          view.lead = "Make the Desktop and Start menu shortcuts of every installed Steam game again.";
          view.detail = "For OrbisDesk installed again over kept games: one step for all of them, instead of Verify on "
                        "each. SteamStub games' shortcuts start them as Play does.";
          break;
        default:
          view.lead = "Signing out deletes the saved Steam session from this console.";
          view.detail = "Installed games and their shortcuts stay. Signing in again uses the Steam app on your phone.";
      }
      Present([&](bp::Painter& p) { bp::DrawSettings(p, view); });
      break;
    }
  }
}

// one button on the tab in front; kLeave or kSignOut to end the client
ShellExit TabButton(Shell& shell, unsigned button) {
  const unsigned directions = STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_LEFT | STEAM_UI_RIGHT;
  switch (shell.tab) {
    case bp::kHome: {
      const auto shelves = Shelves(shell);
      const auto& list = shell.home_shelf == 0 ? shelves.first : shelves.second;
      int& index = shell.home_index[shell.home_shelf];
      if (button == STEAM_UI_UP) shell.home_shelf = 0;
      else if (button == STEAM_UI_DOWN && !shelves.second.empty()) shell.home_shelf = 1;
      else if (button == STEAM_UI_LEFT && index > 0) --index;
      else if (button == STEAM_UI_RIGHT && index + 1 < static_cast<int>(list.size())) ++index;
      else if (button == STEAM_UI_CROSS && index < static_cast<int>(list.size())) GameScreen(shell, *list[static_cast<std::size_t>(index)]);
      else if (button == STEAM_UI_SQUARE && index < static_cast<int>(list.size())) {
        const auto app = list[static_cast<std::size_t>(index)]->app;
        if (!shell.favorites.erase(app)) shell.favorites.insert(app);
        SaveFavorites(shell.favorites);
      } else if (button == STEAM_UI_CIRCLE) return Back(shell);
      return kStay;
    }
    case bp::kLibrary: {
      const auto views = Views(shell);
      const auto& list = views.games[static_cast<std::size_t>(std::min<int>(shell.lib_view, static_cast<int>(views.games.size()) - 1))];
      const int games_n = static_cast<int>(list.size());
      const bool tile = AddTileShown(shell, views);
      const int n = games_n + (tile ? 1 : 0);  // the add tile is the last cell
      if (shell.lib_views_focus) {
        if (button == STEAM_UI_UP && shell.lib_view > 0) --shell.lib_view, shell.lib_index = 0;
        else if (button == STEAM_UI_DOWN && shell.lib_view + 1 < static_cast<int>(views.names.size())) ++shell.lib_view, shell.lib_index = 0;
        else if ((button == STEAM_UI_RIGHT || button == STEAM_UI_CROSS) && n) shell.lib_views_focus = false;
        else if (button == STEAM_UI_CIRCLE) return Back(shell);
      } else {
        int& i = shell.lib_index;
        if (button == STEAM_UI_LEFT) {
          if (i % 6 == 0) shell.lib_views_focus = true;
          else --i;
        } else if (button == STEAM_UI_RIGHT && i + 1 < n) ++i;
        else if (button == STEAM_UI_UP && i >= 6) i -= 6;
        else if (button == STEAM_UI_DOWN && i + 6 < n) i += 6;
        else if (button == STEAM_UI_DOWN && i / 6 < (n - 1) / 6) i = n - 1;
        else if (button == STEAM_UI_CROSS && tile && i == games_n) AddNonSteam(shell);
        else if (button == STEAM_UI_CROSS && i < games_n) GameScreen(shell, *list[static_cast<std::size_t>(i)]);
        else if (button == STEAM_UI_SQUARE && i < games_n) {
          const auto app = list[static_cast<std::size_t>(i)]->app;
          if (!shell.favorites.erase(app)) shell.favorites.insert(app);
          SaveFavorites(shell.favorites);
        } else if (button == STEAM_UI_TRIANGLE) {
          shell.sort = (shell.sort + 1) % 3;
          shell.lib_index = 0;
        } else if (button == STEAM_UI_CIRCLE) shell.lib_views_focus = true;
      }
      return kStay;
    }
    case bp::kDownloads: {
      std::vector<const Game*> rows;  // the active one, the paused ones, the finished ones
      if (download)
        for (const auto& game : shell.library.games)
          if (game.app == download->app) rows.push_back(&game);
      if (download && rows.empty()) rows.push_back(nullptr);
      for (const auto& game : shell.library.games)
        if (Info(shell, game).paused && !DownloadingApp(game.app)) rows.push_back(&game);
      for (const auto& f : finished_downloads) {
        const Game* found = nullptr;
        for (const auto& game : shell.library.games)
          if (game.app == f.app) found = &game;
        rows.push_back(found);
      }
      const int n = static_cast<int>(rows.size());
      int& s = shell.dl_selected;
      if (button == STEAM_UI_UP && s > 0) --s;
      else if (button == STEAM_UI_DOWN && s + 1 < n) ++s;
      else if (button == STEAM_UI_CROSS && s < n && rows[static_cast<std::size_t>(s)]) GameScreen(shell, *rows[static_cast<std::size_t>(s)]);
      else if (button == STEAM_UI_SQUARE) {
        if (DownloadRunning()) download->cancel = true;
        else if (s < n && rows[static_cast<std::size_t>(s)] && Info(shell, *rows[static_cast<std::size_t>(s)]).paused) {
          InstallGame(shell.context, shell.session, shell.library, *rows[static_cast<std::size_t>(s)], shell.installs, "", false);
          RefreshGame(shell, *rows[static_cast<std::size_t>(s)]);
        }
      } else if (button == STEAM_UI_CIRCLE) return Back(shell);
      return kStay;
    }
    case bp::kStorage: {
      if (!shell.drives_loaded) LoadDrives(shell);
      const int drives = static_cast<int>(shell.drives.size());
      std::vector<const Game*> list;
      if (shell.st_drive < drives)
        for (const auto& game : shell.library.games) {
          const auto& info = Info(shell, game);
          if (info.installed && !info.offline && info.library == shell.drives[static_cast<std::size_t>(shell.st_drive)].library)
            list.push_back(&game);
        }
      const int n = static_cast<int>(list.size());
      if (button == STEAM_UI_TRIANGLE) {
        LoadDrives(shell);
        Refresh(shell);
      } else if (button == STEAM_UI_SQUARE && shell.st_drive < drives) {
        auto drive = shell.drives[static_cast<std::size_t>(shell.st_drive)];
        std::string error;
        if (orbisdesk::PrepareGameStorage(&drive, &error)) {
          SaveDefaultStorageId(drive.id == DefaultStorageId() ? "" : drive.id);
          shell.drives[static_cast<std::size_t>(shell.st_drive)].id = drive.id;
        } else {
          StorageMessage("STORAGE\n" + error);
        }
      } else if (shell.st_games_focus) {
        if (button == STEAM_UI_UP && shell.st_game > 0) --shell.st_game;
        else if (button == STEAM_UI_DOWN && shell.st_game + 1 < n) ++shell.st_game;
        else if (button == STEAM_UI_LEFT || button == STEAM_UI_CIRCLE) shell.st_games_focus = false;
        else if (button == STEAM_UI_CROSS && shell.st_game < n) GameScreen(shell, *list[static_cast<std::size_t>(shell.st_game)]);
      } else {
        if (button == STEAM_UI_UP && shell.st_drive > 0) --shell.st_drive, shell.st_game = 0;
        else if (button == STEAM_UI_DOWN && shell.st_drive + 1 < drives) ++shell.st_drive, shell.st_game = 0;
        else if ((button == STEAM_UI_RIGHT || button == STEAM_UI_CROSS) && n) shell.st_games_focus = true;
        else if (button == STEAM_UI_CIRCLE) return Back(shell);
      }
      return kStay;
    }
    case bp::kSettings: {
      std::vector<int> kinds;
      if (InOrbisDesk()) kinds.push_back(0);
      kinds.push_back(1);
      kinds.push_back(2);
      if (InOrbisDesk()) kinds.push_back(3), kinds.push_back(5), kinds.push_back(6);
      kinds.push_back(4);
      const int n = static_cast<int>(kinds.size());
      int& row = shell.set_row;
      const int kind = kinds[static_cast<std::size_t>(std::min(row, n - 1))];
      if (button == STEAM_UI_UP && row > 0) --row;
      else if (button == STEAM_UI_DOWN && row + 1 < n) ++row;
      else if (button == STEAM_UI_CIRCLE) return Back(shell);
      else if (kind == 0 && (button & (STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_CROSS))) {
        if (!SaveStartupMode(!StartupBigPicture())) StorageMessage("SETTINGS\nTHE STARTUP MODE COULD NOT BE SAVED.");
      } else if (kind == 1 && (button & (STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_CROSS))) {
        std::vector<std::string> ids = {""};
        for (const auto& drive : shell.drives) ids.push_back(drive.id.empty() ? "?" + drive.library : drive.id);
        const std::string current = DefaultStorageId();
        int at = 0;
        for (std::size_t i = 0; i < ids.size(); ++i)
          if (ids[i] == current) at = static_cast<int>(i);
        const int count = static_cast<int>(ids.size());
        at = (at + (button == STEAM_UI_LEFT ? count - 1 : 1)) % count;
        std::string id = ids[static_cast<std::size_t>(at)];
        if (!id.empty() && id[0] == '?') {
          // a USB drive without its library id yet: preparing it writes one
          for (auto& drive : shell.drives)
            if ("?" + drive.library == id) {
              std::string error;
              if (orbisdesk::PrepareGameStorage(&drive, &error)) id = drive.id;
              else {
                StorageMessage("STORAGE\n" + error);
                id.clear();
              }
            }
        }
        SaveDefaultStorageId(id);
      } else if (kind == 2 && button == STEAM_UI_CROSS) {
        const std::string current = SteamLanguage();
        const std::string chosen = ChooseLanguage(
            "STEAM LANGUAGE\nNEW INSTALLS ASK STEAM FOR THIS LANGUAGE. A GAME WITHOUT IT INSTALLS IN ENGLISH. "
            "AN INSTALLED GAME KEEPS ITS OWN: LANGUAGE ON ITS PAGE CHANGES IT.\n",
            kSteamLanguages, current, "USE THIS LANGUAGE");
        if (!chosen.empty() && chosen != current) {
          const bool saved = WriteText(kSteamLanguageFile, chosen + "\n", 0644);
          note("PWSTEAM steam_language set=%s saved=%d errno=%d", chosen.c_str(), saved, saved ? 0 : errno);
          if (!saved) StorageMessage("STEAM LANGUAGE\nCOULD NOT SAVE THE LANGUAGE.");
        }
      } else if (kind == 3 && button == STEAM_UI_CROSS) {
        if (shell.big_picture) {
          const int go = GameStillRunning(shell, "EXIT TO DESKTOP", "CLOSE THE GAME AND EXIT TO DESKTOP", Shelves(shell));
          if (go == 2) WaitForGame(shell);
          else if (go == 1) RestartInto(shell, "desktop");
        } else if (Confirm("STEAM BIG PICTURE", "Restart in Steam Big Picture",
                           "The desktop closes and OrbisDesk restarts into Steam Big Picture. Open programs close without "
                           "saving.",
                           "RESTART", "CANCEL", true, 1)) {
          RestartInto(shell, "bigpicture");
        }
      } else if (kind == 5 && button == STEAM_UI_CROSS) {
        AddNonSteam(shell);
      } else if (kind == 6 && button == STEAM_UI_CROSS) {
        CreateAllShortcuts(shell);
      } else if (kind == 4 && button == STEAM_UI_CROSS) {
        if (DownloadRunning()) StorageMessage("SIGN OUT\nPAUSE THE DOWNLOAD FIRST.");
        else if (ConfirmSignOut()) return kSignOut;
      }
      (void)directions;
      return kStay;
    }
  }
  return kStay;
}

// The covers, installed games first.
void StartCovers(Shell& shell) {
  std::vector<std::uint32_t> apps;
  for (const auto& game : shell.library.games)
    if (!game.non_steam && Info(shell, game).installed) apps.push_back(game.app);
  for (const auto& game : shell.library.games)
    if (!game.non_steam && !Info(shell, game).installed) apps.push_back(game.app);
  auto http = std::make_shared<steam::HttpClient>(shell.context.ca);
  shell.covers.Start(
      kArtDir, apps,
      [http](const std::string& url, std::vector<std::uint8_t>* body, const std::atomic<bool>& cancel) -> long {
        steam::HttpRequest request;
        request.url = url;
        request.timeout_ms = 15'000;
        request.max_response_bytes = 4 << 20;
        auto response = http->Perform(request, cancel);
        if (!response.ok()) return 0;
        if (response.status_code == 200) *body = std::move(response.body);
        return response.status_code;
      },
      [] { steam_ui_poke(); }, note);
}

// The background load came back: a complete one replaces the cached list (a game bought since shows
// up, one gone leaves), an incomplete one leaves it. Only here, between screens, where nothing holds
// a reference into the old list.
void TakeLibraryRefresh(Shell& shell) {
  if (!library_refresh || !(library_refresh->done.load() || library_refresh->joined)) return;
  const bool complete = JoinLibraryRefresh(false);
  if (complete) {
    std::set<std::uint32_t> before, after;
    for (const auto& game : shell.library.games)
      if (!game.non_steam) before.insert(game.app);
    for (const auto& game : library_refresh->result.games) after.insert(game.app);
    shell.library = std::move(library_refresh->result);
    MergeNonSteam(&shell.library);
    shell.info.clear();
    Refresh(shell);
    if (before != after) StartCovers(shell);
    trace_note("PWSTEAM library refresh applied games=%zu changed=%d", shell.library.games.size(), before != after);
  }
  library_refresh.reset();
  steam_ui_poke();
}

// The client's screens. True when the user signed out.
bool BigPictureShell(Context& context, const playden::StoredSession& session, Library& library, Installs* installs) {
  MergeNonSteam(&library);
  Shell shell(context, session, library, installs);
  shell.big_picture = BigPictureBoot();
  shell.favorites = LoadFavorites();
  shell.played = LoadPlayed();
  background_installs = true;
  picker_default_id = DefaultStorageId;
  steam_ui_started();  // past network, session and library: a Big Picture start that worked
  ClaimSteamRegistration(0, false);
  trace_note("PWSTEAM bigpicture open mode=%s games=%zu favorites=%zu", shell.big_picture ? "bigpicture" : "client",
       library.games.size(), shell.favorites.size());
  Refresh(shell);
  StartCovers(shell);
  // Big Picture's own start: the client in front of a desktop without a shell
  if (shell.big_picture) shell.tab = bp::kHome;
  ShellExit exit = kStay;
  const unsigned all = STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE | STEAM_UI_SQUARE | STEAM_UI_UP | STEAM_UI_DOWN |
                       STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_L1 | STEAM_UI_R1 | STEAM_UI_OPTIONS;
  while (exit == kStay) {
    if (CollectDownload(installs, true)) Refresh(shell);
    TakeLibraryRefresh(shell);
    if (shell.nonsteam_dirty) {
      shell.nonsteam_dirty = false;
      MergeNonSteam(&shell.library);
      shell.info.clear();
      Refresh(shell);
    }
    // the overlay or Start asked for Steam while it was already up: nothing to do
    steam_ui_show_requested();
    DrawTab(shell);
    const unsigned button = steam_ui_wait_for(all, download ? 1000 : 5000);
    if (!button) continue;
    if (button == STEAM_UI_L1 || button == STEAM_UI_R1) {
      shell.tab = (shell.tab + (button == STEAM_UI_R1 ? 1 : bp::kTabs - 1)) % bp::kTabs;
      if (shell.tab == bp::kStorage || shell.tab == bp::kSettings) shell.drives_loaded = false;
      if (shell.tab == bp::kDownloads || shell.tab == bp::kHome) Refresh(shell);
      trace_note("PWSTEAM bigpicture tab=%d", shell.tab);
      continue;
    }
    if (button == STEAM_UI_OPTIONS) {
      exit = PowerMenu(shell);
      continue;
    }
    exit = TabButton(shell, button);
  }
  if (exit == kSignOut && DownloadRunning()) PauseDownload(installs);
  shell.covers.Stop();
  background_installs = false;
  picker_default_id = nullptr;
  trace_note("PWSTEAM bigpicture close reason=%s", exit == kSignOut ? "sign_out" : "leave");
  return exit == kSignOut;
}
