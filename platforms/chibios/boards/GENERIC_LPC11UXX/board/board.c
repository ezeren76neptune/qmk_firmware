// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#include <hal.h>

/* Pin configurations required before hal init; mirrors the ChibiOS-Contrib
 * LPC11U35_GENERIC board. QMK renames these to __chibios_override_* so that
 * the bootloader-request check runs first (see tmk_core/protocol/chibios). */
static void lpc_board_pins(void) {
    /* Keep /RESET and the ISP strap as pulled-up inputs. */
    palSetLineMode(LINE_RESET, MODE_DIR_IN | MODE_MODE_PULL_UP | MODE_AD_DIGITAL);
    palSetLineMode(LINE_ISP, MODE_DIR_IN | MODE_MODE_PULL_UP | MODE_AD_DIGITAL);
    /* Hand VBUS sense and the soft-connect pull-up to the USB block. */
    palSetLineMode(LINE_USBVBUS, MODE_FUNC_ALT1 | MODE_MODE_PULL_UP | MODE_AD_DIGITAL);
    palSetLineMode(LINE_USBCONN, MODE_FUNC_ALT1);
}

/* Started by a bootloader instead of the boot ROM: the Cortex-M0 has no VTOR,
 * so copy the vector table to the start of SRAM and map interrupts there
 * (SYSMEMREMAP = user RAM mode). The linker script must keep
 * 0x10000000-0x100000BF out of ram0. Also clears the sticky reset-cause
 * flags so a bootloader looking at SYSRSTSTAT sees only the next reset. */
static void lpc_vectors_to_ram(void) {
    extern const uint32_t _vectors[];
    if ((uint32_t)_vectors == 0U) {
        return;
    }
    volatile uint32_t *ram = (volatile uint32_t *)0x10000000U;
    for (uint32_t i = 0; i < 16U + 32U; i++) {
        ram[i] = _vectors[i];
    }
    LPC_SYSCON->SYSMEMREMAP = 1U;
    LPC_SYSCON->SYSRSTSTAT  = LPC_SYSCON->SYSRSTSTAT;
}

__attribute__((weak)) void __early_init(void) {
    lpc_vectors_to_ram();
    /* This runs before halInit(), so the GPIO and IOCON clocks are still at
     * their reset value (off) unless the boot ROM happened to leave them on.
     * With them off, IOCON writes are silently dropped and USB never attaches
     * (seen on the Orbweaver's LPC11U13). */
    LPC_SYSCON->SYSAHBCLKCTRL |= SYSCON_SYSAHBCLKCTRL_GPIO | SYSCON_SYSAHBCLKCTRL_IOCON;
    lpc_board_pins();
}

__attribute__((weak)) void boardInit(void) {
    /* Again after halInit(), in case __early_init was overridden. */
    lpc_board_pins();
}
