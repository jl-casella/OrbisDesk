// SPDX-License-Identifier: GPL-3.0-or-later
// Included by steam_bigpicture.inc.cpp after the shell's helpers: adding, editing, removing and starting
// non-Steam games (docs/STEAM_BIG_PICTURE.md, the approved review of 2026-11-25). The list itself is
// steam_nonsteam.cpp's; this file is the screens. Logs carry counts and outcomes only.

// when a game was last started from Big Picture, as the page says it
std::string PlayedWhen(std::uint64_t when) {
  const auto now = static_cast<std::uint64_t>(time(nullptr));
  const std::uint64_t days = now > when ? (now - when) / 86400 : 0;
  return days == 0 ? "Today" : days == 1 ? "Yesterday" : std::to_string(days) + " days ago";
}

// ---- covers: the store's art by name, an image on the console, or the plain tile ----
struct CoverPick {
  int kind = 2;  // 0 found by name (Steam's store, else Wikipedia), 1 file, 2 plain
  std::uint32_t app = 0;
  std::string provider;  // with kind 0: "steam" or "wikipedia"
  std::vector<std::uint32_t> pixels;
};

const char* ProviderLabel(const CoverPick& pick) {
  return pick.provider == "wikipedia" ? "FROM WIKIPEDIA" : "FROM STEAM'S STORE";
}

long FetchUrl(steam::HttpClient& http, const std::string& url, std::vector<std::uint8_t>* body, std::size_t limit,
              const char* user_agent = nullptr) {
  steam::HttpRequest request;
  request.url = url;
  if (user_agent) request.headers.push_back({"User-Agent", user_agent});
  request.timeout_ms = 12'000;
  request.max_response_bytes = limit;
  const std::atomic<bool> cancel{false};
  auto response = http.Perform(request, cancel);
  if (!response.ok()) return 0;
  if (response.status_code == 200) *body = std::move(response.body);
  return response.status_code;
}

// Up to `most` store matches for `name`, each with its cover drawn (the library cover, else the header
// letterboxed). Only full games whose store name is the term's count (hardware 2026-11-26: a game not sold on
// Steam took three other games' DLC covers); none is better than another game's art. Matches without art are
// left out.
std::vector<CoverPick> StoreCovers(Shell& shell, const std::string& name, const std::string& program, bool named,
                                   int most) {
  std::vector<CoverPick> picks;
  steam::HttpClient http(shell.context.ca);
  std::vector<std::uint8_t> body;
  // each term in turn until one has a match: api.steampowered.com's search, else the store's own; then the
  // store's type and name of each result (GetItems, with the art)
  const auto terms = orbisdesk::StoreSearchTerms(name, program, named);
  std::vector<std::uint32_t> apps;
  std::map<std::uint32_t, orbisdesk::Covers::StoreArt> art;
  int tried = 0, results = 0, not_games = 0, other_names = 0;
  long suggest_status = 0, search_status = 0, items_status = 0;
  for (const auto& term : terms) {
    ++tried;
    body.clear();
    suggest_status = FetchUrl(http, orbisdesk::StoreSuggestUrl(term), &body, 1 << 20);
    std::vector<std::uint32_t> found;
    if (suggest_status == 200) found = orbisdesk::ParseStoreSuggest(std::string(body.begin(), body.end()));
    if (suggest_status != 200) {
      body.clear();
      search_status = FetchUrl(http, orbisdesk::StoreSearchUrl(term), &body, 1 << 20);
      if (search_status == 200)
        for (const auto& match : orbisdesk::ParseStoreSearch(std::string(body.begin(), body.end()))) found.push_back(match.first);
    }
    if (found.empty()) continue;
    results += static_cast<int>(found.size());
    body.clear();
    items_status = FetchUrl(http, orbisdesk::Covers::StoreItemsUrl(found), &body, 1 << 20);
    if (items_status != 200) continue;
    for (auto& [app, entry] : orbisdesk::Covers::ParseStoreItems(std::string(body.begin(), body.end()))) art[app] = entry;
    for (const auto app : found) {
      const auto item = art.find(app);
      if (item == art.end()) continue;
      if (item->second.type != orbisdesk::Covers::kStoreGame) {
        ++not_games;
        continue;
      }
      if (!orbisdesk::CoverNameMatches(name, program, named, item->second.name)) {
        ++other_names;
        continue;
      }
      if (static_cast<int>(apps.size()) < most) apps.push_back(app);
    }
    if (!apps.empty()) break;
  }
  trace_note("PWSTEAM nonsteam cover_search named=%d terms=%zu tried=%d suggest=%ld search=%ld items=%ld results=%d "
       "not_games=%d other_names=%d apps=%zu",
       named, terms.size(), tried, suggest_status, search_status, items_status, results, not_games, other_names,
       apps.size());
  if (apps.empty()) return picks;
  for (const auto app : apps) {
    const auto found = art.find(app);
    if (found == art.end()) continue;
    CoverPick pick;
    pick.kind = 0;
    pick.app = app;
    pick.provider = "steam";
    for (int landscape = 0; landscape < 2 && pick.pixels.empty(); ++landscape) {
      const std::string& url = landscape ? found->second.header : found->second.library;
      if (url.empty()) continue;
      body.clear();
      if (FetchUrl(http, url, &body, 4 << 20) != 200) continue;
      const bool ok = landscape ? orbisdesk::Covers::DecodeLandscape(body.data(), body.size(), &pick.pixels)
                                : orbisdesk::Covers::Decode(body.data(), body.size(), &pick.pixels);
      if (!ok) pick.pixels.clear();
    }
    if (!pick.pixels.empty()) picks.push_back(std::move(pick));
  }
  return picks;
}

// Wikipedia's article image for the game, when Steam's store has none (orbisdesk::ParseWikipediaCovers says
// which articles count): each term in turn until one has a match.
std::vector<CoverPick> WikipediaCovers(Shell& shell, const std::string& name, const std::string& program, bool named,
                                       int most) {
  std::vector<CoverPick> picks;
  steam::HttpClient http(shell.context.ca);
  std::vector<std::uint8_t> body;
  const auto terms = orbisdesk::StoreSearchTerms(name, program, named);
  int tried = 0, articles = 0;
  long status = 0;
  for (const auto& term : terms) {
    ++tried;
    body.clear();
    status = FetchUrl(http, orbisdesk::WikipediaSearchUrl(term), &body, 1 << 20, orbisdesk::kWikimediaUserAgent);
    if (status != 200) continue;
    const auto covers = orbisdesk::ParseWikipediaCovers(std::string(body.begin(), body.end()), name, program, named);
    articles += static_cast<int>(covers.size());
    for (const auto& cover : covers) {
      if (static_cast<int>(picks.size()) >= most) break;
      body.clear();
      if (FetchUrl(http, cover.image, &body, 4 << 20, orbisdesk::kWikimediaUserAgent) != 200) continue;
      CoverPick pick;
      pick.kind = 0;
      pick.provider = "wikipedia";
      // a box cover is portrait; anything wider is letterboxed like a store header
      const bool portrait = cover.width > 0 && cover.height * 5 >= cover.width * 6;
      const bool ok = portrait ? orbisdesk::Covers::Decode(body.data(), body.size(), &pick.pixels)
                               : orbisdesk::Covers::DecodeLandscape(body.data(), body.size(), &pick.pixels);
      if (ok) picks.push_back(std::move(pick));
    }
    if (!picks.empty()) break;
  }
  trace_note("PWSTEAM nonsteam wiki_search named=%d terms=%zu tried=%d status=%ld articles=%d covers=%zu", named, terms.size(),
       tried, status, articles, picks.size());
  return picks;
}

// Steam's store first, else Wikipedia; logs which one gave the covers
std::vector<CoverPick> FindCovers(Shell& shell, const orbisdesk::NonSteamGame& game, int most) {
  auto picks = StoreCovers(shell, game.name, game.program, game.named, most);
  if (picks.empty()) picks = WikipediaCovers(shell, game.name, game.program, game.named, most);
  trace_note("PWSTEAM nonsteam cover provider=%s found=%zu", picks.empty() ? "none" : picks[0].provider.c_str(), picks.size());
  return picks;
}

void SaveCover(Shell& shell, std::uint32_t id, const CoverPick& pick) {
  const std::string base = std::string(kArtDir) + "/" + std::to_string(id);
  mkdir(kArtDir, 0755);
  unlink((base + ".nocover").c_str());
  if (pick.kind == 2 || pick.pixels.empty()) unlink((base + ".cov").c_str());
  else if (!orbisdesk::Covers::Save(base + ".cov", pick.pixels)) note("PWSTEAM nonsteam cover save=0 errno=%d", errno);
  shell.covers.Forget(id);
}

std::string CoverSource(const CoverPick& pick) {
  if (pick.kind == 0) return pick.provider == "wikipedia" ? "wikipedia" : "store:" + std::to_string(pick.app);
  return pick.kind == 1 ? "file" : "plain";
}

// ---- the on-screen keyboard: the new text, or false when cancelled ----
bool Keyboard(const std::string& field, const bp::Cover& cover, std::string* text, std::size_t most) {
  bp::KeyboardView view;
  view.field = field;
  view.cover = cover;
  view.text = *text;
  view.row = 1;
  view.hints = {{bp::kCross, "", "TYPE"}, {bp::kSquare, "", "DELETE"}, {bp::kTriangle, "", "SPACE"},
                {bp::kNoButton, "OPTIONS", "DONE"}, {bp::kCircle, "", "CANCEL"}};
  auto erase_last = [&] {
    if (view.text.empty()) return;
    std::size_t cut = view.text.size() - 1;
    while (cut > 0 && (static_cast<unsigned char>(view.text[cut]) & 0xc0) == 0x80) --cut;
    view.text.erase(cut);
  };
  // what the field keeps: a name is trimmed and capped as names are; the rest only loses control characters
  auto finish = [&] {
    if (field == "NAME") {
      *text = orbisdesk::CleanName(view.text);
      return;
    }
    std::string clean;
    for (const char c : view.text) clean += (static_cast<unsigned char>(c) < 0x20 || c == 0x7f) ? ' ' : c;
    *text = clean.substr(0, most);
  };
  for (;;) {
    Present([&](bp::Painter& p) { bp::DrawKeyboard(p, view); });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_CROSS |
                                          STEAM_UI_CIRCLE | STEAM_UI_SQUARE | STEAM_UI_TRIANGLE | STEAM_UI_OPTIONS);
    if (button == STEAM_UI_CIRCLE) return false;
    if (button == STEAM_UI_UP) view.row = (view.row + bp::kKeyRows - 1) % bp::kKeyRows;
    else if (button == STEAM_UI_DOWN) view.row = (view.row + 1) % bp::kKeyRows;
    else if (button == STEAM_UI_LEFT || button == STEAM_UI_RIGHT) {
      const int step = button == STEAM_UI_RIGHT ? 1 : bp::kKeyCols - 1;
      if (view.row == 4) {
        // the wide keys: one step moves to the next key, not the next column
        static const int starts[] = {0, 2, 5, 7};
        int k = view.col < 2 ? 0 : view.col < 5 ? 1 : view.col < 7 ? 2 : 3;
        k = (k + (button == STEAM_UI_RIGHT ? 1 : 3)) % 4;
        view.col = starts[k];
      } else {
        view.col = (view.col + step) % bp::kKeyCols;
      }
    } else if (button == STEAM_UI_SQUARE) erase_last();
    else if (button == STEAM_UI_TRIANGLE) {
      if (view.text.size() < most) view.text += ' ';
    } else if (button == STEAM_UI_OPTIONS) {
      finish();
      return true;
    } else if (button == STEAM_UI_CROSS) {
      std::string ch;
      switch (bp::KeyAt(view.row, view.col, view.shift, &ch)) {
        case bp::kKeyChar:
          if (view.text.size() < most) view.text += ch;
          break;
        case bp::kKeyShift: view.shift = !view.shift; break;
        case bp::kKeySpace:
          if (view.text.size() < most) view.text += ' ';
          break;
        case bp::kKeyDelete: erase_last(); break;
        case bp::kKeyDone:
          finish();
          return true;
      }
    }
  }
}

// ---- the browser: a file with one of `extensions` (Windows path), or "" when cancelled ----
std::string BrowseFor(const std::string& label, const std::vector<std::string>& extensions, const std::string& note_text) {
  const auto& roots = orbisdesk::Roots();
  struct Place {
    std::string name, unix_path;
  };
  std::vector<Place> places = {{"C: Windows", roots.drive_c}, {"Z: Internal", roots.z}};
  for (std::size_t i = 0; i < roots.usb.size(); ++i)
    if (orbisdesk::PathExists(roots.usb[i]))
      places.push_back({std::string(1, static_cast<char>('D' + i)) + ": USB " + std::to_string(i), roots.usb[i]});
  places.push_back({"Desktop", roots.drive_c + "/users/orbis/Desktop"});
  const bool exes = std::find(extensions.begin(), extensions.end(), ".exe") != extensions.end();
  int place = 0;
  std::string dir = places[0].unix_path;
  bool places_focus = false;
  int selected = 0;
  std::vector<orbisdesk::FolderEntry> listing;
  std::vector<bp::BrowseEntry> entries;
  auto load = [&] {
    std::vector<std::string> wanted = extensions;
    if (exes) wanted.push_back(".lnk");  // a shortcut stands for its target
    orbisdesk::ListFolder(dir, wanted, &listing);
    entries.clear();
    bool root = false;
    for (const auto& p : places) root = root || p.unix_path == dir;
    if (!root) entries.push_back({"..", "UP ONE FOLDER", 0});
    int read = 0;
    for (const auto& e : listing) {
      bp::BrowseEntry entry{e.name, "", e.folder ? 1 : 2};
      if (!e.folder) {
        std::string detail = Size(e.bytes);
        if (exes && read < 60 && orbisdesk::LowerAscii(e.name).size() > 4 &&
            orbisdesk::LowerAscii(e.name).compare(e.name.size() - 4, 4, ".exe") == 0) {
          ++read;
          const auto info = orbisdesk::ReadExeInfo(dir + "/" + e.name);
          const std::string arch = info.arch == "x64" ? "64-BIT" : info.arch == "x86" ? "32-BIT" : "";
          detail = (info.product.empty() ? "" : info.product + " \xc2\xb7 ") + (arch.empty() ? "" : arch + " \xc2\xb7 ") + detail;
        } else if (exes && orbisdesk::LowerAscii(e.name).find(".lnk") != std::string::npos) {
          detail = "SHORTCUT";
        }
        entry.detail = detail;
      }
      entries.push_back(entry);
    }
    if (selected >= static_cast<int>(entries.size())) selected = entries.empty() ? 0 : static_cast<int>(entries.size()) - 1;
  };
  auto up = [&] {
    for (const auto& p : places)
      if (p.unix_path == dir) return;
    const auto slash = dir.find_last_of('/');
    if (slash != std::string::npos && slash > 0) dir.resize(slash);
    selected = 0;
    load();
  };
  load();
  for (;;) {
    Present([&](bp::Painter& p) {
      bp::BrowseView view;
      view.label = label;
      for (const auto& pl : places) view.places.push_back(pl.name);
      view.place = place;
      view.places_focus = places_focus;
      view.path = orbisdesk::UnixToWindows(dir);
      view.entries = entries;
      view.selected = selected;
      view.empty = orbisdesk::PathExists(dir) ? "NOTHING TO SHOW IN THIS FOLDER." : "THIS DRIVE IS NOT CONNECTED.";
      view.note = note_text;
      view.hints = {{bp::kNoButton, bp::kUpDown, "CHOOSE"}, {bp::kCross, "", "OPEN / SELECT"}, {bp::kNoButton, bp::kLeftRight, "DRIVES"},
                    {bp::kTriangle, "", "UP ONE FOLDER"}, {bp::kCircle, "", "CANCEL"}};
      bp::DrawBrowse(p, view);
    });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_CROSS |
                                          STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE);
    const int n = static_cast<int>(entries.size()), places_n = static_cast<int>(places.size());
    if (button == STEAM_UI_CIRCLE) return "";
    if (button == STEAM_UI_TRIANGLE) up();
    else if (places_focus) {
      if (button == STEAM_UI_UP && place > 0) --place;
      else if (button == STEAM_UI_DOWN && place + 1 < places_n) ++place;
      else if (button == STEAM_UI_RIGHT || button == STEAM_UI_CROSS) {
        dir = places[static_cast<std::size_t>(place)].unix_path;
        selected = 0;
        places_focus = false;
        load();
      }
    } else {
      if (button == STEAM_UI_UP && selected > 0) --selected;
      else if (button == STEAM_UI_DOWN && selected + 1 < n) ++selected;
      else if (button == STEAM_UI_LEFT) places_focus = true;
      else if (button == STEAM_UI_CROSS && selected < n) {
        const auto& e = entries[static_cast<std::size_t>(selected)];
        if (e.kind == 0) up();
        else if (e.kind == 1) {
          dir += "/" + e.name;
          selected = 0;
          load();
        } else {
          const std::string path = dir + "/" + e.name;
          if (exes && orbisdesk::LowerAscii(e.name).find(".lnk") != std::string::npos) {
            const auto link = orbisdesk::ReadLink(path);
            if (link.ok && orbisdesk::LowerAscii(link.target).find(".exe") != std::string::npos) return link.target;
            continue;
          }
          return orbisdesk::UnixToWindows(path);
        }
      }
    }
  }
}

// ---- the cover screen: the user's choice, or false when they backed out ----
bool ChooseCover(Shell& shell, const orbisdesk::NonSteamGame& game, CoverPick* out) {
  Splash("LOOKING FOR A COVER");
  auto store = FindCovers(shell, game, 3);
  trace_note("PWSTEAM nonsteam cover_lookup matches=%zu", store.size());
  CoverPick file_pick;
  file_pick.kind = 1;
  std::vector<sd_image> images(store.size() + 1);
  int selected = 0;
  for (;;) {
    bp::CoverChoiceView view;
    view.title = game.name;
    for (std::size_t i = 0; i < store.size(); ++i) {
      images[i] = {orbisdesk::Covers::kWidth, orbisdesk::Covers::kHeight, store[i].pixels.data()};
      bp::CoverChoice choice;
      choice.cover.app = game.id;
      choice.cover.name = game.name;
      choice.cover.art = &images[i];
      choice.label = i == 0 ? ProviderLabel(store[i]) : std::string("OTHER MATCH \xc2\xb7 ") + (store[i].provider == "wikipedia" ? "WIKIPEDIA" : "STEAM");
      choice.sub = i == 0 ? "BEST MATCH FOR THE NAME" : std::to_string(i + 1) + " OF " + std::to_string(store.size());
      view.choices.push_back(choice);
    }
    bp::CoverChoice file;
    file.cover.app = game.id;
    file.cover.name = game.name;
    if (!file_pick.pixels.empty()) {
      images.back() = {orbisdesk::Covers::kWidth, orbisdesk::Covers::kHeight, file_pick.pixels.data()};
      file.cover.art = &images.back();
    }
    file.label = "IMAGE ON THE CONSOLE";
    file.sub = "A .JPG OR .PNG YOU CHOOSE";
    view.choices.push_back(file);
    bp::CoverChoice plain;
    plain.cover.app = game.id;
    plain.cover.name = game.name;
    plain.label = "PLAIN TILE";
    plain.sub = "COLOUR AND INITIALS";
    view.choices.push_back(plain);
    const int n = static_cast<int>(view.choices.size());
    if (selected >= n) selected = n - 1;
    view.selected = selected;
    view.note = store.empty() ? "Neither Steam's store nor Wikipedia has a game by this name, or they could not be reached. Rename "
                                "the game to look again."
                              : "The art is found by the game's name, on Steam's store, else on Wikipedia, and kept on the console. Only the picture "
                                "comes from the store.";
    view.hints = {{bp::kNoButton, bp::kLeftRight, "CHOOSE"}, {bp::kCross, "", "USE THIS COVER"}, {bp::kCircle, "", "BACK"}};
    Present([&](bp::Painter& p) { bp::DrawCoverChoice(p, view); });
    const unsigned button = steam_ui_wait(STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_CROSS | STEAM_UI_CIRCLE);
    if (button == STEAM_UI_CIRCLE) return false;
    if (button == STEAM_UI_LEFT && selected > 0) --selected;
    else if (button == STEAM_UI_RIGHT && selected + 1 < n) ++selected;
    else if (button == STEAM_UI_CROSS) {
      if (selected < static_cast<int>(store.size())) {
        *out = store[static_cast<std::size_t>(selected)];
        return true;
      }
      if (selected == n - 1) {
        *out = CoverPick{};
        return true;
      }
      // the image: chosen with the browser, then used
      const std::string path = BrowseFor("CHOOSE AN IMAGE", {".jpg", ".jpeg", ".png"},
                                         "JPEG and PNG images are shown. The image is cropped to the portrait tile.");
      if (path.empty()) continue;
      std::string bytes;
      int error = 0;
      std::vector<std::uint32_t> pixels;
      if (!ReadAll(orbisdesk::WindowsToUnix(path), &bytes, &error) ||
          !orbisdesk::Covers::Decode(reinterpret_cast<const std::uint8_t*>(bytes.data()), bytes.size(), &pixels)) {
        StorageMessage("COVER\nTHIS IMAGE COULD NOT BE READ. CHOOSE A JPEG OR PNG FILE.");
        continue;
      }
      file_pick.pixels = std::move(pixels);
      *out = file_pick;
      return true;
    }
  }
}

// ---- step 2 and Edit: name, program, folder, options, cover. True when saved. ----
bool DetailsScreen(Shell& shell, orbisdesk::NonSteamGame* game, bool adding, CoverPick* cover, bool* cover_chosen) {
  int selected = 0;
  for (;;) {
    bp::DetailsView view;
    view.label = adding ? "ADD A NON-STEAM GAME" : "EDIT";
    view.cover.app = game->id;
    view.cover.name = game->name;
    view.cover.non_steam = true;
    sd_image image{};
    if (*cover_chosen && !cover->pixels.empty()) {
      image = {orbisdesk::Covers::kWidth, orbisdesk::Covers::kHeight, cover->pixels.data()};
      view.cover.art = &image;
    } else if (!adding) {
      view.cover.art = shell.covers.Get(game->id);
    }
    view.title = game->name;
    const std::string cover_value = *cover_chosen ? (cover->kind == 0 ? ProviderLabel(*cover) : cover->kind == 1 ? "IMAGE ON THE CONSOLE" : "PLAIN TILE")
                                    : adding     ? "FOUND BY NAME"
                                                 : "KEEP THE CURRENT ONE";
    view.rows = {{"Name", game->name, false, false},
                 {"Program", game->program, false, true},
                 {"Start in", game->folder, false, true},
                 {"Launch options", game->options.empty() ? "NONE" : game->options, false, true},
                 {"Cover", cover_value, false, false}};
    view.buttons = {adding ? "ADD TO LIBRARY" : "SAVE", "CANCEL"};
    view.selected = selected;
    view.note = adding ? "Adding never changes the game's files or its Desktop and Start shortcuts." : "";
    view.hints = {{bp::kNoButton, bp::kUpDown, "CHOOSE"}, {bp::kCross, "", selected < 5 ? "CHANGE" : "SELECT"},
                  {bp::kNoButton, "OPTIONS", adding ? "ADD TO LIBRARY" : "SAVE"}, {bp::kCircle, "", "CANCEL"}};
    Present([&](bp::Painter& p) { bp::DrawDetails(p, view); });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_LEFT | STEAM_UI_RIGHT | STEAM_UI_CROSS |
                                          STEAM_UI_CIRCLE | STEAM_UI_OPTIONS);
    if (button == STEAM_UI_CIRCLE) return false;
    if (button == STEAM_UI_OPTIONS) return true;
    if (button == STEAM_UI_UP && selected > 0) --selected;
    else if (button == STEAM_UI_DOWN && selected < 6) ++selected;
    else if ((button == STEAM_UI_LEFT || button == STEAM_UI_RIGHT) && selected >= 5) selected = selected == 5 ? 6 : 5;
    else if (button == STEAM_UI_CROSS) {
      switch (selected) {
        case 0: {
          std::string name = game->name;
          // confirmed, changed or not, the name is the user's: the cover search looks for it from now on (a name
          // edited before 04.86 kept no mark; confirming it again sets one)
          if (Keyboard("NAME", view.cover, &name, 100) && !name.empty()) {
            game->name = name;
            game->named = true;
          }
          break;
        }
        case 1: {
          const std::string program = BrowseFor("CHOOSE THE PROGRAM", {".exe"},
                                                "Only folders, .exe files and shortcuts are shown. The name on the right is the "
                                                "one the exe carries.");
          if (!program.empty()) {
            game->program = program;
            game->folder = orbisdesk::WindowsFolder(program);
            game->id = orbisdesk::NonSteamId(program);
          }
          break;
        }
        case 2: {
          std::string folder = game->folder;
          if (Keyboard("START IN", view.cover, &folder, 240) && folder.size() >= 2 && folder[1] == ':') game->folder = folder;
          break;
        }
        case 3: {
          std::string options = game->options;
          if (Keyboard("LAUNCH OPTIONS", view.cover, &options, 240)) game->options = options;
          break;
        }
        case 4: {
          CoverPick pick;
          if (ChooseCover(shell, *game, &pick)) {
            *cover = std::move(pick);
            *cover_chosen = true;
          }
          break;
        }
        case 5: return true;
        default: return false;
      }
    }
  }
}

// a found or browsed game as the list keeps it
orbisdesk::NonSteamGame NewGame(const orbisdesk::Candidate& c) {
  orbisdesk::NonSteamGame game;
  game.program = c.program;
  game.id = orbisdesk::NonSteamId(c.program);
  game.name = c.name;
  game.folder = c.folder.empty() ? orbisdesk::WindowsFolder(c.program) : c.folder;
  game.options = c.options;
  game.added = static_cast<std::uint64_t>(time(nullptr));
  return game;
}

bool StoreGames(const std::vector<orbisdesk::NonSteamGame>& games) {
  const bool ok = orbisdesk::SaveNonSteamGames(NONSTEAM_FILE, games);
  if (!ok) note("PWSTEAM nonsteam list save=0 errno=%d", errno);
  return ok;
}

// Adds `adds` with their covers (the store's best match where none was chosen); true when the list was saved.
bool AddGames(Shell& shell, std::vector<orbisdesk::NonSteamGame> adds, std::vector<CoverPick> covers, std::vector<bool> chosen) {
  auto games = orbisdesk::LoadNonSteamGames(NONSTEAM_FILE);
  int store = 0;
  for (std::size_t i = 0; i < adds.size(); ++i) {
    auto& game = adds[i];
    CoverPick pick = covers[i];
    if (!chosen[i]) {
      Splash(adds.size() == 1 ? "LOOKING FOR A COVER"
                              : "ADDING " + std::to_string(adds.size()) + " GAMES \xc2\xb7 COVER " + std::to_string(i + 1));
      auto found = FindCovers(shell, game, 1);
      if (!found.empty()) pick = std::move(found[0]);
    }
    store += pick.kind == 0;
    game.cover = CoverSource(pick);
    SaveCover(shell, game.id, pick);
    games.erase(std::remove_if(games.begin(), games.end(), [&](const orbisdesk::NonSteamGame& g) { return g.id == game.id; }),
                games.end());
    games.push_back(game);
  }
  const bool ok = StoreGames(games);
  note("PWSTEAM nonsteam added count=%zu store_covers=%d saved=%d", adds.size(), store, ok);
  if (!ok) StorageMessage("ADD A NON-STEAM GAME\nTHE LIST OF GAMES COULD NOT BE SAVED ON THE CONSOLE.");
  shell.nonsteam_dirty = true;
  return ok;
}

// One game, browsed for: its details first.
void AddBrowsed(Shell& shell) {
  const std::string program = BrowseFor("BROWSE FOR AN EXE", {".exe"},
                                        "Only folders, .exe files and shortcuts are shown. The name on the right is the one "
                                        "the exe carries.");
  if (program.empty()) return;
  for (const auto& g : orbisdesk::LoadNonSteamGames(NONSTEAM_FILE))
    if (g.id == orbisdesk::NonSteamId(program)) {
      StorageMessage("ADD A NON-STEAM GAME\nTHIS PROGRAM IS ALREADY IN THE LIBRARY AS " + Upper(g.name) + ".");
      return;
    }
  orbisdesk::Candidate c;
  c.program = program;
  const auto info = orbisdesk::ReadExeInfo(orbisdesk::WindowsToUnix(program));
  const std::string folder = orbisdesk::WindowsFolder(program);
  c.name = !info.product.empty() ? info.product : orbisdesk::WindowsBasename(folder);
  if (c.name.empty() || c.name.size() <= 3) c.name = orbisdesk::WindowsBasename(program);
  c.folder = folder;
  auto game = NewGame(c);
  CoverPick cover;
  bool chosen = false;
  if (!DetailsScreen(shell, &game, true, &cover, &chosen)) return;
  AddGames(shell, {game}, {cover}, {chosen});
}

// The add flow from the Library's tile or Settings: the games found on the console, or the browser.
void AddNonSteam(Shell& shell) {
  Splash("LOOKING FOR GAMES ON THIS CONSOLE");
  std::set<std::string> known;
  for (const auto& g : orbisdesk::LoadNonSteamGames(NONSTEAM_FILE)) known.insert(orbisdesk::LowerAscii(g.program));
  std::vector<std::string> skip = {orbisdesk::Roots().drive_c + "/orbis", orbisdesk::Roots().drive_c + "/windows",
                                   orbisdesk::Roots().z + "/orbisdesk"};
  for (const auto& game : shell.library.games)
    if (!game.non_steam && Info(shell, game).installed) skip.push_back(GameRoot(game.app));
  for (const auto& usb : orbisdesk::Roots().usb) skip.push_back(usb + "/Steam Games");
  const auto start = std::chrono::steady_clock::now();
  const auto found = orbisdesk::FindNonSteamGames(known, skip);
  int shortcuts = 0;
  for (const auto& c : found) shortcuts += c.shortcut;
  trace_note("PWSTEAM nonsteam found shortcuts=%d folders=%d ms=%lld", shortcuts, static_cast<int>(found.size()) - shortcuts,
       static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count()));
  std::vector<bool> ticked(found.size(), false);
  int selected = 0;
  for (;;) {
    bp::FoundView view;
    view.subtitle = "FROM DESKTOP AND START SHORTCUTS, AND GAME FOLDERS ON C: AND THE USB DRIVES \xc2\xb7 STEAM GAMES LEFT OUT";
    for (std::size_t i = 0; i < found.size(); ++i)
      view.rows.push_back({found[i].name, found[i].program, found[i].arch, found[i].shortcut, ticked[i]});
    view.selected = selected;
    view.empty = "NO GAMES WERE FOUND IN SHORTCUTS OR GAME FOLDERS. SQUARE BROWSES FOR AN EXE.";
    view.note = "Setup, uninstall, update and crash-report programs are left out. A game already in the library is not listed "
                "again. Names and covers can be changed later on the game's page.";
    view.hints = {{bp::kNoButton, bp::kUpDown, "CHOOSE"}, {bp::kCross, "", "TICK"}, {bp::kSquare, "", "BROWSE"},
                  {bp::kNoButton, "OPTIONS", "ADD TICKED"}, {bp::kCircle, "", "CANCEL"}};
    Present([&](bp::Painter& p) { bp::DrawFound(p, view); });
    const unsigned button = steam_ui_wait(STEAM_UI_UP | STEAM_UI_DOWN | STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_SQUARE |
                                          STEAM_UI_OPTIONS);
    const int n = static_cast<int>(found.size());
    if (button == STEAM_UI_CIRCLE) return;
    if (button == STEAM_UI_UP && selected > 0) --selected;
    else if (button == STEAM_UI_DOWN && selected + 1 < n) ++selected;
    else if (button == STEAM_UI_CROSS && selected < n) ticked[static_cast<std::size_t>(selected)] = !ticked[static_cast<std::size_t>(selected)];
    else if (button == STEAM_UI_SQUARE) {
      AddBrowsed(shell);
      return;
    } else if (button == STEAM_UI_OPTIONS) {
      std::vector<orbisdesk::NonSteamGame> adds;
      for (std::size_t i = 0; i < found.size(); ++i)
        if (ticked[i]) adds.push_back(NewGame(found[i]));
      if (adds.empty()) continue;
      AddGames(shell, adds, std::vector<CoverPick>(adds.size()), std::vector<bool>(adds.size(), false));
      return;
    }
  }
}

// ---- the game page of a non-Steam game ----
enum NonSteamAction { kNsPlay, kNsResume, kNsCover, kNsEdit, kNsRemove, kNsCheck };

bool NonSteamRunning(Shell& shell, const Game& game) {
  if (shell.running_app == game.app) return true;
  return pw_hw_steam_exe_running && pw_hw_steam_exe_running(orbisdesk::WindowsBasename(game.ns.program).c_str());
}

bp::GameView NonSteamView(Shell& shell, const Game& game, std::vector<NonSteamAction>* actions) {
  bp::GameView view;
  view.frame = FrameFor(shell, bp::kLibrary);
  view.cover = CoverFor(shell, game);
  const auto& info = Info(shell, game);
  actions->clear();
  auto add = [&](const std::string& label, NonSteamAction action, bool disabled = false) {
    view.buttons.push_back(label);
    view.disabled.push_back(disabled);
    actions->push_back(action);
  };
  const std::string where = info.drive_name.empty() ? "THIS CONSOLE" : Upper(info.drive_name);
  const bool running = !info.offline && NonSteamRunning(shell, game);
  if (info.offline) {
    view.state = bp::kOffline;
    view.cover.offline = true;
    view.status = info.external ? "RECONNECT " + where + " TO PLAY THIS GAME" : "THE PROGRAM IS NOT WHERE IT WAS";
    add("CHECK AGAIN", kNsCheck);
    add("EDIT", kNsEdit);
    add("REMOVE FROM LIBRARY", kNsRemove);
    view.note = info.external ? "The game stays in the library. Its program is on " + info.letter + ", so it starts again once the drive is back."
                              : "The program was moved or deleted. Edit points the game at its new place.";
    view.note_warn = true;
  } else if (running) {
    view.state = bp::kRunning;
    view.status = "RUNNING \xc2\xb7 STARTED FROM BIG PICTURE";
    add(shell.running_app == game.app ? "RESUME GAME" : "RUNNING", kNsResume, shell.running_app != game.app);
    add("EDIT", kNsEdit, true);
    add("REMOVE FROM LIBRARY", kNsRemove, true);
    view.note = "Close the game before editing or removing it. The overlay menu's Steam entry brings this page back over a running game.";
  } else {
    view.state = bp::kInstalled;
    view.status = "ON " + where + (InOrbisDesk() ? "  \xc2\xb7  CROSS TO PLAY" : "");
    if (InOrbisDesk()) add("PLAY", kNsPlay);
    add("CHANGE COVER", kNsCover);
    add("EDIT", kNsEdit);
    add("REMOVE FROM LIBRARY", kNsRemove);
    view.note = "Play starts the program through the desktop, the same way Play starts a Steam game. Big Picture comes back when "
                "the game closes. No Steam emulator is used for a non-Steam game.";
  }
  const auto exe = info.offline ? orbisdesk::ExeInfo{} : orbisdesk::ReadExeInfo(orbisdesk::WindowsToUnix(game.ns.program));
  view.facts.push_back({"PROGRAM", game.ns.program});
  if (exe.pe) view.facts.push_back({"STARTS", orbisdesk::WindowsBasename(game.ns.program) + " \xc2\xb7 " + ArchName(exe.arch)});
  view.facts.push_back({"START IN", game.ns.folder});
  view.facts.push_back({"LAUNCH OPTIONS", game.ns.options.empty() ? "None" : game.ns.options});
  const auto played = shell.played.find(game.app);
  view.facts.push_back({"LAST PLAYED", played == shell.played.end() ? "Never from Big Picture" : PlayedWhen(played->second)});
  view.hints = {{bp::kCross, "", view.buttons.empty() ? "" : view.buttons[0]}, {bp::kNoButton, bp::kLeftRight, "ACTIONS"}};
  if (view.state == bp::kInstalled) view.hints.push_back({bp::kSquare, "", "CHANGE COVER"});
  if (view.state != bp::kRunning) view.hints.push_back({bp::kTriangle, "", "EDIT"});
  view.hints.push_back({bp::kCircle, "", "BACK"});
  return view;
}

// True when the game left the library (the page must close).
bool RemoveNonSteam(Shell& shell, const Game& game) {
  if (!Confirm("REMOVE FROM LIBRARY", game.name,
               "The game leaves Big Picture. Its files and its Desktop and Start shortcuts stay where they are.", "REMOVE",
               "CANCEL", true, 1))
    return false;
  auto games = orbisdesk::LoadNonSteamGames(NONSTEAM_FILE);
  games.erase(std::remove_if(games.begin(), games.end(), [&](const orbisdesk::NonSteamGame& g) { return g.id == game.app; }),
              games.end());
  if (!StoreGames(games)) {
    StorageMessage("REMOVE FROM LIBRARY\nTHE LIST OF GAMES COULD NOT BE SAVED ON THE CONSOLE.");
    return false;
  }
  unlink((std::string(kArtDir) + "/" + std::to_string(game.app) + ".cov").c_str());
  shell.covers.Forget(game.app);
  if (shell.favorites.erase(game.app)) SaveFavorites(shell.favorites);
  if (shell.played.erase(game.app)) SavePlayed(shell.played);
  shell.nonsteam_dirty = true;
  note("PWSTEAM nonsteam removed=1");
  return true;
}

// Edit: true when the game left the page (its program changed, so it is another entry now).
bool EditNonSteam(Shell& shell, const Game& game) {
  auto edited = game.ns;
  CoverPick cover;
  bool chosen = false;
  if (!DetailsScreen(shell, &edited, false, &cover, &chosen)) return false;
  auto games = orbisdesk::LoadNonSteamGames(NONSTEAM_FILE);
  if (edited.id != game.app)
    for (const auto& g : games)
      if (g.id == edited.id) {
        StorageMessage("EDIT\nTHAT PROGRAM IS ALREADY IN THE LIBRARY AS " + Upper(g.name) + ".");
        return false;
      }
  for (auto& g : games)
    if (g.id == game.app) {
      if (chosen) edited.cover = CoverSource(cover);
      g = edited;
    }
  if (!StoreGames(games)) {
    StorageMessage("EDIT\nTHE LIST OF GAMES COULD NOT BE SAVED ON THE CONSOLE.");
    return false;
  }
  const std::string old_cover = std::string(kArtDir) + "/" + std::to_string(game.app) + ".cov";
  if (edited.id != game.app) {
    // another program: the cover, favorite and last-played move with the game
    rename(old_cover.c_str(), (std::string(kArtDir) + "/" + std::to_string(edited.id) + ".cov").c_str());
    if (shell.favorites.erase(game.app)) shell.favorites.insert(edited.id), SaveFavorites(shell.favorites);
    const auto played = shell.played.find(game.app);
    if (played != shell.played.end()) {
      shell.played[edited.id] = played->second;
      shell.played.erase(game.app);
      SavePlayed(shell.played);
    }
    shell.covers.Forget(game.app);
  }
  if (chosen) SaveCover(shell, edited.id, cover);
  note("PWSTEAM nonsteam edited program_changed=%d cover=%d", edited.id != game.app, chosen);
  shell.nonsteam_dirty = true;
  if (edited.id != game.app) return true;
  // the same entry: the page shows the new values at once
  for (auto& g : shell.library.games)
    if (g.app == game.app) g.name = edited.name, g.ns = edited;
  RefreshGame(shell, game);
  return false;
}

void ChangeNonSteamCover(Shell& shell, const Game& game) {
  // the entry as saved: an edit on this page may have renamed it after the page opened
  auto games = orbisdesk::LoadNonSteamGames(NONSTEAM_FILE);
  orbisdesk::NonSteamGame current = game.ns;
  for (const auto& g : games)
    if (g.id == game.app) current = g;
  CoverPick pick;
  if (!ChooseCover(shell, current, &pick)) return;
  for (auto& g : games)
    if (g.id == game.app) g.cover = CoverSource(pick);
  StoreGames(games);
  SaveCover(shell, game.app, pick);
  note("PWSTEAM nonsteam cover kind=%d provider=%s", pick.kind, pick.kind == 0 ? pick.provider.c_str() : "-");
}

void NonSteamScreen(Shell& shell, const Game& game) {
  int focus = 0;
  trace_note("PWSTEAM bigpicture game_page open non_steam=1");
  for (;;) {
    std::vector<NonSteamAction> actions;
    bp::GameView view = NonSteamView(shell, game, &actions);
    if (focus >= static_cast<int>(actions.size())) focus = 0;
    view.focus = focus;
    Present([&](bp::Painter& p) { bp::DrawGame(p, view); });
    const unsigned button = steam_ui_wait_for(STEAM_UI_CROSS | STEAM_UI_CIRCLE | STEAM_UI_TRIANGLE | STEAM_UI_SQUARE |
                                                  STEAM_UI_LEFT | STEAM_UI_RIGHT,
                                              2000);
    if (!button) {
      RefreshGame(shell, game);  // a drive plugged in, a game that ended
      continue;
    }
    if (button == STEAM_UI_CIRCLE) return;
    if (button == STEAM_UI_LEFT || button == STEAM_UI_RIGHT) {
      const int n = static_cast<int>(actions.size());
      if (n) focus = (focus + (button == STEAM_UI_RIGHT ? 1 : n - 1)) % n;
      continue;
    }
    NonSteamAction action;
    if (button == STEAM_UI_CROSS) {
      if (actions.empty() || view.disabled[static_cast<std::size_t>(focus)]) continue;
      action = actions[static_cast<std::size_t>(focus)];
    } else if (button == STEAM_UI_SQUARE) {
      if (view.state != bp::kInstalled) continue;
      action = kNsCover;
    } else {  // triangle
      if (view.state == bp::kRunning) continue;
      action = kNsEdit;
    }
    switch (action) {
      case kNsPlay: PlayGame(shell, game); break;
      case kNsResume: WaitForGame(shell); break;
      case kNsCover: ChangeNonSteamCover(shell, game); break;
      case kNsEdit:
        if (EditNonSteam(shell, game)) return;
        break;
      case kNsRemove:
        if (RemoveNonSteam(shell, game)) return;
        break;
      case kNsCheck: break;
    }
    RefreshGame(shell, game);
  }
}
