// SPDX-License-Identifier: GPL-3.0-or-later
// Big Picture's covers (steam_covers.h). stb_image (public domain / MIT, the copy the builders pin) is
// compiled static to this file: Playden's own objects define a global stb_image implementation.
#include "../../platform/ps4/pw_trace.h"  // diagnostic lines only with traces
#include "steam_covers.h"

#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cctype>
#include <cstring>
#include <initializer_list>
#include <optional>

#include "steam/backend/json.h"

#define STB_IMAGE_STATIC
#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_JPEG
#define STBI_ONLY_PNG
#define STBI_NO_STDIO
#define STBI_NO_LINEAR
#define STBI_NO_HDR
#define STBI_ASSERT(x) ((void)0)
#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wimplicit-fallthrough"
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#pragma GCC diagnostic ignored "-Wshadow"
#pragma GCC diagnostic ignored "-Wdouble-promotion"
#pragma GCC diagnostic ignored "-Wcast-qual"
#pragma GCC diagnostic ignored "-Wold-style-cast"
#pragma GCC diagnostic ignored "-Wcomma"
#pragma GCC diagnostic ignored "-Wunknown-warning-option"
#endif
#include "stb_image.h"
#if defined(__clang__) || defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

namespace orbisdesk {

namespace {
constexpr char kMagic[4] = {'O', 'D', 'C', '1'};

bool WriteAll(int fd, const void* data, std::size_t size) {
  const char* p = static_cast<const char*>(data);
  while (size) {
    const ssize_t n = write(fd, p, size);
    if (n <= 0) return false;
    p += n;
    size -= static_cast<std::size_t>(n);
  }
  return true;
}

bool Exists(const std::string& path) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) return false;
  close(fd);
  return true;
}

struct Rgb {
  unsigned char* data = nullptr;
  int w = 0, h = 0;
  ~Rgb() {
    if (data) stbi_image_free(data);
  }
};

bool LoadRgb(const std::uint8_t* bytes, std::size_t size, Rgb* image) {
  int channels = 0;
  if (!bytes || size > (8u << 20)) return false;
  image->data = stbi_load_from_memory(bytes, static_cast<int>(size), &image->w, &image->h, &channels, 3);
  return image->data && image->w >= 8 && image->h >= 8;
}

// the (cx, cy, cw, ch) part of `image`, box-filtered into an ow x oh block of `out` (row length `stride`) at
// (ox, oy), each channel times shade/256
void Box(const Rgb& image, int cx, int cy, int cw, int ch, std::uint32_t* out, int stride, int ox, int oy, int ow, int oh,
         unsigned shade) {
  for (int y = 0; y < oh; ++y) {
    const int y0 = cy + y * ch / oh, y1 = std::max(y0 + 1, cy + (y + 1) * ch / oh);
    for (int x = 0; x < ow; ++x) {
      const int x0 = cx + x * cw / ow, x1 = std::max(x0 + 1, cx + (x + 1) * cw / ow);
      unsigned r = 0, g = 0, b = 0, n = 0;
      for (int sy = y0; sy < y1 && sy < image.h; ++sy)
        for (int sx = x0; sx < x1 && sx < image.w; ++sx) {
          const unsigned char* p = image.data + (static_cast<std::size_t>(sy) * image.w + sx) * 3;
          r += p[0], g += p[1], b += p[2], ++n;
        }
      if (!n) n = 1;
      r = r / n * shade / 256, g = g / n * shade / 256, b = b / n * shade / 256;
      out[static_cast<std::size_t>(oy + y) * stride + ox + x] = 0xff000000u | r << 16 | g << 8 | b;
    }
  }
}

std::string UrlEncode(const std::string& text) {
  static const char hex[] = "0123456789ABCDEF";
  std::string out;
  for (const unsigned char c : text) {
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~') out += static_cast<char>(c);
    else out += '%', out += hex[c >> 4], out += hex[c & 15];
  }
  return out;
}

const playden::steam::json::Value* Path(const playden::steam::json::Value& value, std::initializer_list<const char*> keys) {
  const playden::steam::json::Value* at = &value;
  for (const char* key : keys)
    if (!at || !at->is_object() || !(at = at->Find(key))) return nullptr;
  return at;
}

std::string Text(const playden::steam::json::Value* value) {
  return value && value->is_string() ? value->text() : std::string();
}
}  // namespace

bool Covers::Decode(const std::uint8_t* data, std::size_t size, std::vector<std::uint32_t>* pixels) {
  Rgb image;
  if (!LoadRgb(data, size, &image)) return false;
  // the 2:3 middle of the image, box-filtered down
  const int w = image.w, h = image.h;
  int cw = w, ch = h, cx = 0, cy = 0;
  if (w * kHeight > h * kWidth) cw = h * kWidth / kHeight, cx = (w - cw) / 2;
  else ch = w * kHeight / kWidth, cy = (h - ch) / 2;
  pixels->assign(static_cast<std::size_t>(kWidth) * kHeight, 0);
  Box(image, cx, cy, cw, ch, pixels->data(), kWidth, 0, 0, kWidth, kHeight, 256);
  return true;
}

bool Covers::DecodeLandscape(const std::uint8_t* data, std::size_t size, std::vector<std::uint32_t>* pixels) {
  Rgb image;
  if (!LoadRgb(data, size, &image)) return false;
  const int w = image.w, h = image.h;
  pixels->assign(static_cast<std::size_t>(kWidth) * kHeight, 0);
  // the fill: the image's 2:3 middle at 12x18, stretched back up (a cheap blur) and darkened
  constexpr int kSmallW = 12, kSmallH = 18;
  std::uint32_t small[kSmallW * kSmallH];
  int cw = w, ch = h, cx = 0, cy = 0;
  if (w * kHeight > h * kWidth) cw = h * kWidth / kHeight, cx = (w - cw) / 2;
  else ch = w * kHeight / kWidth, cy = (h - ch) / 2;
  Box(image, cx, cy, cw, ch, small, kSmallW, 0, 0, kSmallW, kSmallH, 110);
  for (int y = 0; y < kHeight; ++y) {
    const int fy = std::max(0, (y * kSmallH * 256) / kHeight - 128), y0 = std::min(fy >> 8, kSmallH - 1),
              y1 = std::min(y0 + 1, kSmallH - 1), ty = fy & 255;
    for (int x = 0; x < kWidth; ++x) {
      const int fx = std::max(0, (x * kSmallW * 256) / kWidth - 128), x0 = std::min(fx >> 8, kSmallW - 1),
                x1 = std::min(x0 + 1, kSmallW - 1), tx = fx & 255;
      std::uint32_t mixed = 0xff000000u;
      for (int shift = 0; shift < 24; shift += 8) {
        auto c = [&](int sx, int sy) { return static_cast<int>((small[sy * kSmallW + sx] >> shift) & 255); };
        const int top = c(x0, y0) * (256 - tx) + c(x1, y0) * tx, bottom = c(x0, y1) * (256 - tx) + c(x1, y1) * tx;
        mixed |= static_cast<std::uint32_t>(((top * (256 - ty) + bottom * ty) >> 16) & 255) << shift;
      }
      (*pixels)[static_cast<std::size_t>(y) * kWidth + x] = mixed;
    }
  }
  // the image itself across the tile's width, a little above the middle
  const int fh = std::max(1, std::min(kHeight, kWidth * h / w));
  Box(image, 0, 0, w, h, pixels->data(), kWidth, 0, (kHeight - fh) * 2 / 5, kWidth, fh, 256);
  return true;
}

std::string Covers::StoreItemsUrl(const std::vector<std::uint32_t>& apps) {
  std::string ids;
  for (const auto app : apps) ids += (ids.empty() ? "" : ",") + std::string("{\"appid\":") + std::to_string(app) + "}";
  const std::string input = "{\"ids\":[" + ids +
                            "],\"context\":{\"language\":\"english\",\"country_code\":\"US\"},"
                            "\"data_request\":{\"include_assets\":true}}";
  return "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json=" + UrlEncode(input);
}

std::map<std::uint32_t, Covers::StoreArt> Covers::ParseStoreItems(const std::string& body) {
  std::map<std::uint32_t, StoreArt> art;
  playden::steam::json::Limits limits;
  limits.max_bytes = 4u << 20;
  limits.max_values = 1u << 18;
  const auto root = playden::steam::json::Parse(body, limits);
  if (!root) return art;
  const auto* items = Path(*root, {"response", "store_items"});
  if (!items || !items->is_array()) return art;
  constexpr char kHost[] = "https://shared.akamai.steamstatic.com/store_item_assets/";
  for (const auto& item : items->array()) {
    const auto* id = Path(item, {"id"});
    const auto* success = Path(item, {"success"});
    const auto app = id ? id->AsUint64() : std::nullopt;
    if (!app || !*app || *app > 0xffffffffu || !success || success->AsUint64() != 1u) continue;
    const std::string format = Text(Path(item, {"assets", "asset_url_format"}));
    const auto at = format.find("${FILENAME}");
    // the format is "steam/apps/<app>/${FILENAME}?t=<time>"; only Steam's own relative paths are taken
    if (at == std::string::npos || format.find("://") != std::string::npos || format.find("..") != std::string::npos)
      continue;
    auto url = [&](const std::string& file) {
      if (file.empty() || file.find("..") != std::string::npos || file.find("://") != std::string::npos) return std::string();
      return kHost + format.substr(0, at) + file + format.substr(at + 11);
    };
    StoreArt entry;
    entry.library = url(Text(Path(item, {"assets", "library_capsule"})));
    entry.header = url(Text(Path(item, {"assets", "header"})));
    const auto* type = Path(item, {"type"});
    const auto type_value = type ? type->AsUint64() : std::nullopt;
    if (type_value && *type_value < 1000) entry.type = static_cast<int>(*type_value);
    entry.name = Text(Path(item, {"name"}));
    art[static_cast<std::uint32_t>(*app)] = std::move(entry);
  }
  return art;
}

bool Covers::Save(const std::string& path, const std::vector<std::uint32_t>& pixels) {
  if (pixels.size() != static_cast<std::size_t>(kWidth) * kHeight) return false;
  const std::string temp = path + ".tmp";
  const int fd = open(temp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
  if (fd < 0) return false;
  const std::uint32_t size[2] = {kWidth, kHeight};
  const bool ok = WriteAll(fd, kMagic, 4) && WriteAll(fd, size, sizeof(size)) &&
                  WriteAll(fd, pixels.data(), pixels.size() * 4) && fsync(fd) == 0;
  close(fd);
  if (!ok || rename(temp.c_str(), path.c_str())) {
    unlink(temp.c_str());
    return false;
  }
  return true;
}

bool Covers::Load(const std::string& path, std::vector<std::uint32_t>* pixels) {
  const int fd = open(path.c_str(), O_RDONLY);
  if (fd < 0) return false;
  char magic[4];
  std::uint32_t size[2];
  bool ok = read(fd, magic, 4) == 4 && !memcmp(magic, kMagic, 4) && read(fd, size, sizeof(size)) == sizeof(size) &&
            size[0] == kWidth && size[1] == kHeight;
  if (ok) {
    pixels->resize(static_cast<std::size_t>(kWidth) * kHeight);
    std::size_t done = 0, want = pixels->size() * 4;
    char* p = reinterpret_cast<char*>(pixels->data());
    while (done < want) {
      const ssize_t n = read(fd, p + done, want - done);
      if (n <= 0) break;
      done += static_cast<std::size_t>(n);
    }
    ok = done == want;
  }
  close(fd);
  return ok;
}

Covers::~Covers() { Stop(); }

void Covers::Start(const std::string& dir, std::vector<std::uint32_t> apps, CoverFetch fetch,
                   std::function<void()> changed, CoverNote note) {
  Stop();
  dir_ = dir;
  mkdir(dir_.c_str(), 0755);
  cancel_ = false;
  thread_ = std::thread([this, apps = std::move(apps), fetch = std::move(fetch), changed = std::move(changed), note]() mutable {
    Run(std::move(apps), std::move(fetch), std::move(changed), note);
  });
}

void Covers::Stop() {
  cancel_ = true;
  if (thread_.joinable()) thread_.join();
}

void Covers::Run(std::vector<std::uint32_t> apps, CoverFetch fetch, std::function<void()> changed, CoverNote note) {
  int cached = 0, fetched = 0, missing = 0, failed = 0, store = 0, portrait = 0, header = 0, retried = 0;
  // what still needs a look; a "none" marker of before 2026-11-25 (only library_600x900.jpg was tried) is
  // looked at once more
  std::vector<std::uint32_t> pending;
  for (const auto app : apps) {
    const std::string base = dir_ + "/" + std::to_string(app);
    if (Exists(base + ".cov") || Exists(base + ".nocover")) {
      ++cached;
      continue;
    }
    if (Exists(base + ".none")) {
      unlink((base + ".none").c_str());
      ++retried;
    }
    pending.push_back(app);
  }
  // where the store keeps each one's art, 20 apps a request; an app the store did not answer for only has
  // the fixed paths
  std::map<std::uint32_t, StoreArt> art;
  bool store_answered = true;
  constexpr std::size_t kBatch = 20;
  for (std::size_t first = 0; first < pending.size() && !cancel_; first += kBatch) {
    const std::vector<std::uint32_t> batch(pending.begin() + first, pending.begin() + std::min(pending.size(), first + kBatch));
    std::vector<std::uint8_t> body;
    const long status = fetch(StoreItemsUrl(batch), &body, cancel_);
    if (status != 200) {
      store_answered = false;
      continue;
    }
    for (auto& [app, entry] : ParseStoreItems(std::string(body.begin(), body.end()))) {
      art[app] = std::move(entry);
      ++store;
    }
  }
  enum Kind { kPortrait, kHeader };
  for (const auto app : pending) {
    if (cancel_) break;
    const std::string base = dir_ + "/" + std::to_string(app);
    // the store's library cover, the fixed library path on both hosts, then the landscape header letterboxed
    std::vector<std::pair<std::string, Kind>> urls;
    const auto found = art.find(app);
    if (found != art.end() && !found->second.library.empty()) urls.emplace_back(found->second.library, kPortrait);
    for (const char* pattern : {"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/%u/library_600x900.jpg",
                                "https://steamcdn-a.akamaihd.net/steam/apps/%u/library_600x900.jpg"}) {
      char url[160];
      snprintf(url, sizeof(url), pattern, app);
      urls.emplace_back(url, kPortrait);
    }
    if (found != art.end() && !found->second.header.empty()) urls.emplace_back(found->second.header, kHeader);
    char plain_header[160];
    snprintf(plain_header, sizeof(plain_header), "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/%u/header.jpg",
             app);
    urls.emplace_back(plain_header, kHeader);
    // absent only when every place answered that it has none and the store was asked
    bool done = false, absent = store_answered;
    for (const auto& [url, kind] : urls) {
      std::vector<std::uint8_t> body;
      const long status = fetch(url, &body, cancel_);
      if (cancel_) break;
      if (status == 404 || status == 403) continue;
      if (status != 200) {
        absent = false;  // no answer: try again next run
        continue;
      }
      std::vector<std::uint32_t> pixels;
      const bool decoded = kind == kPortrait ? Decode(body.data(), body.size(), &pixels)
                                             : DecodeLandscape(body.data(), body.size(), &pixels);
      if (decoded && Save(base + ".cov", pixels)) {
        done = true;
        ++fetched;
        ++(kind == kPortrait ? portrait : header);
        {
          std::lock_guard<std::mutex> lock(mutex_);
          missing_.erase(app);
        }
        if (changed) changed();
        break;
      }
      absent = false;
    }
    if (done || cancel_) continue;
    if (absent) {
      ++missing;
      const int fd = open((base + ".nocover").c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
      if (fd >= 0) close(fd);
    } else {
      ++failed;
    }
  }
  if (note && pw_trace_on())
    note("PWSTEAM covers games=%zu cached=%d fetched=%d portrait=%d header=%d none=%d failed=%d retried=%d store=%d "
         "store_ok=%d canceled=%d",
         apps.size(), cached, fetched, portrait, header, missing, failed, retried, store, store_answered ? 1 : 0,
         cancel_.load() ? 1 : 0);
}

void Covers::Forget(std::uint32_t app) {
  std::lock_guard<std::mutex> lock(mutex_);
  cache_.erase(app);
  order_.remove(app);
  missing_.erase(app);
}

const sd_image* Covers::Get(std::uint32_t app) {
  std::lock_guard<std::mutex> lock(mutex_);
  const auto found = cache_.find(app);
  if (found != cache_.end()) {
    order_.remove(app);
    order_.push_front(app);
    return &found->second->image;
  }
  if (dir_.empty() || missing_.count(app)) return nullptr;
  auto entry = std::make_unique<Entry>();
  if (!Load(dir_ + "/" + std::to_string(app) + ".cov", &entry->pixels)) {
    missing_.insert(app);
    return nullptr;
  }
  entry->image = {kWidth, kHeight, entry->pixels.data()};
  while (order_.size() >= kKeep) {
    cache_.erase(order_.back());
    order_.pop_back();
  }
  order_.push_front(app);
  return &(cache_[app] = std::move(entry))->image;
}

}  // namespace orbisdesk
