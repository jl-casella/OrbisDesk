// SPDX-License-Identifier: GPL-3.0-or-later
// The library as the last load left it, so the client can show it at once and refresh it in the
// background (2026-11-25). Included by steam_client.cpp and by tests/steam_library_cache_host.cpp.
//
// The file (0600, written to a temporary name and renamed) holds what the load got from Steam:
// the owned count, the licenses and each owned app's PICS buffer. The library is rebuilt from them
// exactly as from a network load. It belongs to one account: a key derived from the SteamID
// (not the SteamID itself) is checked before it is used, and signing out deletes it.
//
// Needs <cstdint>, <map>, <set>, <string>, <vector>, <optional>, <fcntl.h>, <unistd.h>, <stdio.h> and
// steam/backend/cm_client.h before it.

struct LibraryCache {
  std::size_t owned = 0;
  std::vector<std::uint32_t> apps;                 // the owned Steam apps, in GetOwnedGames' order
  std::map<std::uint32_t, std::string> buffers;    // app -> PICS VDF text (absent: Steam gave none)
  playden::steam::AcquisitionResult licenses;
};

namespace library_cache {

constexpr char kMagic[8] = {'O', 'D', 'S', 'T', 'L', 'C', '1', '\n'};
constexpr std::uint32_t kMaxCount = 1u << 20;      // apps, licenses entries
constexpr std::uint32_t kMaxBuffer = 16u << 20;    // one app's PICS text

// Tells accounts apart without keeping the SteamID: FNV-1a over the SteamID with a fixed salt.
inline std::uint64_t AccountKey(std::uint64_t steam_id) {
  std::uint64_t hash = 0xcbf29ce484222325ull;
  const char salt[] = "orbisdesk-library-cache";
  for (const char c : salt) hash = (hash ^ static_cast<std::uint8_t>(c)) * 0x100000001b3ull;
  for (int i = 0; i < 8; ++i) hash = (hash ^ ((steam_id >> (8 * i)) & 0xff)) * 0x100000001b3ull;
  return hash;
}

inline void PutU32(std::string* out, std::uint32_t v) {
  for (int i = 0; i < 4; ++i) out->push_back(static_cast<char>((v >> (8 * i)) & 0xff));
}
inline void PutU64(std::string* out, std::uint64_t v) {
  for (int i = 0; i < 8; ++i) out->push_back(static_cast<char>((v >> (8 * i)) & 0xff));
}
inline void PutSet(std::string* out, const std::set<std::uint32_t>& values) {
  PutU32(out, static_cast<std::uint32_t>(values.size()));
  for (const auto v : values) PutU32(out, v);
}
inline void PutLists(std::string* out, const std::map<std::uint32_t, std::vector<std::uint32_t>>& lists) {
  PutU32(out, static_cast<std::uint32_t>(lists.size()));
  for (const auto& [key, values] : lists) {
    PutU32(out, key);
    PutU32(out, static_cast<std::uint32_t>(values.size()));
    for (const auto v : values) PutU32(out, v);
  }
}

struct Reader {
  const std::string& data;
  std::size_t at = 0;
  bool U32(std::uint32_t* v) {
    if (data.size() - at < 4) return false;
    *v = 0;
    for (int i = 0; i < 4; ++i) *v |= static_cast<std::uint32_t>(static_cast<std::uint8_t>(data[at + i])) << (8 * i);
    at += 4;
    return true;
  }
  bool U64(std::uint64_t* v) {
    if (data.size() - at < 8) return false;
    *v = 0;
    for (int i = 0; i < 8; ++i) *v |= static_cast<std::uint64_t>(static_cast<std::uint8_t>(data[at + i])) << (8 * i);
    at += 8;
    return true;
  }
  bool Count(std::uint32_t* n) { return U32(n) && *n <= kMaxCount && static_cast<std::uint64_t>(*n) * 4 <= data.size() - at; }
  bool Set(std::set<std::uint32_t>* values) {
    std::uint32_t n = 0, v = 0;
    if (!Count(&n)) return false;
    for (std::uint32_t i = 0; i < n; ++i) {
      if (!U32(&v)) return false;
      values->insert(v);
    }
    return true;
  }
  bool Lists(std::map<std::uint32_t, std::vector<std::uint32_t>>* lists) {
    std::uint32_t n = 0, key = 0, m = 0, v = 0;
    if (!Count(&n)) return false;
    for (std::uint32_t i = 0; i < n; ++i) {
      if (!U32(&key) || !Count(&m)) return false;
      auto& values = (*lists)[key];
      for (std::uint32_t j = 0; j < m; ++j) {
        if (!U32(&v)) return false;
        values.push_back(v);
      }
    }
    return true;
  }
};

}  // namespace library_cache

std::string EncodeLibraryCache(const LibraryCache& cache, std::uint64_t steam_id) {
  using namespace library_cache;
  std::string out(kMagic, sizeof(kMagic));
  PutU64(&out, AccountKey(steam_id));
  PutU64(&out, cache.owned);
  const auto& l = cache.licenses;
  PutU32(&out, l.skipped_packages);
  PutU32(&out, static_cast<std::uint32_t>(l.acquired_at.size()));
  for (const auto& [app, when] : l.acquired_at) PutU32(&out, app), PutU32(&out, when);
  PutSet(&out, l.owned_apps);
  PutSet(&out, l.owned_depots);
  PutLists(&out, l.package_apps);
  PutLists(&out, l.package_depots);
  PutSet(&out, l.shared_apps);
  PutU32(&out, static_cast<std::uint32_t>(cache.apps.size()));
  for (const auto app : cache.apps) {
    const auto found = cache.buffers.find(app);
    PutU32(&out, app);
    if (found == cache.buffers.end()) {
      PutU32(&out, 0);
      continue;
    }
    PutU32(&out, static_cast<std::uint32_t>(found->second.size()));
    out += found->second;
  }
  return out;
}

// The cache when `data` is a whole one of `steam_id`'s account; nullopt otherwise (another account,
// another format, cut short).
std::optional<LibraryCache> DecodeLibraryCache(const std::string& data, std::uint64_t steam_id) {
  using namespace library_cache;
  if (steam_id == 0 || data.size() < sizeof(kMagic) || data.compare(0, sizeof(kMagic), kMagic, sizeof(kMagic)) != 0)
    return std::nullopt;
  Reader r{data, sizeof(kMagic)};
  std::uint64_t key = 0, owned = 0;
  if (!r.U64(&key) || key != AccountKey(steam_id) || !r.U64(&owned)) return std::nullopt;
  LibraryCache cache;
  cache.owned = static_cast<std::size_t>(owned);
  auto& l = cache.licenses;
  std::uint32_t n = 0;
  if (!r.U32(&l.skipped_packages) || !r.Count(&n)) return std::nullopt;
  for (std::uint32_t i = 0; i < n; ++i) {
    std::uint32_t app = 0, when = 0;
    if (!r.U32(&app) || !r.U32(&when)) return std::nullopt;
    l.acquired_at[app] = when;
  }
  if (!r.Set(&l.owned_apps) || !r.Set(&l.owned_depots) || !r.Lists(&l.package_apps) || !r.Lists(&l.package_depots) ||
      !r.Set(&l.shared_apps) || !r.Count(&n))
    return std::nullopt;
  for (std::uint32_t i = 0; i < n; ++i) {
    std::uint32_t app = 0, size = 0;
    if (!r.U32(&app) || !r.U32(&size) || size > kMaxBuffer || data.size() - r.at < size) return std::nullopt;
    cache.apps.push_back(app);
    if (size) cache.buffers.emplace(app, data.substr(r.at, size));
    r.at += size;
  }
  if (r.at != data.size()) return std::nullopt;
  l.error = playden::steam::CmError::kNone;
  return cache;
}

// Written whole or not at all: a temporary file, synced, renamed over the old one.
bool WriteLibraryCache(const std::string& path, const LibraryCache& cache, std::uint64_t steam_id) {
  if (steam_id == 0) return false;
  const std::string data = EncodeLibraryCache(cache, steam_id);
  const std::string temporary = path + ".tmp";
  const int fd = open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0) return false;
  std::size_t done = 0;
  bool ok = true;
  while (ok && done < data.size()) {
    const ssize_t wrote = write(fd, data.data() + done, data.size() - done);
    if (wrote <= 0) ok = false;
    else done += static_cast<std::size_t>(wrote);
  }
  ok = ok && fsync(fd) == 0;
  close(fd);
  if (!ok || rename(temporary.c_str(), path.c_str()) != 0) {
    unlink(temporary.c_str());
    return false;
  }
  return true;
}

std::optional<LibraryCache> ReadLibraryCache(const std::string& path, std::uint64_t steam_id) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) return std::nullopt;
  std::string data;
  char chunk[65536];
  for (;;) {
    const ssize_t got = read(fd, chunk, sizeof(chunk));
    if (got < 0) {
      close(fd);
      return std::nullopt;
    }
    if (got == 0) break;
    data.append(chunk, static_cast<std::size_t>(got));
    if (data.size() > (256u << 20)) {
      close(fd);
      return std::nullopt;
    }
  }
  close(fd);
  return DecodeLibraryCache(data, steam_id);
}

void DeleteLibraryCache(const std::string& path) {
  unlink(path.c_str());
  unlink((path + ".tmp").c_str());
}
