// SPDX-License-Identifier: GPL-3.0-or-later
// The Steam client title (ORBS00001) from S4 on (docs/STEAM_S4.md): S3's sign-in, then the user's
// library as a list to install from. native/steam/steam_s3.cpp stays as S3 was accepted.
// The user signs in on the console, scanning the code with the Steam app on their phone; this title
// never sees a password. Steps, each logged as a PWSTEAM line:
//   1. clock, CA bundle and the network (as S2);
//   2. the screen and the pad (native/steam/steam_ui.c);
//   3. once per console, a notice that this is an unofficial client the user accepts with X;
//   4. a saved session (native/steam/steam_session.cpp) is restored: kept as is while its access
//      token lasts, renewed through the CM otherwise; a revoked one is deleted;
//   5. without one, Playden's AuthClient signs in by QR code (IAuthenticationService); the session is
//      saved sealed, by the user's choice ("stay signed in");
//   6. the owned games (GetOwnedGames), the account's licenses (CM) and the PICS app info of each game.
//      The list goes to a file of its own, never to the log;
//   7. the games with Windows content as a list (up and down, X installs, O exits, triangle signs out);
//      an install (native/steam/steam_install.cpp) shows its plan, waits for X, then its progress
//      (O pauses it) and its outcome.
// The log carries event names, counts and Steam's error codes only: no account name, Steam ID,
// token, sign-in link or game. A line holding any of this run's secrets is withheld whole.
// Host: steam_client; buttons from stdin ("x", "o", "t", "u", "d").
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <strings.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include <mbedtls/x509_crt.h>

#include "steam/backend/app_info.h"
#include "steam/backend/auth_client.h"
#include "steam/backend/cm_client.h"
#include "steam/backend/http_client.h"
#include "steam/backend/library_client.h"
#include "steam/backend/native_network.h"
#include "steam/backend/ws_client.h"
#include "steam_install.h"
#include "../../platform/ps4/pw_trace.h"  // alpha-1: the trace switch (weak: on when not linked into OrbisDesk)
#include "steam_session.h"
#include "steam_emu.h"
#include "steam_shortcut.h"
#include "steam_ui.h"

#if defined(STEAM_UI_HOSTED)
// Inside OrbisDesk's title: the same data as the standalone title (session, library, games), the CA
// bundle and gbe_fork's DLLs from the Wine prefix (C:\orbis\steam), which the title's upload carries.
#include <orbis/libkernel.h>
#define STEAM_LOG "/data/orbisdesk/steam-client.txt"
#define STEAM_LOG_PREVIOUS "/data/orbisdesk/steam-client.prev.txt"
#define CA_BUNDLE "/data/wine-prefix/drive_c/orbis/steam/cacert.pem"
#define DATA_DIR "/data/orbisdesk/steam"
#define LIBRARY_FILE "/data/orbisdesk/steam-library.txt"
#define GAMES_DIR "/data/orbisdesk/steam-games"
#elif !defined(STEAM_HOST)
#include <orbis/Sysmodule.h>
#include <orbis/libkernel.h>
#include "../../platform/ps4/pw_brand.h"
#define STEAM_LOG "/data/orbisdesk/steam-client.txt"
#define STEAM_LOG_PREVIOUS "/data/orbisdesk/steam-client.prev.txt"
#define CA_BUNDLE "/app0/assets/misc/cacert.pem"
#define DATA_DIR "/data/orbisdesk/steam"
#define LIBRARY_FILE "/data/orbisdesk/steam-library.txt"
#define GAMES_DIR "/data/orbisdesk/steam-games"
#else
#define STEAM_LOG "steam-client.txt"
#define STEAM_LOG_PREVIOUS "steam-client.prev.txt"
#define CA_BUNDLE "cacert.pem"
#define DATA_DIR "steam-data"
#define LIBRARY_FILE "steam-library.txt"
#define GAMES_DIR "steam-games"
#endif
#ifdef STEAM_UI_HOSTED
#define CLIENT_VERSION "hosted"
#else
#define CLIENT_VERSION "S4"
#endif

namespace steam = playden::steam;
namespace {

int log_fd = -1;
std::mutex secrets_mutex;
std::vector<std::string> secrets;  // this run's account name and tokens: no log line may hold them

void Secret(const std::string& value) {
  if (value.size() < 3) return;
  std::lock_guard<std::mutex> lock(secrets_mutex);
  secrets.push_back(value);
}

void ForgetSecrets() {
  std::lock_guard<std::mutex> lock(secrets_mutex);
  for (auto& value : secrets) steam::ZeroizeSecret(value);
  secrets.clear();
}

void note(const char* format, ...) {
  char line[1024];
  va_list ap;
  va_start(ap, format);
  int n = vsnprintf(line, sizeof(line) - 1, format, ap);
  va_end(ap);
  if (n < 0) return;
  if (n > static_cast<int>(sizeof(line)) - 2) n = sizeof(line) - 2;
  line[n] = 0;
  {
    std::lock_guard<std::mutex> lock(secrets_mutex);
    for (const auto& value : secrets)
      if (strstr(line, value.c_str())) {
        n = snprintf(line, sizeof(line), "PWSTEAM line withheld: it held account data");
        break;
      }
  }
  line[n++] = '\n';
  line[n] = 0;
#ifdef STEAM_HOST
  fputs(line, stdout);
  fflush(stdout);
#else
  sceKernelDebugOutText(0, line);
#endif
  if (log_fd >= 0) {
    write(log_fd, line, static_cast<size_t>(n));
    // alpha-1: every line reaches storage before the next step, except the install's periodic progress
    // without traces (pw_trace.h): it repeats while chunks are written, and write() alone survives a crash
    static const char progress[] = "PWSTEAM install progress ";
    if (pw_trace_on() || strncmp(line, progress, sizeof(progress) - 1)) fsync(log_fd);
  }
}

bool ReadAll(const std::string& path, std::string* out, int* error) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) {
    *error = errno;
    return false;
  }
  char buffer[65536];
  for (;;) {
    const ssize_t got = read(fd, buffer, sizeof(buffer));
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) {
      *error = errno;
      close(fd);
      return false;
    }
    if (got == 0) break;
    out->append(buffer, static_cast<size_t>(got));
  }
  close(fd);
  return true;
}

bool WriteText(const std::string& path, const std::string& text, mode_t mode) {
  const int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, mode);
  if (fd < 0) return false;
  const bool ok = write(fd, text.data(), text.size()) == static_cast<ssize_t>(text.size()) && fsync(fd) == 0;
  close(fd);
  return ok;
}

bool RandomHex(std::size_t bytes, std::string* out) {
  std::vector<std::uint8_t> raw(bytes);
  const int fd = open("/dev/urandom", O_RDONLY);
  if (fd < 0) return false;
  std::size_t done = 0;
  while (done < bytes) {
    const ssize_t got = read(fd, raw.data() + done, bytes - done);
    if (got <= 0) {
      close(fd);
      return false;
    }
    done += static_cast<std::size_t>(got);
  }
  close(fd);
  static const char digits[] = "0123456789abcdef";
  for (const auto b : raw) {
    out->push_back(digits[b >> 4]);
    out->push_back(digits[b & 15]);
  }
  return true;
}

std::uint64_t NowMs() {
  timespec now{};
  clock_gettime(CLOCK_REALTIME, &now);
  return static_cast<std::uint64_t>(now.tv_sec) * 1000 + static_cast<std::uint64_t>(now.tv_nsec) / 1'000'000;
}

bool ClockCheck() {
  const auto steady_start = std::chrono::steady_clock::now();
  const std::uint64_t wall_start = NowMs();
  usleep(300'000);
  const auto steady_ms =
      std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - steady_start).count();
  const std::uint64_t wall_ms = NowMs() - wall_start;
  const bool ok = steady_ms >= 250 && steady_ms <= 2000;
  note("PWSTEAM clock steady_ms=%lld wall_ms=%llu ok=%d", static_cast<long long>(steady_ms),
       static_cast<unsigned long long>(wall_ms), ok);
  return ok;
}

const char* AuthErrorName(steam::AuthError error) {
  switch (error) {
    case steam::AuthError::kNone: return "none";
    case steam::AuthError::kCanceled: return "canceled";
    case steam::AuthError::kExpired: return "expired";
    case steam::AuthError::kRejected: return "rejected";
    case steam::AuthError::kNetwork: return "network";
    case steam::AuthError::kProtocol: return "protocol";
    case steam::AuthError::kCredentialsRevoked: return "credentials_revoked";
    case steam::AuthError::kPersistence: return "persistence";
    case steam::AuthError::kNoSession: return "no_session";
    case steam::AuthError::kInvalidPassword: return "invalid_password";
    case steam::AuthError::kRateLimited: return "rate_limited";
    case steam::AuthError::kSignInRefused: return "sign_in_refused";
    case steam::AuthError::kSignInTimedOut: return "sign_in_timed_out";
  }
  return "unknown";
}

const char* LibraryErrorName(steam::LibraryError error) {
  switch (error) {
    case steam::LibraryError::kNone: return "none";
    case steam::LibraryError::kCanceled: return "canceled";
    case steam::LibraryError::kNetwork: return "network";
    case steam::LibraryError::kProtocol: return "protocol";
    case steam::LibraryError::kCredentialsRevoked: return "credentials_revoked";
    case steam::LibraryError::kNoSession: return "no_session";
    case steam::LibraryError::kPersistence: return "persistence";
  }
  return "unknown";
}

// The pages. native/hw_text.h letters A-Z, 0-9 and : - . / %, and steam_ui.c's accented capitals: no
// commas or question marks; anything else is a blank. What follows PAGE_FOOTER (the page's status and
// its buttons) stays in a band at the bottom of the screen, wherever the text above ends; WARN_LINE
// starts a line drawn in amber.
#define PAGE_FOOTER "\n\x02"
#define WARN_LINE "\x03"
constexpr char kNoticePage[] =
    "BEFORE YOU SIGN IN TO STEAM\n"
    "THIS IS AN UNOFFICIAL CLIENT. IT IS NOT MADE OR APPROVED BY VALVE.\n"
    "USING IT WITH YOUR ACCOUNT MAY GO AGAINST THE STEAM SUBSCRIBER AGREEMENT. VALVE MAY LIMIT OR "
    "SUSPEND THE ACCOUNT. YOU USE IT AT YOUR OWN RISK.\n"
    "YOU SIGN IN WITH A QR CODE AND THE STEAM APP ON YOUR PHONE. THIS CLIENT NEVER SEES YOUR PASSWORD.\n"
    "THE SESSION IS KEPT ENCRYPTED ON THIS CONSOLE. ANYONE WHO COPIES THE FOLDER /DATA/ORBISDESK/STEAM "
    "CAN USE IT. TRIANGLE IN THE LIBRARY SIGNS OUT AND DELETES IT."
    PAGE_FOOTER "X: ACCEPT     O: EXIT";
constexpr char kQrPage[] =
    "SIGN IN TO STEAM\n"
    "ON YOUR PHONE OPEN THE STEAM APP: STEAM GUARD - SCAN A QR CODE.\n"
    "SCAN THIS CODE AND CONFIRM THE SIGN-IN ON THE PHONE.\n"
    "THE CODE RENEWS ITSELF WHILE THIS SCREEN IS OPEN."
    PAGE_FOOTER "O: CANCEL";

enum Outcome { kPass = 0, kFail = 1, kDeclined = 3 };

// Shows `text` with "X: RETRY  O: EXIT"; true for X.
bool AskRetry(const std::string& text) {
  steam_ui_show((text + PAGE_FOOTER "X: RETRY     O: EXIT").c_str(), nullptr);
  return steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE) == STEAM_UI_CROSS;
}

struct Context {
  std::string ca;
  std::string data;
  std::unique_ptr<steam::HttpClient> http;
  std::unique_ptr<steam::CmClient> cm;
  std::unique_ptr<steam::AuthClient> auth;
};

// The device seed CmClient's logon derives its machine fields from: one per console, so Steam sees
// the same device each run. Not account data.
bool DeviceSeed(const std::string& dir, std::string* seed) {
  int error = 0;
  const std::string path = dir + "/device-seed";
  if (ReadAll(path, seed, &error) && seed->size() == 32) return true;
  seed->clear();
  return RandomHex(16, seed) && WriteText(path, *seed, 0600);
}

steam::AuthResult Renew(steam::CmClient& cm, const playden::StoredSession& session, const std::atomic<bool>& cancel) {
  auto renewal = cm.RenewAccessToken(session, cancel);
  note("PWSTEAM renew error=%s rotated=%d", steam::CmErrorName(renewal.error), renewal.refresh_token ? 1 : 0);
  if (!renewal.ok()) {
    switch (renewal.error) {
      case steam::CmError::kCanceled: return {steam::AuthError::kCanceled, std::nullopt};
      case steam::CmError::kNetwork:
      case steam::CmError::kTimeout: return {steam::AuthError::kNetwork, std::nullopt};
      case steam::CmError::kRejected: return {steam::AuthError::kRejected, std::nullopt};
      default: return {steam::AuthError::kProtocol, std::nullopt};
    }
  }
  playden::StoredSession renewed = session;
  renewed.access_token = std::move(renewal.access_token);
  if (renewal.refresh_token) renewed.refresh_token = std::move(*renewal.refresh_token);
  return {steam::AuthError::kNone, std::move(renewed)};
}

// A saved session, restored (and saved again when a token changed). None: sign in by QR.
std::optional<playden::StoredSession> Restore(Context& context, const orbisdesk::SessionFile& file) {
  playden::StoredSession saved;
  const auto loaded = file.Load(&saved);
  note("PWSTEAM session load=%s", orbisdesk::SessionFileErrorName(loaded));
  if (loaded == orbisdesk::SessionFileError::kMissing) return std::nullopt;
  if (loaded != orbisdesk::SessionFileError::kNone) {
    file.Clear();
    note("PWSTEAM session cleared reason=%s", orbisdesk::SessionFileErrorName(loaded));
    return std::nullopt;
  }
  Secret(saved.account_name);
  Secret(saved.refresh_token);
  Secret(saved.access_token);
  for (;;) {
    steam_ui_show("STEAM\nRESTORING THE SAVED SESSION...", nullptr);
    const std::atomic<bool> cancel{false};
    auto restored = context.auth->Restore(saved, cancel);
    note("PWSTEAM session restore error=%s", AuthErrorName(restored.error));
    if (restored.error == steam::AuthError::kNone && restored.session) {
      auto& session = *restored.session;
      Secret(session.refresh_token);
      Secret(session.access_token);
      if (session.refresh_token != saved.refresh_token || session.access_token != saved.access_token)
        note("PWSTEAM session save=%s", orbisdesk::SessionFileErrorName(file.Save(session)));
      steam::ZeroizeSecret(saved.refresh_token);
      steam::ZeroizeSecret(saved.access_token);
      return std::move(session);
    }
    if (restored.error == steam::AuthError::kCredentialsRevoked) {
      // Steam ended the session (or its refresh token ran out): a new sign-in
      file.Clear();
      note("PWSTEAM session cleared reason=credentials_revoked");
      steam::ZeroizeSecret(saved.refresh_token);
      steam::ZeroizeSecret(saved.access_token);
      return std::nullopt;
    }
    // network, refusal or protocol: the saved session stays; the user retries or leaves
    if (!AskRetry(std::string("COULD NOT RESTORE THE SESSION\nERROR: ") + AuthErrorName(restored.error) +
                  "\nTHE SAVED SESSION IS STILL ON THE CONSOLE.")) {
      steam::ZeroizeSecret(saved.refresh_token);
      steam::ZeroizeSecret(saved.access_token);
      return std::nullopt;
    }
  }
}

// A sign-in by QR code. None when the user cancels or gives up.
std::optional<playden::StoredSession> SignIn(Context& context) {
  for (;;) {
    std::atomic<bool> cancel{false}, done{false};
    // O cancels: the UI thread latches the press, this one turns it into the sign-in's cancel flag
    std::thread watcher([&] {
      while (!done.load()) {
        if (steam_ui_take() & STEAM_UI_CIRCLE) cancel.store(true);
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
    });
    steam_ui_show("SIGN IN TO STEAM\nASKING STEAM FOR A CODE..." PAGE_FOOTER "O: CANCEL", nullptr);
    int codes = 0;
    const auto started = NowMs();
    auto result = context.auth->AuthenticateQr(cancel, [&codes](const std::string& challenge) {
      // the link is the sign-in: on the screen only
      const int shown = steam_ui_show(kQrPage, challenge.c_str());
      note("PWSTEAM qr code=%d shown=%d", ++codes, shown == 0);
    });
    done.store(true);
    watcher.join();
    note("PWSTEAM qr result=%s codes=%d ms=%llu", AuthErrorName(result.error), codes,
         static_cast<unsigned long long>(NowMs() - started));
    if (result.error == steam::AuthError::kNone && result.session) return std::move(result.session);
    if (result.error == steam::AuthError::kCanceled) return std::nullopt;
    const std::string why = result.error == steam::AuthError::kExpired
                                ? "THE CODE EXPIRED BEFORE THE SIGN-IN WAS CONFIRMED."
                                : std::string("STEAM DID NOT COMPLETE THE SIGN-IN.\nERROR: ") + AuthErrorName(result.error);
    if (!AskRetry("SIGN IN TO STEAM\n" + why)) return std::nullopt;
  }
}

struct Game {
  std::uint32_t app = 0;
  std::string name;
  steam::AppInfo info;
  std::uint64_t windows_bytes = 0;  // the Windows depots with a public manifest, before selection
};

struct Library {
  steam::LibraryError error = steam::LibraryError::kProtocol;
  std::size_t owned = 0, described = 0;
  std::vector<Game> games;  // the ones with a Windows depot, by name
  steam::AcquisitionResult licenses;
};

// PICS app info of `apps`, parsed, in batches of kMaxAppInfoBatch.
std::map<std::uint32_t, steam::AppInfo> FetchInfos(Context& context, const playden::StoredSession& session,
                                                   const std::vector<std::uint32_t>& apps, std::size_t* unanswered) {
  std::map<std::uint32_t, steam::AppInfo> infos;
  const std::atomic<bool> cancel{false};
  for (std::size_t first = 0; first < apps.size(); first += steam::kMaxAppInfoBatch) {
    const std::vector<std::uint32_t> batch(apps.begin() + first,
                                           apps.begin() + std::min(apps.size(), first + steam::kMaxAppInfoBatch));
    const auto info = context.cm->FetchAppInfo(session, batch, cancel);
    if (unanswered) *unanswered += info.unanswered.size();
    if (!info.ok()) note("PWSTEAM pics batch=%zu error=%s", first / steam::kMaxAppInfoBatch, steam::CmErrorName(info.error));
    for (const auto app : batch) {
      const auto buffer = info.buffers.find(app);
      if (buffer == info.buffers.end()) continue;
      if (auto parsed = steam::ParseAppInfo(app, buffer->second)) infos.emplace(app, std::move(*parsed));
    }
  }
  return infos;
}

// The owned games (GetOwnedGames), the account's licenses (CM) and each game's PICS app info. The
// list goes to LIBRARY_FILE (0600): app, Windows depots, their bytes, name.
Library LoadLibrary(Context& context, const playden::StoredSession& session) {
  Library library;
  const std::atomic<bool> cancel{false};
  steam::LibraryClient client(context.ca);
  const auto owned = client.Fetch(session, cancel);
  library.error = owned.error;
  library.owned = owned.games.size();
  note("PWSTEAM library owned error=%s games=%zu", LibraryErrorName(owned.error), owned.games.size());
  if (owned.error != steam::LibraryError::kNone) return library;

  library.licenses = context.cm->FetchAcquisitionDates(session, cancel);
  const auto& licenses = library.licenses;
  note("PWSTEAM library licenses error=%s apps=%zu depots=%zu shared=%zu skipped_packages=%u",
       steam::CmErrorName(licenses.error), licenses.owned_apps.size(), licenses.owned_depots.size(),
       licenses.shared_apps.size(), licenses.skipped_packages);

  std::vector<std::uint32_t> apps;
  for (const auto& game : owned.games)
    if (const auto app = game.id.steam_app()) apps.push_back(*app);
  std::size_t unanswered = 0;
  auto infos = FetchInfos(context, session, apps, &unanswered);
  library.described = infos.size();
  std::string text = "# app\twindows_depots\twindows_bytes\tname\n";
  for (const auto app : apps) {
    Game game;
    game.app = app;
    std::size_t depots = 0;
    const auto found = infos.find(app);
    if (found != infos.end()) {
      game.info = std::move(found->second);
      game.name = game.info.name;
      for (const auto& depot : game.info.depots)
        if (steam::OsListMatchesWindows(depot.os_list) && depot.manifest_gid) {
          ++depots;
          game.windows_bytes += depot.size;
        }
    }
    for (auto& c : game.name)
      if (c == '\t' || c == '\n' || c == '\r' || c == STEAM_UI_MARK) c = ' ';
    text += std::to_string(app) + "\t" + std::to_string(depots) + "\t" + std::to_string(game.windows_bytes) + "\t" +
            game.name + "\n";
    if (depots) library.games.push_back(std::move(game));
  }
  std::sort(library.games.begin(), library.games.end(),
            [](const Game& a, const Game& b) { return strcasecmp(a.name.c_str(), b.name.c_str()) < 0; });
  note("PWSTEAM library pics described=%zu unanswered=%zu windows=%zu", library.described, unanswered,
       library.games.size());
  note("PWSTEAM library file=%s write=%d", LIBRARY_FILE, WriteText(LIBRARY_FILE, text, 0600));
  return library;
}

std::string GameRoot(std::uint32_t app) { return std::string(GAMES_DIR) + "/" + std::to_string(app); }
// in the game's folder: the content language of the install under way, for a paused one to resume in
constexpr char kLanguageFile[] = ".orbisdesk-language.txt";

// The Steam language: what a new install asks for, as Steam's own setting does. Steam's API language
// codes (partner.steamgames.com/doc/store/localization/languages); a game that doesn't carry it gets
// English, else its first language (Playden's SelectDepots).
const std::vector<std::string> kSteamLanguages = {
    "english", "spanish", "latam", "french", "german", "italian", "portuguese", "brazilian", "russian", "polish",
    "dutch", "swedish", "danish", "norwegian", "finnish", "czech", "hungarian", "romanian", "bulgarian", "greek",
    "turkish", "ukrainian", "arabic", "thai", "vietnamese", "indonesian", "japanese", "koreana", "schinese", "tchinese"};
constexpr char kSteamLanguageFile[] = DATA_DIR "/steam-language.txt";

std::string SteamLanguage() {
  std::string text;
  int error = 0;
  if (!ReadAll(kSteamLanguageFile, &text, &error)) return "english";
  while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
  return std::find(kSteamLanguages.begin(), kSteamLanguages.end(), text) != kSteamLanguages.end() ? text : "english";
}

std::string Size(std::uint64_t bytes) {
  char text[32];
  if (bytes >= (1ull << 30)) snprintf(text, sizeof(text), "%.1f GB", static_cast<double>(bytes) / (1ull << 30));
  else snprintf(text, sizeof(text), "%llu MB", static_cast<unsigned long long>((bytes + (1ull << 20) - 1) >> 20));
  return text;
}

struct Installs {
  int ok = 0, failed = 0, paused = 0;
};

std::string Upper(std::string text) {
  for (auto& c : text)
    if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
  return text;
}

// A Steam language code as the user reads it: the language's own name, as Steam's language page gives
// it (UTF-8; steam_ui draws its marks), where steam_ui's Latin letters can show it, else its English
// name. Logs keep the code.
std::string LanguageName(const std::string& code) {
  static const std::pair<const char*, const char*> kNames[] = {
      {"english", "ENGLISH"},
      {"spanish", "ESPAÑOL - ESPAÑA"},
      {"latam", "ESPAÑOL - LATINOAMÉRICA"},
      {"french", "FRANÇAIS"},
      {"german", "DEUTSCH"},
      {"italian", "ITALIANO"},
      {"portuguese", "PORTUGUÊS - PORTUGAL"},
      {"brazilian", "PORTUGUÊS - BRASIL"},
      {"polish", "POLSKI"},
      {"dutch", "NEDERLANDS"},
      {"swedish", "SVENSKA"},
      {"danish", "DANSK"},
      {"norwegian", "NORSK"},
      {"finnish", "SUOMI"},
      {"czech", "ČEŠTINA"},
      {"hungarian", "MAGYAR"},
      {"romanian", "ROMÂNĂ"},
      {"turkish", "TÜRKÇE"},
      {"indonesian", "BAHASA INDONESIA"},
      // scripts steam_ui has no letters for: the English name
      {"russian", "RUSSIAN"},
      {"bulgarian", "BULGARIAN"},
      {"greek", "GREEK"},
      {"ukrainian", "UKRAINIAN"},
      {"arabic", "ARABIC"},
      {"thai", "THAI"},
      {"vietnamese", "VIETNAMESE"},
      {"japanese", "JAPANESE"},
      {"koreana", "KOREAN"},
      {"schinese", "SIMPLIFIED CHINESE"},
      {"tchinese", "TRADITIONAL CHINESE"},
  };
  const std::string key = code.empty() ? "english" : code;
  for (const auto& [name_code, name] : kNames)
    if (key == name_code) return name;
  return Upper(key);  // a code Steam added later
}

// A list of languages: up and down choose, X takes one, O goes back (empty). `heading`: the page's
// lines above the list; `action`: what X does.
std::string ChooseLanguage(const std::string& heading, const std::vector<std::string>& languages,
                           const std::string& current, const char* action) {
  std::size_t selected = 0;
  for (std::size_t i = 0; i < languages.size(); ++i)
    if (languages[i] == current) selected = i;
  constexpr std::size_t kRows = 9;  // fits under a heading of four lines, above the footer band at 720 lines
  for (;;) {
    std::string page = heading;
    std::size_t first = selected >= kRows / 2 ? selected - kRows / 2 : 0;
    if (languages.size() > kRows) first = std::min(first, languages.size() - kRows);
    else first = 0;
    for (std::size_t i = first; i < languages.size() && i < first + kRows; ++i)
      page += (i == selected ? std::string(1, STEAM_UI_MARK) : std::string()) + LanguageName(languages[i]) +
              (languages[i] == current ? " - NOW" : "") + "\n";
    page += std::string(PAGE_FOOTER) + std::to_string(selected + 1) + " OF " + std::to_string(languages.size()) +
            "\nUP AND DOWN: CHOOSE   X: " + action + "   O: BACK";
    steam_ui_show(page.c_str(), nullptr);
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_CROSS | STEAM_UI_CIRCLE);
    if (button == STEAM_UI_UP && selected > 0) --selected;
    else if (button == STEAM_UI_DOWN && selected + 1 < languages.size()) ++selected;
    else if (button == STEAM_UI_CROSS) return languages[selected];
    else if (button == STEAM_UI_CIRCLE) return std::string();
  }
}

// One game: its DLC's app info, the depot plan, the user's go-ahead, the install with its progress
// on screen (O pauses it), and what came of it. `language`: Steam's name of the content language to
// install; empty keeps an installed game's (its record's), or English for a new one. With
// `choose_language` the user picks one of the game's languages first: its depots are fetched and the
// verification puts the chosen language's files in place of the old one's.
void InstallGame(Context& context, const playden::StoredSession& session, const Library& library, const Game& game,
                 Installs* installs, const std::string& language, bool choose_language) {
  steam_ui_show(("INSTALL\n" + game.name + "\nCHOOSING THE DEPOTS...").c_str(), nullptr);
  std::vector<steam::AppInfo> dlc_apps;
  {
    std::vector<std::uint32_t> wanted = game.info.dlc_app_ids;
    if (game.info.demo_of_app_id) wanted.push_back(game.info.demo_of_app_id);
    auto infos = FetchInfos(context, session, wanted, nullptr);
    for (auto& [app, info] : infos) {
      if (app == game.info.demo_of_app_id) steam::KeepDepotsDemoBorrows(game.info, &info);
      dlc_apps.push_back(std::move(info));
    }
  }
  orbisdesk::InstallPlan plan;
  const std::string root = GameRoot(game.app);
  orbisdesk::InstalledRecord record;
  const bool recorded = orbisdesk::ReadInstallRecord(root, &record);
  // what is on the console now; 01.08..01.14 installed only English
  const std::string installed_language = recorded ? (record.language.empty() ? "english" : record.language) : "";
  // an install that was paused or failed has no record (RunInstall removes it first): it resumes in the
  // language it was started in
  std::string pending_language;
  if (!recorded) {
    int error = 0;
    if (ReadAll(root + "/" + kLanguageFile, &pending_language, &error)) {
      while (!pending_language.empty() && (pending_language.back() == '\n' || pending_language.back() == '\r'))
        pending_language.pop_back();
      if (pending_language.size() > 32 || pending_language.find_first_not_of("abcdefghijklmnopqrstuvwxyz_") != std::string::npos)
        pending_language.clear();
    }
  }
  // a new install asks for the Steam language
  const std::string asked = !language.empty()           ? language
                            : !installed_language.empty() ? installed_language
                            : !pending_language.empty()   ? pending_language
                                                          : SteamLanguage();
  if (!pending_language.empty()) note("PWSTEAM plan resume_language=%s", pending_language.c_str());
  if (language.empty() && installed_language.empty() && pending_language.empty())
    note("PWSTEAM plan steam_language=%s", asked.c_str());
  if (!orbisdesk::PlanInstall(game.info, dlc_apps, library.licenses, asked, note, &plan)) {
    steam_ui_show(("CANNOT INSTALL\n" + game.name + "\n" + plan.failure + PAGE_FOOTER "O: BACK").c_str(), nullptr);
    steam_ui_wait(STEAM_UI_CIRCLE);
    return;
  }
  if (!asked.empty() && plan.language != asked) {
    // Playden fell back: the game's depots no longer carry the installed language
    note("PWSTEAM plan language_fallback asked=%s got=%s", asked.c_str(), plan.language.c_str());
  }
  if (choose_language) {
    note("PWSTEAM language page carried=%zu installed=%s", plan.languages.size(), installed_language.c_str());
    if (plan.languages.size() < 2) {
      steam_ui_show(("LANGUAGE\n" + game.name +
                     "\nSTEAM HAS NO LANGUAGE PACKS FOR THIS GAME: ITS FILES ARE THE SAME IN EVERY LANGUAGE. "
                     "IF IT HAS OTHER LANGUAGES THEY ARE CHOSEN INSIDE THE GAME." PAGE_FOOTER "O: BACK")
                        .c_str(),
                    nullptr);
      steam_ui_wait(STEAM_UI_CIRCLE);
      return;
    }
    const std::string chosen =
        ChooseLanguage("LANGUAGE\n" + game.name + "\nINSTALLED NOW: " + LanguageName(installed_language) + "\n", plan.languages,
                       installed_language, "INSTALL THIS LANGUAGE");
    if (chosen.empty()) return;
    note("PWSTEAM language chosen=%s installed=%s", chosen.c_str(), installed_language.c_str());
    steam_ui_show(("LANGUAGE\n" + game.name + "\nCHOOSING THE DEPOTS FOR " + LanguageName(chosen) + "...").c_str(), nullptr);
    plan = orbisdesk::InstallPlan();
    if (!orbisdesk::PlanInstall(game.info, dlc_apps, library.licenses, chosen, note, &plan)) {
      steam_ui_show(("CANNOT CHANGE THE LANGUAGE\n" + game.name + "\n" + plan.failure + PAGE_FOOTER "O: BACK").c_str(), nullptr);
      steam_ui_wait(STEAM_UI_CIRCLE);
      return;
    }
    if (plan.language != chosen) {
      note("PWSTEAM language unavailable chosen=%s got=%s", chosen.c_str(), plan.language.c_str());
      steam_ui_show(("CANNOT CHANGE THE LANGUAGE\n" + game.name + "\nSTEAM HAS NO " + LanguageName(chosen) +
                     " CONTENT FOR THIS GAME ON THIS ACCOUNT." PAGE_FOOTER "O: BACK")
                        .c_str(),
                    nullptr);
      steam_ui_wait(STEAM_UI_CIRCLE);
      return;
    }
  }
  mkdir(GAMES_DIR, 0777);
  const bool again = orbisdesk::Installed(root);
  // SteamStub before the download, for a new or resumed install (W293 brought Alice: Madness Returns and
  // BioShock down whole before their .bind showed): the manifests and the executables' first chunks
  // only. An installed game's record already says it. Detection only, nothing works around the DRM.
  orbisdesk::Precheck precheck;
  bool steamstub_anyway = false;
  if (!again) {
    steam_ui_show(("INSTALL\n" + game.name + "\nCHECKING THE GAME EXECUTABLE FOR STEAMSTUB DRM...").c_str(), nullptr);
    const std::atomic<bool> no_cancel{false};
    precheck = orbisdesk::PrecheckExecutables(context.ca, *context.cm, session, plan, no_cancel, note);
    if (precheck.steamstub) {
      steam_ui_show(("STEAMSTUB DRM\n" + game.name + "\n" WARN_LINE
                     "THE GAME EXECUTABLE HAS STEAMSTUB DRM. ORBISDESK CANNOT RUN THIS GAME AND WOULD MAKE NO SHORTCUT "
                     "FOR IT.\nNOTHING WAS INSTALLED. ONLY THE START OF THE EXECUTABLE WAS DOWNLOADED TO CHECK IT: " +
                     Size(precheck.fetched) + ".\nTHE FULL INSTALL WOULD TAKE " + Size(plan.install_bytes) + "." PAGE_FOOTER
                     "O: DO NOT INSTALL     OPTIONS: INSTALL ANYWAY")
                        .c_str(),
                    nullptr);
      const unsigned answer = steam_ui_wait(STEAM_UI_CIRCLE | STEAM_UI_OPTIONS);
      note("PWSTEAM precheck answer=%s", answer == STEAM_UI_OPTIONS ? "install_anyway" : "back");
      if (answer != STEAM_UI_OPTIONS) return;
      steamstub_anyway = true;
    }
  }
  const auto space = orbisdesk::MeasureFreeSpace(root);
  note("PWSTEAM plan space ok=%d free=%llu", space.ok, static_cast<unsigned long long>(space.bytes));
  // each attempt of the measurement on a line of its own (a getfsstat list can be long)
  for (std::size_t from = 0; from < space.detail.size();) {
    const auto bar = space.detail.find(" | ", from);
    const auto part = space.detail.substr(from, bar == std::string::npos ? std::string::npos : bar - from);
    for (std::size_t at = 0; at < part.size(); at += 900) note("PWSTEAM plan space %s", part.substr(at, 900).c_str());
    from = bar == std::string::npos ? space.detail.size() : bar + 3;
  }
  // appinfo may leave a depot's download size out (0): unknown, not nothing to download
  std::string page = "INSTALL\n" + game.name + "\nINSTALLED SIZE: " + Size(plan.install_bytes) + "\nDOWNLOAD: " +
                     (plan.download_bytes ? "UP TO " + Size(plan.download_bytes) : std::string("NOT GIVEN BY STEAM")) +
                     "\nFREE ON THE CONSOLE: " +
                     (space.ok ? Size(space.bytes) : std::string("COULD NOT BE MEASURED")) + "\nFOLDER: " + root + "\n";
  if (steamstub_anyway)
    page += WARN_LINE "STEAMSTUB DRM: ORBISDESK CANNOT RUN THIS GAME. IT IS INSTALLED ONLY BECAUSE YOU ASKED.\n";
  else if (!again && !precheck.ran)
    page += WARN_LINE "THE EXECUTABLE COULD NOT BE CHECKED FOR STEAMSTUB BEFORE THE DOWNLOAD: " + precheck.failure + "\n";
  if (!space.ok)
    page += WARN_LINE "CHECK THE FREE SPACE IN SETTINGS - STORAGE. IF THE CONSOLE FILLS UP THE INSTALL STOPS "
            "WITH A MESSAGE AND WHAT WAS DOWNLOADED STAYS.\n";
  if (plan.languages.size() > 1 || !installed_language.empty() || asked != plan.language) {
    page += "LANGUAGE: " + LanguageName(plan.language);
    if (!installed_language.empty() && installed_language != plan.language)
      page += " (INSTALLED NOW: " + LanguageName(installed_language) + ")";
    else if (asked != plan.language)
      page += " (" + LanguageName(asked) + " IS NOT OFFERED FOR THIS GAME)";
    if (installed_language.empty() && plan.languages.size() > 1) page += " - SQUARE ON THE INSTALLED GAME CHANGES IT";
    page += "\n";
  }
  if (again && installed_language != plan.language)
    page += "ALREADY INSTALLED: X DOWNLOADS THE FILES OF THE NEW LANGUAGE AND VERIFIES THE REST. "
            "FILES ONLY THE OLD LANGUAGE USED STAY IN THE FOLDER.\n";
  else if (again) page += "ALREADY INSTALLED: X VERIFIES IT AND DOWNLOADS ONLY WHAT IS MISSING OR CHANGED.\n";
  page += space.ok ? PAGE_FOOTER "X: INSTALL     O: BACK" : PAGE_FOOTER "X: INSTALL ANYWAY     O: BACK";
  steam_ui_show(page.c_str(), nullptr);
  if (steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE) != STEAM_UI_CROSS) return;
  // without a measurement, X is the user's word that the space is there
  const bool unmeasured_ok = !space.ok;
  note("PWSTEAM install start again=%d unmeasured_ok=%d language=%s installed_language=%s", again, unmeasured_ok,
       plan.language.c_str(), installed_language.c_str());
  // gbe_fork's DLL would fail the verification and be replaced by Steam's: the game's own DLLs go
  // back first, and the emulator is turned on again once the install passed
  const bool emulator = orbisdesk::EmulatorEnabled(root);
  if (emulator) {
    std::string failure;
    if (!orbisdesk::RestoreEmulator(root, note, &failure)) {
      steam_ui_show(("CANNOT VERIFY\n" + game.name + "\n" + failure + PAGE_FOOTER "O: BACK").c_str(), nullptr);
      steam_ui_wait(STEAM_UI_CIRCLE);
      return;
    }
  }

  mkdir(root.c_str(), 0777);  // RunInstall makes it too; the language file goes in first
  if (!WriteText(root + "/" + kLanguageFile, plan.language + "\n", 0644))
    note("PWSTEAM install language_file write=0 errno=%d", errno);
  std::atomic<bool> cancel{false}, done{false};
  orbisdesk::InstallProgress progress;
  orbisdesk::InstallResult result;
  std::thread runner([&] {
    result = orbisdesk::RunInstall(context.ca, *context.cm, session, plan, root, cancel, unmeasured_ok, &progress, note,
                                   again ? nullptr : &precheck);
    done = true;
  });
  steam_ui_take();
  // what the last few seconds did: fetching from Steam, or only finding chunks already in place
  std::uint64_t window_fetched = 0;
  auto window_start = std::chrono::steady_clock::now();
  double rate = 0;  // bytes fetched per second over the last window
  bool fetching = false;
  while (!done.load()) {
    if (steam_ui_take() & STEAM_UI_CIRCLE) cancel = true;
    const auto total = progress.total_bytes.load(), placed = progress.done_bytes.load();
    const auto fetched = progress.fetched_bytes.load(), reused = progress.reused_bytes.load();
    const auto now = std::chrono::steady_clock::now();
    const auto window_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - window_start).count();
    if (window_ms >= 3000) {
      rate = static_cast<double>(fetched - window_fetched) * 1000.0 / static_cast<double>(window_ms);
      fetching = fetched != window_fetched;
      window_fetched = fetched;
      window_start = now;
    }
    std::string text = "INSTALLING\n" + game.name + "\n";
    if (cancel.load()) text += "PAUSING...\n";
    else if (progress.phase.load() == 0) text += "PREPARING...\n";
    else if (progress.phase.load() == 2) text += "CHECKING THE EXECUTABLE...\n";
    else {
      text += fetching ? "DOWNLOADING FROM STEAM\n" : "VERIFYING WHAT IS ALREADY ON THE CONSOLE\n";
      text += "PROGRESS: " + Size(placed) + " OF " + Size(total) + " - " + std::to_string(total ? placed * 100 / total : 0) +
              "%\n";
      text += "ALREADY THERE AND CORRECT: " + Size(reused) + "\n";
      text += "DOWNLOADED NOW: " + Size(fetched) + "\n";
      text += "FILES DONE: " + std::to_string(progress.files_done.load()) + " OF " +
              std::to_string(progress.files_total.load()) + "\n";
      if (fetching) text += "SPEED: " + Size(static_cast<std::uint64_t>(rate)) + "/S\n";
    }
    text += PAGE_FOOTER "O: PAUSE. WHAT WAS DOWNLOADED STAYS AND THE NEXT INSTALL RESUMES IT.";
    steam_ui_show(text.c_str(), nullptr);
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }
  runner.join();
  if (result.ok) {
    ++installs->ok;
    page = "INSTALLED\n" + game.name + "\n";
    // SteamStub first, where it can't be missed (W293's Alice: Madness Returns read only as "no shortcut")
    if (result.steamstub)
      page += WARN_LINE "STEAMSTUB DRM: ORBISDESK CANNOT RUN THIS GAME. THE FILES ARE INSTALLED: OPTIONS ON "
              "ITS PAGE UNINSTALLS THEM.\n";
    page += "FILES: " + std::to_string(result.verified) + " VERIFIED - " + Size(result.bytes) + "\n";
    if (!plan.executable.empty())
      page += "EXECUTABLE: " + plan.executable + " - " + (result.arch.empty() ? "NOT READ" : result.arch) + "\n";
    else
      page += "STEAM GIVES NO WINDOWS EXECUTABLE.\n";
    page += std::string("USES STEAM API: ") + (result.steam_api ? "YES" : "NO") + "\n";
    if (plan.languages.size() > 1) page += "LANGUAGE: " + LanguageName(plan.language) + "\n";
    // S5: a launcher in OrbisDesk's Explorer (Desktop and Start menu - Programs - Steam)
    const auto shortcut = orbisdesk::WriteGameShortcuts(game.app, game.name, result, root, plan.language);
    note("PWSTEAM shortcut prefix=%d desktop=%d start=%d skipped=%s language_args=%s", shortcut.prefix,
         !shortcut.desktop.empty(), !shortcut.start.empty(), shortcut.skipped.c_str(),
         shortcut.language_arguments.empty() ? "none" : shortcut.language_arguments.c_str());
    if (!shortcut.desktop.empty() || !shortcut.start.empty())
      page += "IN ORBISDESK: A SHORTCUT ON THE DESKTOP AND IN START - PROGRAMS - STEAM.\n";
    else if (!shortcut.prefix)
      page += "ORBISDESK IS NOT INSTALLED ON THIS CONSOLE: NO SHORTCUT WAS MADE.\n";
    else if (shortcut.skipped == "steamstub")
      page += WARN_LINE "NO SHORTCUT WAS MADE: EVERY EXECUTABLE STEAM LISTS HAS STEAMSTUB DRM.\n";
    else
      page += WARN_LINE "NO SHORTCUT WAS MADE IN ORBISDESK: " + Upper(shortcut.skipped) + ".\n";
    if (emulator) {
      std::string failure;
      const bool on = orbisdesk::EnableEmulator(root, game.app, result.steam_api_paths, plan.language, note, &failure);
      // its configs.user.ini is written again, with the language just installed
      page += on ? "STEAM API EMULATOR: TURNED BACK ON, IN " + LanguageName(plan.language.empty() ? "english" : plan.language) + ".\n"
                 : "STEAM API EMULATOR: " + failure + "\n";
    } else if (result.steam_api) {
      page += "TO PLAY WITHOUT STEAM: OPEN IT FROM THE LIST AND TURN ON THE STEAM API EMULATOR.\n";
    }
  } else {
    if (result.canceled) ++installs->paused;
    else ++installs->failed;
    page = std::string(result.canceled ? "PAUSED\n" : "NOT INSTALLED\n") + game.name + "\n" + result.failure + "\n";
  }
  page += PAGE_FOOTER "O: BACK TO THE LIBRARY";
  steam_ui_show(page.c_str(), nullptr);
  steam_ui_wait(STEAM_UI_CIRCLE);
}

// TRIANGLE asks before signing out, the way OPTIONS asks before uninstalling: a stray press used to
// drop the saved session at once. Only X goes on; O keeps the session.
bool ConfirmSignOut() {
  note("PWSTEAM sign_out page");
  steam_ui_show("SIGN OUT\n" WARN_LINE "THIS DELETES THE SAVED STEAM SESSION FROM THIS CONSOLE. TO USE THE CLIENT AGAIN "
                "YOU HAVE TO SIGN IN AGAIN WITH THE STEAM APP.\n"
                "INSTALLED GAMES AND THEIR SHORTCUTS STAY."
                PAGE_FOOTER "X: SIGN OUT     O: STAY SIGNED IN",
                nullptr);
  const bool confirmed = steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE) == STEAM_UI_CROSS;
  note("PWSTEAM sign_out %s", confirmed ? "confirmed" : "canceled");
  return confirmed;
}

// The removal's progress page (RemoveGameFolder calls it every few hundred files).
std::string uninstall_name;
void UninstallProgress(std::uint64_t files) {
  steam_ui_show(("UNINSTALLING\n" + uninstall_name + "\nFILES DELETED: " + std::to_string(files) + "\n").c_str(), nullptr);
}

// OPTIONS on an installed game's page: after the user confirms, its folder (with the install record)
// and the shortcuts S5 made go. True when the game is gone; a failure stays on screen with what is left.
bool UninstallGame(const Game& game, const orbisdesk::InstalledRecord& record) {
  const std::string root = GameRoot(game.app);
  note("PWSTEAM uninstall page app=%u", game.app);
  steam_ui_show(("UNINSTALL\n" + game.name + "\nSIZE: " + Size(record.bytes) + "\nFOLDER: " + root +
                 "\n" WARN_LINE "THIS DELETES THE WHOLE FOLDER AND THE SHORTCUTS OF THE GAME ON THE DESKTOP AND IN START. "
                 "IT CANNOT BE UNDONE: TO PLAY IT AGAIN IT HAS TO BE DOWNLOADED AGAIN.\n"
                 "SAVES THE GAME KEEPS IN ITS OWN FOLDER ARE DELETED TOO. SAVES IN THE DOCUMENTS OR APPDATA OF THE "
                 "ORBISDESK USER STAY."
                 PAGE_FOOTER "X: UNINSTALL     O: KEEP IT")
                    .c_str(),
                nullptr);
  if (steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE) != STEAM_UI_CROSS) {
    note("PWSTEAM uninstall canceled");
    return false;
  }
  note("PWSTEAM uninstall confirmed bytes=%llu", static_cast<unsigned long long>(record.bytes));
  uninstall_name = game.name;
  UninstallProgress(0);
  const auto start = std::chrono::steady_clock::now();
  const auto removed = orbisdesk::RemoveGameFolder(root, note, UninstallProgress);
  const auto ms =
      std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
  // the shortcuts only once the game is gone: a removal that stopped leaves the game installed and its
  // shortcuts in place, and OPTIONS can try again
  orbisdesk::ShortcutRemoval links;
  if (removed.ok) links = orbisdesk::RemoveGameShortcuts(game.app, game.name);
  note("PWSTEAM uninstall done ok=%d ms=%lld shortcuts_prefix=%d desktop=%s start=%s shortcut_errno=%d", removed.ok,
       static_cast<long long>(ms), links.prefix, removed.ok ? links.desktop.c_str() : "kept",
       removed.ok ? links.start.c_str() : "kept", links.error);
  std::string page;
  if (removed.ok) {
    page = "UNINSTALLED\n" + game.name + "\nDELETED: " + std::to_string(removed.files) + " FILES IN " +
           std::to_string(removed.folders + 1) + " FOLDERS.\n";
    const auto said = [](const std::string& where, const std::string& state) {
      if (state == "removed") return where + ": SHORTCUT DELETED.\n";
      if (state == "absent") return where + ": NO SHORTCUT.\n";
      if (state == "not_ours") return where + ": A SHORTCUT WITH THIS NAME POINTS ELSEWHERE AND WAS KEPT.\n";
      return std::string(WARN_LINE) + where + ": THE SHORTCUT COULD NOT BE DELETED.\n";
    };
    if (links.prefix) page += said("DESKTOP", links.desktop) + said("START - PROGRAMS - STEAM", links.start);
  } else {
    page = "NOT UNINSTALLED\n" + game.name + "\n" WARN_LINE + std::to_string(removed.failures) +
           (removed.failures == 1 ? " ITEM" : " ITEMS") + " COULD NOT BE DELETED. FIRST: " +
           (removed.first_failure.empty() ? std::string(".") : removed.first_failure) + " - ERROR " +
           std::to_string(removed.first_errno) + ".\n" + "DELETED BEFORE IT STOPPED: " + std::to_string(removed.files) +
           " FILES. THE GAME STAYS IN THE LIST AS INSTALLED AND ITS SHORTCUTS STAY: OPTIONS ON ITS PAGE TRIES AGAIN.\n";
  }
  steam_ui_show((page + PAGE_FOOTER "O: BACK TO THE LIBRARY").c_str(), nullptr);
  steam_ui_wait(STEAM_UI_CIRCLE);
  return removed.ok;
}

// An installed game's page: what the record says, X verifies (and updates) it, square changes its
// content language, triangle turns gbe_fork on or off, O goes back.
void GamePage(Context& context, const playden::StoredSession& session, const Library& library, const Game& game,
              Installs* installs) {
  const std::string root = GameRoot(game.app);
  for (;;) {
    orbisdesk::InstalledRecord record;
    if (!orbisdesk::ReadInstallRecord(root, &record)) {
      note("PWSTEAM game page record=unreadable");
      InstallGame(context, session, library, game, installs, "", false);
      return;
    }
    const bool emulator = orbisdesk::EmulatorEnabled(root);
    std::string page = "INSTALLED\n" + game.name + "\n";
    if (record.steamstub)
      page += WARN_LINE "STEAMSTUB DRM: ORBISDESK CANNOT RUN THIS GAME AND MADE NO SHORTCUT FOR IT. OPTIONS UNINSTALLS IT.\n";
    page += "SIZE: " + Size(record.bytes) + "\nFOLDER: " + root + "\n";
    if (!record.executable.empty())
      page += "EXECUTABLE: " + record.executable + " - " + (record.arch.empty() ? "NOT READ" : record.arch) + "\n";
    const bool can_emulate = record.format >= 2 && !record.steam_api_paths.empty();
    if (!record.steam_api) page += "DOES NOT USE STEAM API.\n";
    else if (record.format < 2) page += "USES STEAM API. VERIFY IT WITH X TO TURN ON THE EMULATOR.\n";
    else page += std::string("STEAM API EMULATOR: ") + (emulator ? "ON" : "OFF") + "\n";
    page += "LANGUAGE: " + LanguageName(record.language.empty() ? "english" : record.language) + "\n";
    page += PAGE_FOOTER "X: VERIFY AND UPDATE   SQUARE: LANGUAGE";
    if (can_emulate || emulator) page += emulator ? "   TRIANGLE: RESTORE THE ORIGINAL STEAM API" : "   TRIANGLE: TURN ON THE EMULATOR";
    page += "   OPTIONS: UNINSTALL   O: BACK";
    steam_ui_show(page.c_str(), nullptr);
    const unsigned button =
        steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE | STEAM_UI_SQUARE | STEAM_UI_OPTIONS);
    if (button == STEAM_UI_CIRCLE) return;
    if (button == STEAM_UI_OPTIONS) {
      if (UninstallGame(game, record)) return;  // gone: back to the library, which lists it as not installed
      continue;
    }
    if (button == STEAM_UI_SQUARE) {
      InstallGame(context, session, library, game, installs, "", true);
      continue;  // the page again, with what the record says now
    }
    if (button == STEAM_UI_CROSS) {
      InstallGame(context, session, library, game, installs, "", false);
      return;
    }
    if (!can_emulate && !emulator) continue;
    // the switch reads and writes the game's DLLs: say so at once, so the page doesn't sit unchanged
    steam_ui_show(("STEAM API EMULATOR\n" + game.name + "\n" +
                   (emulator ? "RESTORING THE ORIGINAL STEAM API..." : "TURNING ON THE EMULATOR...") + "\n")
                      .c_str(),
                  nullptr);
    note("PWSTEAM emu %s pressed", emulator ? "restore" : "enable");
    std::string failure;
    const bool ok = emulator ? orbisdesk::RestoreEmulator(root, note, &failure)
                             : orbisdesk::EnableEmulator(root, game.app, record.steam_api_paths, record.language, note, &failure);
    note("PWSTEAM emu %s ok=%d", emulator ? "restore" : "enable", ok);
    if (!ok) {
      steam_ui_show(("STEAM API EMULATOR\n" + game.name + "\n" + failure + PAGE_FOOTER "O: BACK").c_str(), nullptr);
      steam_ui_wait(STEAM_UI_CIRCLE);
    }
    note("PWSTEAM emu page back");
  }
}

// The library list, in three tabs (all, installed, not installed) that L1 and R1 (or L2 and R2) move
// between: up and down choose, X opens or installs, O exits, triangle signs out. True for a sign-out.
bool LibraryScreen(Context& context, const playden::StoredSession& session, const Library& library,
                   Installs* installs) {
  constexpr std::size_t kRows = 11;
  static const char* const kTabs[] = {"ALL", "INSTALLED", "NOT INSTALLED"};
  int tab = 0;
  std::size_t selected = 0;           // in the tab's list
  std::uint32_t selected_app = 0;     // kept across tab changes and installs when the game is still listed
  note("PWSTEAM library screen games=%zu", library.games.size());
  for (;;) {
    // an install or a removal changes the tabs: their lists are read again for every page
    std::vector<std::size_t> lists[3];
    for (std::size_t i = 0; i < library.games.size(); ++i) {
      const bool installed = orbisdesk::Installed(GameRoot(library.games[i].app));
      lists[0].push_back(i);
      lists[installed ? 1 : 2].push_back(i);
    }
    const auto& list = lists[tab];
    if (selected_app) {
      for (std::size_t k = 0; k < list.size(); ++k)
        if (library.games[list[k]].app == selected_app) selected = k;
    }
    if (selected >= list.size()) selected = list.empty() ? 0 : list.size() - 1;
    selected_app = list.empty() ? 0 : library.games[list[selected]].app;

    // the title, the tabs and kRows rows above the footer, whose status and buttons stay put whatever the
    // tab lists: each row is cut to fit one line (a wrapped name would push the rest down)
    std::string page = "STEAM LIBRARY\n";
    // the tabs, the active one in the accent color (the font has no brackets: W292's showed as blanks)
    std::string tabs = "L1 -   ";
    for (int t = 0; t < 3; ++t) {
      const std::string label = std::string(kTabs[t]) + " " + std::to_string(lists[t].size());
      tabs += (t == tab ? std::string(1, STEAM_UI_ACCENT) + label + std::string(1, STEAM_UI_ACCENT) : label) + "    ";
    }
    page += tabs + "- R1\n";
    if (library.games.empty()) page += "NO GAMES WITH WINDOWS CONTENT.\n";
    else if (list.empty()) page += tab == 1 ? "NO GAME IS INSTALLED YET.\n" : "EVERY GAME IS INSTALLED.\n";
    std::size_t first = selected >= kRows / 2 ? selected - kRows / 2 : 0;
    if (list.size() > kRows) first = std::min(first, list.size() - kRows);
    else first = 0;
    for (std::size_t k = first; k < list.size() && k < first + kRows; ++k) {
      const auto& game = library.games[list[k]];
      // 36 + " - 999.9 MB" + " - INSTALLED" fits the 62 columns of the hosted 1280x720 page
      std::string name = game.name.size() > 36 ? game.name.substr(0, 33) + "..." : game.name;
      page += (k == selected ? std::string(1, STEAM_UI_MARK) : std::string()) + name + " - " + Size(game.windows_bytes) +
              (tab == 0 && orbisdesk::Installed(GameRoot(game.app)) ? " - INSTALLED" : "") + "\n";
    }
    page += PAGE_FOOTER;
    page += (list.empty() ? std::string("NO GAME") : "GAME " + std::to_string(selected + 1) + " OF " + std::to_string(list.size())) +
            "   STEAM LANGUAGE: " + LanguageName(SteamLanguage()) + "\n";
#ifdef STEAM_UI_HOSTED
    // the desktop's programs keep running underneath and share the console with the download
    page += "CLOSE RUNNING GAMES BEFORE INSTALLING.\n";
    const char* const exit_hint = "O: DESKTOP";
#else
    const char* const exit_hint = "O: EXIT";
#endif
    // up and down need no hint; four footer lines at 1280x720
    page += std::string("L1 R1: TABS   X: OPEN OR INSTALL   SQUARE: STEAM LANGUAGE   TRIANGLE: SIGN OUT   ") + exit_hint;
    steam_ui_show(page.c_str(), nullptr);
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_CROSS | STEAM_UI_CIRCLE |
                                          STEAM_UI_TRIANGLE | STEAM_UI_L1 | STEAM_UI_R1 | STEAM_UI_SQUARE);
    if (button == STEAM_UI_SQUARE) {
      const std::string current = SteamLanguage();
      const std::string chosen = ChooseLanguage(
          "STEAM LANGUAGE\nNEW INSTALLS ASK STEAM FOR THIS LANGUAGE. A GAME WITHOUT IT INSTALLS IN ENGLISH. "
          "AN INSTALLED GAME KEEPS ITS OWN: SQUARE ON ITS PAGE CHANGES IT.\n",
          kSteamLanguages, current, "USE THIS LANGUAGE");
      if (!chosen.empty() && chosen != current) {
        const bool saved = WriteText(kSteamLanguageFile, chosen + "\n", 0644);
        note("PWSTEAM steam_language set=%s saved=%d errno=%d", chosen.c_str(), saved, saved ? 0 : errno);
        if (!saved) {
          steam_ui_show("STEAM LANGUAGE\nCOULD NOT SAVE THE LANGUAGE." PAGE_FOOTER "O: BACK", nullptr);
          steam_ui_wait(STEAM_UI_CIRCLE);
        }
      }
    } else if (button == STEAM_UI_L1 || button == STEAM_UI_R1) {
      tab = (tab + (button == STEAM_UI_R1 ? 1 : 2)) % 3;
      selected = 0;  // or the same game, when the new tab lists it
      note("PWSTEAM library tab=%d games=%zu", tab, lists[tab].size());
    } else if (button == STEAM_UI_UP && selected > 0) {
      selected_app = library.games[list[--selected]].app;
    } else if (button == STEAM_UI_DOWN && selected + 1 < list.size()) {
      selected_app = library.games[list[++selected]].app;
    } else if (button == STEAM_UI_CROSS && !list.empty()) {
      const auto& game = library.games[list[selected]];
      if (orbisdesk::Installed(GameRoot(game.app))) GamePage(context, session, library, game, installs);
      else InstallGame(context, session, library, game, installs, "", false);
    }
    else if (button == STEAM_UI_CIRCLE) return false;
    else if (button == STEAM_UI_TRIANGLE && ConfirmSignOut()) return true;
  }
}

// A failure before the library, on screen until O: inside OrbisDesk the client would otherwise
// vanish back to the desktop without a word.
int StartFailed(const std::string& why) {
  steam_ui_show(("STEAM COULD NOT START\n" + why + PAGE_FOOTER "O: EXIT").c_str(), nullptr);
  steam_ui_wait(STEAM_UI_CIRCLE);
  return kFail;
}

int Run() {
  // the screen first, so every later step can say what it is doing
  if (steam_ui_open(note)) return kFail;
  steam_ui_show("STEAM\nSTARTING...", nullptr);
  if (!ClockCheck()) return StartFailed("THE CONSOLE CLOCK DOES NOT RUN AS EXPECTED.");
  Context context;
  context.data = DATA_DIR;
  int error = 0;
  if (!ReadAll(CA_BUNDLE, &context.ca, &error) || context.ca.empty()) {
    note("PWSTEAM ca bundle=%s read failed errno=%d", CA_BUNDLE, error);
    return StartFailed("THE CERTIFICATE BUNDLE IS MISSING: " CA_BUNDLE);
  }
  {
    mbedtls_x509_crt roots;
    mbedtls_x509_crt_init(&roots);
    const int parsed = mbedtls_x509_crt_parse(&roots, reinterpret_cast<const unsigned char*>(context.ca.c_str()),
                                              context.ca.size() + 1);
    int count = 0;
    for (const mbedtls_x509_crt* c = &roots; c && c->raw.len; c = c->next) ++count;
    mbedtls_x509_crt_free(&roots);
    note("PWSTEAM ca bytes=%zu roots=%d parse_rc=%d", context.ca.size(), count, parsed);
    if (count == 0) return StartFailed("THE CERTIFICATE BUNDLE HAS NO USABLE ROOTS.");
  }
  const bool net = steam::internal::InitializeNativeNetwork();
  note("PWSTEAM net init=%d", net);
  if (!net) return StartFailed("THE CONSOLE NETWORK COULD NOT BE USED.");

  // access() against open() on the data folder, which exists: S4 01.09 found access() failing for
  // every path, so existence is tested by opening (orbisdesk::PathExists)
  {
    errno = 0;
    const int access_rc = access(context.data.c_str(), F_OK);
    const int access_errno = access_rc ? errno : 0;
    note("PWSTEAM fs probe path=%s access=%d errno=%d open=%d", context.data.c_str(), access_rc, access_errno,
         orbisdesk::PathExists(context.data));
  }

  // 3: the notice, once per console
  const std::string accepted = context.data + "/notice-accepted";
  if (!orbisdesk::PathExists(accepted)) {
    steam_ui_show(kNoticePage, nullptr);
    const unsigned answer = steam_ui_wait(STEAM_UI_CROSS | STEAM_UI_CIRCLE);
    note("PWSTEAM notice answer=%s", answer == STEAM_UI_CROSS ? "accepted" : "declined");
    if (answer != STEAM_UI_CROSS) return kDeclined;
    note("PWSTEAM notice saved=%d", WriteText(accepted, std::to_string(time(nullptr)) + "\n", 0600));
  } else {
    note("PWSTEAM notice already_accepted=1");
  }

  std::string seed;
  if (!DeviceSeed(context.data, &seed)) {
    note("PWSTEAM device seed failed errno=%d", errno);
    return kFail;
  }
  steam::SetCmLog([](const std::string& line) {
    // license lines name packages, which is the library: counts only
    if (line.find("package=") != std::string::npos || line.find("_packages=") != std::string::npos) return;
    note("PWSTEAM cm %s", line.c_str());
  });
  context.http = std::make_unique<steam::HttpClient>(context.ca);
  steam::CmClientHooks hooks;
  steam::HttpClient* http = context.http.get();
  hooks.app_info = [http](const steam::HttpRequest& request, const std::atomic<bool>& c) { return http->Perform(request, c); };
  hooks.directory = [http](const steam::HttpRequest& request, const std::atomic<bool>& c) { return http->Perform(request, c); };
  const std::string ca = context.ca;
  hooks.transport = [ca]() -> std::unique_ptr<steam::MessageTransport> {
    return std::make_unique<steam::WebSocketClient>(ca);
  };
  hooks.unix_now = [] { return static_cast<std::uint64_t>(time(nullptr)); };
  hooks.deadline_ms = 60'000;
  context.cm = std::make_unique<steam::CmClient>(hooks, steam::MakeDeviceIdentity(seed));
  steam::ZeroizeSecret(seed);
  context.auth = std::make_unique<steam::AuthClient>(context.ca);
  steam::CmClient* cm = context.cm.get();
  context.auth->SetCmRenewal([cm](const playden::StoredSession& session, const std::atomic<bool>& cancel) {
    return Renew(*cm, session, cancel);
  });
  context.auth->SetFailureReport([](const char* method, long http_status, int eresult) {
    note("PWSTEAM auth refused method=%s http=%ld eresult=%d", method, http_status, eresult);
  });
  context.auth->SetSignInReport([](long long persistence, std::uint64_t lifetime) {
    note("PWSTEAM auth signed_in persistence=%lld lifetime_s=%llu", persistence, static_cast<unsigned long long>(lifetime));
  });

  // 4-5: a saved session, else a sign-in
  const orbisdesk::SessionFile file(context.data);
  auto session = Restore(context, file);
  if (!session) {
    session = SignIn(context);
    if (!session) {
      note("PWSTEAM signin none");
      return kDeclined;
    }
    Secret(session->account_name);
    Secret(session->refresh_token);
    Secret(session->access_token);
    note("PWSTEAM session save=%s", orbisdesk::SessionFileErrorName(file.Save(*session)));
  }
  note("PWSTEAM signed_in=1");

  // 6: the library, 7: the list and installs
  steam_ui_show("SIGNED IN\nLOADING THE LIBRARY...", nullptr);
  const auto library = LoadLibrary(context, *session);
  Installs installs;
  bool sign_out = false;
  if (library.error == steam::LibraryError::kNone) {
    sign_out = LibraryScreen(context, *session, library, &installs);
  } else {
    steam_ui_show((std::string("COULD NOT LOAD THE LIBRARY\nERROR: ") + LibraryErrorName(library.error) +
                   PAGE_FOOTER "O: EXIT     TRIANGLE: SIGN OUT ON THIS CONSOLE").c_str(),
                  nullptr);
    sign_out = steam_ui_wait(STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE) == STEAM_UI_TRIANGLE && ConfirmSignOut();
  }
  note("PWSTEAM installs ok=%d failed=%d paused=%d", installs.ok, installs.failed, installs.paused);
  if (sign_out) {
    file.Clear();
    note("PWSTEAM signed_out=1");
    steam_ui_show("SIGNED OUT\nTHE SAVED SESSION WAS DELETED FROM THIS CONSOLE.", nullptr);
    sleep(2);
  }
  steam::ZeroizeSecret(session->refresh_token);
  steam::ZeroizeSecret(session->access_token);
  return library.error == steam::LibraryError::kNone && !installs.failed ? kPass : kFail;
}

// One run of the client, from the log's first line to its last; the screen is closed at the end.
int ClientRun() {
  mkdir("/data/orbisdesk", 0777);
  mkdir(DATA_DIR, 0700);
  // the previous run's log is kept beside it (S4 01.10 overwrote the end of 01.09's install)
  rename(STEAM_LOG, STEAM_LOG_PREVIOUS);
  log_fd = open(STEAM_LOG, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  note("PWSTEAM client " CLIENT_VERSION " start log=%s data=%s games=%s", STEAM_LOG, DATA_DIR, GAMES_DIR);
#if !defined(STEAM_HOST) && !defined(STEAM_UI_HOSTED)
  note("PWSTEAM sysmodule_net rc=0x%08x", static_cast<unsigned>(sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_NET)));
#endif
  const int rc = Run();
  note("PWSTEAM client " CLIENT_VERSION " result=%s", rc == kPass ? "pass" : rc == kDeclined ? "declined" : "fail");
  note("PWSTEAM client " CLIENT_VERSION " end");
  ForgetSecrets();
  steam_ui_close();
  if (log_fd >= 0) close(log_fd);
  log_fd = -1;
  return rc;
}

}  // namespace

#ifdef STEAM_UI_HOSTED
// OrbisDesk's side (native/hw_pad.c's "<steam-open>" request, from the Start menu's "Open Steam Client"
// or the Desktop link): the client on a thread of its own, the desktop back when it ends. Its answer
// goes back to the request: "opened", "busy" (already open) or "error <what>".
namespace {
std::atomic<bool> client_running{false};
bool root_mode = false;
void* ClientThread(void*) {
  ClientRun();
  client_running = false;
  return nullptr;
}
}  // namespace

// OrbisDesk's ROOT mode (GoldHEN's jailbreak, native/wine_hardware.c W228): only logged here; the free
// space measurement tries the same calls either way. Weak, so the client links without it.
extern "C" int pw_hw_root_mode(void) __attribute__((weak));

extern "C" const char* pw_hw_steam_open(void) {
  if (client_running.exchange(true)) return "busy";
  root_mode = pw_hw_root_mode && pw_hw_root_mode();
  pthread_t thread;
  pthread_attr_t attributes;
  pthread_attr_init(&attributes);
  pthread_attr_setstacksize(&attributes, 2 << 20);
  pthread_attr_setdetachstate(&attributes, PTHREAD_CREATE_DETACHED);
  const int rc = pthread_create(&thread, &attributes, ClientThread, nullptr);
  pthread_attr_destroy(&attributes);
  if (rc) {
    client_running = false;
    return "error thread";
  }
  return "opened";
}

// Playden's native_network.cpp (patch 0003): Wine has already called sceNetInit in this title, so the
// second call's error is expected.
extern "C" bool orbisdesk_steam_net_shared(int rc) {
  note("PWSTEAM net sceNetInit rc=0x%08x shared=1 root=%d", static_cast<unsigned>(rc), root_mode);
  return true;
}
#else
// The standalone title owns libSceNet: a failing sceNetInit is a failure.
extern "C" bool orbisdesk_steam_net_shared(int rc) {
  note("PWSTEAM net sceNetInit rc=0x%08x shared=0", static_cast<unsigned>(rc));
  return false;
}

int main(int argc, char** argv) {
  (void)argc;
  (void)argv;
#ifndef STEAM_HOST
  pw_brand_prepare_state();
#endif
  return ClientRun();
}
#endif
