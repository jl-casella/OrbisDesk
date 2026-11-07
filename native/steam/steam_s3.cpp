// SPDX-License-Identifier: GPL-3.0-or-later
// S3: the user's Steam sign-in by QR code and their library (docs/STEAM_S3.md).
// The user signs in on the console, scanning the code with the Steam app on their phone; this title
// never sees a password. Steps, each logged as a PWSTEAM line:
//   1. clock, CA bundle and the network (as S2);
//   2. the screen and the pad (native/steam/steam_ui.c);
//   3. once per console, a notice that this is an unofficial client the user accepts with X;
//   4. a saved session (native/steam/steam_session.cpp) is restored: kept as is while its access
//      token lasts, renewed through the CM otherwise; a revoked one is deleted;
//   5. without one, Playden's AuthClient signs in by QR code (IAuthenticationService); the session is
//      saved sealed, by the user's choice ("stay signed in");
//   6. the owned games (GetOwnedGames), the account's licenses (CM) and the PICS app info of each game:
//      how many have a Windows depot. The list goes to a file of its own, never to the log;
//   7. a summary page: O exits, triangle signs out on this console (deletes the saved session).
// The log carries event names, counts and Steam's error codes only: no account name, Steam ID,
// token, sign-in link or game. A line holding any of this run's secrets is withheld whole.
// Host: steam_s3 [--data DIR] [--ca FILE]; buttons from stdin ("x", "o", "t").
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
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
#include "steam_session.h"
#include "steam_ui.h"

#ifndef STEAM_HOST
#include <orbis/Sysmodule.h>
#include <orbis/libkernel.h>
#include "../../platform/ps4/pw_brand.h"
#define STEAM_LOG "/data/orbisdesk/steam-s3.txt"
#define CA_BUNDLE "/app0/assets/misc/cacert.pem"
#define DATA_DIR "/data/orbisdesk/steam"
#define LIBRARY_FILE "/data/orbisdesk/steam-library.txt"
#else
#define STEAM_LOG "steam-s3.txt"
#define CA_BUNDLE "cacert.pem"
#define DATA_DIR "steam-data"
#define LIBRARY_FILE "steam-library.txt"
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
    fsync(log_fd);
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

// The pages. native/hw_text.h letters A-Z, 0-9 and : - . / % only: no accents, commas or question
// marks; anything else is a blank.
constexpr char kNoticePage[] =
    "AVISO ANTES DE ENTRAR A STEAM\n"
    "ESTE ES UN CLIENTE NO OFICIAL: NO ES DE VALVE NI ESTA APROBADO POR VALVE.\n"
    "USARLO CON TU CUENTA PUEDE IR CONTRA EL ACUERDO DE SUSCRIPTOR DE STEAM. VALVE PUEDE LIMITAR O "
    "SUSPENDER LA CUENTA. LO USAS BAJO TU RESPONSABILIDAD.\n"
    "EL INGRESO ES CON EL CODIGO QR Y LA APP STEAM DEL TELEFONO. ESTA APP NUNCA VE TU CONTRASENA.\n"
    "LA SESION QUEDA GUARDADA CIFRADA EN ESTA CONSOLA. QUIEN COPIE LA CARPETA /DATA/ORBISDESK/STEAM "
    "PUEDE USARLA. TRIANGULO EN LA ULTIMA PANTALLA LA BORRA.\n"
    "\n"
    "X: ACEPTO     O: SALIR";
constexpr char kQrPage[] =
    "ENTRAR A STEAM\n"
    "EN EL TELEFONO ABRI LA APP STEAM: STEAM GUARD - ESCANEAR UN CODIGO QR.\n"
    "ESCANEA ESTE CODIGO Y CONFIRMA EL INGRESO EN EL TELEFONO.\n"
    "EL CODIGO SE RENUEVA SOLO MIENTRAS ESTA PANTALLA ESTA ABIERTA.\n"
    "\n"
    "O: CANCELAR";

enum Outcome { kPass = 0, kFail = 1, kDeclined = 3 };

// Shows `text` with "X: REINTENTAR  O: SALIR"; true for X.
bool AskRetry(const std::string& text) {
  steam_ui_show((text + "\n\nX: REINTENTAR     O: SALIR").c_str(), nullptr);
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
    steam_ui_show("STEAM\nRECUPERANDO LA SESION GUARDADA...", nullptr);
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
    if (!AskRetry(std::string("NO SE PUDO RECUPERAR LA SESION\nERROR: ") + AuthErrorName(restored.error) +
                  "\nLA SESION GUARDADA SIGUE EN LA CONSOLA.")) {
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
    steam_ui_show("ENTRAR A STEAM\nPIDIENDO UN CODIGO A STEAM...\n\nO: CANCELAR", nullptr);
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
                                ? "EL CODIGO VENCIO SIN QUE SE CONFIRMARA EL INGRESO."
                                : std::string("STEAM NO COMPLETO EL INGRESO.\nERROR: ") + AuthErrorName(result.error);
    if (!AskRetry("ENTRAR A STEAM\n" + why)) return std::nullopt;
  }
}

struct Library {
  steam::LibraryError error = steam::LibraryError::kProtocol;
  std::size_t games = 0, described = 0, windows = 0;
  std::size_t licensed_apps = 0;
  steam::CmError licenses = steam::CmError::kProtocol;
};

// The owned games, how many PICS describes and how many have a Windows depot with a public manifest.
// The list itself goes to LIBRARY_FILE (0600): app, Windows depots, their bytes, name.
Library LoadLibrary(Context& context, const playden::StoredSession& session) {
  Library library;
  const std::atomic<bool> cancel{false};
  steam::LibraryClient client(context.ca);
  const auto owned = client.Fetch(session, cancel);
  library.error = owned.error;
  library.games = owned.games.size();
  note("PWSTEAM library owned error=%s games=%zu", LibraryErrorName(owned.error), owned.games.size());
  if (owned.error != steam::LibraryError::kNone) return library;

  const auto licenses = context.cm->FetchAcquisitionDates(session, cancel);
  library.licenses = licenses.error;
  library.licensed_apps = licenses.owned_apps.size();
  note("PWSTEAM library licenses error=%s apps=%zu depots=%zu shared=%zu skipped_packages=%u",
       steam::CmErrorName(licenses.error), licenses.owned_apps.size(), licenses.owned_depots.size(),
       licenses.shared_apps.size(), licenses.skipped_packages);

  std::vector<std::uint32_t> apps;
  for (const auto& game : owned.games)
    if (const auto app = game.id.steam_app()) apps.push_back(*app);
  std::string text = "# app\twindows_depots\twindows_bytes\tname\n";
  std::size_t unanswered = 0;
  for (std::size_t first = 0; first < apps.size(); first += steam::kMaxAppInfoBatch) {
    const std::vector<std::uint32_t> batch(apps.begin() + first,
                                           apps.begin() + std::min(apps.size(), first + steam::kMaxAppInfoBatch));
    const auto info = context.cm->FetchAppInfo(session, batch, cancel);
    unanswered += info.unanswered.size();
    if (!info.ok()) note("PWSTEAM library pics batch=%zu error=%s", first / steam::kMaxAppInfoBatch, steam::CmErrorName(info.error));
    for (const auto app : batch) {
      const auto buffer = info.buffers.find(app);
      std::size_t depots = 0;
      std::uint64_t bytes = 0;
      std::string name;
      if (buffer != info.buffers.end()) {
        if (const auto parsed = steam::ParseAppInfo(app, buffer->second)) {
          ++library.described;
          name = parsed->name;
          for (const auto& depot : parsed->depots) {
            const bool windows = depot.os_list.empty() || depot.os_list.find("windows") != std::string::npos;
            if (windows && depot.manifest_gid) {
              ++depots;
              bytes += depot.size;
            }
          }
        }
      }
      if (depots) ++library.windows;
      for (auto& c : name)
        if (c == '\t' || c == '\n' || c == '\r') c = ' ';
      text += std::to_string(app) + "\t" + std::to_string(depots) + "\t" + std::to_string(bytes) + "\t" + name + "\n";
    }
  }
  note("PWSTEAM library pics described=%zu unanswered=%zu windows=%zu", library.described, unanswered, library.windows);
  note("PWSTEAM library file=%s write=%d", LIBRARY_FILE, WriteText(LIBRARY_FILE, text, 0600));
  return library;
}

int Run() {
  if (!ClockCheck()) return kFail;
  Context context;
  context.data = DATA_DIR;
  int error = 0;
  if (!ReadAll(CA_BUNDLE, &context.ca, &error) || context.ca.empty()) {
    note("PWSTEAM ca bundle=%s read failed errno=%d", CA_BUNDLE, error);
    return kFail;
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
    if (count == 0) return kFail;
  }
  note("PWSTEAM net init=%d", steam::internal::InitializeNativeNetwork());

  if (steam_ui_open(note)) return kFail;

  // 3: the notice, once per console
  const std::string accepted = context.data + "/notice-accepted";
  if (access(accepted.c_str(), F_OK) != 0) {
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

  // 6: the library
  steam_ui_show("SESION INICIADA\nCARGANDO LA BIBLIOTECA...", nullptr);
  const auto library = LoadLibrary(context, *session);
  std::string page;
  if (library.error == steam::LibraryError::kNone) {
    page = "SESION INICIADA\nJUEGOS: " + std::to_string(library.games) +
           "\nCON DEPOT DE WINDOWS: " + std::to_string(library.windows) +
           "\nLA LISTA ESTA EN " LIBRARY_FILE "\n";
  } else {
    page = std::string("SESION INICIADA\nNO SE PUDO CARGAR LA BIBLIOTECA.\nERROR: ") + LibraryErrorName(library.error) + "\n";
  }
  page += "\nO: SALIR     TRIANGULO: CERRAR LA SESION EN ESTA CONSOLA";
  steam_ui_show(page.c_str(), nullptr);

  // 7
  const unsigned answer = steam_ui_wait(STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE);
  if (answer == STEAM_UI_TRIANGLE) {
    file.Clear();
    note("PWSTEAM signed_out=1");
    steam_ui_show("SESION CERRADA\nLA SESION GUARDADA SE BORRO DE ESTA CONSOLA.", nullptr);
    sleep(2);
  }
  steam::ZeroizeSecret(session->refresh_token);
  steam::ZeroizeSecret(session->access_token);
  return library.error == steam::LibraryError::kNone ? kPass : kFail;
}

}  // namespace

int main(int argc, char** argv) {
  (void)argc;
  (void)argv;
#ifndef STEAM_HOST
  pw_brand_prepare_state();
  mkdir("/data/orbisdesk", 0777);
#endif
  mkdir(DATA_DIR, 0700);
  log_fd = open(STEAM_LOG, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  note("PWSTEAM S3 start log=%s data=%s", STEAM_LOG, DATA_DIR);
#ifndef STEAM_HOST
  note("PWSTEAM sysmodule_net rc=0x%08x", static_cast<unsigned>(sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_NET)));
#endif
  const int rc = Run();
  note("PWSTEAM S3 result=%s", rc == kPass ? "pass" : rc == kDeclined ? "declined" : "fail");
  note("PWSTEAM S3 end");
  ForgetSecrets();
  steam_ui_close();
  if (log_fd >= 0) close(log_fd);
  return rc;
}
