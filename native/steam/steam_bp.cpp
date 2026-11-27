// SPDX-License-Identifier: GPL-3.0-or-later
// Steam Big Picture's screens (steam_bp.h), drawn as the approved mockups lay them out.
#include "steam_bp.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace bp {
namespace {

std::uint32_t Alpha(std::uint32_t color, unsigned alpha) { return (color & 0xffffff) | (alpha << 24); }

std::uint32_t Hsl(float h, float s, float l) {
  h = std::fmod(h, 360.0f) / 360.0f;
  auto channel = [&](float t) {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    const float q = l < 0.5f ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    if (t < 1.0f / 6) return p + (q - p) * 6 * t;
    if (t < 0.5f) return q;
    if (t < 2.0f / 3) return p + (q - p) * (2.0f / 3 - t) * 6;
    return p;
  };
  const auto r = static_cast<std::uint32_t>(channel(h + 1.0f / 3) * 255), g = static_cast<std::uint32_t>(channel(h) * 255),
             b = static_cast<std::uint32_t>(channel(h - 1.0f / 3) * 255);
  return 0xff000000u | r << 16 | g << 8 | b;
}

const char* const kTabNames[kTabs] = {"HOME", "LIBRARY", "DOWNLOADS", "STORAGE", "SETTINGS"};

}  // namespace

std::string Initials(const std::string& name) {
  std::string out, word;
  auto flush = [&] {
    if (word.empty() || out.size() >= 3) {
      word.clear();
      return;
    }
    const bool digits = word.find_first_not_of("0123456789") == std::string::npos;
    out += digits ? word : std::string(1, word[0]);
    word.clear();
  };
  for (char ch : name) {
    const bool alnum = (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9');
    if (alnum) word += ch;
    else flush();
  }
  flush();
  for (auto& ch : out)
    if (ch >= 'a' && ch <= 'z') ch = static_cast<char>(ch - 32);
  return out.substr(0, 4);
}

void Painter::Background() { sd_gradient(c_, kTop, kBottom); }

float Painter::Text(float x, float y, float size, std::uint32_t color, const std::string& text, bool bold) {
  Note(text);
  return sd_text(c_, x, y, size, bold, color, text.c_str());
}

float Painter::TextFit(float x, float y, float size, std::uint32_t color, const std::string& text, float width, bool bold) {
  Note(text);
  return sd_text_fit(c_, x, y, size, bold, color, text.c_str(), width);
}

float Painter::TextRight(float right, float y, float size, std::uint32_t color, const std::string& text, bool bold) {
  Note(text);
  return sd_text_right(c_, right, y, size, bold, color, text.c_str());
}

int Painter::Wrap(float x, float y, float width, float size, float line, std::uint32_t color, const std::string& text,
                  int max_lines, bool bold) {
  Note(text);
  return sd_text_wrap(c_, x, y, width, size, line, bold, color, text.c_str(), max_lines);
}

float Painter::Width(float size, const std::string& text, bool bold) const {
  return sd_text_width(c_, size, bold, text.c_str());
}

void Painter::Modal(float x, float y, float w, float h) {
  for (int i = 4; i >= 1; --i) sd_round(c_, x - i * 6 + 6, y - i * 4 + 14, w + i * 12 - 12, h + i * 10, 18 + i * 6, 0x22000000);
  sd_round(c_, x, y, w, h, 18, kPanel);
  sd_round_outline(c_, x, y, w, h, 18, 1, 0x0affffff);
}

void Painter::Row(float x, float y, float w, float h, const std::string& label, const std::string& value, int state,
                  std::uint32_t value_color, float size) {
  std::uint32_t fill = kBg, ink = kDim;
  if (state == 1) fill = Alpha(kAccent, 36), ink = kInk;
  if (state == 2) fill = 0x0fffffff, ink = kInk;
  sd_round(c_, x, y, w, h, 8, fill);
  if (state == 1) sd_round_outline(c_, x, y, w, h, 8, 1.5f, kAccent);
  if (state == 2) sd_round_outline(c_, x, y, w, h, 8, 1.5f, Alpha(kAccent, 153));
  const std::uint32_t alpha = state == 3 ? 0x73 : 0xff;
  const float ty = y + (h - size * 1.25f) / 2;
  const float value_w = value.empty() ? 0 : Width(size, value);
  TextFit(x + 24, ty, size, Alpha(ink, alpha), label, w - 48 - value_w - (value.empty() ? 0 : 24));
  if (!value.empty()) TextRight(x + w - 24, ty, size, Alpha(value_color, alpha), value);
}

float Painter::ButtonAt(float x, float y, const std::string& label, bool primary, bool focus, bool disabled, int icon) {
  const float size = 20, h = 60;
  const float text_w = Width(size, label, primary);
  const float icon_w = icon >= 0 ? 32 : 0;
  const float w = 56 + text_w + icon_w;
  const unsigned alpha = disabled ? 0x66 : 0xff;
  if (focus) {
    sd_round(c_, x - 7, y - 7, w + 14, h + 14, 14, Alpha(primary ? kAccent : kHi, alpha));
    sd_round(c_, x - 4, y - 4, w + 8, h + 8, 12, kBottom);
  }
  sd_round(c_, x, y, w, h, 9, Alpha(primary ? kAccent : kRaise, alpha));
  const std::uint32_t ink = primary ? 0xff04121f : kInk;
  if (icon >= 0) sd_icon(c_, icon, x + 26, y + 18, 24, Alpha(ink, alpha));
  Text(x + 28 + icon_w, y + (h - size * 1.25f) / 2, size, Alpha(ink, alpha), label, primary);
  return w;
}

void Painter::Bar(float x, float y, float w, float h, int permille, std::uint32_t color, std::uint32_t back) {
  sd_round(c_, x, y, w, h, h / 2.5f, back);
  permille = std::clamp(permille, 0, 1000);
  if (permille > 0) sd_round(c_, x, y, std::max(h, w * permille / 1000.0f), h, h / 2.5f, color);
}

float Painter::ChipWidth(const std::string& text) const { return Width(13, text) + 16; }

void Painter::Chip(float x, float y, const std::string& text, bool warn) {
  const float w = ChipWidth(text);
  sd_round(c_, x, y, w, 24, 5, warn ? 0x24ffc477 : Alpha(kAccent, 51));
  Text(x + 8, y + 3, 13, warn ? kWarn : kHi, text);
}

void Painter::Badge(float x, float y, const std::string& text, int kind) {
  const float w = ChipWidth(text);
  sd_round(c_, x, y, w, 24, 5, kind == 0 ? kAccent : kind == 1 ? 0x247fd8a6 : 0x24ffc477);
  Text(x + 8, y + 3, 13, kind == 0 ? 0xff04121f : kind == 1 ? kOk : kWarn, text);
}

void Painter::Glyph(float x, float y, int button, float size) {
  sd_circle(c_, x + size / 2, y + size / 2, size / 2, kDark);
  static const int icons[] = {0, SD_ICON_CROSS, SD_ICON_CIRCLE, SD_ICON_TRIANGLE, SD_ICON_SQUARE};
  static const std::uint32_t colors[] = {0, 0xff8fb4ff, 0xffff8a8a, 0xff62d6ad, 0xffeb92d6};
  if (button > 0 && button <= kSquare) sd_icon(c_, icons[button], x + size * 0.1f, y + size * 0.1f, size * 0.8f, colors[button]);
}

float Painter::HintBar(const std::vector<Hint>& hints, float x, float y) {
  for (const auto& hint : hints) {
    if (x > 1820) break;
    if (hint.button != kNoButton) {
      Glyph(x, y - 3, hint.button);
      x += 40;
    } else if (!hint.key.empty() && hint.key[0] == '\x01') {
      const bool vertical = hint.key == kUpDown;
      sd_round(c_, x, y - 2, 52, 28, 6, kDark);
      sd_icon(c_, vertical ? SD_ICON_UP : SD_ICON_LEFT, x + 5, y + 2, 20, kInk);
      sd_icon(c_, vertical ? SD_ICON_DOWN : SD_ICON_RIGHT, x + 27, y + 2, 20, kInk);
      Note(vertical ? "UP/DOWN" : "LEFT/RIGHT");
      x += 62;
    } else if (!hint.key.empty()) {
      const float w = Width(15, hint.key) + 18;
      sd_round(c_, x, y - 2, w, 28, 6, kDark);
      Text(x + 9, y + 2, 15, kInk, hint.key);
      x += w + 10;
    }
    x += TextFit(x, y, 17, kDim, hint.label, 1840 - x) + 34;
  }
  return x;
}

void Painter::TopBar(int tab, bool power_focus, const std::string& download_name, int download_permille,
                     const std::string& clock, const std::string& brand) {
  sd_round(c_, 80, 52, 1760, 84, 14, kPanel);
  for (int t = 0; t < kTabs; ++t) {
    const float x = 98 + t * 204.0f, y = 67;
    const bool on = t == tab && !power_focus;
    if (on) {
      sd_round(c_, x, y, 184, 54, 9, Alpha(kAccent, 31));
      sd_round_outline(c_, x, y, 184, 54, 9, 1.5f, Alpha(kAccent, 204));
    }
    Text(x + 18, y + 14, 20, on ? kInk : kDim, kTabNames[t]);
  }
  // right side, from the power button leftwards
  const float power_x = 1768;
  sd_circle(c_, power_x + 27, 94, 27, power_focus ? Alpha(kAccent, 41) : kRaise);
  if (power_focus) sd_ring(c_, power_x + 27, 94, 26.25f, 1.5f, kAccent);
  sd_icon(c_, SD_ICON_POWER, power_x + 14, 81, 26, power_focus ? kInk : kDim);
  float right = power_x - 22;
  if (!clock.empty()) right -= TextRight(right, 81, 20, kInk, clock) + 22;
  if (!brand.empty()) right -= TextRight(right, 83, 17, kDim, brand) + 22;
  if (download_permille >= 0) {
    char percent[16];
    snprintf(percent, sizeof(percent), "%d%%", download_permille / 10);
    right -= TextRight(right, 82, 17, kInk, percent) + 10;
    right -= 120;
    Bar(right, 91, 120, 6, download_permille, kAccent, kRaise);
    right -= 10;
    const float name_w = std::min(Width(17, download_name), 220.0f);
    right -= name_w;
    TextFit(right, 82, 17, kInk, download_name, name_w);
    right -= 34;
    sd_icon(c_, SD_ICON_DOWNLOAD, right, 82, 24, kAccent);
  }
}

void Painter::Check(float x, float y, float size) {
  sd_circle(c_, x + size / 2, y + size / 2, size / 2, Alpha(kAccent, 46));
  sd_icon(c_, SD_ICON_CHECK, x + size * 0.23f, y + size * 0.23f, size * 0.54f, kAccent);
}

void DrawCover(Painter& p, const Cover& cover, float x, float y, float w, float h, bool focus, bool foot) {
  sd_canvas* c = p.canvas();
  if (focus) {
    sd_round(c, x - 7, y - 7, w + 14, h + 14, 12, kAccent);
    sd_round(c, x - 4, y - 4, w + 8, h + 8, 10, kBottom);
  }
  const float radius = 7;
  if (cover.art) {
    sd_image_draw(c, cover.art, x, y, w, h, radius, cover.offline ? 128 : 0, cover.offline);
    p.Note(cover.name);
  } else {
    // the placeholder: a slanted gradient in the game's own hue, its initials, its name
    const float hue = static_cast<float>((cover.app * 47u) % 360u);
    const std::uint32_t top = Hsl(hue, 0.48f, cover.offline ? 0.16f : 0.38f),
                        bottom = Hsl(hue + 20, 0.42f, cover.offline ? 0.08f : 0.13f);
    sd_round_gradient(c, x, y, w, h, radius, top, bottom);
    const float mono = w * 64 / 180;
    sd_text(c, x + w * 14 / 180, y + h * 8 / 270, mono, 1, 0x29ffffff, Initials(cover.name).c_str());
    if (foot) {
      sd_clip(c, x, y + h - 64, w, 64);
      sd_round_gradient(c, x, y + h - 64, w, 64, radius, Alpha(kDark, 0), Alpha(kDark, 235));
      sd_unclip(c);
      p.TextFit(x + 10, y + h - 34 - (cover.progress >= 0 ? 14 : 0), w > 150 ? 16 : 14, kInk, cover.name, w - 20);
    } else {
      p.Note(cover.name);
    }
  }
  if (cover.installed && !cover.offline) {
    sd_circle(c, x + w - 17, y + 17, 11, 0x99050708);
    sd_circle(c, x + w - 17, y + 17, 8, kAccent);
  }
  float chip_x = x + 8;
  if (!cover.drive.empty() && !cover.offline) {
    const float bw = p.Width(14, cover.drive) + 16;
    sd_round(c, chip_x, y + 8, bw, 26, 6, 0xd1050708);
    p.Text(chip_x + 8, y + 12, 14, kInk, cover.drive);
    chip_x += bw + 6;
  }
  if (cover.non_steam) {
    const std::string text = "NON-STEAM";
    const float size = w > 150 ? 12 : 11, bw = p.Width(size, text) + 14;
    if (chip_x + bw < x + w - 30) {
      sd_round(c, chip_x, y + 8, bw, 26, 6, 0xd1050708);
      p.Text(chip_x + 7, y + 13, size, kHi, text);
    }
  }
  if (cover.favorite) sd_icon(c, SD_ICON_STAR, x + w - 34, y + h - 34 - (cover.progress >= 0 ? 16 : 0), 24, kHi);
  if (cover.progress >= 0) {
    sd_round(c, x + 8, y + h - 16, w - 16, 8, 4, 0xcc050708);
    if (cover.progress > 0) sd_round(c, x + 8, y + h - 16, std::max(8.0f, (w - 16) * cover.progress / 1000.0f), 8, 4, kAccent);
  }
  if (cover.offline) {
    sd_round(c, x + 8, y + h - 70, w - 16, 26, 6, 0xd1050708);
    const std::string text = "DRIVE OFFLINE";
    const float tw = p.Width(14, text);
    p.Text(x + (w - tw) / 2, y + h - 66, 14, kWarn, text);
  }
}

namespace {

void DrawFrame(Painter& p, const Frame& frame) {
  p.Background();
  p.TopBar(frame.tab, frame.power_focus, frame.download_name, frame.download_permille, frame.clock, frame.brand);
}

void More(Painter& p, float x, float y) {
  sd_icon(p.canvas(), SD_ICON_DOWN, x, y, 20, kDim);
  p.Text(x + 24, y, 16, kDim, "MORE");
}

void Shelf(Painter& p, const std::vector<Cover>& covers, float top, int focus) {
  const int visible = 9;
  int first = 0;
  if (focus >= visible - 1) first = focus - (visible - 2);
  for (int i = first; i < static_cast<int>(covers.size()) && i < first + visible; ++i)
    DrawCover(p, covers[static_cast<std::size_t>(i)], 96 + (i - first) * 192.0f, top, 172, 242, i == focus);
}

}  // namespace

void DrawHome(Painter& p, const HomeView& view) {
  DrawFrame(p, view.frame);
  p.Text(96, 196, 22, view.shelf == 0 ? kAccent : kDim, view.first_title);
  Shelf(p, view.first, 236, view.shelf == 0 ? view.index : -1);
  p.Text(96, 548, 22, view.shelf == 1 ? kAccent : kDim, view.second_title);
  if (view.second.empty()) p.Wrap(96, 600, 1200, 20, 30, kDim, view.empty_second, 3);
  Shelf(p, view.second, 588, view.shelf == 1 ? view.index : -1);
  if (!view.hints) return;
  std::vector<Hint> hints = {{kCross, "", "OPEN"}, {kSquare, "", "FAVORITE"}, {kNoButton, "L1 / R1", "SECTIONS"}};
  hints.push_back({kNoButton, "OPTIONS", "POWER"});
  if (!view.big_picture) hints.push_back({kCircle, "", "DESKTOP"});
  p.HintBar(hints);
}

void DrawLibrary(Painter& p, const LibraryView& view) {
  DrawFrame(p, view.frame);
  p.Text(96, 166, 38, kInk, "LIBRARY");
  p.Text(98, 216, 16, kDim, view.subtitle);
  float y = 272;
  for (std::size_t i = 0; i < view.views.size(); ++i) {
    if (static_cast<int>(i) == view.separator) {
      sd_rect(p.canvas(), 116, y + 4, 276, 1, 0x1fffffff);
      y += 14;
    }
    const bool on = static_cast<int>(i) == view.view;
    p.Row(96, y, 316, 58, view.views[i].first, std::to_string(view.views[i].second),
          on ? (view.views_focus ? 1 : 2) : 0, kDim);
    y += 68;
    if (y > 900) break;
  }
  p.Panel(510, 272, 1304, 664);
  const int count = static_cast<int>(view.games.size());
  const int row = view.index / 6, first_row = row > 0 ? row - 1 : 0;
  const int first = first_row * 6;
  char range[96];
  if (count) snprintf(range, sizeof(range), "GAMES %d\xe2\x80\x93%d OF %d", first + 1, std::min(first + 12, count), count);
  else snprintf(range, sizeof(range), "NO GAMES");
  p.Text(548, 300, 19, kDim, range);
  p.TextRight(1776, 302, 17, kDim, "SORT  " + view.sort);
  const int cells = count + (view.add_tile ? 1 : 0);
  if (!count && !view.add_tile) p.Wrap(548, 360, 1200, 22, 32, kDim, view.empty, 3);
  for (int i = first; i < cells && i < first + 12; ++i) {
    const int k = i - first;
    const float x = 548 + (k % 6) * 204.0f, y = 348 + (k / 6) * 296.0f;
    const bool focus = !view.views_focus && i == view.index;
    if (i < count) {
      DrawCover(p, view.games[static_cast<std::size_t>(i)], x, y, 180, 270, focus);
      continue;
    }
    // the add tile: a dashed outline, a plus, three lines
    sd_canvas* c = p.canvas();
    if (focus) {
      sd_round(c, x - 7, y - 7, 194, 284, 12, kAccent);
      sd_round(c, x - 4, y - 4, 188, 278, 10, kBottom);
      sd_round(c, x, y, 180, 270, 7, Alpha(kAccent, 20));
    }
    const std::uint32_t dash = Alpha(kAccent, 140);
    for (float d = 10; d < 170; d += 18) sd_rect(c, x + d, y, 10, 2.5f, dash), sd_rect(c, x + d, y + 267.5f, 10, 2.5f, dash);
    for (float d = 10; d < 260; d += 18) sd_rect(c, x, y + d, 2.5f, 10, dash), sd_rect(c, x + 177.5f, y + d, 2.5f, 10, dash);
    sd_rect(c, x + 72, y + 92, 36, 5, kAccent);
    sd_rect(c, x + 87.5f, y + 76.5f, 5, 36, kAccent);
    const char* const lines[] = {"ADD A", "NON-STEAM", "GAME"};
    for (int l = 0; l < 3; ++l) p.Text(x + (180 - p.Width(18, lines[l])) / 2, y + 140 + l * 24.0f, 18, kHi, lines[l]);
  }
  // more below: a fade over the second row's lower edge
  if (first + 12 < cells) More(p, 1700, 914);
  const bool on_tile = view.add_tile && view.index == count && !view.views_focus;
  if (on_tile)
    p.HintBar({{kCross, "", "ADD A GAME"}, {kNoButton, kLeftRight, "VIEWS"}, {kNoButton, "L1 / R1", "SECTIONS"},
               {kNoButton, "OPTIONS", "POWER"}});
  else
    p.HintBar({{kCross, "", view.views_focus ? "SHOW" : "DETAILS"}, {kSquare, "", "FAVORITE"}, {kTriangle, "", "SORT"},
               {kNoButton, kLeftRight, "VIEWS"}, {kNoButton, "L1 / R1", "SECTIONS"},
               {kNoButton, "OPTIONS", "POWER"}});
}

void DrawGame(Painter& p, const GameView& view) {
  DrawFrame(p, view.frame);
  p.Panel(180, 180, 1560, 740);
  p.Text(260, 226, 22, kAccent, "GAME");
  DrawCover(p, view.cover, 260, 272, 220, 330, false);
  {
    static const char* const kStates[] = {"INSTALLED", "NOT INSTALLED", "RUNNING", "DRIVE OFFLINE", "MOVE PENDING",
                                          "DOWNLOADING", "PAUSED"};
    static const std::uint32_t kColors[] = {kAccent, kDim, kOk, kWarn, kWarn, kAccent, kWarn};
    sd_round(p.canvas(), 260, 622, 220, 56, 8, Alpha(kAccent, 31));
    const std::string text = kStates[view.state];
    p.Text(260 + (220 - p.Width(18, text)) / 2, 638, 18, kColors[view.state], text);
  }
  p.TextFit(530, 262, 48, kInk, view.cover.name, 1170);
  const std::uint32_t status_color = view.state == kOffline || view.state == kMovePending || view.state == kPaused ? kWarn
                                     : view.state == kRunning                                                    ? kOk
                                     : view.state == kNotInstalled                                               ? kDim
                                                                                                                 : kAccent;
  const float status_w = p.TextFit(532, 330, 21, status_color, view.status, view.status_chip.empty() ? 1170 : 900);
  if (!view.status_chip.empty()) p.Chip(532 + status_w + 14, 330, view.status_chip, true);
  float x = 530;
  for (std::size_t i = 0; i < view.buttons.size(); ++i) {
    const bool disabled = i < view.disabled.size() && view.disabled[i];
    int icon = -1;
    if (i == 0 && (view.state == kInstalled || view.state == kRunning)) icon = SD_ICON_PLAY;
    if (i == 0 && (view.state == kNotInstalled || view.state == kPaused)) icon = SD_ICON_DOWNLOAD;
    if (i == 0 && (view.state == kOffline || view.state == kMovePending)) icon = SD_ICON_REFRESH;
    x += p.ButtonAt(x, 384, view.buttons[i], i == 0, static_cast<int>(i) == view.focus, disabled, icon) + 16;
  }
  float y = 492;
  if (view.progress >= 0) {
    p.Bar(532, 486, 1150, 20, view.progress);
    y = 530;
  }
  for (const auto& [label, value] : view.facts) {
    p.Text(532, y + 2, 16, kDim, label);
    const float w = p.TextFit(812, y, 19, kInk, value, 870);
    if (label == "LOCATION" && !view.chip.empty()) p.Chip(812 + w + 10, y, view.chip);
    y += 36;
  }
  p.Wrap(532, 810, 1150, 17, 25, view.note_warn ? kWarn : kDim, view.note, 3);
  p.HintBar(view.hints);
}

namespace {

void DrawDrive(Painter& p, const Drive& drive, float x, float y, float w, float h, bool selected) {
  sd_canvas* c = p.canvas();
  const unsigned alpha = drive.disabled ? 0x80 : 0xff;
  sd_round(c, x, y, w, h, 10, selected ? Alpha(kAccent, 33) : kBg);
  if (selected) sd_round_outline(c, x, y, w, h, 10, 1.5f, kAccent);
  const float letter_y = y + (h - 72) / 2;
  sd_round(c, x + 26, letter_y, 72, 72, 12, selected ? Alpha(kAccent, 64) : kRaise);
  p.Text(x + 26 + (72 - p.Width(30, drive.letter)) / 2, letter_y + 17, 30, Alpha(kInk, alpha), drive.letter);
  const float text_x = x + 26 + 96 + 22;
  const bool side = !drive.side_big.empty();
  const float text_w = w - (text_x - x) - (side ? 352 : 26);
  const float name_w = p.TextFit(text_x, y + 16, 24, Alpha(kInk, alpha), drive.name, text_w);
  if (!drive.chip.empty()) p.Chip(text_x + name_w + 10, y + 19, drive.chip, drive.chip_warn);
  p.TextFit(text_x, y + 48, 16, Alpha(kDim, alpha), drive.path, text_w);
  if (drive.used_permille >= 0) {
    const float bw = text_w;
    sd_round(c, text_x, y + 78, bw, 10, 5, kRaise);
    const float steam = drive.steam_permille > 0 ? bw * drive.steam_permille / 1000.0f : 0;
    const float used = bw * std::clamp(drive.used_permille, 0, 1000) / 1000.0f;
    if (used > 0) sd_round(c, text_x, y + 78, std::max(10.0f, used), 10, 5, kMuted);
    if (steam > 0) sd_round(c, text_x, y + 78, std::max(10.0f, steam), 10, 5, kAccent);
  }
  if (side) {
    p.TextRight(x + w - 26, y + 22, 22, drive.side_warn ? kWarn : Alpha(kInk, alpha), drive.side_big);
    p.TextRight(x + w - 26, y + 56, 17, Alpha(kDim, alpha), drive.side_small);
  }
}

void ModalHead(Painter& p, const GameView& backdrop, bool has_backdrop, const std::string& label, const std::string& title) {
  if (has_backdrop) DrawGame(p, backdrop);
  else p.Background();
  p.Scrim();
  p.Modal(300, 150, 1320, 770);
  p.Text(370, 200, 24, kAccent, label);
  p.TextFit(370, 240, 40, kInk, title, 1180);
}

}  // namespace

void DrawPicker(Painter& p, const PickerView& view) {
  // the hints of the backdrop stay off: the picker's own replace them
  GameView backdrop = view.backdrop;
  backdrop.hints.clear();
  ModalHead(p, backdrop, view.has_backdrop, view.label, view.title);
  p.TextFit(372, 296, 19, kDim, view.subtitle, 1180);
  const int shown = 3;
  int first = view.selected >= shown ? view.selected - shown + 1 : 0;
  float y = 346;
  for (int i = first; i < static_cast<int>(view.drives.size()) && i < first + shown; ++i) {
    DrawDrive(p, view.drives[static_cast<std::size_t>(i)], 370, y, 1180, 104, i == view.selected);
    y += 118;
  }
  if (view.drives.empty()) p.Text(370, 360, 22, kWarn, "NO DRIVE FOUND. TRIANGLE LOOKS AGAIN.");
  if (static_cast<int>(view.drives.size()) > first + shown) More(p, 1480, 700);
  if (view.show_default) {
    sd_canvas* c = p.canvas();
    sd_round_outline(c, 370, 718, 30, 30, 6, 2, kAccent);
    if (view.make_default) sd_icon(c, SD_ICON_CHECK, 373, 721, 24, kAccent);
    const float w = p.Text(416, 720, 19, kInk, "Install here every time");
    p.Text(416 + w + 8, 722, 16, kDim, "\xc2\xb7 SETTINGS CAN CHANGE IT LATER");
  }
  p.Wrap(370, 780, 1180, 17, 25, kDim, view.note, 3);
  p.HintBar(view.hints);
}

void DrawMove(Painter& p, const MoveView& view) {
  GameView backdrop = view.backdrop;
  backdrop.hints.clear();
  ModalHead(p, backdrop, view.has_backdrop, "MOVE GAME", view.title);
  if (view.step == 0) {
    DrawDrive(p, view.from, 370, 330, 550, 120, false);
    sd_icon(p.canvas(), SD_ICON_ARROW_RIGHT, 935, 370, 40, kAccent);
    DrawDrive(p, view.to, 1000, 330, 550, 120, true);
    float y = 490;
    for (const auto& [label, value] : view.facts) {
      p.Text(372, y + 2, 16, kDim, label);
      p.TextFit(672, y, 19, kInk, value, 870);
      y += 36;
    }
    p.Wrap(372, 600, 1180, 18, 27, kDim, view.note, 3);
    float x = 370;
    for (std::size_t i = 0; i < view.buttons.size(); ++i)
      x += p.ButtonAt(x, 700, view.buttons[i], i == 0, static_cast<int>(i) == view.focus, false) + 16;
  } else if (view.step == 1) {
    p.TextFit(372, 296, 19, kDim, view.route, 1180);
    static const char* const kStages[] = {"SCAN", "COPY", "CHECK", "UPDATE LOCATION", "REMOVE OLD COPY"};
    const float w = (1180 - 4 * 8) / 5.0f;
    for (int i = 0; i < 5; ++i) {
      const float x = 370 + i * (w + 8);
      const std::uint32_t bar = i < view.stage ? Alpha(kAccent, 140) : i == view.stage ? kAccent : kRaise;
      sd_rect(p.canvas(), x, 356, w, 6, bar);
      p.Text(x, 376, 15, i <= view.stage ? kInk : kDim, kStages[i]);
    }
    p.Text(370, 440, 64, kInk, view.percent);
    p.Bar(370, 550, 1180, 20, view.permille);
    p.TextFit(370, 592, 21, kInk, view.detail, 1180);
    p.Wrap(370, 660, 1180, 18, 27, kDim, view.note, 3);
  } else {
    if (view.ok) p.Check(370, 330, 96);
    else {
      sd_circle(p.canvas(), 418, 378, 48, 0x2effc477);
      sd_icon(p.canvas(), SD_ICON_CROSS, 388, 348, 60, kWarn);
    }
    p.TextFit(500, 340, 36, kInk, view.headline, 1050);
    p.TextFit(502, 392, 19, view.ok ? kDim : kWarn, view.headline_sub, 1050);
    float y = 480;
    for (const auto& [label, value] : view.facts) {
      p.Text(372, y + 2, 16, kDim, label);
      p.TextFit(632, y, 19, kInk, value, 910);
      y += 36;
    }
    p.Wrap(372, 600, 1180, 17, 25, kDim, view.note, 2);
    float x = 370;
    for (std::size_t i = 0; i < view.buttons.size(); ++i)
      x += p.ButtonAt(x, 680, view.buttons[i], i == 0, static_cast<int>(i) == view.focus, false,
                      i == 0 && view.ok && view.buttons[i].find("PLAY") != std::string::npos ? SD_ICON_PLAY : -1) + 16;
  }
  p.HintBar(view.hints);
}

void DrawDownloads(Painter& p, const DownloadsView& view) {
  DrawFrame(p, view.frame);
  p.Text(96, 166, 38, kInk, "DOWNLOADS");
  p.Text(98, 216, 16, kDim, view.subtitle);
  p.Wrap(98, 282, 360, 17, 25, kDim,
         "One download at a time. The desktop and a running game keep working while Steam downloads.", 5);
  p.Panel(510, 180, 1304, 740);
  int row = 0;
  float y = 222;
  if (view.active) {
    p.Text(590, y, 22, kAccent, view.current.right.empty() ? "DOWNLOADING" : view.current.right);
    y += 40;
    const bool sel = view.selected == row++;
    sd_round(p.canvas(), 590, y, 1144, 200, 8, sel ? Alpha(kAccent, 36) : kBg);
    if (sel) sd_round_outline(p.canvas(), 590, y, 1144, 200, 8, 1.5f, kAccent);
    DrawCover(p, view.current.cover, 618, y + 24, 100, 150, false, false);
    p.TextFit(746, y + 24, 30, kInk, view.current.name, 960);
    p.TextFit(746, y + 68, 17, kDim, view.current.detail, 960);
    p.Bar(746, y + 104, 960, 20, view.permille);
    p.Text(746, y + 140, 19, kInk, view.percent_line);
    p.TextRight(1706, y + 140, 19, kInk, view.speed_line);
    if (!view.state_line.empty()) p.TextFit(746, y + 168, 16, kWarn, view.state_line, 960);
    y += 238;
  } else {
    p.Text(590, y, 22, kAccent, "DOWNLOADING");
    p.Text(590, y + 44, 20, kDim, "NOTHING IS DOWNLOADING.");
    y += 110;
  }
  auto section = [&](const char* title, const std::vector<DownloadRow>& rows) {
    if (rows.empty()) return;
    p.Text(590, y, 20, kDim, title);
    y += 30;
    for (const auto& r : rows) {
      if (y > 840) {
        ++row;
        continue;
      }
      const bool sel = view.selected == row++;
      sd_round(p.canvas(), 590, y, 1144, 76, 8, sel ? 0x0fffffff : kBg);
      if (sel) sd_round_outline(p.canvas(), 590, y, 1144, 76, 8, 1.5f, Alpha(kAccent, 153));
      const float w = p.TextFit(614, y + 22, 22, kInk, r.name, 420);
      p.TextFit(614 + w + 20, y + 26, 17, kDim, r.detail, 1100 - w - 20 - (r.right.empty() ? 0 : p.Width(17, r.right) + 20));
      if (!r.right.empty()) p.TextRight(1710, y + 26, 17, kAccent, r.right);
      y += 86;
    }
    y += 14;
  };
  section("PAUSED", view.paused);
  section("FINISHED THIS SESSION", view.finished);
  p.HintBar({{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "OPEN GAME"},
             {kSquare, "", view.active ? "PAUSE" : "RESUME"}, {kNoButton, "L1 / R1", "SECTIONS"},
             {kNoButton, "OPTIONS", "POWER"}});
}

void DrawStorage(Painter& p, const StorageView& view) {
  DrawFrame(p, view.frame);
  p.Text(96, 166, 38, kInk, "STORAGE");
  p.Text(98, 216, 16, kDim, view.subtitle);
  float y = 272;
  for (std::size_t i = 0; i < view.drives.size() && y < 900; ++i, y += 68)
    p.Row(96, y, 316, 58, view.drives[i].first, std::to_string(view.drives[i].second),
          static_cast<int>(i) == view.drive ? (view.games_focus ? 2 : 1) : 0, kDim);
  p.Panel(510, 180, 1304, 740);
  if (view.drives.empty()) {
    p.Text(590, 220, 28, kWarn, "NO DRIVE FOUND");
  } else {
    const float w = p.TextFit(590, 220, 34, kInk, view.name, 900);
    if (!view.chip.empty()) p.Chip(590 + w + 12, 232, view.chip);
    p.TextFit(592, 272, 17, kDim, view.paths, 1144);
    sd_round(p.canvas(), 590, 322, 1144, 26, 8, kBg);
    const float other = 1144 * std::clamp(view.steam_permille + view.other_permille, 0, 1000) / 1000.0f;
    const float steam = 1144 * std::clamp(view.steam_permille, 0, 1000) / 1000.0f;
    if (other > 0) sd_round(p.canvas(), 590, 322, std::max(16.0f, other), 26, 8, kMuted);
    if (steam > 0) sd_round(p.canvas(), 590, 322, std::max(16.0f, steam), 26, 8, kAccent);
    float x = 590;
    sd_round(p.canvas(), x, 365, 14, 14, 4, kAccent);
    x += 24 + p.Text(x + 24, 362, 17, kDim, view.steam_label) + 36;
    sd_round(p.canvas(), x, 365, 14, 14, 4, kMuted);
    x += 24 + p.Text(x + 24, 362, 17, kDim, view.other_label) + 36;
    p.Text(x, 362, 17, kInk, view.free_label);
    p.Text(590, 430, 20, kDim, "GAMES ON THIS DRIVE");
    float gy = 466;
    const int shown = 3;
    const int first = view.game >= shown ? view.game - shown + 1 : 0;
    for (int i = first; i < static_cast<int>(view.games.size()) && i < first + shown; ++i, gy += 86) {
      const bool sel = view.games_focus && i == view.game;
      sd_round(p.canvas(), 590, gy, 1144, 76, 8, sel ? 0x0fffffff : kBg);
      if (sel) sd_round_outline(p.canvas(), 590, gy, 1144, 76, 8, 1.5f, Alpha(kAccent, 153));
      const auto& game = view.games[static_cast<std::size_t>(i)];
      const float nw = p.TextFit(614, gy + 22, 22, kInk, game.name, 700);
      p.Text(614 + nw + 20, gy + 26, 17, kDim, game.size);
      if (sel) p.TextRight(1710, gy + 26, 17, kAccent, "CROSS OPENS");
    }
    if (view.games.empty()) p.Text(590, gy + 10, 20, kDim, "NO STEAM GAME ON THIS DRIVE.");
    p.Wrap(590, 740, 1144, 17, 25, kDim, view.note, 4);
  }
  p.HintBar({{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", view.games_focus ? "OPEN GAME" : "GAMES"},
             {kSquare, "", "MAKE DEFAULT"}, {kTriangle, "", "REFRESH"}, {kNoButton, "L1 / R1", "SECTIONS"},
             {kNoButton, "OPTIONS", "POWER"}});
}

void DrawSettings(Painter& p, const SettingsView& view) {
  DrawFrame(p, view.frame);
  p.Text(96, 166, 38, kInk, "SETTINGS");
  p.TextFit(98, 216, 16, kDim, view.subtitle, 400);
  p.Panel(510, 180, 1304, 740);
  p.Text(590, 222, 24, kAccent, "ORBISDESK & STEAM");
  float y = 268;
  for (std::size_t i = 0; i < view.rows.size(); ++i, y += 68) {
    const auto& row = view.rows[i];
    const bool sel = static_cast<int>(i) == view.selected;
    const std::string value = sel && row.choice ? "<  " + row.value + "  >" : row.value;
    p.Row(590, y, 1144, 58, row.label, value, sel ? 1 : 0, row.dim_value ? kDim : kAccent);
  }
  y += 24;
  float used = 0;
  if (!view.lead.empty()) used = static_cast<float>(p.Wrap(590, y, 1144, 18, 27, kInk, view.lead, 2)) * 27;
  if (!view.detail.empty()) used += static_cast<float>(p.Wrap(590, y + used, 1144, 18, 27, kDim, view.detail, 3)) * 27;
  if (!view.saved.empty()) p.Wrap(590, y + used + 10, 1144, 18, 27, kAccent, view.saved, 2);
  p.HintBar({{kNoButton, kUpDown, "CHOOSE"}, {kNoButton, kLeftRight, "CHANGE"},
             {kCross, "", "OPEN"}, {kNoButton, "L1 / R1", "SECTIONS"}, {kNoButton, "OPTIONS", "POWER"}});
}

void DrawMenu(Painter& p, const MenuView& view) {
  HomeView home = view.home;
  home.hints = false;
  DrawHome(p, home);
  p.Scrim(0x9e030508);
  if (view.right_panel) {
    p.Modal(1240, 150, 600, 420);
    p.Text(1290, 190, 22, kAccent, view.label);
    float y = 236;
    for (std::size_t i = 0; i < view.rows.size(); ++i, y += 82) {
      const bool sel = static_cast<int>(i) == view.selected;
      sd_round(p.canvas(), 1290, y, 500, 70, 8, sel ? Alpha(kAccent, 36) : kBg);
      if (sel) sd_round_outline(p.canvas(), 1290, y, 500, 70, 8, 1.5f, kAccent);
      const int icon = i < view.icons.size() ? view.icons[i] : -1;
      if (icon >= 0) sd_icon(p.canvas(), icon, 1314, y + 21, 28, sel ? kInk : kDim);
      p.Text(1360, y + 22, 20, sel ? kInk : kDim, view.rows[i]);
    }
    p.Wrap(1290, y + 6, 500, 16, 23, kDim, view.note, 3);
  } else {
    p.Modal(300, 210, 1320, 650);
    p.Text(390, 262, 24, kAccent, view.label);
    p.TextFit(390, 304, 40, kInk, view.title, 1140);
    const int lines = p.Wrap(392, 368, 1140, 19, 28, kDim, view.text, 3);
    float y = 368 + lines * 28 + 36;
    for (std::size_t i = 0; i < view.rows.size(); ++i, y += 72)
      p.Row(390, y, 1140, 58, view.rows[i], "", static_cast<int>(i) == view.selected ? 1 : 0);
  }
  p.HintBar(view.hints);
}

void DrawMessage(Painter& p, const MessageView& view) {
  if (view.has_backdrop) {
    GameView backdrop = view.backdrop;
    backdrop.hints.clear();
    DrawGame(p, backdrop);
    p.Scrim();
  } else {
    p.Background();
  }
  p.Modal(300, 210, 1320, 650);
  p.Text(390, 262, 24, view.warn ? kWarn : kAccent, view.label);
  p.TextFit(390, 304, 40, kInk, view.title, 1140);
  const int lines = p.Wrap(392, 372, 1140, 19, 28, view.warn ? kWarn : kDim, view.text, 9);
  float y = 372 + lines * 28.0f + 30;
  if (view.permille >= 0) {
    p.Bar(390, y, 1140, 20, view.permille);
    y += 60;
  }
  float x = 390;
  y = std::max(y, 700.0f);
  for (std::size_t i = 0; i < view.buttons.size(); ++i)
    x += p.ButtonAt(x, y, view.buttons[i], i == 0, static_cast<int>(i) == view.focus, false) + 16;
  p.HintBar(view.hints);
}

void DrawChoice(Painter& p, const ChoiceView& view) {
  GameView backdrop = view.backdrop;
  backdrop.hints.clear();
  DrawGame(p, backdrop);
  p.Scrim();
  p.Modal(300, 190, 1320, 690);
  p.Text(370, 236, 22, kAccent, view.label);
  p.TextFit(370, 276, 40, kInk, view.title, 1180);
  float y = 350;
  for (std::size_t i = 0; i < view.rows.size(); ++i, y += 84) {
    const auto& row = view.rows[i];
    const bool sel = static_cast<int>(i) == view.selected;
    const int state = row.disabled ? 3 : sel ? 1 : 0;
    const bool noted = !row.marks.empty() && !row.warn;
    p.Row(370, y, 1180, 72, row.label, row.warn || noted ? "" : row.value, state, kDim);
    float right = 1550 - 24;
    for (auto mark = row.marks.rbegin(); mark != row.marks.rend(); ++mark) {
      right -= p.ChipWidth(mark->first);
      p.Badge(right, y + 24, mark->first, mark->second);
      right -= 10;
    }
    if (row.warn && !row.value.empty()) p.Chip(right - p.ChipWidth(row.value), y + 24, row.value, true);
    else if (noted && !row.value.empty()) p.TextRight(right - 4, y + 26, 16, row.disabled ? 0x7397a4b2 : kDim, row.value);
  }
  p.Wrap(372, y + 16, 1180, 18, 27, kDim, view.text, 5);
  p.HintBar(view.hints);
}

void DrawSplash(Painter& p, const std::string& what) {
  sd_rect(p.canvas(), 0, 0, 1920, 1080, 0xff05080c);
  sd_icon(p.canvas(), SD_ICON_LOGO, 865, 330, 190, 0);
  const std::string who = "ORBISDESK";
  p.Text((1920 - p.Width(40, who, true)) / 2, 548, 40, kInk, who, true);
  p.Text((1920 - p.Width(22, what)) / 2, 612, 22, 0xff8fa0b2, what);
  sd_round(p.canvas(), 840, 676, 240, 6, 3, 0xff16202b);
  sd_round(p.canvas(), 900, 676, 96, 6, 3, kAccent);
}

// ---- adding a non-Steam game ----
namespace {

void WideModal(Painter& p, const std::string& label, const std::string& title) {
  p.Background();
  p.TopBar(kLibrary, false, "", -1, "", "ORBISDESK \xc2\xb7 STEAM");
  p.Scrim();
  p.Modal(240, 150, 1440, 770);
  p.Text(310, 196, 24, kAccent, label);
  if (!title.empty()) p.TextFit(310, 236, 36, kInk, title, 1300);
}

// the first of `shown` rows that keeps `selected` in view
int FirstShown(int selected, int count, int shown) {
  int first = selected >= shown ? selected - shown + 1 : 0;
  return std::max(0, std::min(first, std::max(0, count - shown)));
}

void TickBox(Painter& p, float x, float y, bool on) {
  sd_canvas* c = p.canvas();
  sd_round_outline(c, x, y, 30, 30, 6, 2, on ? kAccent : kDim);
  if (on) {
    sd_round(c, x + 2, y + 2, 26, 26, 5, Alpha(kAccent, 30));
    sd_icon(c, SD_ICON_CHECK, x + 3, y + 3, 24, kAccent);
  }
}

}  // namespace

void DrawFound(Painter& p, const FoundView& view) {
  WideModal(p, view.label, view.title);
  p.TextFit(312, 290, 18, kDim, view.subtitle, 1300);
  const int count = static_cast<int>(view.rows.size()), shown = 4;
  const int first = FirstShown(view.selected, count, shown);
  int ticked = 0;
  for (const auto& row : view.rows) ticked += row.ticked;
  float y = 336;
  for (int i = first; i < count && i < first + shown; ++i, y += 88) {
    const auto& row = view.rows[static_cast<std::size_t>(i)];
    const bool sel = i == view.selected;
    p.Row(310, y, 1300, 78, "", "", sel ? 1 : 0);
    TickBox(p, 334, y + 24, row.ticked);
    p.TextFit(384, y + 25, 22, sel ? kInk : kInk, row.name, 400);
    float right = 1586;
    if (row.shortcut) {
      right -= p.ChipWidth("SHORTCUT");
      p.Chip(right, y + 27, "SHORTCUT");
      right -= 10;
    }
    if (!row.arch.empty()) {
      const std::string arch = row.arch == "x64" ? "64-BIT" : row.arch == "x86" ? "32-BIT" : "OTHER";
      right -= p.ChipWidth(arch);
      p.Chip(right, y + 27, arch);
      right -= 10;
    }
    p.TextFit(804, y + 29, 16, kDim, row.path, right - 804 - 16);
  }
  if (!count) p.Wrap(312, 360, 1300, 21, 31, kDim, view.empty, 4);
  if (first + shown < count) More(p, 1500, 690);
  p.Wrap(312, 700, 1300, 17, 25, kDim, view.note, 2);
  const std::string add = ticked == 1 ? "ADD 1 GAME" : "ADD " + std::to_string(ticked) + " GAMES";
  const float w = p.ButtonAt(310, 780, add, true, false, ticked == 0);
  p.ButtonAt(310 + w + 16, 780, "BROWSE FOR AN EXE...", false, false, false);
  p.HintBar(view.hints);
}

void DrawBrowse(Painter& p, const BrowseView& view) {
  WideModal(p, view.label, "");
  float y = 240;
  for (std::size_t i = 0; i < view.places.size() && y < 860; ++i, y += 68) {
    const bool on = static_cast<int>(i) == view.place;
    p.Row(310, y, 300, 58, view.places[i], "", on ? (view.places_focus ? 1 : 2) : 0);
  }
  p.TextFit(650, 244, 19, kInk, view.path, 960);
  const int count = static_cast<int>(view.entries.size()), shown = 7;
  const int first = FirstShown(view.selected, count, shown);
  y = 290;
  sd_canvas* c = p.canvas();
  for (int i = first; i < count && i < first + shown; ++i, y += 70) {
    const auto& e = view.entries[static_cast<std::size_t>(i)];
    const bool sel = !view.places_focus && i == view.selected;
    p.Row(650, y, 960, 62, "", "", sel ? 1 : 0);
    const float ix = 666, iy = y + 11;
    if (e.kind == 0) {
      sd_round(c, ix, iy, 40, 40, 8, kRaise);
      sd_icon(c, SD_ICON_LEFT, ix + 8, iy + 8, 24, kInk);
    } else if (e.kind == 1) {
      sd_round(c, ix + 2, iy + 6, 16, 8, 3, kMuted);
      sd_round(c, ix + 2, iy + 10, 36, 24, 4, kMuted);
    } else {
      sd_round(c, ix, iy, 40, 40, 8, Alpha(kAccent, 77));
      const auto dot = e.name.find_last_of('.');
      std::string ext = dot == std::string::npos ? "" : e.name.substr(dot + 1, 3);
      for (auto& ch : ext)
        if (ch >= 'a' && ch <= 'z') ch = static_cast<char>(ch - 32);
      p.Text(ix + (40 - p.Width(12, ext)) / 2, iy + 13, 12, kInk, ext);
    }
    const float detail_w = e.detail.empty() ? 0 : std::min(440.0f, p.Width(16, e.detail));
    p.TextFit(722, y + 18, 20, sel || e.kind != 1 ? kInk : kDim, e.name, 960 - 72 - detail_w - 48);
    if (!e.detail.empty()) {
      p.TextFit(1586 - detail_w, y + 21, 16, kDim, e.detail, detail_w);
    }
  }
  if (!count) p.Wrap(650, 300, 960, 20, 30, kDim, view.empty, 3);
  if (first + shown < count) More(p, 1500, 786);
  p.Wrap(650, 800, 960, 17, 25, kDim, view.note, 3);
  p.HintBar(view.hints);
}

void DrawDetails(Painter& p, const DetailsView& view) {
  WideModal(p, view.label, "");
  DrawCover(p, view.cover, 310, 250, 220, 330, false);
  p.TextFit(580, 244, 40, kInk, view.title, 1030);
  float y = 316;
  const int rows = static_cast<int>(view.rows.size());
  for (int i = 0; i < rows; ++i, y += 72) {
    const auto& row = view.rows[static_cast<std::size_t>(i)];
    p.Row(580, y, 1030, 62, row.label, row.value, i == view.selected ? 1 : 0, row.dim_value ? kDim : kAccent);
  }
  if (!view.note.empty()) p.Wrap(580, y + 4, 1030, 17, 25, kDim, view.note, 2);
  float x = 580;
  for (std::size_t i = 0; i < view.buttons.size(); ++i)
    x += p.ButtonAt(x, 800, view.buttons[i], i == 0, view.selected == rows + static_cast<int>(i), false) + 16;
  p.HintBar(view.hints);
}

KeyKind KeyAt(int row, int col, bool shift, std::string* text) {
  static const char* const kLower[4] = {"1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm-:."};
  static const char* const kUpper[4] = {"!&()+,?/#_", "QWERTYUIOP", "ASDFGHJKL\"", "ZXCVBNM;!."};
  if (row < 0 || row >= kKeyRows || col < 0 || col >= kKeyCols) return kKeyDone;
  if (row < 4) {
    if (text) *text = std::string(1, (shift ? kUpper : kLower)[row][col]);
    return kKeyChar;
  }
  return col < 2 ? kKeyShift : col < 5 ? kKeySpace : col < 7 ? kKeyDelete : kKeyDone;
}

void DrawKeyboard(Painter& p, const KeyboardView& view) {
  WideModal(p, view.label, "");
  DrawCover(p, view.cover, 310, 250, 220, 330, false);
  sd_canvas* c = p.canvas();
  p.Text(580, 252, 18, kDim, view.field);
  sd_round(c, 580, 284, 1030, 72, 10, kBg);
  sd_round_outline(c, 580, 284, 1030, 72, 10, 1.5f, kAccent);
  // the end of a long text stays in view
  std::string shown = view.text;
  while (!shown.empty() && p.Width(28, shown) > 980) {
    std::size_t cut = 1;
    while (cut < shown.size() && (static_cast<unsigned char>(shown[cut]) & 0xc0) == 0x80) ++cut;
    shown.erase(0, cut);
  }
  const float tw = p.Text(604, 302, 28, kInk, shown);
  sd_rect(c, 606 + tw, 300, 3, 38, kAccent);
  const float kx = 580, ky = 390, kw = 68, kh = 60, gap = 8;
  for (int r = 0; r < kKeyRows; ++r) {
    for (int col = 0; col < kKeyCols; ++col) {
      std::string text;
      const KeyKind kind = KeyAt(r, col, view.shift, &text);
      int span = 1;
      if (r == 4) {
        // one key over its columns: SHIFT 0-1, SPACE 2-4, DELETE 5-6, DONE 7-9
        const int starts[] = {0, 2, 5, 7}, spans[] = {2, 3, 2, 3};
        int k = -1;
        for (int s = 0; s < 4; ++s)
          if (col == starts[s]) k = s;
        if (k < 0) continue;
        span = spans[k];
        text = kind == kKeyShift ? "SHIFT" : kind == kKeySpace ? "SPACE" : kind == kKeyDelete ? "DELETE" : "DONE";
      }
      const bool on = view.row == r && view.col >= col && view.col < col + span;
      const float x = kx + col * (kw + gap), y = ky + r * (kh + gap), w = span * kw + (span - 1) * gap;
      const bool lit = kind == kKeyShift && view.shift;
      sd_round(c, x, y, w, kh, 8, on ? kAccent : kRaise);
      if (lit && !on) sd_round_outline(c, x, y, w, kh, 8, 2, kAccent);
      const float size = r == 4 ? 16 : 22;
      p.Text(x + (w - p.Width(size, text, on)) / 2, y + (kh - size * 1.25f) / 2, size, on ? 0xff04121f : kInk, text, on);
    }
  }
  p.HintBar(view.hints);
}

void DrawCoverChoice(Painter& p, const CoverChoiceView& view) {
  WideModal(p, view.label, view.title);
  const int n = static_cast<int>(view.choices.size());
  const float gap = 20, w = n ? std::min(300.0f, (1300 - gap * static_cast<float>(n - 1)) / static_cast<float>(n)) : 300;
  sd_canvas* c = p.canvas();
  for (int i = 0; i < n; ++i) {
    const auto& choice = view.choices[static_cast<std::size_t>(i)];
    const float x = 310 + i * (w + gap), y = 310;
    const bool sel = i == view.selected;
    sd_round(c, x, y, w, 360, 12, sel ? Alpha(kAccent, 31) : kBg);
    if (sel) sd_round_outline(c, x, y, w, 360, 12, 1.5f, kAccent);
    const float cw = std::min(150.0f, w - 32), ch = cw * 1.5f;
    DrawCover(p, choice.cover, x + (w - cw) / 2, y + 16, cw, ch, false);
    const float lw = std::min(w - 20, p.Width(17, choice.label));
    p.TextFit(x + (w - lw) / 2, y + 26 + ch, 17, sel ? kInk : kDim, choice.label, w - 20);
    const float sw = std::min(w - 20, p.Width(14, choice.sub));
    p.TextFit(x + (w - sw) / 2, y + 52 + ch, 14, kDim, choice.sub, w - 20);
  }
  p.Wrap(312, 700, 1300, 17, 25, kDim, view.note, 2);
  p.ButtonAt(310, 780, "USE THIS COVER", true, true, n == 0);
  p.HintBar(view.hints);
}

}  // namespace bp

// ---- steam_ui.c's text pages ----
// The page's first line is its label; a short second line its title. Lines starting with \x01 are a
// list's selected entry, \x03 a warning; \x04 switches to the accent. What follows \x02 is the footer: its
// last line, "X: ACCEPT     O: EXIT", becomes the hint bar, the lines before it a status above the bar.
namespace {

std::vector<std::string> Lines(const std::string& text) {
  std::vector<std::string> out;
  std::size_t at = 0;
  while (at <= text.size()) {
    const auto end = text.find('\n', at);
    out.push_back(text.substr(at, end == std::string::npos ? std::string::npos : end - at));
    if (end == std::string::npos) break;
    at = end + 1;
  }
  return out;
}

std::string Strip(std::string s, char byte) {
  s.erase(std::remove(s.begin(), s.end(), byte), s.end());
  return s;
}

std::vector<bp::Hint> ParseHints(const std::string& line) {
  std::vector<bp::Hint> hints;
  std::vector<std::string> parts;
  std::size_t at = 0;
  while (at < line.size()) {
    auto gap = line.find("  ", at);
    std::string part = line.substr(at, gap == std::string::npos ? std::string::npos : gap - at);
    if (!part.empty()) parts.push_back(part);
    if (gap == std::string::npos) break;
    at = line.find_first_not_of(' ', gap);
    if (at == std::string::npos) break;
  }
  for (const auto& part : parts) {
    bp::Hint hint;
    const auto colon = part.find(": ");
    if (colon == std::string::npos || colon > 24) {
      hint.label = part;
      hints.push_back(hint);
      continue;
    }
    const std::string key = part.substr(0, colon);
    hint.label = part.substr(colon + 2);
    if (key == "X") hint.button = bp::kCross;
    else if (key == "O") hint.button = bp::kCircle;
    else if (key == "TRIANGLE") hint.button = bp::kTriangle;
    else if (key == "SQUARE") hint.button = bp::kSquare;
    else if (key == "UP AND DOWN" || key == "UP/DOWN") hint.key = bp::kUpDown;
    else hint.key = key;
    hints.push_back(hint);
  }
  return hints;
}

}  // namespace

extern "C" void steam_bp_draw_page(sd_canvas* canvas, const char* text, const unsigned char* qr, int qr_size) {
  using namespace bp;
  Painter p(canvas);
  p.Background();
  std::string all = text ? text : "";
  std::string body = all, footer;
  const auto mark = all.find('\x02');
  if (mark != std::string::npos) {
    body = all.substr(0, mark);
    footer = all.substr(mark + 1);
    while (!body.empty() && body.back() == '\n') body.pop_back();
  }
  auto lines = Lines(body);
  std::vector<std::string> status;
  std::string hint_line;
  if (!footer.empty()) {
    status = Lines(footer);
    hint_line = status.back();
    status.pop_back();
  }
  const float panel_x = 180, panel_y = 110, panel_w = 1560, panel_h = 810 - 28.0f * static_cast<float>(status.size());
  p.Modal(panel_x, panel_y, panel_w, panel_h);
  float x = panel_x + 80, y = panel_y + 50;
  float width = panel_w - 160;
  if (qr && qr_size > 0) {
    const float side = 560;
    sd_qr(canvas, qr, qr_size, panel_x + panel_w - 80 - side, panel_y + (panel_h - side) / 2, side);
    width -= side + 60;
  }
  std::size_t i = 0;
  if (!lines.empty()) {
    p.TextFit(x, y, 24, kAccent, Strip(lines[0], '\x04'), width);
    y += 44;
    i = 1;
  }
  if (lines.size() > 1) {
    const std::string& second = lines[1];
    const bool title = !second.empty() && second.size() <= 44 && second[0] != '\x01' && second[0] != '\x03' &&
                       second.find(". ") == std::string::npos && second.find(':') == std::string::npos;
    if (title) {
      p.TextFit(x, y, 40, kInk, Strip(second, '\x04'), width);
      y += 66;
      i = 2;
    }
  }
  const float bottom = panel_y + panel_h - 30;
  for (; i < lines.size(); ++i) {
    std::string line = lines[i];
    bool selected = false, warn = false;
    if (!line.empty() && line[0] == '\x01') selected = true, line.erase(0, 1);
    if (!line.empty() && line[0] == '\x03') warn = true, line.erase(0, 1);
    // the accent bytes (the old library's active tab): drawn in the accent, whole line
    bool accent = line.find('\x04') != std::string::npos;
    line = Strip(line, '\x04');
    if (line.empty()) {
      y += 14;
      continue;
    }
    sd_canvas measure = *canvas;
    measure.px = nullptr;
    const int count = sd_text_wrap(&measure, 0, 0, width - (selected ? 40 : 0), 20, 30, 0, 0, line.c_str(), 0);
    const float h = count * 30.0f;
    if (y + h > bottom) {
      p.Note("(cut) " + line);
      continue;
    }
    if (selected) {
      sd_round(canvas, x - 4, y - 8, width + 8, h + 16, 8, Alpha(kAccent, 36));
      sd_round_outline(canvas, x - 4, y - 8, width + 8, h + 16, 8, 1.5f, kAccent);
    }
    p.Wrap(x + (selected ? 20 : 0), y, width - (selected ? 40 : 0), 20, 30,
           warn ? kWarn : selected ? kInk : accent ? kHi : 0xffd4dce5, line);
    y += h + (selected ? 16 : 10);
  }
  float sy = panel_y + panel_h + 12;
  for (const auto& s : status) {
    p.TextFit(96, sy, 18, kDim, Strip(s, '\x04'), 1728);
    sy += 28;
  }
  if (!hint_line.empty()) p.HintBar(ParseHints(hint_line));
}
