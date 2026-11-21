// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/*
 * NXP LPC11Uxx pin naming for QMK.
 *
 *   A0..A23 = PIO0_0..PIO0_23  (port 0 is 24 bits wide)
 *   B0..B31 = PIO1_0..PIO1_31  (only the pins bonded out on the package exist)
 *
 * Pins with a fixed role on a typical USB design:
 *   A0 = /RESET, A1 = ISP strap, A3 = USB_VBUS, A6 = USB_CONNECT,
 *   A10 = SWCLK, A15 = SWDIO. Avoid them in matrices unless the board
 *   repurposes them (A10/A15 lose SWD when used as GPIO).
 */

/* The LPC PAL driver #undefs PAL_MODE_INPUT without redefining it, so pull in
 * the HAL first (as the Kinetis pin defs do) and supply a floating input. */
#include <hal.h>
#if !defined(PAL_MODE_INPUT)
#    define PAL_MODE_INPUT (MODE_DIR_IN | MODE_MODE_INACTIVE | MODE_AD_DIGITAL)
#endif

/*
 * On PIO0_0 (RESET), PIO0_10 (SWCLK) and PIO0_11..PIO0_15 (JTAG/SWD) GPIO is
 * IOCON function 1, not function 0, and the ChibiOS LPC PAL always writes the
 * function bits from the mode. Pick the GPIO function per pin here so QMK's
 * gpio_* helpers (and therefore the matrix code) work on every pad.
 * Note: using A0 or A10/A15 as GPIO gives up /RESET or SWD respectively.
 */
static inline iomode_t lpc_gpio_mode(ioline_t line, iomode_t mode) {
    uint32_t pad = PAL_PAD(line);
    if (PAL_PORT(line) == IOPORT0 && (pad == 0U || (pad >= 10U && pad <= 15U))) {
        mode |= MODE_FUNC_ALT1;
    }
    return mode;
}

#define gpio_set_pin_input(pin) palSetLineMode((pin), lpc_gpio_mode((pin), PAL_MODE_INPUT))
#define gpio_set_pin_input_high(pin) palSetLineMode((pin), lpc_gpio_mode((pin), PAL_MODE_INPUT_PULLUP))
#define gpio_set_pin_input_low(pin) palSetLineMode((pin), lpc_gpio_mode((pin), PAL_MODE_INPUT_PULLDOWN))
#define gpio_set_pin_output_push_pull(pin) palSetLineMode((pin), lpc_gpio_mode((pin), PAL_MODE_OUTPUT_PUSHPULL))
#define gpio_set_pin_output_open_drain(pin) palSetLineMode((pin), lpc_gpio_mode((pin), PAL_MODE_OUTPUT_OPENDRAIN))

#define A0 PAL_LINE(IOPORT0, 0)
#define A1 PAL_LINE(IOPORT0, 1)
#define A2 PAL_LINE(IOPORT0, 2)
#define A3 PAL_LINE(IOPORT0, 3)
#define A4 PAL_LINE(IOPORT0, 4)
#define A5 PAL_LINE(IOPORT0, 5)
#define A6 PAL_LINE(IOPORT0, 6)
#define A7 PAL_LINE(IOPORT0, 7)
#define A8 PAL_LINE(IOPORT0, 8)
#define A9 PAL_LINE(IOPORT0, 9)
#define A10 PAL_LINE(IOPORT0, 10)
#define A11 PAL_LINE(IOPORT0, 11)
#define A12 PAL_LINE(IOPORT0, 12)
#define A13 PAL_LINE(IOPORT0, 13)
#define A14 PAL_LINE(IOPORT0, 14)
#define A15 PAL_LINE(IOPORT0, 15)
#define A16 PAL_LINE(IOPORT0, 16)
#define A17 PAL_LINE(IOPORT0, 17)
#define A18 PAL_LINE(IOPORT0, 18)
#define A19 PAL_LINE(IOPORT0, 19)
#define A20 PAL_LINE(IOPORT0, 20)
#define A21 PAL_LINE(IOPORT0, 21)
#define A22 PAL_LINE(IOPORT0, 22)
#define A23 PAL_LINE(IOPORT0, 23)

#define B0 PAL_LINE(IOPORT1, 0)
#define B1 PAL_LINE(IOPORT1, 1)
#define B2 PAL_LINE(IOPORT1, 2)
#define B3 PAL_LINE(IOPORT1, 3)
#define B4 PAL_LINE(IOPORT1, 4)
#define B5 PAL_LINE(IOPORT1, 5)
#define B6 PAL_LINE(IOPORT1, 6)
#define B7 PAL_LINE(IOPORT1, 7)
#define B8 PAL_LINE(IOPORT1, 8)
#define B9 PAL_LINE(IOPORT1, 9)
#define B10 PAL_LINE(IOPORT1, 10)
#define B11 PAL_LINE(IOPORT1, 11)
#define B12 PAL_LINE(IOPORT1, 12)
#define B13 PAL_LINE(IOPORT1, 13)
#define B14 PAL_LINE(IOPORT1, 14)
#define B15 PAL_LINE(IOPORT1, 15)
#define B16 PAL_LINE(IOPORT1, 16)
#define B17 PAL_LINE(IOPORT1, 17)
#define B18 PAL_LINE(IOPORT1, 18)
#define B19 PAL_LINE(IOPORT1, 19)
#define B20 PAL_LINE(IOPORT1, 20)
#define B21 PAL_LINE(IOPORT1, 21)
#define B22 PAL_LINE(IOPORT1, 22)
#define B23 PAL_LINE(IOPORT1, 23)
#define B24 PAL_LINE(IOPORT1, 24)
#define B25 PAL_LINE(IOPORT1, 25)
#define B26 PAL_LINE(IOPORT1, 26)
#define B27 PAL_LINE(IOPORT1, 27)
#define B28 PAL_LINE(IOPORT1, 28)
#define B29 PAL_LINE(IOPORT1, 29)
#define B30 PAL_LINE(IOPORT1, 30)
#define B31 PAL_LINE(IOPORT1, 31)
