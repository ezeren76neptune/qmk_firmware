// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

/*
 * pinfinder: maps an unknown key matrix by typing what it finds.
 *
 * Every 20 ms each candidate pin is driven low in turn while all the others sit
 * as pulled-up inputs. A pin that reads low is connected to the driven one.
 * Connections present during the first second (straps, LED networks, shorts)
 * are learnt as a baseline and ignored. Afterwards, every new connection is
 * typed into whatever text field has focus, e.g.
 *
 *     A7>B14
 *
 * meaning "driving A7 low pulls B14 low", i.e. a switch (+ diode) between them:
 * A7 belongs in "rows" and B14 in "cols" with "diode_direction": "COL2ROW".
 * If a key only ever shows up the other way round (B14>A7), use ROW2COL.
 *
 * Pin names follow QMK's LPC11Uxx convention: A<n> = PIO0_<n>, B<n> = PIO1_<n>.
 * /RESET (A0), USB_VBUS (A3), USB_CONNECT (A6) and the SWD pins (A10, A15) are
 * never touched, so the debugger stays usable.
 */

#include QMK_KEYBOARD_H
#include "send_string.h"

// clang-format off
const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [0] = LAYOUT(
        KC_NO, KC_NO, KC_NO, KC_NO, KC_NO,
        KC_NO, KC_NO, KC_NO, KC_NO, KC_NO,
        KC_NO, KC_NO, KC_NO, KC_NO, KC_NO,
        KC_NO, KC_NO, KC_NO, KC_NO, KC_NO,
        KC_NO, KC_NO, KC_NO, KC_NO, KC_NO,
        KC_NO
    ),
};
// clang-format on

/* Every GPIO bonded out on the LQFP48 package (LPC11U1x datasheet, Fig. 3),
 * minus /RESET, USB_VBUS, USB_CONNECT and the SWD pins. */
#define PORT0_COUNT 19
#define PORT1_COUNT 16
static const uint8_t port0_pads[PORT0_COUNT] = {1, 2, 4, 5, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23};
static const uint8_t port1_pads[PORT1_COUNT] = {13, 14, 15, 16, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31};
#define PIN_COUNT (PORT0_COUNT + PORT1_COUNT)

#define BASELINE_SCANS 50 /* 50 x 20 ms = 1 s */
#define STARTUP_DELAY_MS 3000

static uint64_t baseline[PIN_COUNT];
static uint64_t reported[PIN_COUNT];
static uint8_t  scans;

static pin_t probe_pin(uint8_t i) {
    return i < PORT0_COUNT ? PAL_LINE(IOPORT0, port0_pads[i]) : PAL_LINE(IOPORT1, port1_pads[i - PORT0_COUNT]);
}

static void append_name(char **p, uint8_t i) {
    uint8_t pad = i < PORT0_COUNT ? port0_pads[i] : port1_pads[i - PORT0_COUNT];
    *(*p)++     = i < PORT0_COUNT ? 'A' : 'B';
    if (pad >= 10) *(*p)++ = '0' + pad / 10;
    *(*p)++ = '0' + pad % 10;
}

static void report(uint8_t from, uint8_t to) {
    char  buf[12];
    char *p = buf;
    append_name(&p, from);
    *p++ = '>';
    append_name(&p, to);
    *p++ = '\n';
    *p   = '\0';
    send_string(buf);
}

/* Drive pin i low and return the set of other pins that follow it. */
static uint64_t probe_once(uint8_t i) {
    pin_t drive = probe_pin(i);
    gpio_set_pin_output(drive);
    gpio_write_pin_low(drive);
    wait_us(20);
    uint64_t seen = 0;
    for (uint8_t j = 0; j < PIN_COUNT; j++) {
        if (j != i && !gpio_read_pin(probe_pin(j))) {
            seen |= (uint64_t)1 << j;
        }
    }
    gpio_set_pin_input_high(drive);
    wait_us(20);
    return seen;
}

/* Two back-to-back probes must agree: cheap debounce without extra state. */
static uint64_t probe_one(uint8_t i) {
    uint64_t a = probe_once(i);
    return a & probe_once(i);
}

void matrix_init_custom(void) {
    for (uint8_t i = 0; i < PIN_COUNT; i++) {
        gpio_set_pin_input_high(probe_pin(i));
    }
}

bool matrix_scan_custom(matrix_row_t current_matrix[]) {
    return false;
}

void housekeeping_task_user(void) {
    static uint32_t last_probe = 0;
    if (timer_read32() < STARTUP_DELAY_MS || timer_elapsed32(last_probe) < 20) {
        return;
    }
    last_probe = timer_read32();

    bool learning = scans < BASELINE_SCANS;
    for (uint8_t i = 0; i < PIN_COUNT; i++) {
        uint64_t seen = probe_one(i);
        if (learning) {
            baseline[i] |= seen;
            continue;
        }
        uint64_t active = seen & ~baseline[i];
        uint64_t fresh  = active & ~reported[i];
        for (uint8_t j = 0; fresh; j++, fresh >>= 1) {
            if (fresh & 1) {
                report(i, j);
            }
        }
        reported[i] = active;
    }
    if (learning && ++scans == BASELINE_SCANS) {
        send_string("pinfinder ready\n");
    }
}
