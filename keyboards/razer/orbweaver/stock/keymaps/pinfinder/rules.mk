# Replace the matrix scanner with a GPIO pair prober (see keymap.c).
CUSTOM_MATRIX = lite
SEND_STRING_ENABLE = yes
BOOTMAGIC_ENABLE = no
EXTRAKEY_ENABLE = no

# The LPC11U13 has 4 KiB of RAM; this keymap's loop is shallow.
USE_PROCESS_STACKSIZE = 0x400
USE_EXCEPTIONS_STACKSIZE = 0x100
