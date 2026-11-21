// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/* Each LPC11Uxx logical endpoint has independent IN and OUT halves. */
#define USB_ENDPOINTS_ARE_REORDERABLE

/* bootloader_jump() sets a RAM marker and resets; the jump into the ROM ISP
 * then happens from __early_init, before clocks/USB are reconfigured. */
#ifndef EARLY_INIT_PERFORM_BOOTLOADER_JUMP
#    define EARLY_INIT_PERFORM_BOOTLOADER_JUMP TRUE
#endif
