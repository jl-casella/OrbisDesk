// SPDX-License-Identifier: GPL-3.0-or-later
// S4's installer (steam_install.h).
#include "steam_install.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <thread>

#include <mbedtls/sha1.h>

#include "steam/backend/cdn_client.h"
#include "steam/backend/depot_chunk.h"
#include "steam/backend/depot_manifest.h"
#include "steam/backend/gzip.h"
#include "steam/backend/json.h"

#ifdef STEAM_HOST
#include <sys/statvfs.h>
#else
// The kernel's struct statfs is FreeBSD 9's (native/disc_probe.c, W180, W218): f_bsize at 0x10,
// f_bavail at 0x30. The SDK's own struct (musl) doesn't match it.
extern "C" int kernel_fstatfs(int, void*) __asm__("_fstatfs");
#endif

namespace orbisdesk {
namespace steam = playden::steam;
namespace {

constexpr char kRecord[] = ".orbisdesk-install.json";
constexpr int kWorkers = 4;
constexpr std::uint64_t kSpaceMargin = 512ull << 20;  // left free on the drive after an install

std::uint64_t NowMs() {
  timespec now{};
  clock_gettime(CLOCK_REALTIME, &now);
  return static_cast<std::uint64_t>(now.tv_sec) * 1000 + static_cast<std::uint64_t>(now.tv_nsec) / 1'000'000;
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

std::string Lower(std::string text) {
  for (auto& c : text) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return text;
}

bool MakeParents(const std::string& path) {
  for (std::size_t slash = path.find('/', 1); slash != std::string::npos; slash = path.find('/', slash + 1)) {
    const std::string dir = path.substr(0, slash);
    if (mkdir(dir.c_str(), 0777) && errno != EEXIST) return false;
  }
  return true;
}

// The size of an open file. lseek, not fstat: the SDK's struct stat is not the kernel's (S1 01.00).
std::uint64_t FileSize(int fd) {
  const off_t end = lseek(fd, 0, SEEK_END);
  return end > 0 ? static_cast<std::uint64_t>(end) : 0;
}

bool ReadAt(int fd, std::uint8_t* data, std::size_t size, std::uint64_t offset) {
  std::size_t done = 0;
  while (done < size) {
    const ssize_t got = pread(fd, data + done, size - done, static_cast<off_t>(offset + done));
    if (got < 0 && errno == EINTR) continue;
    if (got <= 0) return false;
    done += static_cast<std::size_t>(got);
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

bool Sha1Of(const std::uint8_t* data, std::size_t size, const std::array<std::uint8_t, 20>& want) {
  std::array<std::uint8_t, 20> got{};
  mbedtls_sha1(data, size, got.data());
  return got == want;
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

std::string JsonText(const std::string& text) {
  std::string out = "\"";
  for (const unsigned char c : text) {
    if (c == '"' || c == '\\') out += '\\', out += static_cast<char>(c);
    else if (c < 0x20) {
      char escaped[8];
      snprintf(escaped, sizeof(escaped), "\\u%04x", c);
      out += escaped;
    } else out += static_cast<char>(c);
  }
  return out + "\"";
}

// One depot's manifest with its key.
struct Depot {
  steam::DepotManifest manifest;
  std::array<std::uint8_t, 32> key{};
};

// A file of the merged install: which depot's entry won.
struct Placement {
  std::size_t depot = 0;
  const steam::ManifestFile* file = nullptr;
};

}  // namespace

bool ParsePe(const std::function<bool(std::uint8_t*, std::size_t, std::uint64_t)>& read, LaunchCheck* check) {
  std::uint8_t dos[64];
  std::uint8_t pe[24];
  bool ok = read(dos, sizeof(dos), 0) && dos[0] == 'M' && dos[1] == 'Z';
  const std::uint32_t at = ok ? dos[0x3c] | dos[0x3d] << 8 | dos[0x3e] << 16 | static_cast<std::uint32_t>(dos[0x3f]) << 24 : 0;
  ok = ok && at < (1u << 20) && read(pe, sizeof(pe), at) && !memcmp(pe, "PE\0\0", 4);
  if (ok) {
    const unsigned machine = pe[4] | pe[5] << 8, sections = pe[6] | pe[7] << 8, optional = pe[20] | pe[21] << 8;
    check->arch = machine == 0x14c ? "x86" : machine == 0x8664 ? "x64" : "other";
    std::vector<std::uint8_t> table(static_cast<std::size_t>(sections) * 40);
    // a section table that can't be read leaves SteamStub unknown: not a PE read, rather than "no .bind"
    ok = sections <= 96 && read(table.data(), table.size(), at + 24 + optional);
    if (ok)
      for (unsigned i = 0; i < sections; ++i)
        if (!memcmp(table.data() + i * 40, ".bind\0", 6)) check->steamstub = true;
  }
  check->pe = ok;
  return ok;
}

namespace {

// The executable's PE machine and whether it carries SteamStub's .bind section.
void ReadExecutable(const std::string& path, LaunchCheck* check, std::size_t entry, NoteFn note) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) {
    note("PWSTEAM install exe entry=%zu open errno=%d", entry, errno);
    return;
  }
  check->present = true;
  const bool ok =
      ParsePe([fd](std::uint8_t* data, std::size_t size, std::uint64_t offset) { return ReadAt(fd, data, size, offset); }, check);
  close(fd);
  note("PWSTEAM install exe entry=%zu pe=%d arch=%s steamstub=%d", entry, ok, check->arch.c_str(), check->steamstub);
}

}  // namespace

// What the precheck fetched, for RunInstall to start from: the depot keys, the content servers, the
// manifests, and the executables' chunks (decrypted, written in place once the files are sized).
struct Prepared {
  std::uint32_t app = 0;
  std::vector<std::uint32_t> depot_ids;  // plan.depots' ids, to tell the plan it was made for
  std::vector<steam::ContentServer> servers;
  std::vector<Depot> depots;
  struct Chunk {
    std::string path;  // as in the manifest
    std::uint64_t offset = 0;
    std::vector<std::uint8_t> plain;
  };
  std::vector<Chunk> chunks;
};

namespace {

std::vector<std::uint32_t> DepotIds(const InstallPlan& plan) {
  std::vector<std::uint32_t> ids;
  for (const auto& depot : plan.depots) ids.push_back(depot.id);
  return ids;
}

// The depot keys, the content servers and the manifests of `plan`. `step` names what failed, for the
// log; `failure` says it on screen.
bool PrepareDepots(const std::string& ca, steam::CmClient& cm, const playden::StoredSession& session, const InstallPlan& plan,
                   const std::atomic<bool>& cancel, NoteFn note, Prepared* out, const char** step, std::string* failure) {
  out->app = plan.app;
  out->depot_ids = DepotIds(plan);
  std::vector<steam::DepotRequest> requests;
  for (const auto& depot : plan.depots)
    requests.push_back({depot.id, *depot.manifest_gid, depot.depot_from_app.has_value(), depot.source_app, "public"});
  const auto access = cm.FetchDepotAccess(session, plan.app, requests, cancel);
  note("PWSTEAM install access error=%s grants=%zu skipped=%zu", steam::CmErrorName(access.error), access.grants.size(),
       access.skipped.size());
  if (!access.ok() || access.grants.empty()) {
    *step = "access";
    *failure = "STEAM DID NOT GIVE THE GAME KEYS.";
    return false;
  }
  steam::CdnClient cdn(ca);
  cdn.Servers(session.cell_id.value_or(0), cancel, &out->servers);
  note("PWSTEAM install cdn servers=%zu", out->servers.size());
  if (out->servers.empty()) {
    *step = "servers";
    *failure = "NO CONTENT SERVERS.";
    return false;
  }
  for (const auto& grant : access.grants) {
    Depot depot;
    depot.key = grant.key;
    bool got = false;
    for (std::size_t i = 0; i < out->servers.size() && i < 3 && !got; ++i) {
      std::vector<std::uint8_t> zip, raw;
      if (cdn.Manifest(out->servers[i], grant.depot_id, grant.manifest_gid, grant.manifest_request_code, cancel, &zip) !=
          steam::CdnError::kNone)
        continue;
      std::string reason;
      depot.manifest = {};
      got = steam::UnzipFirstEntry(zip, steam::InflateRaw, &raw, steam::kMaxManifestBytes) &&
            steam::ParseDepotManifest(raw, &depot.manifest) &&
            steam::DecryptManifestFilenames(&depot.manifest, grant.key, steam::SymmetricDecrypt) &&
            steam::ValidateDepotManifest(depot.manifest, &reason);
      if (!got) note("PWSTEAM install manifest decode failed reason=%s", reason.c_str());
    }
    if (!got) {
      *step = "manifest";
      *failure = "COULD NOT READ A DEPOT MANIFEST.";
      return false;
    }
    out->depots.push_back(std::move(depot));
  }
  return true;
}

// Bytes [offset, offset + size) of `file`, copied out of its chunks: `chunk(c)` gives chunk c's
// plain bytes (fetching it), null when it can't. Only the chunks under those bytes are asked for.
bool ReadFromChunks(const steam::ManifestFile& file,
                    const std::function<const std::vector<std::uint8_t>*(std::size_t)>& chunk, std::uint8_t* data,
                    std::size_t size, std::uint64_t offset) {
  if (offset + size > file.size) return false;
  std::uint64_t covered = 0;
  for (std::size_t c = 0; c < file.chunks.size(); ++c) {
    const auto& entry = file.chunks[c];
    const std::uint64_t begin = entry.offset, end = entry.offset + entry.original_size;
    if (end <= offset || begin >= offset + size) continue;
    const auto* plain = chunk(c);
    if (!plain || plain->size() != entry.original_size) return false;
    const std::uint64_t from = std::max(begin, offset), to = std::min(end, offset + size);
    memcpy(data + (from - offset), plain->data() + (from - begin), static_cast<std::size_t>(to - from));
    covered += to - from;
  }
  return covered == size;  // a gap in the chunks (ValidateDepotManifest refuses them) is not read as zeros
}

// The merge: by lowercase path, a later depot's entry replacing an earlier one's. Directories go to
// `folders`, symbolic links are counted.
std::map<std::string, Placement> MergeDepots(const std::vector<Depot>& depots, std::vector<std::string>* folders,
                                             std::uint32_t* links) {
  std::map<std::string, Placement> files;
  for (std::size_t d = 0; d < depots.size(); ++d)
    for (const auto& file : depots[d].manifest.files) {
      if (file.is_directory()) {
        if (folders) folders->push_back(file.path);
        continue;
      }
      if (file.is_symlink()) {
        if (links) ++*links;
        continue;
      }
      files[Lower(file.path)] = {d, &file};
    }
  return files;
}

}  // namespace

Precheck PrecheckExecutables(const std::string& ca, steam::CmClient& cm, const playden::StoredSession& session,
                             const InstallPlan& plan, const std::atomic<bool>& cancel, NoteFn note) {
  Precheck result;
  const auto started = NowMs();
  // the distinct executables Steam lists, in order (the default first); a few at most
  std::vector<std::string> executables;
  for (const auto& launch : plan.launches) {
    const auto key = Lower(launch.executable);
    if (std::find(executables.begin(), executables.end(), key) == executables.end() && executables.size() < 4)
      executables.push_back(key);
  }
  if (executables.empty()) {
    note("PWSTEAM precheck app=%u exe=0 steamstub=0 none_listed=1", plan.app);
    result.failure = "STEAM LISTS NO WINDOWS EXECUTABLE.";
    return result;
  }
  auto prepared = std::make_shared<Prepared>();
  const char* step = "";
  std::string failure;
  if (!PrepareDepots(ca, cm, session, plan, cancel, note, prepared.get(), &step, &failure)) {
    note("PWSTEAM precheck app=%u stop step=%s canceled=%d", plan.app, step, cancel.load());
    result.failure = failure;
    return result;
  }
  const auto files = MergeDepots(prepared->depots, nullptr, nullptr);
  steam::CdnClient client(ca);
  std::uint64_t fetched = 0;
  std::size_t pe_count = 0, stub_count = 0, fetch_failures = 0;
  for (std::size_t e = 0; e < executables.size(); ++e) {
    LaunchCheck check;
    const auto found = files.find(executables[e]);
    if (found == files.end()) {
      note("PWSTEAM precheck entry=%zu missing_from_depots=1", e);
      result.checks.push_back(check);
      continue;
    }
    check.present = true;
    const auto& file = *found->second.file;
    const auto& depot = prepared->depots[found->second.depot];
    std::map<std::size_t, std::size_t> cached;  // chunk index -> prepared->chunks index
    std::size_t chunks_fetched = 0;
    // a read of the executable's bytes, from its chunks: only the chunks under the bytes asked for are
    // fetched (the headers and the section table sit in the first one)
    auto fetch = [&](std::size_t c) -> const std::vector<std::uint8_t>* {
      if (const auto have = cached.find(c); have != cached.end()) return &prepared->chunks[have->second].plain;
      const auto& chunk = file.chunks[c];
      std::vector<std::uint8_t> encrypted, plain;
      bool ok = false;
      for (int attempt = 0; !ok && attempt < 3 && !cancel.load(); ++attempt) {
        const auto& server = prepared->servers[static_cast<std::size_t>(attempt) % prepared->servers.size()];
        encrypted.clear();
        plain.clear();
        ok = client.Chunk(server, depot.manifest.depot_id, Hex(chunk.sha), chunk.compressed_size + 4096, cancel,
                          &encrypted) == steam::CdnError::kNone &&
             steam::ProcessDepotChunk(encrypted, depot.key, chunk.original_size, chunk.crc, chunk.sha, &plain) ==
                 steam::ChunkError::kNone;
      }
      if (!ok) {
        if (fetch_failures++ < 4) note("PWSTEAM precheck chunk failed %s", client.last_failure().c_str());
        return nullptr;
      }
      fetched += encrypted.size();
      ++chunks_fetched;
      prepared->chunks.push_back({file.path, chunk.offset, std::move(plain)});
      cached.emplace(c, prepared->chunks.size() - 1);
      return &prepared->chunks.back().plain;
    };
    auto read = [&](std::uint8_t* data, std::size_t size, std::uint64_t offset) {
      return ReadFromChunks(file, fetch, data, size, offset);
    };
    ParsePe(read, &check);
    if (check.pe) ++pe_count;
    if (check.steamstub) ++stub_count;
    note("PWSTEAM precheck entry=%zu pe=%d arch=%s steamstub=%d chunks=%zu", e, check.pe, check.arch.c_str(), check.steamstub,
         chunks_fetched);
    result.checks.push_back(check);
  }
  result.ran = pe_count > 0;
  // as the shortcut is made: SteamStub only when no executable Steam lists can be run without it
  result.steamstub = result.ran && stub_count == pe_count;
  result.fetched = fetched;
  if (!result.checks.empty()) result.arch = result.checks.front().arch;
  if (!result.ran) result.failure = cancel.load() ? "CANCELED." : "THE EXECUTABLE COULD NOT BE READ FROM STEAM.";
  note("PWSTEAM precheck app=%u exe=%zu pe=%zu steamstub=%d fetched=%llu ms=%llu", plan.app, executables.size(), pe_count,
       result.steamstub, static_cast<unsigned long long>(fetched), static_cast<unsigned long long>(NowMs() - started));
  result.prepared = std::move(prepared);
  return result;
}

#ifndef STEAM_HOST
namespace {

// FreeBSD's struct statfs (STATFS_VERSION 0x20030518): 472 bytes; f_bsize at 0x10, f_blocks 0x20,
// f_bfree 0x28, f_bavail 0x30, f_fstypename 0x118, f_mntfromname 0x128, f_mntonname 0x180.
constexpr std::size_t kStatfsBytes = 0x1d8;

// A raw FreeBSD system call through syscall(0, number, ...), as native/disc_probe.c makes sdk_cmd:
// the SDK has no wrapper for these, and the libkernel exports no other import proves usable here.
long RawSyscall(long number, long a1, long a2, long a3, int* error) {
  long ret;
  unsigned char failed;
  register long r10 __asm__("r10") = a3;
  __asm__ volatile("syscall\n\tsetc %1"
                   : "=a"(ret), "=q"(failed)
                   : "a"(0L), "D"(number), "S"(a1), "d"(a2), "r"(r10)
                   : "rcx", "r8", "r9", "r11", "memory", "cc");
  *error = failed ? static_cast<int>(ret) : 0;
  return failed ? -1 : ret;
}

struct Statfs {
  bool plausible = false;
  std::uint64_t bytes = 0;
  std::string on, text;
};

// Reads one struct statfs; `text` is what the log needs to judge it.
Statfs ReadStatfs(const std::uint8_t* fs) {
  Statfs out;
  std::uint32_t version = 0, type = 0;
  std::uint64_t bsize = 0, blocks = 0, bfree = 0;
  std::int64_t bavail = 0;
  memcpy(&version, fs + 0x00, 4);
  memcpy(&type, fs + 0x04, 4);
  memcpy(&bsize, fs + 0x10, 8);
  memcpy(&blocks, fs + 0x20, 8);
  memcpy(&bfree, fs + 0x28, 8);
  memcpy(&bavail, fs + 0x30, 8);
  char fstype[17] = {}, on[89] = {};
  memcpy(fstype, fs + 0x118, 16);
  memcpy(on, fs + 0x180, 88);
  for (char* c = fstype; *c; ++c)
    if (*c < 0x20 || *c > 0x7e) *c = '?';
  for (char* c = on; *c; ++c)
    if (*c < 0x20 || *c > 0x7e) *c = '?';
  out.on = on;
  out.plausible = version == 0x20030518 && bsize >= 512 && bsize <= (1u << 20) && !(bsize & (bsize - 1)) && blocks > 0 &&
                  bfree <= blocks;
  if (out.plausible) out.bytes = bavail > 0 ? static_cast<std::uint64_t>(bavail) * bsize : 0;
  char text[256];
  snprintf(text, sizeof(text), "version=%08x type=%u bsize=%llu blocks=%llu bfree=%llu bavail=%lld fstype=%s on=%s", version,
           type, static_cast<unsigned long long>(bsize), static_cast<unsigned long long>(blocks),
           static_cast<unsigned long long>(bfree), static_cast<long long>(bavail), fstype, on);
  out.text = text;
  return out;
}

}  // namespace
#endif

FreeSpace MeasureFreeSpace(const std::string& path) {
  FreeSpace space;
  // the nearest folder that exists: a game's own folder may not yet
  std::string at = path;
  while (at.size() > 1 && !PathExists(at)) {
    const auto slash = at.rfind('/');
    at = slash == std::string::npos || slash == 0 ? "/" : at.substr(0, slash);
  }
#ifdef STEAM_HOST
  char text[512];
  struct statvfs fs;
  errno = 0;
  const int rc = statvfs(at.c_str(), &fs);
  snprintf(text, sizeof(text), "path=%s statvfs=%d errno=%d frsize=%lu blocks=%llu bavail=%llu", at.c_str(), rc, rc ? errno : 0,
           rc ? 0ul : fs.f_frsize, rc ? 0ull : static_cast<unsigned long long>(fs.f_blocks),
           rc ? 0ull : static_cast<unsigned long long>(fs.f_bavail));
  space.detail = text;
  if (rc || !fs.f_frsize || !fs.f_blocks) return space;
  space.ok = true;
  space.bytes = static_cast<std::uint64_t>(fs.f_bavail) * fs.f_frsize;
#else
  // In order, each tried only when the one before gave nothing (S4 01.10: this title's sandbox
  // answers fstatfs with EPERM, on "/" and on /data/orbisdesk/steam-games alike):
  //   1. fstatfs on the folder (libkernel's _fstatfs);
  //   2. statfs by path (FreeBSD 9 syscall 396) on the folder, /data/orbisdesk and /data;
  //   3. getfsstat (syscall 395, MNT_NOWAIT): the mount whose f_mntonname is the longest prefix of
  //      the folder (/data, or /user, which /data lives on).
  // Every attempt goes to `detail`; the first plausible reading is the answer.
  alignas(8) std::uint8_t fs[kStatfsBytes + 64] = {};
  auto attempt = [&](const char* how, const std::string& where, long rc, int error) -> bool {
    char line[160];
    snprintf(line, sizeof(line), "%s%s path=%s rc=%ld errno=%d", space.detail.empty() ? "" : " | ", how, where.c_str(), rc,
             error);
    space.detail += line;
    if (rc != 0) return false;
    const auto read = ReadStatfs(fs);
    space.detail += " " + read.text;
    if (!read.plausible) return false;
    space.ok = true;
    space.bytes = read.bytes;
    space.detail += " used=" + std::string(how);
    return true;
  };
  {
    errno = 0;
    const int fd = open(at.c_str(), O_RDONLY);
    if (fd < 0) {
      attempt("open", at, -1, errno);
    } else {
      errno = 0;
      const int rc = kernel_fstatfs(fd, fs);
      const int error = rc ? errno : 0;
      close(fd);
      if (attempt("fstatfs", at, rc, error)) return space;
    }
  }
  for (const std::string& where : {at, std::string("/data/orbisdesk"), std::string("/data")}) {
    memset(fs, 0, sizeof(fs));
    int error = 0;
    const long rc = RawSyscall(396, reinterpret_cast<long>(where.c_str()), reinterpret_cast<long>(fs), 0, &error);
    if (attempt("statfs", where, rc, error)) return space;
  }
  {
    constexpr int kMounts = 64;
    std::vector<std::uint8_t> list(kMounts * kStatfsBytes);
    int error = 0;
    const long count = RawSyscall(395, reinterpret_cast<long>(list.data()), static_cast<long>(list.size()), 2, &error);
    char line[96];
    snprintf(line, sizeof(line), " | getfsstat rc=%ld errno=%d", count, error);
    space.detail += line;
    std::size_t best = 0;
    Statfs chosen;
    for (long i = 0; i < count && i < kMounts; ++i) {
      const auto read = ReadStatfs(list.data() + i * kStatfsBytes);
      space.detail += " [" + read.on + (read.plausible ? "" : " implausible") + "]";
      const bool prefix = !read.on.empty() && at.compare(0, read.on.size(), read.on) == 0 &&
                          (at.size() == read.on.size() || at[read.on.size()] == '/' || read.on == "/");
      if (read.plausible && prefix && read.on.size() > best) {
        best = read.on.size();
        chosen = read;
      }
    }
    if (best) {
      space.ok = true;
      space.bytes = chosen.bytes;
      space.detail += " chosen " + chosen.text + " used=getfsstat";
    }
  }
#endif
  return space;
}

bool PathExists(const std::string& path) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) return false;
  close(fd);
  return true;
}

bool Installed(const std::string& root) {
  return PathExists(root + "/" + kRecord);
}

bool ReadInstallRecord(const std::string& root, InstalledRecord* record) {
  const int fd = open((root + "/" + kRecord).c_str(), O_RDONLY);
  if (fd < 0) return false;
  std::string text;
  char buffer[16384];
  ssize_t got;
  while ((got = read(fd, buffer, sizeof(buffer))) > 0 && text.size() < (1u << 20)) text.append(buffer, static_cast<std::size_t>(got));
  close(fd);
  const auto parsed = steam::json::Parse(text);
  if (!parsed || !parsed->is_object()) return false;
  auto string = [&](const char* key) -> std::string {
    const auto* value = parsed->Find(key);
    return value && value->is_string() ? value->text() : std::string();
  };
  auto boolean = [&](const char* key) {
    const auto* value = parsed->Find(key);
    return value && value->is_bool() && value->boolean();
  };
  const auto* format = parsed->Find("format");
  record->format = format && format->AsUint64() ? static_cast<int>(*format->AsUint64()) : 0;
  record->language = string("language");
  record->executable = string("executable");
  record->arch = string("arch");
  record->steamstub = boolean("steamstub");
  record->steam_api = boolean("steam_api");
  if (const auto* bytes = parsed->Find("bytes"); bytes && bytes->AsUint64()) record->bytes = *bytes->AsUint64();
  record->steam_api_paths.clear();
  if (const auto* paths = parsed->Find("steam_api_paths"); paths && paths->is_array())
    for (const auto& path : paths->array())
      if (path.is_string() && steam::RelativeGamePath(path.text()) == path.text()) record->steam_api_paths.push_back(path.text());
  return true;
}

bool PlanInstall(const steam::AppInfo& app, const std::vector<steam::AppInfo>& dlc_apps,
                 const steam::AcquisitionResult& licenses, const std::string& language, NoteFn note,
                 InstallPlan* plan) {
  plan->app = app.app_id;
  plan->name = app.name;
  plan->install_dir = app.install_dir;
  std::set<std::uint32_t> owned = licenses.owned_apps;
  owned.insert(app.app_id);
  steam::DepotSelection selection;
  selection.language = language.empty() ? "english" : language;
  steam::SelectionResult selected;
  // licenses the CM didn't read are unknown (every depot passes that check), not an empty grant
  const std::optional<std::set<std::uint32_t>> owned_depots =
      licenses.ok() ? std::optional<std::set<std::uint32_t>>(licenses.owned_depots) : std::nullopt;
  const bool any = steam::SelectDepots(app, dlc_apps, owned, owned_depots, selection, &selected);
  std::map<std::string, int> reasons;
  for (const auto& rejected : selected.rejected) ++reasons[rejected.reason];
  std::string reason_text;
  for (const auto& [reason, count] : reasons) reason_text += " " + reason + "=" + std::to_string(count);
  note("PWSTEAM plan depots=%zu dlc_apps=%zu rejected=%zu%s language=%s asked=%s carried=%zu", selected.depots.size(),
       dlc_apps.size(), selected.rejected.size(), reason_text.c_str(), selected.effective_language.c_str(),
       selection.language.c_str(), selected.languages.size());
  plan->languages = selected.languages;
  const auto missing = steam::MissingBaseDepots(app, owned_depots, selected.depots);
  if (!any || !missing.empty()) {
    note("PWSTEAM plan none missing_base=%zu", missing.size());
    plan->failure = !missing.empty()          ? "STEAM DOES NOT GRANT ACCESS TO PART OF THIS GAME."
                    : selected.depots.empty() ? "THERE IS NO WINDOWS CONTENT TO INSTALL."
                                              : "THIS VERSION HAS NO CONTENT OF THE GAME ITSELF.";
    return false;
  }
  plan->depots = std::move(selected.depots);
  plan->language = selected.effective_language;
  steam::DepotBytes(plan->depots, &plan->install_bytes, &plan->download_bytes);
  std::vector<steam::AppLaunch> launches;
  std::string reason;
  std::size_t unusable = 0;
  if (steam::EligibleLaunches(app, owned, "", &launches, &reason)) {
    for (const auto& entry : launches) {
      const auto executable = steam::RelativeGamePath(entry.executable);
      if (!executable) {
        ++unusable;
        continue;
      }
      Launch launch;
      launch.executable = *executable;
      launch.arguments = entry.arguments;
      if (!entry.working_directory.empty()) {
        const auto folder = steam::RelativeGamePath(entry.working_directory, true);
        if (!folder) {
          ++unusable;
          continue;
        }
        launch.working_dir = *folder;
      }
      launch.description = entry.description.value_or("");
      launch.type = entry.type;
      plan->launches.push_back(std::move(launch));
    }
  }
  if (!plan->launches.empty()) plan->executable = plan->launches.front().executable;
  note("PWSTEAM plan install_bytes=%llu download_bytes=%llu launches=%zu usable=%zu unusable=%zu",
       static_cast<unsigned long long>(plan->install_bytes), static_cast<unsigned long long>(plan->download_bytes),
       launches.size(), plan->launches.size(), unusable);
  return true;
}

InstallResult RunInstall(const std::string& ca, steam::CmClient& cm, const playden::StoredSession& session,
                         const InstallPlan& plan, const std::string& root, const std::atomic<bool>& cancel,
                         bool unmeasured_ok, InstallProgress* progress, NoteFn note, const Precheck* precheck) {
  InstallResult result;
  const auto started = NowMs();
  auto fail = [&](const char* step, std::string text) {
    result.canceled = cancel.load();
    result.failure = result.canceled ? "INSTALL PAUSED. WHAT WAS DOWNLOADED STAYS AND THE NEXT INSTALL RESUMES IT."
                                     : std::move(text);
    note("PWSTEAM install stop step=%s canceled=%d", step, result.canceled);
    return result;
  };

  // depot keys, servers and manifests: the precheck's, when it fetched them for this plan
  std::shared_ptr<const Prepared> prepared;
  if (precheck && precheck->prepared && precheck->prepared->app == plan.app && precheck->prepared->depot_ids == DepotIds(plan)) {
    prepared = precheck->prepared;
    note("PWSTEAM install from_precheck=1 servers=%zu depots=%zu chunks=%zu", prepared->servers.size(), prepared->depots.size(),
         prepared->chunks.size());
  } else {
    auto own = std::make_shared<Prepared>();
    const char* step = "";
    std::string failure;
    if (!PrepareDepots(ca, cm, session, plan, cancel, note, own.get(), &step, &failure)) return fail(step, failure);
    prepared = std::move(own);
  }
  const std::vector<steam::ContentServer>& servers = prepared->servers;
  const std::vector<Depot>& depots = prepared->depots;

  std::vector<std::string> folders;
  const std::map<std::string, Placement> files = MergeDepots(depots, &folders, &result.links);
  std::uint64_t total = 0, chunks = 0;
  for (const auto& [key, placed] : files) {
    total += placed.file->size;
    chunks += placed.file->chunks.size();
  }
  result.files = static_cast<std::uint32_t>(files.size());
  progress->total_bytes = total;
  progress->files_total = result.files;
  for (const auto& [key, placed] : files) {
    const auto name = Lower(placed.file->path);
    const auto slash = name.rfind('/');
    const auto base = slash == std::string::npos ? name : name.substr(slash + 1);
    if (base == "steam_api.dll" || base == "steam_api64.dll") {
      result.steam_api = true;
      result.steam_api_paths.push_back(placed.file->path);
    }
  }
  note("PWSTEAM install merged depots=%zu files=%u folders=%zu links=%u chunks=%llu bytes=%llu steam_api=%d", depots.size(),
       result.files, folders.size(), result.links, static_cast<unsigned long long>(chunks),
       static_cast<unsigned long long>(total), result.steam_api);

  // the folder, its space and every file at its final size (what is there already counts). A record
  // from an earlier install goes first: until this one passes, the folder is not a finished install.
  if (!MakeParents(root + "/")) return fail("mkdir", "COULD NOT CREATE THE GAME FOLDER.");
  unlink((root + "/" + kRecord).c_str());
  std::uint64_t present = 0;
  for (const auto& [key, placed] : files) {
    const int fd = open((root + "/" + placed.file->path).c_str(), O_RDONLY);
    if (fd < 0) continue;
    present += std::min(FileSize(fd), placed.file->size);
    close(fd);
  }
  const auto space = MeasureFreeSpace(root);
  const std::uint64_t need = total - present;
  // the measurement's attempts are on the "plan space" lines; here only its outcome and method
  const auto used = space.detail.rfind("used=");
  note("PWSTEAM install space ok=%d free=%llu present=%llu need=%llu unmeasured_ok=%d %s", space.ok,
       static_cast<unsigned long long>(space.bytes), static_cast<unsigned long long>(present),
       static_cast<unsigned long long>(need), unmeasured_ok,
       used == std::string::npos ? "used=none" : space.detail.substr(used).c_str());
  if (!space.ok && !unmeasured_ok) return fail("space_unmeasured", "COULD NOT MEASURE THE FREE SPACE.");
  if (space.ok && space.bytes < need + kSpaceMargin)
    return fail("space", "NOT ENOUGH FREE SPACE: NEEDS " + std::to_string((need + kSpaceMargin) >> 20) +
                             " MB AND THERE ARE " + std::to_string(space.bytes >> 20) + " MB.");
  for (const auto& folder : folders)
    if (!MakeParents(root + "/" + folder + "/")) return fail("mkdir", "COULD NOT CREATE A GAME FOLDER.");
  for (const auto& [key, placed] : files) {
    const std::string path = root + "/" + placed.file->path;
    int fd = -1;
    if (!MakeParents(path) || (fd = open(path.c_str(), O_RDWR | O_CREAT, 0644)) < 0)
      return fail("create", "COULD NOT CREATE A GAME FILE.");
    const bool sized = FileSize(fd) == placed.file->size || ftruncate(fd, static_cast<off_t>(placed.file->size)) == 0;
    close(fd);
    if (!sized) return fail("size", "COULD NOT SIZE A GAME FILE.");
  }
  // the precheck's chunks of the executables go in place: the workers find them there (their SHA-1
  // matches) and fetch them no more
  std::size_t prefetched = 0;
  for (const auto& chunk : prepared->chunks) {
    const auto found = files.find(Lower(chunk.path));
    if (found == files.end() || chunk.offset + chunk.plain.size() > found->second.file->size) continue;
    const int fd = open((root + "/" + found->second.file->path).c_str(), O_RDWR);
    if (fd < 0) continue;
    if (WriteAt(fd, chunk.plain, chunk.offset)) ++prefetched;
    close(fd);
  }
  if (!prepared->chunks.empty()) note("PWSTEAM install prefetched=%zu of=%zu", prefetched, prepared->chunks.size());

  // the chunks, by four workers; a file is checked by whoever places its last chunk
  struct Task {
    const steam::ManifestFile* file;
    std::size_t depot;
    std::size_t chunk;
    std::size_t index;  // the file's index in `state`
  };
  struct FileState {
    std::atomic<std::size_t> left{0};
    std::atomic<bool> bad{false};
    std::atomic<bool> wrote{false};  // a chunk of it was fetched and written in this run
  };
  std::vector<Task> tasks;
  std::vector<std::unique_ptr<FileState>> state;
  std::vector<const steam::ManifestFile*> zero_chunk_files;
  for (const auto& [key, placed] : files) {
    state.push_back(std::make_unique<FileState>());
    state.back()->left = placed.file->chunks.size();
    if (placed.file->chunks.empty()) zero_chunk_files.push_back(placed.file);
    for (std::size_t c = 0; c < placed.file->chunks.size(); ++c)
      tasks.push_back({placed.file, placed.depot, c, state.size() - 1});
  }
  progress->phase = 1;
  std::atomic<std::size_t> next{0};
  std::atomic<std::uint32_t> verified{0}, failed{0};
  std::atomic<std::uint64_t> fetched{0}, reused{0};
  std::atomic<std::uint32_t> chunk_failures{0};
  std::atomic<bool> full{false};  // a write met ENOSPC: every worker stops
  // A file all of whose chunks were found in place, matching their SHA-1, needs no second read: the
  // chunks cover it end to end (ValidateDepotManifest), so its bytes are already checked. A file with a
  // chunk written in this run is hashed whole against the manifest.
  auto covered = [](const steam::ManifestFile& file) {
    std::uint64_t end = 0;
    for (const auto& chunk : file.chunks) {
      if (chunk.offset != end) return false;
      end += chunk.original_size;
    }
    return end == file.size;
  };
  std::atomic<std::uint32_t> files_rehashed{0};
  auto check_file = [&](const steam::ManifestFile& file, bool bad, bool wrote) {
    std::array<std::uint8_t, 20> digest{};
    const bool zero_sha = std::all_of(file.sha_content.begin(), file.sha_content.end(), [](std::uint8_t b) { return !b; });
    bool ok = false;
    if (!bad) {
      if (file.size == 0 && zero_sha) ok = true;
      else if (!wrote && covered(file)) ok = true;
      else {
        ++files_rehashed;
        ok = FileSha1(root + "/" + file.path, &digest) && digest == file.sha_content;
      }
    }
    if (ok) ++verified;
    else ++failed;
    const auto done = ++progress->files_done;
    // a line now and then, so a long run shows in the log whether it fetches or only checks
    if (done % 250 == 0)
      note("PWSTEAM install progress files=%u/%u reused=%llu fetched=%llu failed=%u", done, progress->files_total.load(),
           static_cast<unsigned long long>(progress->reused_bytes.load()),
           static_cast<unsigned long long>(progress->fetched_bytes.load()), failed.load());
  };
  auto worker = [&](int id) {
    steam::CdnClient client(ca);
    std::vector<std::uint8_t> present_bytes, encrypted, plain;
    for (;;) {
      if (cancel.load() || full.load()) return;
      const std::size_t at = next++;
      if (at >= tasks.size()) return;
      const auto& task = tasks[at];
      const auto& chunk = task.file->chunks[task.chunk];
      const std::string path = root + "/" + task.file->path;
      bool ok = false;
      const int fd = open(path.c_str(), O_RDWR);
      if (fd >= 0) {
        present_bytes.resize(chunk.original_size);
        if (ReadAt(fd, present_bytes.data(), present_bytes.size(), chunk.offset) &&
            Sha1Of(present_bytes.data(), present_bytes.size(), chunk.sha)) {
          ok = true;
          reused += chunk.original_size;
          progress->reused_bytes += chunk.original_size;
        }
        const std::uint32_t depot_id = depots[task.depot].manifest.depot_id;
        for (int attempt = 0; !ok && attempt < 3 && !cancel.load(); ++attempt) {
          const auto& server = servers[(static_cast<std::size_t>(id) + static_cast<std::size_t>(attempt)) % servers.size()];
          encrypted.clear();
          plain.clear();
          if (client.Chunk(server, depot_id, Hex(chunk.sha), chunk.compressed_size + 4096, cancel, &encrypted) !=
              steam::CdnError::kNone)
            continue;
          if (steam::ProcessDepotChunk(encrypted, depots[task.depot].key, chunk.original_size, chunk.crc, chunk.sha,
                                       &plain) != steam::ChunkError::kNone)
            continue;
          if (!WriteAt(fd, plain, chunk.offset)) {
            const int error = errno;
            if (error == ENOSPC && !full.exchange(true)) note("PWSTEAM install write errno=%d drive_full=1", error);
            else if (error != ENOSPC && chunk_failures < 8) note("PWSTEAM install write errno=%d", error);
            break;
          }
          ok = true;
          state[task.index]->wrote = true;
          fetched += encrypted.size();
          progress->fetched_bytes += encrypted.size();
        }
        close(fd);
      }
      if (!ok) {
        if (cancel.load() || full.load()) return;
        state[task.index]->bad = true;
        if (chunk_failures++ < 8) note("PWSTEAM install chunk failed worker=%d %s", id, client.last_failure().c_str());
      }
      progress->done_bytes += chunk.original_size;
      if (--state[task.index]->left == 0)
        check_file(*task.file, state[task.index]->bad.load(), state[task.index]->wrote.load());
    }
  };
  for (const auto* file : zero_chunk_files) check_file(*file, false, false);
  std::vector<std::thread> workers;
  for (int i = 0; i < kWorkers; ++i) workers.emplace_back(worker, i);
  for (auto& thread : workers) thread.join();
  result.verified = verified;
  result.failed = failed;
  result.fetched = fetched;
  result.reused = reused;
  result.bytes = total;
  result.ms = NowMs() - started;
  note("PWSTEAM install files=%u verified=%u failed=%u fetched=%llu reused=%llu rehashed=%u ms=%llu kib_s=%llu canceled=%d",
       result.files, result.verified, result.failed, static_cast<unsigned long long>(result.fetched),
       static_cast<unsigned long long>(result.reused), files_rehashed.load(), static_cast<unsigned long long>(result.ms),
       static_cast<unsigned long long>(result.ms ? result.fetched * 1000 / 1024 / result.ms : 0), cancel.load());
  if (cancel.load()) return fail("download", "");
  if (full.load())
    return fail("drive_full", "THE CONSOLE RAN OUT OF SPACE. WHAT WAS DOWNLOADED STAYS: FREE SOME SPACE AND INSTALL AGAIN.");
  if (result.failed || result.verified != result.files)
    return fail("verify", "SOME FILES DID NOT DOWNLOAD CORRECTLY. INSTALL AGAIN TO RETRY.");

  // the executable, then the record
  // Paths in the record are as installed on disk: appinfo's case can differ from the depots' (Windows
  // doesn't care, the console's file system does).
  progress->phase = 2;
  std::map<std::string, std::string> folder_case;
  for (const auto& folder : folders) folder_case[Lower(folder)] = folder;
  std::vector<Launch> launches = plan.launches;
  for (std::size_t i = 0; i < launches.size(); ++i) {
    LaunchCheck check;
    const auto found = files.find(Lower(launches[i].executable));
    if (found != files.end()) {
      launches[i].executable = found->second.file->path;
      ReadExecutable(root + "/" + launches[i].executable, &check, i, note);
    } else {
      note("PWSTEAM install exe entry=%zu missing_from_depots=1", i);
    }
    if (const auto folder = folder_case.find(Lower(launches[i].working_dir)); folder != folder_case.end())
      launches[i].working_dir = folder->second;
    result.checks.push_back(check);
  }
  result.launches = launches;
  if (!result.checks.empty()) {
    result.arch = result.checks.front().arch;
    result.steamstub = result.checks.front().steamstub;
  }
  std::string record = "{\n \"format\": 2,\n \"app\": " + std::to_string(plan.app) + ",\n \"name\": " + JsonText(plan.name) +
                       ",\n \"installdir\": " + JsonText(plan.install_dir) + ",\n \"language\": " + JsonText(plan.language) +
                       ",\n \"branch\": \"public\",\n \"depots\": [";
  for (std::size_t d = 0; d < depots.size(); ++d)
    record += std::string(d ? ", " : "") + "{\"id\": " + std::to_string(depots[d].manifest.depot_id) +
              ", \"manifest\": \"" + std::to_string(depots[d].manifest.gid) + "\"}";
  record += "],\n \"files\": " + std::to_string(result.files) + ",\n \"bytes\": " + std::to_string(total) +
            ",\n \"executable\": " + JsonText(launches.empty() ? std::string() : launches.front().executable) +
            ",\n \"arch\": " + JsonText(result.arch) + ",\n \"steamstub\": " + (result.steamstub ? "true" : "false") +
            ",\n \"launches\": [";
  for (std::size_t i = 0; i < launches.size(); ++i) {
    const auto& launch = launches[i];
    const auto& check = result.checks[i];
    record += std::string(i ? "," : "") + "\n  {\"executable\": " + JsonText(launch.executable) +
              ", \"arguments\": " + JsonText(launch.arguments) + ", \"working_dir\": " + JsonText(launch.working_dir) +
              ", \"description\": " + JsonText(launch.description) + ", \"type\": " + JsonText(launch.type) +
              ", \"present\": " + (check.present ? "true" : "false") + ", \"pe\": " + (check.pe ? "true" : "false") +
              ", \"arch\": " + JsonText(check.arch) + ", \"steamstub\": " + (check.steamstub ? "true" : "false") + "}";
  }
  record += std::string(launches.empty() ? "]" : "\n ]") + ",\n \"steam_api\": " + (result.steam_api ? "true" : "false") +
            ",\n \"steam_api_paths\": [";
  for (std::size_t i = 0; i < result.steam_api_paths.size(); ++i)
    record += std::string(i ? ", " : "") + JsonText(result.steam_api_paths[i]);
  record += "],\n \"installed_at\": " + std::to_string(time(nullptr)) + "\n}\n";
  const std::string record_path = root + "/" + kRecord;
  const int fd = open((record_path + ".tmp").c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
  const bool written = fd >= 0 && write(fd, record.data(), record.size()) == static_cast<ssize_t>(record.size()) &&
                       fsync(fd) == 0;
  if (fd >= 0) close(fd);
  if (!written || rename((record_path + ".tmp").c_str(), record_path.c_str()))
    return fail("record", "COULD NOT WRITE THE INSTALL RECORD.");
  result.ok = true;
  note("PWSTEAM install done");
  return result;
}


namespace {

// One folder's entries, depth first. `relative`: the folder's path below the game's root ("" for the
// root). The root's install record is left for the caller.
void RemoveEntries(const std::string& root, const std::string& relative, UninstallResult* result,
                   void (*progress)(std::uint64_t)) {
  const std::string folder = relative.empty() ? root : root + "/" + relative;
  const auto fail = [&](const std::string& path, int error) {
    ++result->failures;
    if (!result->first_errno) {
      result->first_errno = error;
      result->first_failure = path.empty() ? "." : path;
    }
  };
  const int fd = open(folder.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
  if (fd < 0) {
    fail(relative, errno);
    return;
  }
  DIR* listing = fdopendir(fd);
  if (!listing) {
    fail(relative, errno);
    close(fd);
    return;
  }
  std::vector<std::string> names;
  for (errno = 0; dirent* entry = readdir(listing); errno = 0) {
    const std::string name = entry->d_name;
    if (name == "." || name == "..") continue;
    if (relative.empty() && name == kRecord) continue;
    names.push_back(name);
  }
  if (errno) fail(relative, errno);
  closedir(listing);
  for (const auto& name : names) {
    const std::string inner = relative.empty() ? name : relative + "/" + name;
    const std::string path = root + "/" + inner;
    // a folder opens with O_DIRECTORY | O_NOFOLLOW; a file or a link doesn't, and is unlinked
    const int probe = open(path.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (probe >= 0) {
      close(probe);
      RemoveEntries(root, inner, result, progress);
      if (rmdir(path.c_str())) fail(inner, errno);
      else ++result->folders;
    } else if (unlink(path.c_str())) {
      fail(inner, errno);
    } else if (++result->files % 500 == 0 && progress) {
      progress(result->files);
    }
  }
}

}  // namespace

UninstallResult RemoveGameFolder(const std::string& root, NoteFn note, void (*progress)(std::uint64_t files)) {
  UninstallResult result;
  note("PWSTEAM uninstall remove start record=%d", Installed(root));
  RemoveEntries(root, "", &result, progress);
  if (!result.failures) {
    const std::string record = root + "/" + kRecord;
    if (unlink(record.c_str()) && errno != ENOENT) {
      result.failures = 1;
      result.first_errno = errno;
      result.first_failure = kRecord;
    } else if (rmdir(root.c_str())) {
      result.failures = 1;
      result.first_errno = errno;
      result.first_failure = ".";
    }
  }
  result.ok = !result.failures && !PathExists(root);
  // the failing path goes on the screen only: a game's file names can name the game
  note("PWSTEAM uninstall remove ok=%d files=%llu folders=%llu failures=%llu errno=%d", result.ok,
       static_cast<unsigned long long>(result.files), static_cast<unsigned long long>(result.folders),
       static_cast<unsigned long long>(result.failures), result.first_errno);
  return result;
}

}  // namespace orbisdesk
