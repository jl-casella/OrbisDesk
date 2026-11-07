// SPDX-License-Identifier: GPL-3.0-or-later
// S2: an anonymous Steam download, from the CM logon to verified files on disk (docs/STEAM_S2.md).
// No account: Steam's anonymous logon (native/steam/patches/0001) reaches content any account may
// download, such as app 1007 (Steamworks SDK Redist), which game servers install anonymously.
// Steps, each logged as a PWSTEAM line:
//   1. CM directory, WebSocket connect, hello and anonymous logon (Playden's CmClient);
//   2. PICS app info of the app, parsed by Playden's ParseAppInfo: its depots and public manifests;
//   3. the depot's decryption key and manifest request code;
//   4. content servers, the manifest (unzip, parse, decrypt the file names, validate);
//   5. every file, chunk by chunk: download, decrypt, decompress, Adler-32 or SHA-1 per chunk, then
//      the SHA-1 of the whole file against the manifest.
// The last line says pass only when every file of the depot was written and its SHA-1 matched; a
// download cut by --max-bytes says partial, never pass. Nothing about an account is involved.
// Host: steam_s2 [--app N] [--depot N] [--out DIR] [--max-bytes N] [--ca FILE]
// Console: the same with the defaults (app 1007, its first Windows depot, /data/orbisdesk/steam).
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
#include <string>
#include <vector>

#include <mbedtls/sha1.h>
#include <mbedtls/x509_crt.h>

#include "steam/backend/app_info.h"
#include "steam/backend/cdn_client.h"
#include "steam/backend/cm_client.h"
#include "steam/backend/cm_messages.h"
#include "steam/backend/depot_chunk.h"
#include "steam/backend/depot_manifest.h"
#include "steam/backend/gzip.h"
#include "steam/backend/http_client.h"
#include "steam/backend/ws_client.h"
#include "steam_netdiag.h"

#ifndef STEAM_HOST
#include <orbis/libkernel.h>
#include "../../platform/ps4/pw_brand.h"
#include <orbis/Sysmodule.h>
#define STEAM_LOG "/data/orbisdesk/steam-s2.txt"
#define CA_BUNDLE "/app0/assets/misc/cacert.pem"
#define OUT_ROOT "/data/orbisdesk/steam"
#else
#define STEAM_LOG "steam-s2.txt"
#define CA_BUNDLE "cacert.pem"
#define OUT_ROOT "download"
#endif

namespace steam = playden::steam;
namespace {

int log_fd = -1;
void note(const char* format, ...) {
  char line[1024];
  va_list ap;
  va_start(ap, format);
  int n = vsnprintf(line, sizeof(line) - 1, format, ap);
  va_end(ap);
  if (n < 0) return;
  if (n > static_cast<int>(sizeof(line)) - 2) n = sizeof(line) - 2;
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

// The CM logon's device seed, new for each run: nothing about S2 is kept
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

std::string Hex(const std::array<std::uint8_t, 20>& bytes) {
  static const char digits[] = "0123456789abcdef";
  std::string text;
  for (const auto b : bytes) {
    text.push_back(digits[b >> 4]);
    text.push_back(digits[b & 15]);
  }
  return text;
}

// mkdir -p of the folders above `path` (relative parts validated by ValidateDepotManifest)
bool MakeParents(const std::string& path, int* error) {
  for (std::size_t slash = path.find('/', 1); slash != std::string::npos; slash = path.find('/', slash + 1)) {
    const std::string dir = path.substr(0, slash);
    if (mkdir(dir.c_str(), 0777) && errno != EEXIST) {
      *error = errno;
      return false;
    }
  }
  return true;
}

bool WriteAt(int fd, const std::vector<std::uint8_t>& data, std::uint64_t offset) {
  std::size_t done = 0;
  while (done < data.size()) {
    const ssize_t put = pwrite(fd, data.data() + done, data.size() - done, static_cast<off_t>(offset + done));
    if (put < 0 && errno == EINTR) continue;
    if (put <= 0) return false;
    done += static_cast<std::size_t>(put);
  }
  return true;
}

bool FileSha1(const std::string& path, std::array<std::uint8_t, 20>* digest) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) return false;
  mbedtls_sha1_context sha;
  mbedtls_sha1_init(&sha);
  mbedtls_sha1_starts(&sha);
  std::vector<std::uint8_t> buffer(1 << 20);
  bool ok = true;
  for (;;) {
    const ssize_t got = read(fd, buffer.data(), buffer.size());
    if (got < 0 && errno == EINTR) continue;
    if (got < 0) {
      ok = false;
      break;
    }
    if (got == 0) break;
    mbedtls_sha1_update(&sha, buffer.data(), static_cast<size_t>(got));
  }
  close(fd);
  if (ok) mbedtls_sha1_finish(&sha, digest->data());
  mbedtls_sha1_free(&sha);
  return ok;
}

const char* ChunkErrorName(steam::ChunkError error) {
  switch (error) {
    case steam::ChunkError::kNone: return "none";
    case steam::ChunkError::kDecrypt: return "decrypt";
    case steam::ChunkError::kFormat: return "format";
    case steam::ChunkError::kDecompress: return "decompress";
    case steam::ChunkError::kSize: return "size";
    case steam::ChunkError::kChecksum: return "checksum";
  }
  return "unknown";
}

std::uint64_t NowMs() {
  timespec now{};
  clock_gettime(CLOCK_REALTIME, &now);
  return static_cast<std::uint64_t>(now.tv_sec) * 1000 + static_cast<std::uint64_t>(now.tv_nsec) / 1'000'000;
}

struct Options {
  std::uint32_t app = 1007;  // Steamworks SDK Redist: anonymous, small
  std::uint32_t depot = 0;   // 0: the app's first Windows depot with a public manifest
  std::string out = OUT_ROOT;
  std::uint64_t max_bytes = 0;  // 0: the whole depot
  std::string ca = CA_BUNDLE;
};

// steady_clock against the wall clock over a 300 ms sleep: on the console the SDK's clock numbers
// are Linux's (native/steam/orbis/orbis_clock.c turns them into FreeBSD's). Every CM and HTTP
// deadline counts on steady_clock; without the turn it measured CPU time and barely moved.
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

int Run(const Options& options) {
  const std::atomic<bool> cancel{false};
  if (!ClockCheck()) return 1;
  std::string ca;
  int error = 0;
  if (!ReadAll(options.ca, &ca, &error) || ca.empty()) {
    note("PWSTEAM ca bundle=%s read failed errno=%d", options.ca.c_str(), error);
    return 1;
  }
  // The roots as curl will parse them (curl adds the NUL PEM needs): counted here first, so a bundle
  // that doesn't load fails with its own line instead of as a failed TLS handshake later. S1's first
  // console run loaded none (its fstat-sized read; this read goes to end of file).
  {
    char head[33];
    for (std::size_t i = 0; i < sizeof(head) - 1; ++i)
      head[i] = i < ca.size() && ca[i] >= 0x20 && ca[i] < 0x7f ? ca[i] : '.';
    head[sizeof(head) - 1] = 0;
    mbedtls_x509_crt roots;
    mbedtls_x509_crt_init(&roots);
    const int parsed = mbedtls_x509_crt_parse(&roots, reinterpret_cast<const unsigned char*>(ca.c_str()), ca.size() + 1);
    int count = 0;
    for (const mbedtls_x509_crt* c = &roots; c && c->raw.len; c = c->next) ++count;
    mbedtls_x509_crt_free(&roots);
    note("PWSTEAM ca bundle=%s bytes=%zu roots=%d parse_rc=%d head=%s", options.ca.c_str(), ca.size(), count, parsed,
         head);
    if (count == 0) return 1;
  }
  // S2 01.02 on the console stopped at the CM directory with "error=network http=0": every step
  // of the way to curl, logged before the CM (native/steam/steam_netdiag.cpp)
  const NoteFn log_line = note;
  SteamNetDiagnosis(ca, log_line);

  std::string seed;
  if (!RandomHex(16, &seed)) {
    note("PWSTEAM device seed: /dev/urandom failed errno=%d", errno);
    return 1;
  }
  steam::SetCmLog([](const std::string& line) { note("PWSTEAM cm %s", line.c_str()); });
  steam::HttpClient http(ca);
  steam::CmClientHooks hooks;
  hooks.app_info = [&http](const steam::HttpRequest& request, const std::atomic<bool>& c) {
    return http.Perform(request, c);
  };
  // the CM directory request, with what CmClient's own log leaves out (category, curl code, times)
  hooks.directory = [&http](const steam::HttpRequest& request, const std::atomic<bool>& c) {
    auto response = http.Perform(request, c);
    note("PWSTEAM directory %s status=%ld body=%zu ms_resolve=%u ms_connect=%u ms_tls=%u ms_total=%u",
         steam::HttpFailureName(response).c_str(), response.status_code, response.body.size(),
         response.timing.resolve_ms, response.timing.connect_ms, response.timing.tls_ms, response.timing.total_ms);
    return response;
  };
  hooks.transport = [&ca]() -> std::unique_ptr<steam::MessageTransport> {
    return std::make_unique<steam::WebSocketClient>(ca);
  };
  hooks.unix_now = [] { return static_cast<std::uint64_t>(time(nullptr)); };
  hooks.deadline_ms = 60'000;
  steam::CmClient cm(hooks, steam::MakeDeviceIdentity(seed));

  playden::StoredSession anonymous;
  anonymous.steam_id = steam::cm::kAnonUserSteamId;

  // 1-2: logon and app info
  auto info = cm.FetchAppInfo(anonymous, {options.app}, cancel);
  note("PWSTEAM pics app=%u error=%s buffers=%zu unanswered=%zu", options.app, steam::CmErrorName(info.error),
       info.buffers.size(), info.unanswered.size());
  for (const auto& [id, why] : info.unanswered) note("PWSTEAM pics app=%u unanswered=%s", id, why.c_str());
  const auto buffer = info.buffers.find(options.app);
  if (!info.ok() || buffer == info.buffers.end()) return 1;
  const auto app = steam::ParseAppInfo(options.app, buffer->second);
  if (!app) {
    note("PWSTEAM appinfo app=%u parse failed bytes=%zu", options.app, buffer->second.size());
    return 1;
  }
  note("PWSTEAM appinfo app=%u name=%s depots=%zu", app->app_id, app->name.c_str(), app->depots.size());
  const steam::DepotInfo* depot = nullptr;
  for (const auto& d : app->depots) {
    note("PWSTEAM depot id=%u os=%s arch=%s manifest=%llu size=%llu", d.id, d.os_list.c_str(), d.os_arch.c_str(),
         static_cast<unsigned long long>(d.manifest_gid.value_or(0)), static_cast<unsigned long long>(d.size));
    const bool windows = d.os_list.empty() || d.os_list.find("windows") != std::string::npos;
    if (!depot && d.manifest_gid && (options.depot ? d.id == options.depot : windows)) depot = &d;
  }
  if (!depot) {
    note("PWSTEAM depot: none %s with a public manifest", options.depot ? "with that id" : "for Windows");
    return 1;
  }

  // 3: key and manifest request code
  steam::DepotRequest request;
  request.depot_id = depot->id;
  request.manifest_gid = *depot->manifest_gid;
  const auto access = cm.FetchDepotAccess(anonymous, options.app, {request}, cancel);
  note("PWSTEAM access depot=%u error=%s grants=%zu %s", depot->id, steam::CmErrorName(access.error),
       access.grants.size(), access.detail.c_str());
  if (!access.ok() || access.grants.empty()) return 1;
  const auto& grant = access.grants.front();

  // 4: servers and manifest
  steam::CdnClient cdn(ca);
  std::vector<steam::ContentServer> servers;
  const auto listed = cdn.Servers(0, cancel, &servers);
  note("PWSTEAM cdn servers=%zu error=%d %s", servers.size(), static_cast<int>(listed), cdn.last_failure().c_str());
  if (servers.empty()) return 1;
  std::vector<std::uint8_t> zip;
  std::size_t used = servers.size();
  for (std::size_t i = 0; i < servers.size() && i < 3; ++i) {
    zip.clear();
    const auto got = cdn.Manifest(servers[i], depot->id, grant.manifest_gid, grant.manifest_request_code, cancel, &zip);
    note("PWSTEAM manifest server=%s error=%d bytes=%zu %s", steam::CdnServerLabel(servers[i].host).c_str(),
         static_cast<int>(got), zip.size(), got == steam::CdnError::kNone ? "" : cdn.last_failure().c_str());
    if (got == steam::CdnError::kNone) {
      used = i;
      break;
    }
  }
  if (used == servers.size()) return 1;
  std::vector<std::uint8_t> raw;
  steam::DepotManifest manifest;
  std::string reason;
  if (!steam::UnzipFirstEntry(zip, steam::InflateRaw, &raw, steam::kMaxManifestBytes) ||
      !steam::ParseDepotManifest(raw, &manifest) ||
      !steam::DecryptManifestFilenames(&manifest, grant.key, steam::SymmetricDecrypt) ||
      !steam::ValidateDepotManifest(manifest, &reason)) {
    note("PWSTEAM manifest decode failed unzipped=%zu files=%zu reason=%s", raw.size(), manifest.files.size(),
         reason.c_str());
    return 1;
  }
  std::uint64_t total = 0, chunks = 0;
  for (const auto& file : manifest.files) {
    total += file.size;
    chunks += file.chunks.size();
  }
  note("PWSTEAM manifest depot=%u gid=%llu files=%zu chunks=%llu bytes=%llu", manifest.depot_id,
       static_cast<unsigned long long>(manifest.gid), manifest.files.size(), static_cast<unsigned long long>(chunks),
       static_cast<unsigned long long>(total));

  // 5: files
  const std::string root = options.out + "/" + std::to_string(options.app) + "/" + std::to_string(depot->id);
  if (!MakeParents(root + "/", &error)) {
    note("PWSTEAM out root=%s mkdir failed errno=%d", root.c_str(), error);
    return 1;
  }
  note("PWSTEAM out root=%s", root.c_str());
  std::uint64_t written = 0, verified = 0, failed = 0, skipped = 0, directories = 0;
  bool partial = false;
  const std::uint64_t started = NowMs();
  for (const auto& file : manifest.files) {
    const std::string path = root + "/" + file.path;
    if (file.is_directory()) {
      if (!MakeParents(path + "/", &error)) {
        note("PWSTEAM dir %s mkdir failed errno=%d", file.path.c_str(), error);
        ++failed;
      }
      ++directories;
      continue;
    }
    if (file.is_symlink()) {
      note("PWSTEAM file %s symlink not created", file.path.c_str());
      ++skipped;
      continue;
    }
    if (options.max_bytes && written + file.size > options.max_bytes) {
      partial = true;
      break;
    }
    int fd = -1;
    if (!MakeParents(path, &error) || (fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0666)) < 0) {
      note("PWSTEAM file %s open failed errno=%d", file.path.c_str(), fd < 0 ? errno : error);
      ++failed;
      continue;
    }
    bool ok = true;
    for (const auto& chunk : file.chunks) {
      steam::ChunkError last = steam::ChunkError::kNone;
      bool done = false;
      for (std::size_t attempt = 0; attempt < 3 && !done; ++attempt) {
        const auto& server = servers[(used + attempt) % servers.size()];
        std::vector<std::uint8_t> encrypted, plain;
        const auto got = cdn.Chunk(server, depot->id, Hex(chunk.sha), chunk.compressed_size + 4096, cancel, &encrypted);
        if (got != steam::CdnError::kNone) {
          note("PWSTEAM chunk %s attempt=%zu download error=%d %s", Hex(chunk.sha).c_str(), attempt,
               static_cast<int>(got), cdn.last_failure().c_str());
          continue;
        }
        last = steam::ProcessDepotChunk(encrypted, grant.key, chunk.original_size, chunk.crc, chunk.sha, &plain);
        if (last != steam::ChunkError::kNone) {
          note("PWSTEAM chunk %s attempt=%zu decode=%s", Hex(chunk.sha).c_str(), attempt, ChunkErrorName(last));
          continue;
        }
        if (!WriteAt(fd, plain, chunk.offset)) {
          note("PWSTEAM file %s write failed errno=%d", file.path.c_str(), errno);
          break;
        }
        done = true;
      }
      if (!done) {
        ok = false;
        break;
      }
    }
    if (ok && ftruncate(fd, static_cast<off_t>(file.size))) ok = false;
    close(fd);
    if (!ok) {
      note("PWSTEAM file %s failed", file.path.c_str());
      ++failed;
      continue;
    }
    written += file.size;
    std::array<std::uint8_t, 20> digest{};
    const bool zero_sha = std::all_of(file.sha_content.begin(), file.sha_content.end(), [](std::uint8_t b) { return !b; });
    if (file.size == 0 && zero_sha) {
      ++verified;
    } else if (FileSha1(path, &digest) && digest == file.sha_content) {
      ++verified;
    } else {
      note("PWSTEAM file %s sha1 mismatch got=%s want=%s", file.path.c_str(), Hex(digest).c_str(),
           Hex(file.sha_content).c_str());
      ++failed;
    }
  }
  const std::uint64_t seconds_ms = NowMs() - started;
  const std::size_t regular = manifest.files.size() - directories;
  note("PWSTEAM files regular=%zu verified=%llu failed=%llu skipped=%llu bytes=%llu ms=%llu kib_s=%llu partial=%d",
       regular, static_cast<unsigned long long>(verified), static_cast<unsigned long long>(failed),
       static_cast<unsigned long long>(skipped), static_cast<unsigned long long>(written),
       static_cast<unsigned long long>(seconds_ms),
       static_cast<unsigned long long>(seconds_ms ? written * 1000 / 1024 / seconds_ms : 0), partial);
  if (partial) return 2;
  return verified == regular && !failed && !skipped ? 0 : 1;
}

}  // namespace

int main(int argc, char** argv) {
  Options options;
#ifdef STEAM_HOST
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string flag = argv[i], value = argv[i + 1];
    if (flag == "--app") options.app = static_cast<std::uint32_t>(std::stoul(value));
    else if (flag == "--depot") options.depot = static_cast<std::uint32_t>(std::stoul(value));
    else if (flag == "--out") options.out = value;
    else if (flag == "--max-bytes") options.max_bytes = std::stoull(value);
    else if (flag == "--ca") options.ca = value;
    else {
      fprintf(stderr, "unknown option %s\n", flag.c_str());
      return 64;
    }
  }
#else
  (void)argc;
  (void)argv;
  pw_brand_prepare_state();
  mkdir("/data/orbisdesk", 0777);
#endif
  log_fd = open(STEAM_LOG, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  note("PWSTEAM S2 start log=%s app=%u depot=%u out=%s max_bytes=%llu", STEAM_LOG, options.app, options.depot,
       options.out.c_str(), static_cast<unsigned long long>(options.max_bytes));
#ifndef STEAM_HOST
  note("PWSTEAM sysmodule_net rc=0x%08x", static_cast<unsigned>(sceSysmoduleLoadModuleInternal(ORBIS_SYSMODULE_INTERNAL_NET)));
  // No sceNetInit here: Playden's InitializeNativeNetwork calls it and requires 0, and on the PS4 a
  // second call returns an error (platform/ps4/pw_ws2_32_libc.c). S2 01.02 called it first, and its
  // HTTP client then failed without reaching curl ("error=network http=0").
#endif
  const int rc = Run(options);
  note("PWSTEAM S2 result=%s", rc == 0 ? "pass" : rc == 2 ? "partial" : "fail");
  note("PWSTEAM S2 end");
  if (log_fd >= 0) close(log_fd);
#ifndef STEAM_HOST
  sceKernelUsleep(2000000);
#endif
  return rc;
}
