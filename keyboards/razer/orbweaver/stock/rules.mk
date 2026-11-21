# QMK lives at 0x1000-0x4FFF behind Razer's bootloader: 16 KiB of flash.
MCU_LDSCRIPT = LPC11U13_razer_bootloader

# Features the default keymaps do not use, off to stay inside 16 KiB.
MAGIC_ENABLE = no
SPACE_CADET_ENABLE = no
GRAVE_ESC_ENABLE = no
