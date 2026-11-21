// Copyright 2026 QMK
// SPDX-License-Identifier: GPL-2.0-or-later

#include "quantum.h"

/*
 * Keymap indicator LEDs.
 *
 * The original Orbweaver has three single-colour "keymap" LEDs on the thumb
 * module (OpenRazer drives them as profile_led_red/green/blue, LED ids
 * 0x0C/0x0D/0x0E). Stock firmware uses them to show which of the 8 Synapse
 * keymaps is active; here they show the highest active layer as (layer + 1)
 * in binary, read along the row as it sits on the keypad (checked on a real
 * unit): farthest (blue) = bit 0, middle (red) = bit 1, closest (green) = bit 2.
 *   layer 0 -> farthest, layer 1 -> middle, layer 2 -> farthest + middle,
 *   layer 3 -> closest, ... layer 6 -> all three
 *
 * A revision enables this by defining ORBWEAVER_LED_{RED,GREEN,BLUE}_PIN in
 * its config.h. ORBWEAVER_LED_ON_STATE is 1 for active-high LEDs (default).
 */

#if defined(ORBWEAVER_LED_RED_PIN) && defined(ORBWEAVER_LED_GREEN_PIN) && defined(ORBWEAVER_LED_BLUE_PIN)
#    define ORBWEAVER_HAS_PROFILE_LEDS
#    ifndef ORBWEAVER_LED_ON_STATE
#        define ORBWEAVER_LED_ON_STATE 1
#    endif

static const pin_t profile_led_pins[3] = {ORBWEAVER_LED_BLUE_PIN, ORBWEAVER_LED_RED_PIN, ORBWEAVER_LED_GREEN_PIN};

static void profile_leds_write(uint8_t value) {
    for (uint8_t i = 0; i < 3; i++) {
        bool on = (value >> i) & 1;
        gpio_write_pin(profile_led_pins[i], on == (ORBWEAVER_LED_ON_STATE != 0));
    }
}

void keyboard_pre_init_kb(void) {
    for (uint8_t i = 0; i < 3; i++) {
        gpio_set_pin_output(profile_led_pins[i]);
    }
    profile_leds_write(0);
    keyboard_pre_init_user();
}

void keyboard_post_init_kb(void) {
    profile_leds_write(get_highest_layer(layer_state | default_layer_state) + 1);
    keyboard_post_init_user();
}

layer_state_t layer_state_set_kb(layer_state_t state) {
    state = layer_state_set_user(state);
    profile_leds_write(get_highest_layer(state | default_layer_state) + 1);
    return state;
}

void suspend_power_down_kb(void) {
    profile_leds_write(0);
    suspend_power_down_user();
}

void suspend_wakeup_init_kb(void) {
    profile_leds_write(get_highest_layer(layer_state | default_layer_state) + 1);
    suspend_wakeup_init_user();
}
#endif
