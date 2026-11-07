// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>

// printf-style log line writer (steam_s2.cpp's note)
using NoteFn = void (*)(const char* format, ...);

// Logs why HTTP over curl would fail on this console, step by step (native/steam/steam_netdiag.cpp)
void SteamNetDiagnosis(const std::string& ca, const NoteFn& note);
