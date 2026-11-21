# Razer Orbweaver (original, 2013)

QMK for the original Razer Orbweaver / Orbweaver Stealth gaming keypad
(model RZ07-0074, USB `1532:0113`). This is **not** the Orbweaver Chroma
(`1532:0207`); for that one see `handwired/orbweaver` and
`lostdotfish/rp2040_orbweaver`, which this port follows.

* Keyboard Maintainer: [qmk](https://github.com/qmk)
* Hardware Supported: Razer Orbweaver (RZ07-0074) with either its stock controller board ("CHERYL", NXP LPC11U13, experimental) or an RP2040 controller swap
* Hardware Availability: discontinued; second-hand only

Make example for this keyboard (after setting up your build environment):

    make razer/orbweaver/rp2040:default
    make razer/orbweaver/stock:pinfinder
    make razer/orbweaver/stock:default

See the [build environment setup](https://docs.qmk.fm/#/getting_started_build_tools) and the [make instructions](https://docs.qmk.fm/#/getting_started_make_guide) for more information. Brand new to QMK? Start with our [Complete Newbs Guide](https://docs.qmk.fm/#/newbs).

## Layout

Stock factory keymap (from Razer Synapse 2's default profile for PID 0x0113):

| | | | | |
|---|---|---|---|---|
| 01 `` ` `` | 02 `1` | 03 `2` | 04 `3` | 05 `4` |
| 06 `Tab` | 07 `Q` | 08 `W` | 09 `E` | 10 `R` |
| 11 `Caps` | 12 `A` | 13 `S` | 14 `D` | 15 `F` |
| 16 `LShift` | 17 `Z` | 18 `X` | 19 `C` | 20 `V` |

Thumb module: upper key `LAlt`, lower key `Space`, 4-switch D-pad (8-way:
diagonals press two switches). 26 switches in total, laid out on the same 6x5
matrix positions as the Chroma ports.

The `default` keymap keeps that layout on layer 0 and makes key 01
`LT(_FN, KC_GRV)`: tap for `` ` ``, hold for FN. The FN layer selects layers, controls the backlight and has
`QK_BOOT`. Holding key 01 while plugging in also enters the bootloader.

Lighting matches the stock hardware as OpenRazer drives it: one single-colour
key backlight (static / breathing, brightness) and three keymap indicator LEDs
(red, green, blue). The indicators show the active layer + 1 in binary
(blue = bit 0, green = bit 1, red = bit 2).

## Revisions

### `rp2040` (default): controller swap

Same approach as the Chroma ports: the stock controller board is replaced by an
RP2040 board (e.g. Elite-Pi) wired to the switch-board matrix. This route is
fully reversible because the stock board is left untouched.

| Function | RP2040 pins |
|---|---|
| Matrix rows 0-5 | GP4, GP5, GP6, GP7, GP8, GP9 |
| Matrix cols 0-4 | GP12, GP13, GP14, GP15, GP16 |
| Backlight PWM (to LED driver / MOSFET gate) | GP26 |
| Keymap LEDs red / green / blue | GP27 / GP28 / GP29 |

Diodes are assumed `ROW2COL`, as on the Chroma. Bootloader: hold key 01 while
plugging in, or double-tap reset.

### `stock`: the Orbweaver's own controller

QMK running on the keypad's original controller board, behind Razer's own USB
bootloader, using the LPC11Uxx support added to `platforms/chibios` in this
fork (ChibiOS-Contrib HAL, transient EEPROM because the LPC11U1x has none).

Tested on hardware (2026-11-20/21): it enumerates as `FEED:0113` "Orbweaver
(QMK)", all 26 keys work (20 main keys and the thumb module), the backlight
and the keymap LEDs work, and updates go over USB (FN + key 05, then
`util/razer_orbweaver_usb_flash.py`; the keypad restarts into the new QMK by
itself). Settings changed at runtime are lost at power-off.

* **Keymap LEDs:** the row of three LEDs on the thumb module shows the highest
  active layer + 1 in binary: farthest (blue) = 1, middle (red) = 2, closest
  (green) = 4. So layer 0 lights the farthest LED, layer 1 the middle one,
  layer 2 both, layer 3 the closest, and so on up to layer 6 (all three).
* **Thumb D-pad:** in the layout, matrix `[1,4]` is the top key, `[2,4]` the
  bottom, `[3,4]` the left and `[4,4]` the right one, as seen from above.
  Razer's own default keymap (and this port's default) sends Up from the right
  key, Right from the bottom one, and so on: arrows turned a quarter turn,
  presumably for the angle of the thumb.
* **Backlight:** 8 levels through QMK's software PWM driver (the LPC11U port
  has no hardware PWM driver). QMK has no breathing for software PWM, so the
  stock revision adds its own: `BL_BRTG` steps the brightness up and down
  through all levels, about one breath every 3 seconds.

Flash layout (24 KiB):

| Range | Contents |
|---|---|
| `0x0000-0x0FFF` | Razer's bootloader (USB `1532:110D`), from the stock flash, with the factory serial number. Patched so that key 01 held while plugging in enters it |
| `0x1000-0x4FFF` | QMK, linked at 0x1000. The bootloader can only erase and write this range, so QMK must fit in 16 KiB (the default keymap: 15.6 KiB) |
| `0x5000-0x5FFF` | Razer's settings (unused by QMK) and, at `0x5FFC`, the bootloader's marker: `0x12345678` = update in progress (stay in the bootloader), `0x12305670` = done |

The controller board, as photographed:

| Item | Detail |
|---|---|
| Board | silkscreen `CHERYL`, `651000024700 V0.4` |
| MCU | NXP **LPC11U13FBD48/201**: 24 KiB flash, 4 KiB SRAM + 2 KiB USB SRAM, no EEPROM, LQFP48 |
| Clock | 12.000 MHz crystal (X1), as `mcuconf.h` assumes |
| ISP pads | `RST` (/RESET, pin 3), `ISP` (PIO0_1, pin 4), `RXD` (PIO0_18, pin 46), `TXD` (PIO0_19, pin 47), `GND`, `VCC3_3` |
| `ISP1` | two-pad footprint next to the crystal, presumably a jumper from PIO0_1 to GND |
| `CON1` / `CON2` | 2x5 and 2x4 through-hole footprints next to the ISP pads, unlabelled. CON1 has the shape of a 10-pin Cortex SWD header; check with a meter before relying on it |
| `CN1` | 4-pin USB cable connector |
| `J_KEYB` | FFC to the 20-key switch board, with series parts L3..L12 on its lines |

The pin map comes from Razer's own firmware, read out of a v1.01 flash
backup (key table at `0x3BFA`, pin table at `0x3C1E`), so `pinfinder` is only
needed for a board revision that differs:

| | Pins |
|---|---|
| Matrix rows (driven low) | PIO0_12, PIO0_13, PIO0_14, PIO0_16, PIO0_11 (`A12 A13 A14 A16 A11`) |
| Matrix cols (pull-up) | PIO1_16, PIO0_2, PIO0_20, PIO0_17, PIO0_7, PIO1_28 (`B16 A2 A20 A17 A7 B28`) |
| Backlight | PIO0_22 (`A22`), active low; stock drives it with CT16B1 PWM |
| Keymap LEDs red / green / blue | PIO1_14 / PIO1_15 / PIO1_13 (`B14 B15 B13`), active low |

The thumb module sits on the same matrix (Alt and Space on the first row, the
D-pad on the fifth column). Razer's LED ids match OpenRazer's: backlight
`0x05`, red `0x0C`, green `0x0D`, blue `0x0E`.

#### Editing the keymap

    python3 util/razer_orbweaver_editor.py      # Linux / macOS
    py util\razer_orbweaver_editor.py           # Windows

(run from the top of this repository) opens a page in the browser that shows the keypad. Click a key, pick its
keycode (letters, symbols, modifiers, F-keys, media, backlight, layer keys,
tap/hold keys, or any QMK keycode typed in), then **Build & flash**. It saves
`keyboards/razer/orbweaver/stock/keymaps/mine/keymap.json` (the keymap.json
format QMK Configurator uses; `--keymap NAME` picks another folder), builds
it, waits for the keypad's bootloader and writes it over USB; the page says
which keys reach the bootloader in the current keymap. The page only answers
on 127.0.0.1 and every change needs a per-launch token, so other websites
cannot start a build or a flash.

It needs Python 3.8+ and one way to build: the QMK CLI with its toolchain
(`qmk setup`), or Docker (it runs `ghcr.io/qmk/qmk_cli`; on Windows it keeps
the source in a Docker volume, `qmk_orbweaver`, because bind mounts are slow
there). The same editor runs on Windows, Linux and macOS.

On Windows it can also be installed as an app (Start Menu > Orbweaver Keymap):

    powershell -ExecutionPolicy Bypass -File util\windows\install.ps1 [-Desktop]

That compiles `util\windows\OrbweaverKeymap.cs` with the C# compiler that
comes with Windows (nothing is downloaded) and installs it for the current
user in `%LOCALAPPDATA%\Programs\Orbweaver Keymap`. It runs the editor in the
background with a tray icon (Open keymap editor, Show log, Quit) and opens it
in the browser; quitting, or the app ending any other way, also stops any
build or flash it started. It still needs Python 3 and this repository, which
`OrbweaverKeymap.ini` in that folder points to. `uninstall.ps1` in the same
folder removes it.

On Linux, flashing also needs pyusb and permission to open the bootloader:

    pip install --user pyusb        # uses the system libusb-1.0
    sudo cp util/udev/50-razer-orbweaver.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules && sudo udevadm trigger

Wear: NXP rates this flash for at least 10,000 erase cycles (typically
100,000; LPC11U1x data sheet, Table 10). An update erases each sector once
and typing never writes to flash, so that is 10,000 updates.

#### Updating over USB (after the one-time setup below)

1. Put the keypad in its bootloader: FN + key 05 (`QK_BOOT`) in QMK, or hold
   key 01 (top left) while plugging it in. It shows up as "Razer Bootloader".
   Windows binds it to WinUSB through Razer's `rzrbtldr.inf`, which Synapse
   installs; without Synapse, give `1532:110D` the WinUSB driver (Zadig).
2. Flash:

       python util/razer_orbweaver_usb_flash.py razer_orbweaver_stock_default.bin

   It erases 0x1000-0x4FFF, writes 64 bytes at a time, checks every page,
   verifies everything, then tells the bootloader to mark the firmware valid
   and restart. `--exit` leaves the bootloader without flashing.

The bootloader key in QMK erases sector 5 and writes the "update in progress"
marker, so an interrupted update comes back to the bootloader by itself. If a
build does not start at all, hold key 01 while plugging in.

#### One-time setup over the UART ISP pads

The LPC11U13 boot ROM only does UART ISP (no USB), so the first install needs
a 3.3 V USB-serial adapter (CP2102, CH340, FT232 set to 3.3 V).

1. Wire adapter GND to `GND`, adapter TX to `RXD`, adapter RX to `TXD`.
2. Enter ISP: power the board from 3.3 V on `VCC3_3` with USB unplugged, hold
   `ISP` to `GND` (or bridge `ISP1`), tap `RST` to `GND`, then release `ISP`.
   Power-cycling instead of `RST` is unreliable: the adapter's TX line keeps
   the chip half-powered. A chip with no valid firmware (erased, or a flash
   that stopped part-way) enters ISP on any reset, with no `ISP` link needed.
3. **Back up first** (read-only; `pip install pyserial`). Razer never
   published firmware for this model, so this is the only copy, and the
   bootloader for the next step comes from it:

       python util/lpc_isp_backup.py COM5 --out orbweaver_stock_flash.bin

   If it reports code read protection, there is no backup to be had.
4. Build the full image (Razer bootloader, patched for key 01, plus QMK) and
   write it:

       python util/razer_orbweaver_image.py orbweaver_stock_flash.bin razer_orbweaver_stock_default.bin -o orbweaver_qmk_full.bin
       python util/lpc_isp_flash.py COM5 orbweaver_qmk_full.bin --wait 300

   The writer refuses images that would lock the chip, writes a test pattern
   to RAM before erasing anything, writes and reads back each 1 KiB (the
   vector table last), then compares the whole flash. It defaults to 19200
   baud and waits 10 ms before each send; without that gap the ROM lost bytes
   sent right after its replies. On the board this was written on, the ROM
   still ignored about one command in ten, and twice jammed on a block of
   repeated bytes until `RST` was tapped. `--resume` continues an interrupted
   run, and `--sectors 0` writes only the bootloader sector; the rest of QMK
   can then go in over USB (hold key 01 while plugging in).

To restore the stock firmware, write the backup the same way. It is a full
24 KiB image with Razer's bootloader and settings:

    python util/lpc_isp_flash.py COM5 orbweaver_stock_flash.bin --wait 300

`util/lpc11u_image_check.py` checks any image on its own: the boot ROM vector
checksum, and that the word at 0x2FC would not turn on CRP and lock the chip.

Only if keys come out wrong on a different board revision: flash
`razer/orbweaver/stock:pinfinder` over USB, open a text editor, wait for
`pinfinder ready`, press every key once (each prints e.g. `A12>B16`, meaning
row `A12`, col `B16`, `COL2ROW`), and fix `stock/keyboard.json`. A4/A5
(PIO0_4/5) are true open-drain I2C pins with no internal pull-up, so they read
as floating unless the board pulls them up.

## What the stock firmware exposes (for reference)

Probed read-only over the Razer control interface (USB interface 2, 90-byte
feature report, transaction id 0xFF):

* firmware version command `00:81` returns `1.01`; device mode `00:84` = normal
* bootloader entry used by Synapse (`RazerProtocolDLL.dll!EnterBootloader`):
  command `00:04` (set device mode) with mode `0x01`. The device then
  re-enumerates as **Razer Bootloader** `1532:110D` (WinUSB, interface GUID
  `{C9348766-D27C-41EE-B2BE-EA9412F72B52}`), reporting the target product id in
  `bcdDevice`.
* the bootloader's update protocol, read out of its code: vendor control
  requests on endpoint 0 (`0x82` erase sector, `0x81` write up to 64 bytes
  into a 256-byte page buffer, `0x87` compare, `0x8F` status, `0x83` checksum,
  `0x84` mark valid and reset), limited to 0x1000-0x4FFF. Details in the
  docstring of `util/razer_orbweaver_usb_flash.py`. It stays in update mode
  when a key combo is held at reset (stock: thumb Space + Alt), when the
  marker at 0x5FFC is `0x12345678`, or after a software reset with
  `0xAAAAAAAA` at 0x10000FF8 (the request Razer's firmware used; nothing ever
  clears it, so the bootloader then restarts into itself until power is cut).
