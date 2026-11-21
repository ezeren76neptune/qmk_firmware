#!/usr/bin/env python3
"""Flash QMK onto a Razer Orbweaver over USB, through Razer's own bootloader.

Needs the one-time setup from util/razer_orbweaver_image.py (Razer bootloader
at 0x0000, QMK at 0x1000). Then, to update:

  1. put the keypad in its bootloader: FN + key 05 (QK_BOOT) in QMK, or hold
     key 01 while plugging it in. It shows up as "Razer Bootloader" 1532:110D.
  2. python util/razer_orbweaver_usb_flash.py razer_orbweaver_stock_default.bin

The bootloader protocol (read out of the bootloader code, Synapse never used
publicly): vendor control requests on endpoint 0, request type ignored.
  0x82 OUT, no data   erase the 4 KiB sector holding address wValue
  0x81 OUT, <=64 B    store data at wValue in a 256-byte page buffer; the
                      buffered page is programmed when a request names an
                      address in another page (an out-of-range one included)
  0x87 OUT, data      compare the data with flash at wValue -> status
  0x8F IN, 1 byte     status: 1 = ok, 0xFF = failed or busy
  0x84 OUT, no data   write the "application valid" marker and reset
Only 0x1000-0x4FFF can be erased or written, so the bootloader itself and
Razer's sector 5 are out of reach of this tool.

On Windows it uses the WinUSB driver Razer's rzrbtldr.inf installs (part of
Synapse; already present if Synapse was ever installed). Elsewhere it uses
pyusb (pip install pyusb).

usage: razer_orbweaver_usb_flash.py QMK.bin [--wait SECONDS] [--no-reset]
       razer_orbweaver_usb_flash.py --exit     leave the bootloader without flashing
"""

import argparse
import hashlib
import struct
import sys
import time

VID, PID = 0x1532, 0x110D
DEVICE_INTERFACE_GUID = "{C9348766-D27C-41EE-B2BE-EA9412F72B52}"  # from rzrbtldr.inf
APP_BASE, APP_END = 0x1000, 0x5000
SECTOR, PAGE, CHUNK = 0x1000, 0x100, 64

REQ_WRITE, REQ_ERASE, REQ_FINISH, REQ_VERIFY, REQ_STATUS = 0x81, 0x82, 0x84, 0x87, 0x8F
OUT, IN = 0x40, 0xC0  # vendor request to the device


class FlashError(Exception):
    pass


# --------------------------------------------------------------------------- backends

class WinUsbDevice:
    """Minimal WinUSB access through ctypes (no extra packages)."""

    def __init__(self, path):
        import ctypes
        from ctypes import wintypes

        self.ct = ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.winusb = winusb = ctypes.WinDLL("winusb", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        winusb.WinUsb_Initialize.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        winusb.WinUsb_Initialize.restype = wintypes.BOOL
        winusb.WinUsb_Free.argtypes = [ctypes.c_void_p]
        winusb.WinUsb_SetPipePolicy.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p]
        winusb.WinUsb_SetPipePolicy.restype = wintypes.BOOL

        class SetupPacket(ctypes.Structure):
            _pack_ = 1
            _fields_ = [("RequestType", ctypes.c_ubyte), ("Request", ctypes.c_ubyte),
                        ("Value", ctypes.c_ushort), ("Index", ctypes.c_ushort), ("Length", ctypes.c_ushort)]

        self.SetupPacket = SetupPacket
        winusb.WinUsb_ControlTransfer.argtypes = [ctypes.c_void_p, SetupPacket, ctypes.c_void_p, wintypes.ULONG,
                                                  ctypes.POINTER(wintypes.ULONG), ctypes.c_void_p]
        winusb.WinUsb_ControlTransfer.restype = wintypes.BOOL

        self.k32 = k32
        self.file = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0x80 | 0x40000000, None)
        if self.file in (None, wintypes.HANDLE(-1).value):
            raise OSError(ctypes.get_last_error(), f"cannot open {path}")
        self.h = ctypes.c_void_p()
        if not winusb.WinUsb_Initialize(self.file, ctypes.byref(self.h)):
            err = ctypes.get_last_error()
            k32.CloseHandle(self.file)
            raise OSError(err, "WinUsb_Initialize failed")
        timeout = wintypes.ULONG(5000)
        winusb.WinUsb_SetPipePolicy(self.h, 0, 0x03, 4, ctypes.byref(timeout))  # PIPE_TRANSFER_TIMEOUT

    @staticmethod
    def find():
        """Device paths of present devices with Razer's bootloader interface GUID."""
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        class InterfaceData(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wintypes.DWORD),
                        ("Reserved", ctypes.c_void_p)]

        u = uuid.UUID(DEVICE_INTERFACE_GUID)
        guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        sa = ctypes.WinDLL("setupapi", use_last_error=True)
        sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        sa.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
        sa.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                   wintypes.DWORD, ctypes.POINTER(InterfaceData)]
        sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(InterfaceData), ctypes.c_void_p,
                                                        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        hdev = sa.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x02 | 0x10)  # DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        if hdev in (None, ctypes.c_void_p(-1).value):
            return []
        paths = []
        try:
            i = 0
            while True:
                ifd = InterfaceData()
                ifd.cbSize = ctypes.sizeof(InterfaceData)
                if not sa.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), i, ctypes.byref(ifd)):
                    break
                need = wintypes.DWORD()
                sa.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
                buf = ctypes.create_string_buffer(need.value)
                struct.pack_into("<I", buf, 0, 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)
                if sa.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifd), buf, need, None, None):
                    paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
                i += 1
        finally:
            sa.SetupDiDestroyDeviceInfoList(hdev)
        return paths

    def _xfer(self, rtype, req, value, data, length):
        ct = self.ct
        pkt = self.SetupPacket(rtype, req, value, 0, length)
        buf = ct.create_string_buffer(bytes(data), max(length, 1)) if rtype == OUT else ct.create_string_buffer(max(length, 1))
        done = ct.c_ulong()
        if not self.winusb.WinUsb_ControlTransfer(self.h, pkt, buf, length, ct.byref(done), None):
            raise FlashError(f"control request 0x{req:02X} failed (Windows error {ct.get_last_error()})")
        return buf.raw[:done.value]

    def ctrl_out(self, req, value, data=b""):
        self._xfer(OUT, req, value, data, len(data))

    def ctrl_in(self, req, value, length):
        return self._xfer(IN, req, value, b"", length)

    def close(self):
        self.winusb.WinUsb_Free(self.h)
        self.k32.CloseHandle(self.file)


class PyUsbDevice:
    """libusb through pyusb, for Linux and macOS. Control transfers on endpoint 0
    need no interface claim; on Linux the user needs access to the device node
    (util/udev/50-razer-orbweaver.rules)."""

    def __init__(self, dev):
        self.dev = dev
        try:
            dev.set_configuration()
        except Exception:
            pass  # already configured, or busy: endpoint 0 works either way

    @staticmethod
    def find():
        try:
            import usb.core
        except ImportError:
            raise FlashError("pyusb is missing: pip install pyusb (it uses the system libusb-1.0)")
        try:
            return list(usb.core.find(find_all=True, idVendor=VID, idProduct=PID))
        except usb.core.NoBackendError:
            raise FlashError("pyusb found no libusb backend: install libusb-1.0 (e.g. apt install libusb-1.0-0)")

    def _xfer(self, *args):
        import usb.core
        try:
            return self.dev.ctrl_transfer(*args, timeout=5000)
        except usb.core.USBError as e:
            if getattr(e, "errno", None) == 13:
                raise FlashError("permission denied on the USB device: install util/udev/50-razer-orbweaver.rules "
                                 "(see its header), or run as root")
            raise FlashError(f"control request 0x{args[1]:02X} failed ({e})")

    def ctrl_out(self, req, value, data=b""):
        self._xfer(OUT, req, value, 0, bytes(data))

    def ctrl_in(self, req, value, length):
        return bytes(self._xfer(IN, req, value, 0, length))

    def close(self):
        try:
            import usb.util
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass


def bootloader_present():
    if sys.platform == "win32":
        return bool(WinUsbDevice.find())
    return bool(PyUsbDevice.find())


def open_bootloader(wait_s):
    deadline = time.time() + wait_s
    told = False
    while True:
        if sys.platform == "win32":
            paths = WinUsbDevice.find()
            if paths:
                return WinUsbDevice(paths[0])
        else:
            devs = PyUsbDevice.find()
            if devs:
                return PyUsbDevice(devs[0])
        if time.time() >= deadline:
            hint = ("On Windows it needs Razer's rzrbtldr driver (installed with Synapse) or WinUSB via Zadig."
                    if sys.platform == "win32" else
                    "Check that `lsusb` lists 1532:110d; for access without root install util/udev/50-razer-orbweaver.rules.")
            raise FlashError("Razer bootloader (1532:110D) not found. Press FN + key 05, or hold key 01 while "
                             "plugging the keypad in. " + hint)
        if not told:
            print(f"waiting up to {wait_s} s for the Razer bootloader (FN + key 05, or hold key 01 while plugging in) ...",
                  flush=True)
            told = True
        time.sleep(0.5)


# --------------------------------------------------------------------------- protocol

def check_app(app):
    if not 0x100 <= len(app) <= APP_END - APP_BASE:
        raise FlashError(f"{len(app)} bytes does not fit in 0x{APP_BASE:X}-0x{APP_END - 1:X}")
    sp, reset = struct.unpack_from("<II", app, 0)
    if not 0x10000000 < sp <= 0x10001000:
        raise FlashError(f"initial SP 0x{sp:08X} is not in SRAM: not a firmware image?")
    if not (reset & 1 and APP_BASE <= (reset & ~1) < APP_BASE + len(app)):
        raise FlashError(f"reset vector 0x{reset:08X} is not inside 0x1000+: build razer/orbweaver/stock, "
                         "which is linked at 0x1000 (a full 24 KiB image is for lpc_isp_flash.py)")


def status(dev):
    return dev.ctrl_in(REQ_STATUS, 0, 1)[0]


def flash(dev, app, log=print, reset=True):
    image = app + b"\xFF" * (-len(app) % CHUNK)
    end = APP_BASE + len(image)

    for sec in range(APP_BASE, APP_END, SECTOR):
        dev.ctrl_out(REQ_ERASE, sec)
        if status(dev) != 1:
            raise FlashError(f"erasing sector 0x{sec:04X} failed")
    log("erased 0x1000-0x4FFF")

    pages = [p for p in range(APP_BASE, end, PAGE) if image[p - APP_BASE:p - APP_BASE + PAGE].strip(b"\xFF")]
    for n, page in enumerate(pages, 1):
        for i, a in enumerate(range(page, min(page + PAGE, end), CHUNK)):
            dev.ctrl_out(REQ_WRITE, a, image[a - APP_BASE:a - APP_BASE + CHUNK])
            # This page's first request programmed the previous page. Every request
            # sets the status back to 1 when it starts, so check it right away.
            if i == 0 and n > 1 and status(dev) != 1:
                raise FlashError(f"programming page 0x{pages[n - 2]:04X} failed")
        log(f"\r  page {n}/{len(pages)}", end="")
    dev.ctrl_out(REQ_WRITE, APP_END, b"\xFF" * CHUNK)  # out of range: programs the last page, stores nothing
    if status(dev) != 1:
        raise FlashError(f"programming page 0x{pages[-1]:04X} failed")
    log("")

    for a in range(APP_BASE, end, CHUNK):
        dev.ctrl_out(REQ_VERIFY, a, image[a - APP_BASE:a - APP_BASE + CHUNK])
        if status(dev) != 1:
            raise FlashError(f"verify failed at 0x{a:04X}")
    log(f"verified {len(app)} bytes")

    if reset:
        try:
            dev.ctrl_out(REQ_FINISH, 0)  # the keypad resets mid-request, so an error here is normal
        except FlashError:
            pass
        log("marker written, keypad restarting into QMK")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image", nargs="?", help="razer_orbweaver_stock_*.bin (linked at 0x1000)")
    ap.add_argument("--exit", action="store_true", help="only mark the firmware already on the keypad as valid and restart it")
    ap.add_argument("--wait", type=int, default=60, help="seconds to wait for the bootloader to appear")
    ap.add_argument("--no-reset", action="store_true", help="stay in the bootloader after verifying")
    args = ap.parse_args(argv)

    if args.exit:
        try:
            dev = open_bootloader(args.wait)
        except FlashError as e:
            print(f"error: {e}")
            return 1
        try:
            dev.ctrl_out(REQ_FINISH, 0)  # the keypad resets mid-request
        except FlashError:
            pass
        dev.close()
        print("marked the firmware valid; the keypad is restarting")
        return 0
    if not args.image:
        ap.error("give the firmware image, or --exit")

    app = open(args.image, "rb").read()
    try:
        check_app(app)
        print(f"{args.image}: {len(app)} bytes, sha256 {hashlib.sha256(app).hexdigest()}")
        dev = open_bootloader(args.wait)
        try:
            print("Razer bootloader found")
            flash(dev, app, log=lambda *a, **k: print(*a, **k, flush=True), reset=not args.no_reset)
        finally:
            dev.close()
    except FlashError as e:
        print(f"error: {e}")
        return 1
    if not args.no_reset:
        # QMK's bootloader key uses the flash marker, which the update clears.
        # A keypad sent here with Razer's RAM request word (0xAAAAAAAA at
        # 0x10000FF8, e.g. by an older build) comes back to the bootloader
        # until it loses power.
        time.sleep(3)
        try:
            back = bootloader_present()
        except FlashError:
            back = False
        if back:
            print("note: the keypad came back as the bootloader; unplug it and plug it back in to start QMK")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
