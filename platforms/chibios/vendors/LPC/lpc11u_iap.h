// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/*
 * NXP LPC11Uxx boot ROM In-Application-Programming (IAP) entry point
 * (UM10462, "Flash/EEPROM programming firmware" chapter).
 *
 * IAP uses the top 32 bytes of SRAM0 as scratch; the LPC11Uxx linker scripts
 * in platforms/chibios/boards/GENERIC_LPC11UXX/ld keep that area out of ram0.
 */

#include <stdint.h>

#define LPC_IAP_ENTRY_ADDRESS 0x1FFF1FF1UL

#define LPC_IAP_CMD_PREPARE_SECTORS 50U
#define LPC_IAP_CMD_COPY_RAM_TO_FLASH 51U
#define LPC_IAP_CMD_ERASE_SECTORS 52U
#define LPC_IAP_CMD_REINVOKE_ISP 57U
#define LPC_IAP_CMD_READ_UID 58U
#define LPC_IAP_CMD_EEPROM_WRITE 61U
#define LPC_IAP_CMD_EEPROM_READ 62U

#define LPC_IAP_STATUS_CMD_SUCCESS 0U

/* ROM variable cleared before ReinvokeISP so the USB-MSC ISP restarts cleanly
 * (NXP LPC11Uxx USB ROM examples, init_msdstate()). */
#define LPC_ISP_MSD_STATE_ADDRESS 0x10000054UL

typedef void (*lpc_iap_entry_t)(uint32_t *command, uint32_t *result);

static inline void lpc_iap_call(uint32_t *command, uint32_t *result) {
    ((lpc_iap_entry_t)LPC_IAP_ENTRY_ADDRESS)(command, result);
}
