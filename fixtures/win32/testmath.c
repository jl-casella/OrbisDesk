/* SPDX-License-Identifier: LGPL-2.1-or-later */
volatile unsigned factor = 5;
volatile unsigned bias = 30;
unsigned Scale(unsigned value) { return value * factor + 7; }
unsigned OrdinalScale(unsigned value) { return value + bias; }
