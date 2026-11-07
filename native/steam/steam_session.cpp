// SPDX-License-Identifier: GPL-3.0-or-later
// S3's saved session (steam_session.h).
// session.key: 32 random bytes, 0600, written once.
// session.bin: "ODSS" 1, a 12-byte nonce, then AES-256-GCM over the fields below with "ODSS1" as
// associated data, then the 16-byte tag. Fields: steam_id (u64), cell flag (u8) and cell (u32), then
// account name, refresh token and access token, each a u32 length and its bytes. All little-endian.
#include "steam_session.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

#include <algorithm>
#include <cstdint>
#include <vector>

#include <mbedtls/gcm.h>
#include <mbedtls/platform_util.h>

#include "steam/secret.h"

namespace orbisdesk {
namespace {

using Bytes = std::vector<std::uint8_t>;
constexpr std::uint8_t kMagic[5] = {'O', 'D', 'S', 'S', 1};
constexpr std::size_t kKeyBytes = 32, kNonceBytes = 12, kTagBytes = 16;
constexpr std::size_t kMaxFile = 64 * 1024, kMaxString = 24 * 1024;

// Clears a buffer that held a secret however the call ends.
struct Wipe {
  Bytes& bytes;
  ~Wipe() {
    if (!bytes.empty()) mbedtls_platform_zeroize(bytes.data(), bytes.size());
  }
};

bool ReadFile(const std::string& path, Bytes* out, bool* missing) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) {
    *missing = errno == ENOENT;
    return false;
  }
  std::uint8_t buffer[4096];
  for (;;) {
    const ssize_t got = read(fd, buffer, sizeof(buffer));
    if (got < 0 && errno == EINTR) continue;
    if (got < 0 || out->size() + static_cast<std::size_t>(got) > kMaxFile) {
      mbedtls_platform_zeroize(buffer, sizeof(buffer));
      close(fd);
      return false;
    }
    if (got == 0) break;
    out->insert(out->end(), buffer, buffer + got);
  }
  mbedtls_platform_zeroize(buffer, sizeof(buffer));
  close(fd);
  return true;
}

// Writes `bytes` to a new 0600 file at path.tmp, syncs it and renames it to path.
bool WriteFile(const std::string& path, const Bytes& bytes) {
  const std::string temporary = path + ".tmp";
  unlink(temporary.c_str());
  const int fd = open(temporary.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
  if (fd < 0) return false;
  std::size_t done = 0;
  while (done < bytes.size()) {
    const ssize_t put = write(fd, bytes.data() + done, bytes.size() - done);
    if (put < 0 && errno == EINTR) continue;
    if (put <= 0) break;
    done += static_cast<std::size_t>(put);
  }
  const bool ok = done == bytes.size() && fsync(fd) == 0;
  close(fd);
  if (!ok || rename(temporary.c_str(), path.c_str())) {
    unlink(temporary.c_str());
    return false;
  }
  return true;
}

bool Random(std::uint8_t* out, std::size_t size) {
  const int fd = open("/dev/urandom", O_RDONLY);
  if (fd < 0) return false;
  std::size_t done = 0;
  while (done < size) {
    const ssize_t got = read(fd, out + done, size - done);
    if (got < 0 && errno == EINTR) continue;
    if (got <= 0) break;
    done += static_cast<std::size_t>(got);
  }
  close(fd);
  return done == size;
}

void Put(Bytes& out, std::uint64_t value, int bytes) {
  for (int i = 0; i < bytes; ++i) out.push_back(static_cast<std::uint8_t>(value >> (8 * i)));
}
void PutString(Bytes& out, const std::string& value) {
  Put(out, value.size(), 4);
  out.insert(out.end(), value.begin(), value.end());
}

class Reader {
 public:
  explicit Reader(const Bytes& bytes) : bytes_(bytes) {}
  bool Get(std::uint64_t* value, int bytes) {
    if (bytes_.size() - at_ < static_cast<std::size_t>(bytes)) return false;
    *value = 0;
    for (int i = 0; i < bytes; ++i) *value |= static_cast<std::uint64_t>(bytes_[at_++]) << (8 * i);
    return true;
  }
  bool GetString(std::string* value) {
    std::uint64_t size = 0;
    if (!Get(&size, 4) || size > kMaxString || size > bytes_.size() - at_) return false;
    value->assign(reinterpret_cast<const char*>(bytes_.data() + at_), size);
    at_ += size;
    return true;
  }
  bool done() const { return at_ == bytes_.size(); }

 private:
  const Bytes& bytes_;
  std::size_t at_ = 0;
};

// The key from session.key; with `create`, a new one when there is none.
SessionFileError Key(const std::string& dir, bool create, Bytes* key) {
  const std::string path = dir + "/session.key";
  bool missing = false;
  if (ReadFile(path, key, &missing)) return key->size() == kKeyBytes ? SessionFileError::kNone : SessionFileError::kFormat;
  if (!missing) return SessionFileError::kRead;
  if (!create) return SessionFileError::kMissing;
  key->assign(kKeyBytes, 0);
  if (!Random(key->data(), key->size())) return SessionFileError::kRandom;
  return WriteFile(path, *key) ? SessionFileError::kNone : SessionFileError::kWrite;
}

}  // namespace

const char* SessionFileErrorName(SessionFileError error) {
  switch (error) {
    case SessionFileError::kNone: return "none";
    case SessionFileError::kMissing: return "missing";
    case SessionFileError::kRead: return "read";
    case SessionFileError::kFormat: return "format";
    case SessionFileError::kDecrypt: return "decrypt";
    case SessionFileError::kWrite: return "write";
    case SessionFileError::kRandom: return "random";
  }
  return "unknown";
}

SessionFileError SessionFile::Load(playden::StoredSession* session) const {
  Bytes sealed, key, plain;
  Wipe wipe_key{key}, wipe_plain{plain};
  bool missing = false;
  if (!ReadFile(dir_ + "/session.bin", &sealed, &missing))
    return missing ? SessionFileError::kMissing : SessionFileError::kRead;
  if (sealed.size() < sizeof(kMagic) + kNonceBytes + kTagBytes ||
      !std::equal(kMagic, kMagic + sizeof(kMagic), sealed.begin()))
    return SessionFileError::kFormat;
  if (const auto got = Key(dir_, false, &key); got != SessionFileError::kNone) return got;
  const std::uint8_t* nonce = sealed.data() + sizeof(kMagic);
  const std::uint8_t* body = nonce + kNonceBytes;
  const std::size_t body_size = sealed.size() - sizeof(kMagic) - kNonceBytes - kTagBytes;
  plain.assign(body_size, 0);
  mbedtls_gcm_context gcm;
  mbedtls_gcm_init(&gcm);
  int rc = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key.data(), 256);
  if (!rc)
    rc = mbedtls_gcm_auth_decrypt(&gcm, body_size, nonce, kNonceBytes, kMagic, sizeof(kMagic), body + body_size,
                                  kTagBytes, body, plain.data());
  mbedtls_gcm_free(&gcm);
  if (rc) return SessionFileError::kDecrypt;
  Reader reader(plain);
  std::uint64_t steam_id = 0, has_cell = 0, cell = 0;
  playden::StoredSession loaded;
  if (!reader.Get(&steam_id, 8) || !reader.Get(&has_cell, 1) || !reader.Get(&cell, 4) ||
      !reader.GetString(&loaded.account_name) || !reader.GetString(&loaded.refresh_token) ||
      !reader.GetString(&loaded.access_token) || !reader.done() || has_cell > 1) {
    playden::steam::ZeroizeSecret(loaded.refresh_token);
    playden::steam::ZeroizeSecret(loaded.access_token);
    return SessionFileError::kFormat;
  }
  loaded.steam_id = steam_id;
  if (has_cell) loaded.cell_id = static_cast<std::uint32_t>(cell);
  *session = std::move(loaded);
  return SessionFileError::kNone;
}

SessionFileError SessionFile::Save(const playden::StoredSession& session) const {
  Bytes key, plain, sealed;
  Wipe wipe_key{key}, wipe_plain{plain};
  if (const auto got = Key(dir_, true, &key); got != SessionFileError::kNone) return got;
  Put(plain, session.steam_id, 8);
  Put(plain, session.cell_id ? 1 : 0, 1);
  Put(plain, session.cell_id.value_or(0), 4);
  PutString(plain, session.account_name);
  PutString(plain, session.refresh_token);
  PutString(plain, session.access_token);
  sealed.assign(kMagic, kMagic + sizeof(kMagic));
  sealed.resize(sizeof(kMagic) + kNonceBytes + plain.size() + kTagBytes);
  std::uint8_t* nonce = sealed.data() + sizeof(kMagic);
  std::uint8_t* body = nonce + kNonceBytes;
  if (!Random(nonce, kNonceBytes)) return SessionFileError::kRandom;
  mbedtls_gcm_context gcm;
  mbedtls_gcm_init(&gcm);
  int rc = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key.data(), 256);
  if (!rc)
    rc = mbedtls_gcm_crypt_and_tag(&gcm, MBEDTLS_GCM_ENCRYPT, plain.size(), nonce, kNonceBytes, kMagic, sizeof(kMagic),
                                   plain.data(), body, kTagBytes, body + plain.size());
  mbedtls_gcm_free(&gcm);
  if (rc) return SessionFileError::kWrite;
  return WriteFile(dir_ + "/session.bin", sealed) ? SessionFileError::kNone : SessionFileError::kWrite;
}

void SessionFile::Clear() const {
  for (const char* name : {"/session.bin", "/session.key", "/session.bin.tmp", "/session.key.tmp"}) {
    const std::string path = dir_ + name;
    // the bytes first, so a later look at the free blocks finds less
    const int fd = open(path.c_str(), O_WRONLY);
    if (fd >= 0) {
      const off_t size = lseek(fd, 0, SEEK_END);
      std::vector<std::uint8_t> zeros(size > 0 ? static_cast<std::size_t>(size) : 0);
      if (!zeros.empty()) pwrite(fd, zeros.data(), zeros.size(), 0);
      fsync(fd);
      close(fd);
    }
    unlink(path.c_str());
  }
}

}  // namespace orbisdesk
