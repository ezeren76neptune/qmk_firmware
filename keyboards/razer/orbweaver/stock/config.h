// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/*
 * Pin map read out of the stock Razer firmware (v1.01) on the "CHERYL"
 * controller board:
 *   matrix  : rows PIO0_12/13/14/16/11 driven low, cols PIO1_16, PIO0_2/20/17/7,
 *             PIO1_28 read with pull-ups (key table at 0x3BFA, pin table 0x3C1E)
 *   backlight: PIO0_22 (CT16B1_MAT1 in stock), active low
 *   keymap LEDs: Razer LED ids 0x0C/0x0D/0x0E (OpenRazer red/green/blue profile
 *             LEDs) map to PIO1_14 / PIO1_15 / PIO1_13, active low
 */
#define ORBWEAVER_LED_RED_PIN B14
#define ORBWEAVER_LED_GREEN_PIN B15
#define ORBWEAVER_LED_BLUE_PIN B13
#define ORBWEAVER_LED_ON_STATE 0

/* Size: QMK has to fit in the 16 KiB the Razer bootloader can write. */
#define NO_ACTION_ONESHOT
#define LAYER_STATE_8BIT
