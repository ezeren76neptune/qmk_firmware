// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#include QMK_KEYBOARD_H

enum layers {
    _BASE, // Razer factory default keymap
    _NUMS, // modifiers swapped for plain keys, like the reference ports
    _GAME, // blank game profile: everything falls through to _BASE
    _FN,   // hold key 01
};

/*
 * Key 01 is LT(_FN, `): tap for `, hold for the function layer.
 * Holding key 01 while plugging in enters the bootloader (bootmagic on rp2040,
 * the Razer bootloader itself on the stock controller).
 *
 *        ┌───┬───┬───┬───┬───┐
 *        │01 │02 │03 │04 │05 │
 *        ├───┼───┼───┼───┼───┤
 *        │06 │07 │08 │09 │10 │
 *        ├───┼───┼───┼───┼───┤          ┌────┐  ┌───┐
 *        │11 │12 │13 │14 │15 │          │Up- │  │ ↑ │
 *        ├───┼───┼───┼───┼───┤          │per │┌─┼───┼─┐
 *        │16 │17 │18 │19 │20 │          └────┘│←│   │→│
 *        └───┴───┴───┴───┴───┘                └─┼───┼─┘
 *                                       ┌─────┐ │ ↓ │
 *                                       │Lower│ └───┘
 *                                       └─────┘
 */
// clang-format off
const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    [_BASE] = LAYOUT(
        LT(_FN, KC_GRV), KC_1, KC_2, KC_3, KC_4,
        KC_TAB,          KC_Q, KC_W, KC_E, KC_R,
        KC_CAPS,         KC_A, KC_S, KC_D, KC_F,
        KC_LSFT,         KC_Z, KC_X, KC_C, KC_V,
        KC_LALT, KC_UP, KC_DOWN, KC_RIGHT, KC_LEFT,
        KC_SPC
    ),
    [_NUMS] = LAYOUT(
        _______, KC_1, KC_2, KC_3, KC_4,
        KC_5,    KC_Q, KC_W, KC_E, KC_R,
        KC_6,    KC_A, KC_S, KC_D, KC_F,
        KC_7,    KC_Z, KC_X, KC_C, KC_V,
        KC_8,    _______, _______, _______, _______,
        _______
    ),
    [_GAME] = LAYOUT(
        _______, _______, _______, _______, _______,
        _______, _______, _______, _______, _______,
        _______, _______, _______, _______, _______,
        _______, _______, _______, _______, _______,
        _______, _______, _______, _______, _______,
        _______
    ),
    [_FN] = LAYOUT(
        _______, TO(_BASE), TO(_NUMS), TO(_GAME), QK_BOOT,
        BL_TOGG, BL_DOWN,   BL_UP,     BL_BRTG,   EE_CLR,
        _______, KC_MPRV,   KC_MPLY,   KC_MNXT,   KC_MUTE,
        _______, KC_VOLD,   KC_VOLU,   _______,   _______,
        _______, _______,   _______,   _______,   _______,
        _______
    ),
};
// clang-format on
