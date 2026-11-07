// SPDX-License-Identifier: GPL-3.0-or-later
// S3's saved Steam session ("stay signed in", on by the user's choice): the StoredSession sealed with
// AES-256-GCM under a random key kept in a file of its own beside it. The PS4 gives this title no key
// store, so whoever copies both files has the session: the sealing keeps the tokens out of plain
// text (a /data listing, a backup of one file, an FTP glance), it doesn't protect them from someone
// with the whole folder. docs/STEAM_S3.md says so to the user.
#pragma once

#include <optional>
#include <string>

#include "steam/session_store.h"

namespace orbisdesk {

enum class SessionFileError { kNone, kMissing, kRead, kFormat, kDecrypt, kWrite, kRandom };
const char* SessionFileErrorName(SessionFileError error);

class SessionFile {
 public:
  // dir: the folder of session.bin and session.key, which must exist
  explicit SessionFile(std::string dir) : dir_(std::move(dir)) {}
  SessionFileError Load(playden::StoredSession* session) const;
  // Writes session.bin.tmp and renames it; creates the key on first use.
  SessionFileError Save(const playden::StoredSession& session) const;
  // Removes both files (signing out on this console).
  void Clear() const;

 private:
  std::string dir_;
};

}  // namespace orbisdesk
