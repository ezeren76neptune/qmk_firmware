/*
 * LPC11U14/201 memory setup (based on ChibiOS-Contrib LPC11U35_401.ld).
 *
 *   flash  : 0x00000000, 32 KiB
 *   SRAM0  : 0x10000000, 4 KiB
 *            - all of it is usable: the low SRAM the boot ROM ISP uses
 *              (0x1000017C..0x1000025B) only matters while the ISP runs, and
 *              the application never returns from ReinvokeISP.
 *            - top 32 bytes left free: IAP calls use them as scratch.
 *   USB RAM: 0x20004000, 2 KiB, managed directly by the ChibiOS USB LLD.
 *   No EEPROM on LPC11U1x.
 */

MEMORY {
    flash0  : org = 0x00000000, len = 32k
    flash1  : org = 0x00000000, len = 0
    flash2  : org = 0x00000000, len = 0
    flash3  : org = 0x00000000, len = 0
    flash4  : org = 0x00000000, len = 0
    flash5  : org = 0x00000000, len = 0
    flash6  : org = 0x00000000, len = 0
    flash7  : org = 0x00000000, len = 0
    ram0    : org = 0x10000000, len = 4k - 32
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

/* NXP boot ROM only starts user code when the first 8 vector words sum to 0;
 * vector 7 (0x1C) carries the two's complement checksum. */
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
