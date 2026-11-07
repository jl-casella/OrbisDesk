/* SPDX-License-Identifier: LGPL-2.1-or-later */
__declspec(dllimport) unsigned Scale(unsigned value);
unsigned NestedScale(unsigned value) { return Scale(value); }
unsigned NestedOrdinal(unsigned value) { return value + 30; }
