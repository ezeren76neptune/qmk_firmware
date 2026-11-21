// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

/*
 * Bootloader jump for NXP LPC11Uxx: re-invokes the boot ROM ISP.
 *
 * LPC11U2x/3x: with USB_VBUS (PIO0_3) high the ROM enumerates as a USB
 * mass-storage drive ("CRP DISABLD") holding firmware.bin; replacing that file
 * reflashes the MCU. With VBUS low it falls back to UART ISP.
 * LPC11U1x: the boot ROM has no USB stack, so this always lands in UART ISP
 * (PIO0_18 = RXD, PIO0_19 = TXD; Flash Magic, lpc21isp, autobaud).
 *
 * bootloader_jump() only sets a RAM marker and resets, so the ROM is entered
 * from a just-reset MCU (IRC clock, peripherals in reset state) via
 * enter_bootloader_mode_if_requested(), which QMK runs first in __early_init.
 */

#include "bootloader.h"

#include <ch.h>
#include <hal.h>

#include "lpc11u_iap.h"

extern uint32_t __ram0_end__;

#define SYMVAL(sym) (uint32_t)(((uint8_t *)&(sym)) - ((uint8_t *)0))
#define BOOTLOADER_MAGIC 0x4C504349U /* "LPCI" */
#define MAGIC_ADDR ((volatile uint32_t *)(SYMVAL(__ram0_end__) - 4))

/* Must not live on the stack: MSP is moved right before the ROM call. */
static uint32_t iap_command[5];
static uint32_t iap_result[5];

__attribute__((weak)) void bootloader_jump(void) {
    *MAGIC_ADDR = BOOTLOADER_MAGIC;
    NVIC_SystemReset();
}

__attribute__((weak)) void mcu_reset(void) {
    NVIC_SystemReset();
}

void enter_bootloader_mode_if_requested(void) {
    if (*MAGIC_ADDR != BOOTLOADER_MAGIC) {
        return;
    }
    *MAGIC_ADDR = 0;

    __disable_irq();
    SysTick->CTRL = 0;
    NVIC->ICER[0] = 0xFFFFFFFFU;
    NVIC->ICPR[0] = 0xFFFFFFFFU;

    /* Clocks the ROM ISP expects to be running (LPCOpen Chip_FLASH_ReInvokeISP):
     * GPIO (bit 6), CT32B1 (bit 10), USB (bit 14), IOCON (bit 16). */
    LPC_SYSCON->SYSAHBCLKCTRL |= (1U << 6) | (1U << 10) | (1U << 14) | (1U << 16);
    LPC_SYSCON->SYSAHBCLKDIV = 1;

    iap_command[0]                                  = LPC_IAP_CMD_REINVOKE_ISP;
    *((volatile uint32_t *)LPC_ISP_MSD_STATE_ADDRESS) = 0;

    /* Give the ROM a stack at the top of ram0 (just under the IAP scratch area),
     * well clear of the low SRAM the ISP code uses. This must be the last thing
     * done before the call: locals are unusable once MSP moves. */
    __set_MSP(SYMVAL(__ram0_end__) & ~7U);
    lpc_iap_call(iap_command, iap_result);

    while (true) {
    }
}
