/*
 * LPC11U13/201 memory setup for QMK started by the Razer Orbweaver bootloader,
 * which stays at 0x0000-0x0FFF (copied from the stock firmware).
 *
 *   flash  : 0x00001000, 16 KiB. The bootloader only erases and writes
 *            0x1000-0x4FFF; 0x5000-0x5FFF holds Razer's settings and, at
 *            0x5FFC, the "application valid" marker (0x12305670).
 *   SRAM0  : 0x100000C8 .. top - 32.
 *            - 0x10000000-0x100000C7: the bootloader copies the first 0xC4
 *              bytes of the application (its vector table) here, and the
 *              board code maps interrupts to it (SYSMEMREMAP = user RAM),
 *              because the Cortex-M0 has no VTOR.
 *            - top 32 bytes: IAP scratch, and the bootloader request word at
 *              0x10000FF8 (0xAAAAAAAA + software reset = stay in bootloader).
 *   USB RAM: 0x20004000, 2 KiB, managed directly by the ChibiOS USB LLD.
 */
MEMORY {
    flash0  : org = 0x00001000, len = 16k
    flash1  : org = 0x00000000, len = 0
    flash2  : org = 0x00000000, len = 0
    flash3  : org = 0x00000000, len = 0
    flash4  : org = 0x00000000, len = 0
    flash5  : org = 0x00000000, len = 0
    flash6  : org = 0x00000000, len = 0
    flash7  : org = 0x00000000, len = 0
    ram0    : org = 0x100000C8, len = 4k - 0xC8 - 32
    ram1    : org = 0x00000000, len = 0
    ram2    : org = 0x00000000, len = 0
    ram3    : org = 0x00000000, len = 0
    ram4    : org = 0x00000000, len = 0
    ram5    : org = 0x00000000, len = 0
    ram6    : org = 0x00000000, len = 0
    ram7    : org = 0x00000000, len = 0
}

REGION_ALIAS("VECTORS_FLASH", flash0);
REGION_ALIAS("VECTORS_FLASH_LMA", flash0);
REGION_ALIAS("XTORS_FLASH", flash0);
REGION_ALIAS("XTORS_FLASH_LMA", flash0);
REGION_ALIAS("TEXT_FLASH", flash0);
REGION_ALIAS("TEXT_FLASH_LMA", flash0);
REGION_ALIAS("RODATA_FLASH", flash0);
REGION_ALIAS("RODATA_FLASH_LMA", flash0);
REGION_ALIAS("VARIOUS_FLASH", flash0);
REGION_ALIAS("VARIOUS_FLASH_LMA", flash0);
REGION_ALIAS("RAM_INIT_FLASH_LMA", flash0);
REGION_ALIAS("MAIN_STACK_RAM", ram0);
REGION_ALIAS("PROCESS_STACK_RAM", ram0);
REGION_ALIAS("DATA_RAM", ram0);
REGION_ALIAS("DATA_RAM_LMA", flash0);
REGION_ALIAS("BSS_RAM", ram0);
REGION_ALIAS("HEAP_RAM", ram0);

/* Vector 7 is unused on Cortex-M0; keep the NXP checksum expression so the
 * table is identical to a standalone build. */
Vector1C = (0 -
        ((__main_stack_end__) +
        (Reset_Handler + 1) +
        (NMI_Handler + 1) +
        (HardFault_Handler + 1) +
        (MemManage_Handler + 1) +
        (BusFault_Handler + 1) +
        (UsageFault_Handler + 1))
    );

INCLUDE rules.ld
