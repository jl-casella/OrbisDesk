// SPDX-License-Identifier: GPL-3.0-or-later
// Big Picture's covers (docs/STEAM_BIG_PICTURE.md): each game's Steam library cover, fetched once from
// Steam's CDN on a thread of its own, decoded (stb_image, static to this file) and downscaled to 144x216,
// then kept on the console in <dir>/<app>.cov. Where the store says the cover is (GetItems), else the fixed
// library_600x900.jpg, else the landscape header letterboxed. A game with none of them gets a
// <app>.nocover marker and the screens draw a placeholder. The UI thread reads the files lazily and keeps the
// most recent few in memory. Logs carry counts only, never a game.
#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <list>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

#include "steam_draw.h"

namespace orbisdesk {

using CoverNote = void (*)(const char*, ...);
// fetch(url, *body) -> HTTP status (0: no answer); the client passes its HttpClient
using CoverFetch = std::function<long(const std::string& url, std::vector<std::uint8_t>* body, const std::atomic<bool>& cancel)>;

class Covers {
 public:
  static constexpr int kWidth = 144, kHeight = 216;
  ~Covers();
  // starts fetching what isn't cached yet; `changed` runs (on the fetch thread) after each new cover
  void Start(const std::string& dir, std::vector<std::uint32_t> apps, CoverFetch fetch, std::function<void()> changed,
             CoverNote note);
  void Stop();
  // the UI thread: the cover, or nullptr (not cached, none on Steam, unreadable)
  const sd_image* Get(std::uint32_t app);
  // the UI thread: drops what is kept of `app`, so a cover written or deleted since shows at once
  void Forget(std::uint32_t app);

  // decodes a JPEG or PNG and box-filters it to kWidth x kHeight 0xAARRGGBB; false when unreadable (exposed for
  // the host test)
  static bool Decode(const std::uint8_t* data, std::size_t size, std::vector<std::uint32_t>* pixels);
  // a landscape image (the store header) made into a portrait tile: itself across the middle, over a dark
  // blurred fill of its own colours
  static bool DecodeLandscape(const std::uint8_t* data, std::size_t size, std::vector<std::uint32_t>* pixels);
  // Steam's store (IStoreBrowseService/GetItems, no key): where each app's art lives. Many apps keep their
  // library cover under another name (portrait.png, a hashed folder), so the fixed library_600x900.jpg
  // path answers 404 for them (2026-11-25).
  struct StoreArt {
    std::string library;  // the portrait library cover's URL, empty when the store has none
    std::string header;   // the landscape header's URL
    int type = -1;        // the store's app type: 0 a game, 4 a DLC, 5 a soundtrack...; -1 not given
    std::string name;     // the store's name for it
  };
  static constexpr int kStoreGame = 0;
  static std::string StoreItemsUrl(const std::vector<std::uint32_t>& apps);
  // the apps the store answered for (success 1); others are absent
  static std::map<std::uint32_t, StoreArt> ParseStoreItems(const std::string& body);
  static bool Save(const std::string& path, const std::vector<std::uint32_t>& pixels);
  static bool Load(const std::string& path, std::vector<std::uint32_t>* pixels);

 private:
  struct Entry {
    std::vector<std::uint32_t> pixels;
    sd_image image{};
  };
  void Run(std::vector<std::uint32_t> apps, CoverFetch fetch, std::function<void()> changed, CoverNote note);
  std::string dir_;
  std::thread thread_;
  std::atomic<bool> cancel_{false};
  std::mutex mutex_;
  std::set<std::uint32_t> missing_;  // checked and absent: not looked up again this run
  std::map<std::uint32_t, std::unique_ptr<Entry>> cache_;
  std::list<std::uint32_t> order_;  // most recent first
  static constexpr std::size_t kKeep = 40;
};

}  // namespace orbisdesk
