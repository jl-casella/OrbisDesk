// SPDX-License-Identifier: GPL-3.0-or-later
// The three Storage calls Playden's cm_client.cpp makes (LoadOrCreateDeviceSeed, for its
// file-backed CmClient constructor), for a title that keeps nothing on disk: S2 builds its
// CmClient with hooks and a per-run device identity and never reaches them. Each one fails,
// says so, and never claims a file was read or written. Linking these instead of Playden's
// platform/storage.cpp keeps opendir/readdir (getdents) and seteuid out of the title's imports.
// The client that keeps a device seed (S3) brings the real storage back.
#include "platform/storage.h"

namespace playden {
namespace {
constexpr char kNoStorage[] = "no storage in this title (native/steam/orbis/storage_none.cpp)";
}

Result<void> Storage::EnsureRootDirectory() const {
  return Result<void>::Failure(StorageError::kPermissionFailed, kNoStorage);
}

Result<Bytes> Storage::Read(const std::string&, std::size_t) const {
  return Result<Bytes>::Failure(StorageError::kNotFound, kNoStorage);
}

Result<void> Storage::WriteAtomicPrivate(const std::string&, const Bytes&) const {
  return Result<void>::Failure(StorageError::kWriteFailed, kNoStorage);
}
}  // namespace playden
