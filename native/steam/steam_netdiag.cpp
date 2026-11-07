// SPDX-License-Identifier: GPL-3.0-or-later
// S2's network diagnosis, before the CM (docs/STEAM_S2.md). S2 01.02 on the console failed its
// first HTTP request (the CM directory) with "error=network http=0" and nothing more, while S1's
// own HTTPS over libSceNet worked. Three steps, each logged as PWSTEAM netdiag lines:
//   1. Playden's SO_NBIO preflight (native_network.cpp, NativeNonblockingPreflight), redone here
//      value by value: if it fails, Playden's HttpClient never reaches curl (kInitializationFailed);
//   2. Playden's HttpClient on the CM directory: HttpFailureName (category, curl code, address)
//      and the time of each step (resolve, connect, TLS, first byte);
//   3. curl alone on the same URL, resolved by sceNetResolver and handed over with CURLOPT_RESOLVE
//      (on the host: curl's own resolver): CURLcode, CURLOPT_ERRORBUFFER, curl's step times and its
//      debug text lines (connect, TLS), so the line where it stops names the step.
// Nothing here changes what S2 does next; it only reports.
#include "steam_netdiag.h"

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include <curl/curl.h>

#include "steam/backend/http_client.h"
#include "steam/backend/native_network.h"

#ifndef STEAM_HOST
extern "C" {
int* sceNetErrnoLoc(void);
int sceNetRecv(int socket, void* data, std::size_t size, int flags);
int sceNetSetsockopt(int socket, int level, int option, const void* value, unsigned int size);
int sceNetPoolCreate(const char* name, int size, int flags);
int sceNetPoolDestroy(int pool_id);
int sceNetResolverCreate(const char* name, int pool_id, int flags);
int sceNetResolverDestroy(int resolver_id);
int sceNetResolverStartNtoa(int resolver_id, const char* hostname, in_addr_t* address, int timeout, int retries,
                            int flags);
}
#endif

namespace {
using Clock = std::chrono::steady_clock;
[[maybe_unused]] constexpr char kDirectoryHost[] = "api.steampowered.com";  // console only (sceNetResolver)
constexpr char kDirectoryUrl[] =
    "https://api.steampowered.com/ISteamDirectory/GetCMListForConnect/v1/?cmtype=websockets&maxcount=16&format=json";

long long Ms(Clock::time_point since) {
  return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - since).count();
}

#ifndef STEAM_HOST
// NativeNonblockingPreflight with every value logged; same calls, same order
void Preflight(const NoteFn& note) {
  const int listener = socket(AF_INET, SOCK_STREAM, 0);
  const int listener_errno = listener < 0 ? errno : 0;
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  socklen_t size = sizeof(address);
  const int bound = listener >= 0 ? bind(listener, reinterpret_cast<sockaddr*>(&address), sizeof(address)) : -1;
  const int bound_errno = bound ? errno : 0;
  const int listening = bound == 0 ? listen(listener, 1) : -1;
  const int named = listening == 0 ? getsockname(listener, reinterpret_cast<sockaddr*>(&address), &size) : -1;
  note("PWSTEAM netdiag preflight listener=%d errno=%d bind=%d errno=%d listen=%d getsockname=%d port=%u", listener,
       listener_errno, bound, bound_errno, listening, named, static_cast<unsigned>(ntohs(address.sin_port)));
  if (named != 0) {
    if (listener >= 0) close(listener);
    return;
  }
  const int client = socket(AF_INET, SOCK_STREAM, 0);
  const int connected = client >= 0 ? connect(client, reinterpret_cast<sockaddr*>(&address), sizeof(address)) : -1;
  const int connect_errno = connected ? errno : 0;
  note("PWSTEAM netdiag preflight client=%d connect=%d errno=%d", client, connected, connect_errno);
  if (connected != 0) {
    if (client >= 0) close(client);
    close(listener);
    return;
  }
  std::atomic<bool> release{false};
  std::thread watchdog([client, &release] {
    const auto deadline = Clock::now() + std::chrono::milliseconds(2000);
    while (!release.load() && Clock::now() < deadline) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    if (!release.load()) shutdown(client, SHUT_RDWR);
  });
  int enabled = 1;
  const int option = sceNetSetsockopt(client, 0xffff, 0x1200, &enabled, sizeof(enabled));
  unsigned char byte = 0;
  auto start = Clock::now();
  const int native = sceNetRecv(client, &byte, 1, 0);
  const int native_errno = native < 0 && sceNetErrnoLoc() ? *sceNetErrnoLoc() : 0;
  const long long native_ms = Ms(start);
  errno = 0;
  start = Clock::now();
  const ssize_t posix = recv(client, &byte, 1, 0);
  const int posix_errno = posix < 0 ? errno : 0;
  const long long posix_ms = Ms(start);
  release.store(true);
  watchdog.join();
  close(client);
  close(listener);
  // Playden's verdict: option 0, both reads fail at once with EWOULDBLOCK/EAGAIN, each within 20 ms
  const bool pass = option == 0 && native < 0 && native_errno == EWOULDBLOCK && native_ms < 20 && posix < 0 &&
                    (posix_errno == EAGAIN || posix_errno == EWOULDBLOCK) && posix_ms < 20;
  note("PWSTEAM netdiag preflight so_nbio=%d sceNetRecv=%d errno=%d ms=%lld recv=%zd errno=%d ms=%lld "
       "ewouldblock=%d eagain=%d playden_pass=%d",
       option, native, native_errno, native_ms, posix, posix_errno, posix_ms, EWOULDBLOCK, EAGAIN, pass);
}

bool Resolve(const char* host, std::string* numeric, const NoteFn& note) {
  const int pool = sceNetPoolCreate("orbis-steam-diag", 0x4000, 0);
  const int resolver = pool >= 0 ? sceNetResolverCreate("orbis-steam-diag", pool, 0) : -1;
  in_addr_t address = 0;
  const int rc = resolver >= 0 ? sceNetResolverStartNtoa(resolver, host, &address, 5'000'000, 2, 0) : -1;
  if (resolver >= 0) sceNetResolverDestroy(resolver);
  if (pool >= 0) sceNetPoolDestroy(pool);
  char text[INET_ADDRSTRLEN] = "";
  if (rc >= 0) inet_ntop(AF_INET, &address, text, sizeof(text));
  note("PWSTEAM netdiag resolve host=%s pool=%d resolver=%d rc=0x%08x address=%s", host, pool, resolver,
       static_cast<unsigned>(rc), text);
  *numeric = text;
  return rc >= 0;
}
#endif

int Debug(CURL*, curl_infotype type, char* data, size_t size, void* context) {
  if (type != CURLINFO_TEXT) return 0;
  auto* lines = static_cast<std::pair<const NoteFn*, int>*>(context);
  if (++lines->second > 40) return 0;  // the first ones name the step; the rest repeat it
  std::string text(data, size);
  while (!text.empty() && (text.back() == '\n' || text.back() == '\r')) text.pop_back();
  (*lines->first)("PWSTEAM netdiag curl_info %s", text.c_str());
  return 0;
}

// Each option Playden's HttpClient and WebSocketClient set, on a fresh handle, with the code curl
// gives back: S2 01.03 on the console found every Playden request ending with CURLE_FAILED_INIT,
// the value Perform keeps when one PLAYDEN_SETOPT fails (it was CURLOPT_PROXY, not built in).
void PlaydenOptions(const std::string& ca, const NoteFn& note) {
  CURL* easy = curl_easy_init();
  if (!easy) {
    note("PWSTEAM netdiag options easy_init failed");
    return;
  }
  curl_blob blob{const_cast<char*>(ca.data()), ca.size(), CURL_BLOB_COPY};
  int refused = 0;
  auto check = [&](const char* name, CURLcode code) {
    if (code != CURLE_OK) {
      ++refused;
      note("PWSTEAM netdiag options %s code=%d (%s)", name, static_cast<int>(code), curl_easy_strerror(code));
    }
  };
  check("URL", curl_easy_setopt(easy, CURLOPT_URL, kDirectoryUrl));
  check("CAINFO_BLOB", curl_easy_setopt(easy, CURLOPT_CAINFO_BLOB, &blob));
  check("SSL_VERIFYPEER", curl_easy_setopt(easy, CURLOPT_SSL_VERIFYPEER, 1L));
  check("SSL_VERIFYHOST", curl_easy_setopt(easy, CURLOPT_SSL_VERIFYHOST, 2L));
  check("SSLVERSION", curl_easy_setopt(easy, CURLOPT_SSLVERSION, CURL_SSLVERSION_TLSv1_2));
  check("PROXY", curl_easy_setopt(easy, CURLOPT_PROXY, ""));
  check("FOLLOWLOCATION", curl_easy_setopt(easy, CURLOPT_FOLLOWLOCATION, 0L));
  check("MAXREDIRS", curl_easy_setopt(easy, CURLOPT_MAXREDIRS, 0L));
  check("PROTOCOLS_STR", curl_easy_setopt(easy, CURLOPT_PROTOCOLS_STR, "https"));
  check("REDIR_PROTOCOLS_STR", curl_easy_setopt(easy, CURLOPT_REDIR_PROTOCOLS_STR, "https"));
  check("NOSIGNAL", curl_easy_setopt(easy, CURLOPT_NOSIGNAL, 1L));
  check("TCP_KEEPALIVE", curl_easy_setopt(easy, CURLOPT_TCP_KEEPALIVE, 1L));
  check("FRESH_CONNECT", curl_easy_setopt(easy, CURLOPT_FRESH_CONNECT, 1L));
  check("FORBID_REUSE", curl_easy_setopt(easy, CURLOPT_FORBID_REUSE, 1L));
  check("HTTPGET", curl_easy_setopt(easy, CURLOPT_HTTPGET, 1L));
  check("CONNECT_ONLY", curl_easy_setopt(easy, CURLOPT_CONNECT_ONLY, 2L));  // WebSocketClient
  check("NOPROGRESS", curl_easy_setopt(easy, CURLOPT_NOPROGRESS, 0L));
  check("CONNECTTIMEOUT_MS", curl_easy_setopt(easy, CURLOPT_CONNECTTIMEOUT_MS, 10'000L));
  check("TIMEOUT_MS", curl_easy_setopt(easy, CURLOPT_TIMEOUT_MS, 10'000L));
  curl_easy_cleanup(easy);
  CURLM* multi = curl_multi_init();
  if (multi) check("MULTI_MAXCONNECTS", static_cast<CURLcode>(curl_multi_setopt(multi, CURLMOPT_MAXCONNECTS, 8L)));
  else note("PWSTEAM netdiag options multi_init failed");
  if (multi) curl_multi_cleanup(multi);
  note("PWSTEAM netdiag options refused=%d", refused);
}

void CurlAlone(const std::string& ca, const NoteFn& note) {
  CURL* easy = curl_easy_init();
  if (!easy) {
    note("PWSTEAM netdiag curl easy_init failed");
    return;
  }
  char error[CURL_ERROR_SIZE] = "";
  std::string body;
  curl_slist* resolve = nullptr;
#ifndef STEAM_HOST
  std::string numeric;
  if (!Resolve(kDirectoryHost, &numeric, note)) {
    curl_easy_cleanup(easy);
    return;
  }
  resolve = curl_slist_append(nullptr, (std::string(kDirectoryHost) + ":443:" + numeric).c_str());
  curl_easy_setopt(easy, CURLOPT_RESOLVE, resolve);
#endif
  curl_blob blob{const_cast<char*>(ca.data()), ca.size(), CURL_BLOB_COPY};
  std::pair<const NoteFn*, int> lines{&note, 0};
  curl_easy_setopt(easy, CURLOPT_URL, kDirectoryUrl);
  curl_easy_setopt(easy, CURLOPT_CAINFO_BLOB, &blob);
  curl_easy_setopt(easy, CURLOPT_SSL_VERIFYPEER, 1L);
  curl_easy_setopt(easy, CURLOPT_SSL_VERIFYHOST, 2L);
  curl_easy_setopt(easy, CURLOPT_ERRORBUFFER, error);
  curl_easy_setopt(easy, CURLOPT_NOSIGNAL, 1L);
  curl_easy_setopt(easy, CURLOPT_CONNECTTIMEOUT_MS, 15'000L);
  curl_easy_setopt(easy, CURLOPT_TIMEOUT_MS, 30'000L);
  curl_easy_setopt(easy, CURLOPT_VERBOSE, 1L);
  curl_easy_setopt(easy, CURLOPT_DEBUGFUNCTION, Debug);
  curl_easy_setopt(easy, CURLOPT_DEBUGDATA, &lines);
  curl_easy_setopt(easy, CURLOPT_WRITEFUNCTION, +[](char* data, size_t size, size_t count, void* out) {
    static_cast<std::string*>(out)->append(data, size * count);
    return size * count;
  });
  curl_easy_setopt(easy, CURLOPT_WRITEDATA, &body);
  const auto start = Clock::now();
  const CURLcode code = curl_easy_perform(easy);
  long status = 0;
  curl_off_t lookup = 0, connect = 0, tls = 0, first = 0;
  curl_easy_getinfo(easy, CURLINFO_RESPONSE_CODE, &status);
  curl_easy_getinfo(easy, CURLINFO_NAMELOOKUP_TIME_T, &lookup);
  curl_easy_getinfo(easy, CURLINFO_CONNECT_TIME_T, &connect);
  curl_easy_getinfo(easy, CURLINFO_APPCONNECT_TIME_T, &tls);
  curl_easy_getinfo(easy, CURLINFO_STARTTRANSFER_TIME_T, &first);
  long os_errno = 0;
  curl_easy_getinfo(easy, CURLINFO_OS_ERRNO, &os_errno);
  note("PWSTEAM netdiag curl code=%d (%s) error=\"%s\" os_errno=%ld status=%ld body=%zu us_lookup=%lld us_connect=%lld "
       "us_tls=%lld us_first=%lld ms=%lld",
       static_cast<int>(code), curl_easy_strerror(code), error, os_errno, status, body.size(),
       static_cast<long long>(lookup), static_cast<long long>(connect), static_cast<long long>(tls),
       static_cast<long long>(first), Ms(start));
  curl_easy_cleanup(easy);
  curl_slist_free_all(resolve);
}
}  // namespace

void SteamNetDiagnosis(const std::string& ca, const NoteFn& note) {
  const curl_version_info_data* version = curl_version_info(CURLVERSION_NOW);
  note("PWSTEAM netdiag curl=%s ssl=%s features=0x%x", version->version, version->ssl_version ? version->ssl_version : "-",
       version->features);
  // Playden's own initialization first (it calls sceNetInit once and requires 0), then the preflight
  // again value by value, now that the network is up
  const bool bootstrap = playden::steam::internal::InitializeNativeNetworkForBootstrap();
  const bool init = playden::steam::internal::InitializeNativeNetwork();
  note("PWSTEAM netdiag playden init_bootstrap=%d init=%d", bootstrap, init);
#ifndef STEAM_HOST
  Preflight(note);
#endif
  PlaydenOptions(ca, note);
  {
    playden::steam::HttpClient http(ca);
    playden::steam::HttpRequest request;
    request.url = kDirectoryUrl;
    request.timeout_ms = 15'000;
    const std::atomic<bool> cancel{false};
    const auto response = http.Perform(request, cancel);
    note("PWSTEAM netdiag playden_http %s status=%ld body=%zu address=%s ms_resolve=%u ms_connect=%u ms_tls=%u "
         "ms_first=%u ms_total=%u",
         playden::steam::HttpFailureName(response).c_str(), response.status_code, response.body.size(),
         response.address.c_str(), response.timing.resolve_ms, response.timing.connect_ms, response.timing.tls_ms,
         response.timing.first_byte_ms, response.timing.total_ms);
  }
  CurlAlone(ca, note);
}
