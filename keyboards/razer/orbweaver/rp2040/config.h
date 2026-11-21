// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/* Single-colour key backlight: GP26 = PWM slice 5, channel A. Drive the
 * backlight MOSFET / LED driver on the switch board from this pin; a GPIO
 * cannot source the current for all key LEDs directly. */
#define BACKLIGHT_PWM_DRIVER PWMD5
#define BACKLIGHT_PWM_CHANNEL RP2040_PWM_CHANNEL_A

/* Thumb-module keymap indicator LEDs (see orbweaver.c). */
#define ORBWEAVER_LED_RED_PIN GP27
#define ORBWEAVER_LED_GREEN_PIN GP28
#define ORBWEAVER_LED_BLUE_PIN GP29

#define RP2040_BOOTLOADER_DOUBLE_TAP_RESET
#define RP2040_BOOTLOADER_DOUBLE_TAP_RESET_TIMEOUT 500U
