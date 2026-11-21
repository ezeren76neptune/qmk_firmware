// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#define BOARD_GENERIC_LPC11UXX
#define BOARD_NAME "Generic LPC11Uxx"

/*
 * The ChibiOS-Contrib LPC11Uxx registry only recognises LPC11U35. LPC11U24 and
 * LPC11U35 have identical USB, GPIO, SSP, USART and SysTick blocks (the only
 * peripherals that HAL drives); they differ only in flash/SRAM size, which is
 * handled by the linker script selected in mcu_selection.mk.
 */
#if !defined(LPC11U35)
#    define LPC11U35
#endif

/* Map the two LPC GPIO ports onto QMK's port-letter pin names:
 *   A0..A23 = PIO0_0..PIO0_23,  B0..B31 = PIO1_0..PIO1_31 */
#define GPIOA IOPORT0
#define GPIOB IOPORT1

/* Pins with a fixed role on every LPC11Uxx USB design. Boards that do not
 * wire USB_VBUS / USB_CONNECT can override the weak __early_init(). */
#define LINE_RESET PAL_LINE(IOPORT0, 0)   /* PIO0_0  = /RESET            */
#define LINE_ISP PAL_LINE(IOPORT0, 1)     /* PIO0_1  = ISP entry (low)   */
#define LINE_USBVBUS PAL_LINE(IOPORT0, 3) /* PIO0_3  = USB_VBUS          */
#define LINE_USBCONN PAL_LINE(IOPORT0, 6) /* PIO0_6  = USB_CONNECT (D+)  */
#define LINE_SWCLK PAL_LINE(IOPORT0, 10)  /* PIO0_10 = SWCLK             */
#define LINE_SWDIO PAL_LINE(IOPORT0, 15)  /* PIO0_15 = SWDIO             */

#if !defined(_FROM_ASM_)
#    ifdef __cplusplus
extern "C" {
#    endif
void boardInit(void);
#    ifdef __cplusplus
}
#    endif
#endif /* _FROM_ASM_ */
