// SPDX-License-Identifier: GPL-3.0-or-later
// The Steam client's library cache (native/steam/steam_library_cache.inc.cpp): what it writes
// comes back whole, only for the account that wrote it, and a damaged file is never used.
#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdint>
#include <cstdlib>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "steam/backend/cm_client.h"

namespace {
#include "steam_library_cache.inc.cpp"

int failures = 0;
#define CHECK(x)                                                    \
  do {                                                              \
    if (!(x)) {                                                     \
      fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); \
      ++failures;                                                   \
    }                                                               \
  } while (0)

LibraryCache Sample() {
  LibraryCache cache;
  cache.owned = 3;
  cache.apps = {10, 70, 400};
  cache.buffers[10] = std::string("\"10\"\n{\n\t\"common\"\n\t{\n\t\t\"name\"\t\"A\"\n\t}\n}\n");
  cache.buffers[70] = std::string("binary\0with nul", 15);
  // 400: Steam gave no buffer
  auto& l = cache.licenses;
  l.acquired_at = {{10, 1000}, {70, 2000}};
  l.owned_apps = {10, 70, 400};
  l.owned_depots = {11, 71, 228988};
  l.package_apps = {{7, {10, 70}}, {9, {}}};
  l.package_depots = {{7, {11, 71}}};
  l.shared_apps = {400};
  l.skipped_packages = 2;
  return cache;
}

bool Same(const LibraryCache& a, const LibraryCache& b) {
  return a.owned == b.owned && a.apps == b.apps && a.buffers == b.buffers &&
         a.licenses.acquired_at == b.licenses.acquired_at && a.licenses.owned_apps == b.licenses.owned_apps &&
         a.licenses.owned_depots == b.licenses.owned_depots && a.licenses.package_apps == b.licenses.package_apps &&
         a.licenses.package_depots == b.licenses.package_depots && a.licenses.shared_apps == b.licenses.shared_apps &&
         a.licenses.skipped_packages == b.licenses.skipped_packages && b.licenses.ok();
}
}  // namespace

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : "library-cache-sandbox";
  mkdir(dir.c_str(), 0700);
  const std::string path = dir + "/library-cache.bin";
  const std::uint64_t account = 76561197960287930ull, other = 76561197960287931ull;
  const LibraryCache sample = Sample();

  // round trip, in memory and through the file
  const std::string encoded = EncodeLibraryCache(sample, account);
  auto decoded = DecodeLibraryCache(encoded, account);
  CHECK(decoded && Same(sample, *decoded));
  CHECK(encoded.find("76561197960287930") == std::string::npos);
  CHECK(WriteLibraryCache(path, sample, account));
  struct stat st {};
  CHECK(stat(path.c_str(), &st) == 0 && (st.st_mode & 0777) == 0600);
  CHECK(access((path + ".tmp").c_str(), F_OK) != 0);
  auto read = ReadLibraryCache(path, account);
  CHECK(read && Same(sample, *read));

  // another account (or none) never sees it
  CHECK(!ReadLibraryCache(path, other));
  CHECK(!ReadLibraryCache(path, 0));
  CHECK(!WriteLibraryCache(dir + "/none.bin", sample, 0));

  // every cut-short or extended file is refused, as is a changed magic
  for (std::size_t cut = 0; cut < encoded.size(); ++cut) CHECK(!DecodeLibraryCache(encoded.substr(0, cut), account));
  CHECK(!DecodeLibraryCache(encoded + "x", account));
  std::string magic = encoded;
  magic[6] = '2';
  CHECK(!DecodeLibraryCache(magic, account));

  // an empty library is a library
  LibraryCache empty;
  auto empty_back = DecodeLibraryCache(EncodeLibraryCache(empty, account), account);
  CHECK(empty_back && empty_back->apps.empty() && empty_back->owned == 0);

  // sign-out: gone, temporary file too
  CHECK(WriteLibraryCache(path, sample, account));
  const int fd = open((path + ".tmp").c_str(), O_WRONLY | O_CREAT, 0600);
  if (fd >= 0) close(fd);
  DeleteLibraryCache(path);
  CHECK(access(path.c_str(), F_OK) != 0 && access((path + ".tmp").c_str(), F_OK) != 0);
  CHECK(!ReadLibraryCache(path, account));

  printf("library cache: %s\n", failures ? "FAILED" : "ok");
  return failures ? 1 : 0;
}
