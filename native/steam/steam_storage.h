// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "steam_install.h"
#include <atomic>
#include <functional>
#include <string>
#include <vector>

namespace orbisdesk {
struct GameStorage {
  std::string name, mount, library, id;
  bool external = false;
  std::uint64_t device = 0;
  FreeSpace free;
};
std::vector<GameStorage> GameStorages();
bool PrepareGameStorage(GameStorage* storage, std::string* error);
bool GameStorageAvailable(const GameStorage& storage);
std::string StorageGameRoot(const GameStorage& storage, std::uint32_t app);
std::string FindGameRoot(std::uint32_t app);
bool KnownInstalledGame(std::uint32_t app);
bool GameLocationAvailable(std::uint32_t app);
bool RememberGameStorage(std::uint32_t app, const GameStorage& storage, bool installed);
bool ForgetGameStorage(std::uint32_t app);
std::string StorageWindowsPath(const std::string& root, const std::string& relative);
bool StorageForGame(const std::string& root, GameStorage* storage);

struct MoveProgress {
  std::atomic<std::uint64_t> total{0}, copied{0}, verified{0}, files{0}, files_done{0};
  std::atomic<int> phase{0}; // 0 scanning, 1 copying, 2 verifying, 3 committing, 4 cleaning up
};
struct MoveResult {
  bool ok = false, canceled = false, cleanup_pending = false;
  std::string failure, destination;
};
// The source survives copy/verify/cancel errors. Only after the destination,
// shortcut update and location record commit do we remove the owned source.
MoveResult MoveInstalledGame(std::uint32_t app, const std::string& source, GameStorage target,
                            const std::atomic<bool>& cancel, bool unmeasured_ok, MoveProgress* progress,
                            const std::function<bool(const std::string&)>& update_shortcuts, NoteFn note);
bool PendingGameMove(std::uint32_t app);
bool PendingMoveRoute(std::uint32_t app, std::string* source, GameStorage* target);
bool FinishGameMove(std::uint32_t app, MoveProgress* progress, std::string* error, NoteFn note);
#ifdef STEAM_HOST
void StorageTestPaths(const std::string& internal, const std::string& state, const std::vector<std::string>& usb);
#ifdef STEAM_STORAGE_TEST
void StorageTestHook(std::function<void(const char*,const std::string&)> hook);
#endif
#endif
} // namespace orbisdesk
