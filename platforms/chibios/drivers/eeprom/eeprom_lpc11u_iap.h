// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/* LPC11Uxx parts carry 4 KiB of true EEPROM; the top 64 bytes are reserved by
 * NXP and cannot be written, leaving 4032 bytes. */
#ifndef LPC11U_EEPROM_SIZE
#    define LPC11U_EEPROM_SIZE 4032
#endif
