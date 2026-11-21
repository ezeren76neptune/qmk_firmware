// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#include <hal.h>
#include "quantum.h"
#include "bootloader.h"
#include "lpc11u_iap.h"

#ifdef BACKLIGHT_ENABLE
/*
 * Breathing for the software backlight driver, which has none of its own
 * (QMK only breathes with hardware PWM, and the LPC11U port has no PWM
 * driver): BL_BRTG steps the brightness through every level and back.
 */
#    ifndef ORBWEAVER_BREATH_STEP_MS
#        define ORBWEAVER_BREATH_STEP_MS 190 /* 2 * BACKLIGHT_LEVELS steps per breath */
#    endif
static bool     breathing;
static uint8_t  breath_step;
static uint16_t breath_timer;

bool process_record_kb(uint16_t keycode, keyrecord_t *record) {
    if (keycode == BL_BRTG) {
        if (record->event.pressed) {
            breathing = !breathing;
            if (!breathing) {
                backlight_set(is_backlight_enabled() ? get_backlight_level() : 0);
            }
        }
        return false;
    }
    return process_record_user(keycode, record);
}

void housekeeping_task_kb(void) {
    if (breathing && is_backlight_enabled() && timer_elapsed(breath_timer) >= ORBWEAVER_BREATH_STEP_MS) {
        breath_timer = timer_read();
        breath_step  = (breath_step + 1) % (2 * BACKLIGHT_LEVELS);
        backlight_set(breath_step <= BACKLIGHT_LEVELS ? breath_step : 2 * BACKLIGHT_LEVELS - breath_step);
    }
    housekeeping_task_user();
}
#endif

/*
 * QMK runs at 0x1000 behind Razer's own USB bootloader (1532:110D, the one
 * Synapse used for firmware updates); util/razer_orbweaver_usb_flash.py
 * writes a new QMK through it.
 *
 * The bootloader stays in update mode at reset when the word at 0x5FFC holds
 * 0x12345678 ("update in progress"), and its finish command programs
 * 0x12305670 ("application valid") over it. Flash bits only go from 1 to 0,
 * and 0x12345678 & 0x12305670 == 0x12305670, so that always works, and an
 * interrupted update comes back to the bootloader by itself.
 *
 * Razer's own firmware asked for the bootloader with a RAM word instead
 * (0xAAAAAAAA at 0x10000FF8 + software reset). Nothing clears that word, so
 * after an update the bootloader restarts into itself until the keypad is
 * unplugged; it is only the fallback here.
 */
#define RAZER_MARKER_ADDR 0x5FFCU
#define RAZER_MARKER_PAGE 0x5F00U
#define RAZER_MARKER_SECTOR 5U
#define RAZER_MARKER_UPDATE_PENDING 0x12345678U
#define RAZER_REQUEST_ADDR 0x10000FF8U
#define RAZER_REQUEST_MAGIC 0xAAAAAAAAU

static bool iap(uint32_t c0, uint32_t c1, uint32_t c2, uint32_t c3, uint32_t c4) {
    uint32_t cmd[5] = {c0, c1, c2, c3, c4};
    uint32_t res[5] = {0};
    lpc_iap_call(cmd, res);
    return res[0] == LPC_IAP_STATUS_CMD_SUCCESS;
}

static bool razer_mark_update_pending(void) {
    /* IAP copies from RAM. With interrupts off, the exception stack (MSP) is
     * idle, since QMK runs on the process stack, so it is free as the
     * 256-byte page buffer. */
    extern uint32_t __main_stack_base__[], __main_stack_end__[];
    uint32_t *page = __main_stack_base__;
    if ((uintptr_t)__main_stack_end__ - (uintptr_t)page < 256U) {
        return false;
    }
    if (*(volatile uint32_t *)RAZER_MARKER_ADDR == RAZER_MARKER_UPDATE_PENDING) {
        return true;
    }
    for (uint32_t i = 0; i < 63U; i++) {
        page[i] = 0xFFFFFFFFU;
    }
    page[63] = RAZER_MARKER_UPDATE_PENDING;
    const uint32_t khz = LPC_SYS_FREQUENCY / 1000U;
    return iap(LPC_IAP_CMD_PREPARE_SECTORS, RAZER_MARKER_SECTOR, RAZER_MARKER_SECTOR, 0, 0) &&
           iap(LPC_IAP_CMD_ERASE_SECTORS, RAZER_MARKER_SECTOR, RAZER_MARKER_SECTOR, khz, 0) &&
           iap(LPC_IAP_CMD_PREPARE_SECTORS, RAZER_MARKER_SECTOR, RAZER_MARKER_SECTOR, 0, 0) &&
           iap(LPC_IAP_CMD_COPY_RAM_TO_FLASH, RAZER_MARKER_PAGE, (uint32_t)page, 256U, khz) &&
           *(volatile uint32_t *)RAZER_MARKER_ADDR == RAZER_MARKER_UPDATE_PENDING;
}

void bootloader_jump(void) {
    __disable_irq();
    if (!razer_mark_update_pending()) {
        *(volatile uint32_t *)RAZER_REQUEST_ADDR = RAZER_REQUEST_MAGIC;
    }
    NVIC_SystemReset();
}

void mcu_reset(void) {
    NVIC_SystemReset();
}
