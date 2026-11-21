#!/usr/bin/env python3
"""Keymap editor for the Razer Orbweaver running QMK on its stock controller.

Opens a page in your browser that shows the keypad, lets you set every key on
every layer, and builds and flashes the result over USB with one click. The
keymap is a normal QMK keymap.json (the format QMK Configurator exports) at
keyboards/razer/orbweaver/stock/keymaps/<name>/keymap.json.

Runs on Windows, Linux and macOS with Python 3.8+; the editor itself needs
nothing else. Building needs one of:
  * the QMK CLI with its ARM toolchain (`qmk setup`), or
  * Docker (uses the ghcr.io/qmk/qmk_cli image)
Flashing goes through util/razer_orbweaver_usb_flash.py: on Windows it uses
Razer's WinUSB driver (installed with Synapse), on Linux pyusb plus
util/udev/50-razer-orbweaver.rules.

usage: python util/razer_orbweaver_editor.py [--keymap mine] [--port 8765]
                                             [--builder auto|qmk|docker] [--no-browser]
"""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEYBOARD = "razer/orbweaver/stock"
KB_DIR = REPO / "keyboards" / "razer" / "orbweaver" / "stock"
FLASHER = REPO / "util" / "razer_orbweaver_usb_flash.py"
IMAGE = "ghcr.io/qmk/qmk_cli"
VOLUME = "qmk_orbweaver"  # Windows: building in a Docker volume is far faster than a bind mount
MAX_LAYERS = 8  # LAYER_STATE_8BIT
KEYCODE_RE = re.compile(r"^[A-Za-z0-9_(), |]{1,64}$")

T = "KC_TRNS"
DEFAULT_LAYERS = [
    ["LT(3,KC_GRV)", "KC_1", "KC_2", "KC_3", "KC_4", "KC_TAB", "KC_Q", "KC_W", "KC_E", "KC_R",
     "KC_CAPS", "KC_A", "KC_S", "KC_D", "KC_F", "KC_LSFT", "KC_Z", "KC_X", "KC_C", "KC_V",
     "KC_LALT", "KC_UP", "KC_DOWN", "KC_RGHT", "KC_LEFT", "KC_SPC"],
    [T, "KC_1", "KC_2", "KC_3", "KC_4", "KC_5", "KC_Q", "KC_W", "KC_E", "KC_R",
     "KC_6", "KC_A", "KC_S", "KC_D", "KC_F", "KC_7", "KC_Z", "KC_X", "KC_C", "KC_V",
     "KC_8", T, T, T, T, T],
    [T] * 26,
    [T, "TO(0)", "TO(1)", "TO(2)", "QK_BOOT", "BL_TOGG", "BL_DOWN", "BL_UP", "BL_BRTG", "EE_CLR",
     T, "KC_MPRV", "KC_MPLY", "KC_MNXT", "KC_MUTE", T, "KC_VOLD", "KC_VOLU", T, T,
     T, T, T, T, T, T],
]


# --------------------------------------------------------------------------- keymap files

def load_layout():
    kb = json.loads((KB_DIR / "keyboard.json").read_text(encoding="utf-8"))
    keys = kb["layouts"]["LAYOUT"]["layout"]
    return [{"label": k.get("label", ""), "x": k["x"], "y": k["y"], "w": k.get("w", 1), "h": k.get("h", 1)} for k in keys]


def keymap_path(name):
    return KB_DIR / "keymaps" / name / "keymap.json"


def load_keymap(name, nkeys):
    p = keymap_path(name)
    if p.exists():
        km = json.loads(p.read_text(encoding="utf-8"))
        layers = km.get("layers", [])
    else:
        layers = [list(l) for l in DEFAULT_LAYERS]
    return {"layers": validate_layers(layers, nkeys), "exists": p.exists(), "path": str(p)}


def validate_layers(layers, nkeys):
    if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
        raise ValueError(f"need 1 to {MAX_LAYERS} layers")
    out = []
    for i, layer in enumerate(layers):
        if not isinstance(layer, list) or len(layer) != nkeys:
            raise ValueError(f"layer {i} must have {nkeys} keys")
        row = []
        for kc in layer:
            kc = str(kc).strip().replace(" ", "")
            if not KEYCODE_RE.match(kc) or kc.count("(") != kc.count(")"):
                raise ValueError(f"not a keycode: {kc!r}")
            row.append(kc)
        out.append(row)
    return out


def save_keymap(name, layers):
    p = keymap_path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    km = {
        "version": 1,
        "notes": "Edited with util/razer_orbweaver_editor.py",
        "keyboard": KEYBOARD,
        "keymap": name,
        "layout": "LAYOUT",
        "layers": layers,
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(km, indent=4) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


# --------------------------------------------------------------------------- build backends

def detect_builder(pref):
    """('qmk' | 'docker' | None, explanation)"""
    notes = []
    if pref in ("auto", "qmk"):
        if shutil.which("qmk") and shutil.which("arm-none-eabi-gcc"):
            return "qmk", "QMK CLI and ARM toolchain found"
        notes.append("no QMK CLI with arm-none-eabi-gcc on PATH")
    if pref in ("auto", "docker"):
        if shutil.which("docker"):
            try:
                r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=30)
                if r.returncode == 0:
                    return "docker", f"Docker {r.stdout.strip()}"
                notes.append("Docker is installed but not running (start Docker Desktop / the docker service)")
            except (OSError, subprocess.TimeoutExpired):
                notes.append("Docker did not answer")
        else:
            notes.append("no Docker")
    return None, "; ".join(notes) + ". Install the QMK CLI (qmk setup) or Docker to build."


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.lines = []
        self.state = "idle"  # idle | running | done | failed
        self.step = ""
        self.proc = None
        self.cancelled = False
        self.last_progress = False

    def log(self, line, progress=False):
        """progress=True: the line ended in a bare CR, so (as on a terminal)
        whatever comes next overwrites it instead of adding a new line."""
        with self.lock:
            if self.last_progress and self.lines:
                self.lines[-1] = line
            else:
                self.lines.append(line.rstrip("\r\n"))
            self.last_progress = progress

    def snapshot(self, since):
        with self.lock:
            return {"state": self.state, "step": self.step, "lines": self.lines[since:], "next": len(self.lines)}


def run_streamed(job, cmd, **kw):
    """Run cmd, copy its output into the job log (progress lines ending in a
    bare CR become separate lines). Returns the exit code."""
    job.log("$ " + " ".join(str(c) for c in cmd))
    kw.setdefault("cwd", str(REPO))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    job.proc = p
    buf = b""
    while True:
        chunk = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(1)
        if not chunk:
            break
        buf += chunk
        while True:
            cut = min([i for i in (buf.find(b"\n"), buf.find(b"\r")) if i >= 0], default=-1)
            if cut < 0 or (buf[cut:cut + 1] == b"\r" and cut + 1 == len(buf)):
                break  # a CR at the very end may still be followed by its LF
            progress = buf[cut:cut + 1] == b"\r" and buf[cut + 1:cut + 2] != b"\n"
            line, buf = buf[:cut], buf[cut + 1:]
            if not progress and buf[:1] == b"\n":
                buf = buf[1:]
            text = re.sub(r"\x1b\[[0-9;]*m", "", line.decode("utf-8", "replace")).strip()
            if text:
                job.log(text, progress)
    if buf.strip():
        job.log(buf.decode("utf-8", "replace"))
    p.wait()
    job.proc = None
    return p.returncode


def bin_name(keymap):
    return f"{KEYBOARD.replace('/', '_')}_{keymap}.bin"


def build_qmk(job, keymap):
    env = dict(os.environ, QMK_HOME=str(REPO))
    rc = run_streamed(job, ["qmk", "compile", "-kb", KEYBOARD, "-km", keymap], env=env)
    return rc == 0


def build_docker_bind(job, keymap):
    """Linux / macOS: bind-mount the repo; output lands in it directly."""
    user = [] if not hasattr(os, "getuid") else ["-u", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
    rc = run_streamed(job, ["docker", "run", "--rm", "-v", f"{REPO}:/qmk_firmware", "-w", "/qmk_firmware", *user,
                            IMAGE, "make", f"{KEYBOARD}:{keymap}", "SKIP_GIT=yes"])
    return rc == 0


def repo_files_for_sync():
    """Files in this fork that differ from what a plain QMK checkout has: the
    ones git sees as modified or untracked."""
    try:
        r = subprocess.run(["git", "-C", str(REPO), "ls-files", "-m", "-o", "--exclude-standard"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return [f for f in r.stdout.splitlines() if f and (REPO / f).is_file()]
    except OSError:
        pass
    roots = ["keyboards/razer", "platforms", "builddefs", "data", "lib/python/qmk", "util"]
    return [str(p.relative_to(REPO)).replace("\\", "/") for r in roots for p in (REPO / r).rglob("*") if p.is_file()]


def tar_into_volume(job, members, label):
    """Stream files from the repo into the Docker volume."""
    p = subprocess.Popen(["docker", "run", "--rm", "-i", "-v", f"{VOLUME}:/qmk_firmware", "-w", "/qmk_firmware",
                          IMAGE, "tar", "-xf", "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    n = 0
    with tarfile.open(fileobj=p.stdin, mode="w|") as tar:
        for rel in members:
            tar.add(str(REPO / rel), arcname=rel, recursive=False)
            n += 1
            if n % 2000 == 0:
                job.log(f"  {label}: {n} files ...")
    p.stdin.close()
    out = p.stdout.read().decode("utf-8", "replace").strip()
    p.wait()
    if out:
        job.log(out)
    return p.returncode == 0


def build_docker_volume(job, keymap):
    """Windows: keep a copy of the tree in a Docker volume and sync changes."""
    have = subprocess.run(["docker", "run", "--rm", "-v", f"{VOLUME}:/q", IMAGE, "test", "-f", "/q/Makefile"],
                          capture_output=True).returncode == 0
    if not have:
        job.log(f"first build: copying the QMK tree into Docker volume '{VOLUME}' (a few minutes, once) ...")
        files = []
        for root, dirs, names in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in (".git", ".build", "__pycache__")]
            for n in names:
                files.append(os.path.relpath(os.path.join(root, n), REPO).replace("\\", "/"))
        if not tar_into_volume(job, files, "copy"):
            return False
    changed = repo_files_for_sync()
    km_dir = f"keyboards/razer/orbweaver/stock/keymaps/{keymap}/keymap.json"
    if km_dir not in changed:
        changed.append(km_dir)
    job.log(f"syncing {len(changed)} changed files into the build volume")
    if not tar_into_volume(job, changed, "sync"):
        return False
    if run_streamed(job, ["docker", "run", "--rm", "-v", f"{VOLUME}:/qmk_firmware", "-w", "/qmk_firmware",
                          IMAGE, "make", f"{KEYBOARD}:{keymap}", "SKIP_GIT=yes"]) != 0:
        return False
    out = subprocess.run(["docker", "run", "--rm", "-v", f"{VOLUME}:/qmk_firmware", IMAGE, "cat",
                          f"/qmk_firmware/{bin_name(keymap)}"], capture_output=True)
    if out.returncode != 0 or not out.stdout:
        job.log("could not copy the firmware out of the build volume")
        return False
    (REPO / bin_name(keymap)).write_bytes(out.stdout)
    return True


def build(job, builder, keymap):
    if builder == "qmk":
        ok = build_qmk(job, keymap)
    elif sys.platform == "win32":
        ok = build_docker_volume(job, keymap)
    else:
        ok = build_docker_bind(job, keymap)
    out = REPO / bin_name(keymap)
    if ok and out.exists():
        job.log(f"firmware: {out} ({out.stat().st_size} bytes of 16384)")
        return out
    if any("overflowed" in l for l in job.lines[-40:]):
        job.log("The firmware no longer fits in the 16 KiB Razer's bootloader can write. "
                "Remove features from the keymap (or turn others off in keyboards/razer/orbweaver/stock/rules.mk).")
    return None


def run_job(job, keymap, builder_pref, flash):
    try:
        job.step = "checking the build tools"
        builder, note = detect_builder(builder_pref)
        job.log(f"build tools: {builder or 'none'} ({note})")
        if not builder:
            job.state = "failed"
            return
        job.step = "building"
        fw = build(job, builder, keymap)
        if not fw or job.cancelled:
            job.log("build cancelled" if job.cancelled else "build failed")
            job.state = "failed"
            return
        if not flash:
            job.state = "done"
            job.step = "built"
            return
        job.step = "waiting for the bootloader"
        rc = run_streamed(job, [sys.executable, "-u", str(FLASHER), str(fw), "--wait", "300"])
        job.state = "done" if rc == 0 and not job.cancelled else "failed"
        job.step = "flashed" if job.state == "done" else "flash failed"
    except Exception as e:  # report anything unexpected in the page instead of dying silently
        job.log(f"error: {e!r}")
        job.state = "failed"


# --------------------------------------------------------------------------- web server

class Editor:
    def __init__(self, keymap, builder_pref, port):
        self.keymap = keymap
        self.builder_pref = builder_pref
        self.port = port
        self.token = secrets.token_urlsafe(24)
        self.layout = load_layout()
        self.job = Job()


def make_handler(ed):
    allowed_hosts = {f"127.0.0.1:{ed.port}", f"localhost:{ed.port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            # DNS rebinding guard: only answer requests addressed to this machine
            return self.headers.get("Host", "") in allowed_hosts

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "bad host"})
            path = self.path.split("?")[0]
            if path == "/":
                page = PAGE.replace("__TOKEN__", ed.token).replace("__KEYMAP__", ed.keymap)
                return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/state":
                try:
                    km = load_keymap(ed.keymap, len(ed.layout))
                except (ValueError, OSError, json.JSONDecodeError) as e:
                    km = {"layers": [list(l) for l in DEFAULT_LAYERS], "exists": False, "error": str(e)}
                return self._send(200, {"layout": ed.layout, "keymap": ed.keymap, "km": km,
                                        "defaults": DEFAULT_LAYERS, "maxLayers": MAX_LAYERS, "platform": sys.platform})
            if path == "/api/job":
                since = 0
                if "since=" in self.path:
                    try:
                        since = int(self.path.split("since=")[1].split("&")[0])
                    except ValueError:
                        pass
                return self._send(200, ed.job.snapshot(since))
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or self.headers.get("X-Token") != ed.token:
                return self._send(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(400, {"error": "bad request"})
            path = self.path.split("?")[0]
            if path == "/api/save" or path == "/api/build":
                try:
                    layers = validate_layers(body.get("layers"), len(ed.layout))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                p = save_keymap(ed.keymap, layers)
                if path == "/api/save":
                    return self._send(200, {"saved": str(p)})
                if ed.job.state == "running":
                    return self._send(409, {"error": "a build is already running"})
                ed.job = Job()
                ed.job.state = "running"
                ed.job.log(f"saved {p}")
                threading.Thread(target=run_job, args=(ed.job, ed.keymap, ed.builder_pref, bool(body.get("flash", True))),
                                 daemon=True).start()
                return self._send(200, {"started": True})
            if path == "/api/cancel":
                ed.job.cancelled = True
                proc = ed.job.proc
                if proc and proc.poll() is None:
                    proc.terminate()
                return self._send(200, {"cancelled": True})
            return self._send(404, {"error": "not found"})

    return Handler


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keymap", default="mine", help="keymap folder under keyboards/razer/orbweaver/stock/keymaps")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--builder", choices=["auto", "qmk", "docker"], default="auto")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    if not re.match(r"^[a-z0-9_]+$", args.keymap):
        ap.error("keymap names are lower case letters, digits and _")

    class Server(ThreadingHTTPServer):
        # On Windows SO_REUSEADDR lets a second server bind a port that is in
        # use; fail instead, so a second copy cannot share the port.
        allow_reuse_address = sys.platform != "win32"

    ed = Editor(args.keymap, args.builder, args.port)
    try:
        server = Server(("127.0.0.1", args.port), make_handler(ed))
    except OSError as e:
        print(f"cannot listen on 127.0.0.1:{args.port} ({e}); is the editor already running? Open http://127.0.0.1:{args.port}/")
        return 2
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Orbweaver keymap editor: {url}  (keymap: {keymap_path(args.keymap)})")
    print("Close this window or press Ctrl+C to stop it.", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


# --------------------------------------------------------------------------- the page

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Orbweaver keymap</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:#f6f6f4; --fg:#1d1d1b; --muted:#6b6b66; --key:#ffffff; --line:#d4d4cf; --sel:#2f6fde; --trns:#a7a7a0; --accent:#2f6fde; --warn:#b4541a; }
@media (prefers-color-scheme: dark) { :root { --bg:#1b1b1a; --fg:#ececea; --muted:#9d9d97; --key:#2a2a28; --line:#3d3d3a; --sel:#6b9bff; --trns:#6f6f6a; --accent:#6b9bff; --warn:#e8935a; } }
* { box-sizing: border-box; }
body { margin:0; font:14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; background:var(--bg); color:var(--fg); }
header { display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding:12px 20px; border-bottom:1px solid var(--line); }
header h1 { font-size:16px; margin:0 12px 0 0; font-weight:600; }
button { font:inherit; padding:6px 12px; border:1px solid var(--line); border-radius:6px; background:var(--key); color:var(--fg); cursor:pointer; }
button:hover { border-color:var(--accent); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
button:disabled { opacity:.5; cursor:default; }
.tabs { display:flex; gap:4px; flex-wrap:wrap; }
.tabs button.on { border-color:var(--accent); box-shadow:inset 0 -2px 0 var(--accent); }
main { display:grid; grid-template-columns: minmax(520px, auto) 1fr; gap:20px; padding:20px; }
@media (max-width: 1100px) { main { grid-template-columns: 1fr; } }
#board { position:relative; }
.key { position:absolute; border:1px solid var(--line); border-radius:8px; background:var(--key); display:flex; flex-direction:column;
       align-items:center; justify-content:center; text-align:center; cursor:pointer; padding:2px; overflow:hidden; user-select:none; }
.key .n { position:absolute; top:2px; left:5px; font-size:10px; color:var(--muted); }
.key .k { font-size:13px; font-weight:600; line-height:1.15; word-break:break-word; }
.key .h { font-size:10px; color:var(--muted); }
.key.trns .k { color:var(--trns); font-weight:400; }
.key.sel { outline:3px solid var(--sel); outline-offset:1px; }
.panel h2 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:14px 0 6px; }
.grid { display:flex; flex-wrap:wrap; gap:4px; }
.grid button { padding:4px 8px; min-width:38px; }
.row { display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin:4px 0; }
select, input[type=text] { font:inherit; padding:5px 8px; border:1px solid var(--line); border-radius:6px; background:var(--key); color:var(--fg); }
#log { font:12px/1.35 ui-monospace, Consolas, monospace; background:var(--key); border:1px solid var(--line); border-radius:8px; padding:10px;
       height:220px; overflow:auto; white-space:pre-wrap; margin:0 20px 20px; }
#banner { margin:0 20px 12px; padding:10px 14px; border-radius:8px; border:1px solid var(--accent); display:none; font-weight:600; }
#banner.warn { border-color:var(--warn); color:var(--warn); }
.muted { color:var(--muted); }
#status { margin-left:auto; color:var(--muted); }
</style></head>
<body>
<header>
  <h1>Orbweaver keymap <span class="muted">· __KEYMAP__</span></h1>
  <div class="tabs" id="tabs"></div>
  <button id="addLayer" title="Add a layer">+ layer</button>
  <button id="delLayer" title="Remove the last layer">− layer</button>
  <button id="save">Save</button>
  <button id="revert">Revert</button>
  <button id="defaults">Defaults</button>
  <button id="export">Export</button>
  <button id="import">Import</button>
  <input type="file" id="file" accept=".json,application/json" hidden>
  <button id="build">Build only</button>
  <button id="flash" class="primary">Build &amp; flash</button>
  <span id="status"></span>
</header>
<div id="banner"></div>
<main>
  <div>
    <div id="board"></div>
    <p class="muted" id="layerNote"></p>
  </div>
  <div class="panel" id="palette"></div>
</main>
<pre id="log"></pre>
<script>
const TOKEN = "__TOKEN__";
let S = null, layers = [], cur = 0, sel = 0, dirty = false, logNext = 0, polling = null, found = false;
const U = 62;

const L = {};
"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").forEach(c => L["KC_" + c] = c);
"1234567890".split("").forEach(c => L["KC_" + c] = c);
for (let i = 1; i <= 24; i++) L["KC_F" + i] = "F" + i;
for (let i = 0; i <= 9; i++) L["KC_P" + i] = "Num " + i;
Object.assign(L, {
  KC_GRV:"`", KC_MINS:"-", KC_EQL:"=", KC_LBRC:"[", KC_RBRC:"]", KC_BSLS:"\\", KC_SCLN:";", KC_QUOT:"'", KC_COMM:",", KC_DOT:".", KC_SLSH:"/",
  KC_ESC:"Esc", KC_TAB:"Tab", KC_SPC:"Space", KC_ENT:"Enter", KC_BSPC:"Bksp", KC_DEL:"Del", KC_INS:"Ins", KC_CAPS:"Caps",
  KC_PSCR:"PrtSc", KC_SCRL:"ScrLk", KC_PAUS:"Pause", KC_APP:"Menu",
  KC_UP:"↑", KC_DOWN:"↓", KC_LEFT:"←", KC_RGHT:"→", KC_RIGHT:"→", KC_HOME:"Home", KC_END:"End", KC_PGUP:"PgUp", KC_PGDN:"PgDn",
  KC_LCTL:"Ctrl", KC_LSFT:"Shift", KC_LALT:"Alt", KC_LGUI:"Win", KC_RCTL:"R Ctrl", KC_RSFT:"R Shift", KC_RALT:"R Alt", KC_RGUI:"R Win",
  KC_PDOT:"Num .", KC_PENT:"Num Ent", KC_PPLS:"Num +", KC_PMNS:"Num −", KC_PAST:"Num *", KC_PSLS:"Num /", KC_NUM:"NumLk",
  KC_MUTE:"Mute", KC_VOLD:"Vol −", KC_VOLU:"Vol +", KC_MPLY:"Play", KC_MNXT:"Next", KC_MPRV:"Prev", KC_MSTP:"Stop",
  KC_CALC:"Calc", KC_MAIL:"Mail", KC_WHOM:"Web", KC_MYCM:"My PC",
  BL_TOGG:"Light on/off", BL_UP:"Light +", BL_DOWN:"Light −", BL_BRTG:"Breathe", BL_ON:"Light on", BL_OFF:"Light off", BL_STEP:"Light step",
  KC_TRNS:"▽", KC_NO:"—", QK_BOOT:"Boot", QK_RBT:"Reboot", EE_CLR:"Clear EE"
});
const MODS = { MOD_LCTL:"Ctrl", MOD_LSFT:"Shift", MOD_LALT:"Alt", MOD_LGUI:"Win", MOD_RCTL:"R Ctrl", MOD_RSFT:"R Shift", MOD_RALT:"R Alt", MOD_RGUI:"R Win" };
const MODFN = { LCTL:"Ctrl", LSFT:"Shift", LALT:"Alt", LGUI:"Win", RCTL:"R Ctrl", RSFT:"R Shift", RALT:"R Alt", RGUI:"R Win" };

function label(kc) {
  if (L[kc]) return { k: L[kc] };
  let m;
  if ((m = kc.match(/^LT\((\d+),(.+)\)$/))) return { k: label(m[2]).k, h: "hold L" + m[1] };
  if ((m = kc.match(/^(MO|TO|TG|TT|DF)\((\d+)\)$/))) return { k: m[1] + " " + m[2], h: { MO:"while held", TO:"switch", TG:"toggle", TT:"tap-toggle", DF:"default" }[m[1]] };
  if ((m = kc.match(/^MT\(([A-Z_|]+),(.+)\)$/))) return { k: label(m[2]).k, h: "hold " + m[1].split("|").map(x => MODS[x] || x).join("+") };
  if ((m = kc.match(/^(LCTL|LSFT|LALT|LGUI|RCTL|RSFT|RALT|RGUI)_T\((.+)\)$/))) return { k: label(m[2]).k, h: "hold " + MODFN[m[1]] };
  if ((m = kc.match(/^(LCTL|LSFT|LALT|LGUI|RCTL|RSFT|RALT|RGUI)\((.+)\)$/))) return { k: MODFN[m[1]] + "+" + label(m[2]).k };
  return { k: kc.replace(/^KC_/, "") };
}

function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: JSON.stringify(body) };
  return fetch(path, opt).then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j; });
}

function setDirty(d) { dirty = d; document.getElementById("status").textContent = d ? "unsaved changes" : ""; }

function drawTabs() {
  const t = document.getElementById("tabs"); t.innerHTML = "";
  layers.forEach((_, i) => {
    const b = document.createElement("button"); b.textContent = "Layer " + i; if (i === cur) b.className = "on";
    b.onclick = () => { cur = i; drawAll(); }; t.appendChild(b);
  });
  document.getElementById("addLayer").disabled = layers.length >= S.maxLayers;
  document.getElementById("delLayer").disabled = layers.length <= 1;
  const v = cur + 1, leds = [v & 1 ? "farthest" : null, v & 2 ? "middle" : null, v & 4 ? "closest" : null].filter(Boolean);
  document.getElementById("layerNote").textContent = "Layer " + cur + (cur === 0 ? " is the base layer. " : ". ") +
    (cur < 7 ? "Keymap LEDs while it is the top layer: " + leds.join(" + ") + "." : "") + "  ▽ = transparent (uses the key from the layer below).";
}

function drawBoard() {
  const b = document.getElementById("board"); b.innerHTML = "";
  let W = 0, H = 0;
  S.layout.forEach((k, i) => {
    const d = document.createElement("div"), kc = layers[cur][i], lb = label(kc);
    d.className = "key" + (i === sel ? " sel" : "") + (kc === "KC_TRNS" ? " trns" : "");
    Object.assign(d.style, { left: k.x * U + "px", top: k.y * U + "px", width: k.w * U - 4 + "px", height: k.h * U - 4 + "px" });
    d.title = (k.label || "") + ": " + kc;
    d.innerHTML = '<span class="n"></span><span class="k"></span><span class="h"></span>';
    d.querySelector(".n").textContent = /^\d+$/.test(k.label) ? k.label : "";
    d.querySelector(".k").textContent = lb.k;
    d.querySelector(".h").textContent = lb.h || "";
    d.onclick = () => { sel = i; drawAll(); };
    b.appendChild(d);
    W = Math.max(W, (k.x + k.w) * U); H = Math.max(H, (k.y + k.h) * U);
  });
  b.style.width = W + "px"; b.style.height = H + "px";
}

function assign(kc) {
  layers[cur][sel] = kc; setDirty(true);
  if (sel < S.layout.length - 1) sel++;
  drawAll();
}

const GROUPS = [
  ["Letters", "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map(c => "KC_" + c)],
  ["Numbers", "1234567890".split("").map(c => "KC_" + c)],
  ["Symbols", ["KC_GRV","KC_MINS","KC_EQL","KC_LBRC","KC_RBRC","KC_BSLS","KC_SCLN","KC_QUOT","KC_COMM","KC_DOT","KC_SLSH"]],
  ["Editing", ["KC_ESC","KC_TAB","KC_SPC","KC_ENT","KC_BSPC","KC_DEL","KC_INS","KC_CAPS","KC_PSCR","KC_SCRL","KC_PAUS","KC_APP"]],
  ["Navigation", ["KC_UP","KC_DOWN","KC_LEFT","KC_RGHT","KC_HOME","KC_END","KC_PGUP","KC_PGDN"]],
  ["Modifiers", ["KC_LCTL","KC_LSFT","KC_LALT","KC_LGUI","KC_RCTL","KC_RSFT","KC_RALT","KC_RGUI"]],
  ["Function keys", Array.from({ length: 24 }, (_, i) => "KC_F" + (i + 1))],
  ["Numpad", ["KC_P7","KC_P8","KC_P9","KC_P4","KC_P5","KC_P6","KC_P1","KC_P2","KC_P3","KC_P0","KC_PDOT","KC_PENT","KC_PPLS","KC_PMNS","KC_PAST","KC_PSLS","KC_NUM"]],
  ["Media", ["KC_MUTE","KC_VOLD","KC_VOLU","KC_MPLY","KC_MPRV","KC_MNXT","KC_MSTP","KC_CALC","KC_MAIL","KC_WHOM","KC_MYCM"]],
  ["Backlight", ["BL_TOGG","BL_DOWN","BL_UP","BL_BRTG","BL_ON","BL_OFF","BL_STEP"]],
  ["Special", ["KC_TRNS","KC_NO","QK_BOOT","QK_RBT","EE_CLR"]],
];

function drawPalette() {
  const p = document.getElementById("palette"); p.innerHTML = "";
  const k = S.layout[sel], h = document.createElement("div");
  h.innerHTML = '<div class="row"><b id="selName"></b> <span class="muted" id="selCode"></span></div>';
  p.appendChild(h);
  document.getElementById("selName").textContent = "Key " + (k.label || sel) + " on layer " + cur + ":";
  document.getElementById("selCode").textContent = layers[cur][sel];

  const adv = document.createElement("div");
  adv.innerHTML = '<h2>Layers and hold actions</h2>' +
    '<div class="row"><select id="lt"><option value="MO">MO: layer while held</option><option value="TO">TO: switch to layer</option>' +
    '<option value="TG">TG: toggle layer</option><option value="TT">TT: hold, or tap to toggle</option>' +
    '<option value="LT">LT: tap for this key, hold for layer</option></select> <select id="ln"></select> <button id="ltApply">Set</button></div>' +
    '<div class="row"><select id="mt"><option value="LCTL">Ctrl</option><option value="LSFT">Shift</option><option value="LALT">Alt</option>' +
    '<option value="LGUI">Win</option></select> <span class="muted">held, this key tapped</span> <button id="mtApply">Set</button></div>' +
    '<div class="row"><input type="text" id="raw" placeholder="any QMK keycode, e.g. LCTL(KC_C)" size="28"> <button id="rawApply">Set</button></div>';
  p.appendChild(adv);
  const ln = document.getElementById("ln");
  for (let i = 0; i < layers.length; i++) { const o = document.createElement("option"); o.value = i; o.textContent = "layer " + i; ln.appendChild(o); }
  const tapOf = kc => { const m = kc.match(/^(?:LT\(\d+,|MT\([A-Z_|]+,|[A-Z]+_T\()(.+)\)$/); return m ? m[1] : kc; };
  document.getElementById("ltApply").onclick = () => {
    const t = document.getElementById("lt").value, n = ln.value;
    if (t === "LT") { const tap = tapOf(layers[cur][sel]); if (!L[tap]) return alert("Give the key a plain keycode first; LT taps it."); assign("LT(" + n + "," + tap + ")"); }
    else assign(t + "(" + n + ")");
  };
  document.getElementById("mtApply").onclick = () => {
    const tap = tapOf(layers[cur][sel]); if (!L[tap]) return alert("Give the key a plain keycode first; it is what a tap sends.");
    assign(document.getElementById("mt").value + "_T(" + tap + ")");
  };
  document.getElementById("rawApply").onclick = () => { const v = document.getElementById("raw").value.trim().replace(/\s+/g, ""); if (v) assign(v); };

  GROUPS.forEach(([name, codes]) => {
    const t = document.createElement("h2"); t.textContent = name; p.appendChild(t);
    const g = document.createElement("div"); g.className = "grid";
    codes.forEach(c => { const b = document.createElement("button"); b.textContent = label(c).k; b.title = c; b.onclick = () => assign(c); g.appendChild(b); });
    p.appendChild(g);
  });
}

function drawAll() { drawTabs(); drawBoard(); drawPalette(); }

function bootHint() {
  // where is QK_BOOT, and which key reaches its layer from layer 0?
  for (let l = 0; l < layers.length; l++) {
    const i = layers[l].indexOf("QK_BOOT"); if (i < 0) continue;
    const name = j => "key " + (S.layout[j].label || j);
    if (l === 0) return "press " + name(i);
    const via = layers[0].findIndex(kc => kc === "MO(" + l + ")" || kc === "TT(" + l + ")" || kc.startsWith("LT(" + l + ","));
    if (via >= 0) return "hold " + name(via) + " and press " + name(i);
    return "switch to layer " + l + " and press " + name(i);
  }
  return null;
}

function banner(text, warn) {
  const b = document.getElementById("banner");
  b.style.display = text ? "block" : "none"; b.textContent = text || ""; b.className = warn ? "warn" : "";
}

function poll() {
  api("/api/job?since=" + logNext).then(j => {
    const log = document.getElementById("log");
    if (j.lines.length) { log.textContent += j.lines.join("\n") + "\n"; log.scrollTop = log.scrollHeight; }
    logNext = j.next;
    if (j.lines.some(l => l.startsWith("Razer bootloader found"))) found = true;
    if (j.state === "running") {
      document.getElementById("status").textContent = j.step + " …";
      if (j.step === "waiting for the bootloader") {
        if (found) banner("Flashing. Don't unplug the keypad.");
        else {
          const h = bootHint();
          banner("Put the keypad in its bootloader now: " + (h ? h : "unplug it, hold key 01 and plug it back in") +
                 ". (Or hold key 01 while plugging it in.)");
        }
      }
    } else {
      clearInterval(polling); polling = null;
      document.getElementById("flash").disabled = document.getElementById("build").disabled = false;
      if (j.state === "done") { banner(j.step === "flashed" ? "Flashed. The keypad restarts with the new keymap." : "Built."); document.getElementById("status").textContent = j.step; }
      else if (j.state === "failed") { banner("Something went wrong; see the log below.", true); document.getElementById("status").textContent = "failed"; }
    }
  }).catch(e => { clearInterval(polling); polling = null; banner("Lost contact with the editor program: " + e.message, true); });
}

function start(flash) {
  if (flash && !bootHint() && !confirm("This keymap has no QK_BOOT key. Updating it later will need key 01 held while plugging in. Continue?")) return;
  document.getElementById("log").textContent = ""; logNext = 0; found = false;
  document.getElementById("flash").disabled = document.getElementById("build").disabled = true;
  banner(flash ? "Building … then you will be asked to put the keypad in its bootloader." : "Building …");
  api("/api/build", { layers, flash }).then(() => { setDirty(false); polling = setInterval(poll, 700); })
    .catch(e => { banner(e.message, true); document.getElementById("flash").disabled = document.getElementById("build").disabled = false; });
}

function load() {
  return api("/api/state").then(s => {
    S = s; layers = s.km.layers.map(l => l.slice()); cur = Math.min(cur, layers.length - 1); setDirty(false);
    if (s.km.error) banner("Could not read the keymap file (" + s.km.error + "); showing the defaults.", true);
    else if (!s.km.exists) banner("New keymap: starting from the default layout. It is saved when you press Save or Build.");
    drawAll();
  });
}

document.getElementById("save").onclick = () => api("/api/save", { layers }).then(r => { setDirty(false); banner("Saved to " + r.saved); }).catch(e => banner(e.message, true));
document.getElementById("revert").onclick = () => { if (!dirty || confirm("Throw away unsaved changes?")) load(); };
document.getElementById("defaults").onclick = () => { if (confirm("Replace every layer with the default keymap?")) { layers = S.defaults.map(l => l.slice()); cur = 0; setDirty(true); drawAll(); } };
document.getElementById("addLayer").onclick = () => { layers.push(Array(S.layout.length).fill("KC_TRNS")); cur = layers.length - 1; setDirty(true); drawAll(); };
document.getElementById("delLayer").onclick = () => { if (confirm("Remove layer " + (layers.length - 1) + "?")) { layers.pop(); cur = Math.min(cur, layers.length - 1); setDirty(true); drawAll(); } };
document.getElementById("export").onclick = () => {
  const blob = new Blob([JSON.stringify({ version: 1, keyboard: "razer/orbweaver/stock", keymap: "__KEYMAP__", layout: "LAYOUT", layers }, null, 4)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "orbweaver___KEYMAP__.json"; a.click();
};
document.getElementById("import").onclick = () => document.getElementById("file").click();
document.getElementById("file").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  f.text().then(t => {
    const j = JSON.parse(t), ls = j.layers;
    if (!Array.isArray(ls) || !ls.length || ls.some(l => !Array.isArray(l) || l.length !== S.layout.length)) throw new Error("expected " + S.layout.length + " keys per layer");
    layers = ls.slice(0, S.maxLayers).map(l => l.map(String)); cur = 0; setDirty(true); drawAll(); banner("Imported " + f.name + ". Save or build to keep it.");
  }).catch(err => banner("Import failed: " + err.message, true));
  e.target.value = "";
};
document.getElementById("build").onclick = () => start(false);
document.getElementById("flash").onclick = () => start(true);
window.addEventListener("beforeunload", e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
load().catch(e => banner("Could not load: " + e.message, true));
</script>
</body></html>
"""

if __name__ == "__main__":
    sys.exit(main())
