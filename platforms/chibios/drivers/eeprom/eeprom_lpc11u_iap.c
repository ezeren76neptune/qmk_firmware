// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

/*
 * EEPROM driver for the on-chip EEPROM of NXP LPC11Uxx parts, accessed through
 * the boot ROM IAP "Write EEPROM" (61) / "Read EEPROM" (62) commands.
 * The ROM routines run from ROM and do not touch flash, so interrupts can stay
 * enabled; data is bounced through a RAM buffer because IAP needs RAM addresses.
 */

#include <stdint.h>
#include <string.h>

#include <hal.h>

#include "eeprom_driver.h"
#include "eeprom_lpc11u_iap.h"
#include "lpc11u_iap.h"

#define IAP_CHUNK 64U

static uint32_t iap_command[5];
static uint32_t iap_result[5];
static uint8_t  bounce[IAP_CHUNK] __attribute__((aligned(4)));

static size_t clamp_length(intptr_t offset, size_t len) {
    if (offset < 0 || offset >= LPC11U_EEPROM_SIZE) {
        return 0;
    }
    if ((size_t)offset + len > LPC11U_EEPROM_SIZE) {
        len = LPC11U_EEPROM_SIZE - (size_t)offset;
    }
    return len;
}

static bool iap_eeprom(uint32_t command, uint32_t eeprom_addr, uint8_t *ram, uint32_t len) {
    iap_command[0] = command;
    iap_command[1] = eeprom_addr;
    iap_command[2] = (uint32_t)ram;
    iap_command[3] = len;
    iap_command[4] = CPU_CLOCK / 1000U; /* system clock in kHz */
    lpc_iap_call(iap_command, iap_result);
    return iap_result[0] == LPC_IAP_STATUS_CMD_SUCCESS;
}

void eeprom_driver_init(void) {}

void eeprom_driver_erase(void) {
    memset(bounce, 0x00, sizeof(bounce));
    for (uint32_t addr = 0; addr < LPC11U_EEPROM_SIZE; addr += IAP_CHUNK) {
        uint32_t n = LPC11U_EEPROM_SIZE - addr;
        iap_eeprom(LPC_IAP_CMD_EEPROM_WRITE, addr, bounce, n < IAP_CHUNK ? n : IAP_CHUNK);
    }
}

void eeprom_read_block(void *buf, const void *addr, size_t len) {
    intptr_t offset = (intptr_t)addr;
    uint8_t *dst    = buf;
    memset(dst, 0x00, len);
    len = clamp_length(offset, len);
    while (len > 0) {
        uint32_t n = len < IAP_CHUNK ? len : IAP_CHUNK;
        if (iap_eeprom(LPC_IAP_CMD_EEPROM_READ, (uint32_t)offset, bounce, n)) {
            memcpy(dst, bounce, n);
        }
        dst += n;
        offset += n;
        len -= n;
    }
}

void eeprom_write_block(const void *buf, void *addr, size_t len) {
    intptr_t       offset = (intptr_t)addr;
    const uint8_t *src    = buf;
    len                   = clamp_length(offset, len);
    while (len > 0) {
        uint32_t n = len < IAP_CHUNK ? len : IAP_CHUNK;
        memcpy(bounce, src, n);
        iap_eeprom(LPC_IAP_CMD_EEPROM_WRITE, (uint32_t)offset, bounce, n);
        src += n;
        offset += n;
        len -= n;
    }
}
