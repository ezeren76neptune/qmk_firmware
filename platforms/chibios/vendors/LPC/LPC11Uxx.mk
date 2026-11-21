#
# NXP LPC11Uxx specific QMK glue.
##############################################################################

PLATFORM_LPC_PATH := $(PLATFORM_PATH)/$(PLATFORM_KEY)/vendors/$(MCU_FAMILY)

# Vendor pin definitions (A*/B* names and PAL_MODE_INPUT, which the LPC PAL
# driver leaves undefined).
EXTRAINCDIRS += $(PLATFORM_LPC_PATH)

# The ChibiOS-Contrib LPC port has no PWM or I2C driver yet.
ifeq ($(strip $(BACKLIGHT_ENABLE)), yes)
    BACKLIGHT_DRIVER ?= software
endif
