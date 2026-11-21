// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

/*
 * LPC11Uxx drivers configuration for ChibiOS-Contrib.
 *
 * Default clocking: 12 MHz crystal on XTALIN/XTALOUT -> system PLL x4 = 48 MHz
 * core, USB PLL 48 MHz. Every value is overridable from a keyboard mcuconf.h
 * (#include_next <mcuconf.h> then #undef/#define).
 */

#define LPC11Uxx_MCUCONF

/* Clock tree */
#define LPC_USE_SYSOSC TRUE
#define LPC_SYSOSC_FREQUENCY 12000000UL
#define LPC_SYSPLLCLKSEL SYSCON_SYSPLLCLKSEL_SYSOSC
#define LPC_MAINCLKSEL SYSCON_MAINCLKSEL_PLLOUT
#define LPC_SYSPLL_MULT 4 /* 12 MHz * 4 = 48 MHz */
#define LPC_SYSPLL_PDIV 4 /* FCCO = 48 MHz * 2 * 2 = 192 MHz (156..320) */
#define LPC_SYS_DIV 1

/* USB */
#define LPC_USB_USE_USB1 TRUE
#define LPC_USB_USB1_IRQ_PRIORITY 3
