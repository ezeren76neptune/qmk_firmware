// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

/* The ChibiOS-Contrib LPC system timer driver only implements periodic SysTick
 * mode. Its tick-less ("free running") functions are stubs with no interrupt
 * handler, so with QMK's default CH_CFG_ST_TIMEDELTA the first sleep never
 * returns and the SysTick exception lands in _unhandled_exception: no USB,
 * no LEDs. Use a 10 kHz periodic tick instead (SysTick reload 4799 at 48 MHz). */
#define CH_CFG_ST_TIMEDELTA 0
#define CH_CFG_ST_FREQUENCY 10000

#include_next <chconf.h>
