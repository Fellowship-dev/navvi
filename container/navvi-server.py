"""
Navvi API Server — FastAPI REST endpoints for browser automation.

Runs inside the container. Controls Camoufox (anti-detect Firefox) via:
  - xdotool (OS-level mouse/keyboard — isTrusted: true events)
  - scrot (screenshots)
  - marionette.py (navigate, getURL, getTitle, executeJS via Marionette protocol)
"""

import argparse
import asyncio
import base64
import os
import re
import shlex
import subprocess
import tempfile

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from marionette import Marionette, MarionetteError

import signal
import time

app = FastAPI(title="Navvi Server", version="3.0.0")

# --- Globals ---

display: str = ":1"
PROFILES_DIR = os.path.expanduser("~/.mozilla/profiles")
BASE_MARIONETTE_PORT = 2828
MAX_PERSONAS = int(os.environ.get("NAVVI_MAX_PERSONAS", "5"))


# --- Marionette Pool ---

class MarionettePool:
    """Manages multiple Firefox/Camoufox instances, one per persona."""

    def __init__(self):
        self.instances = {}  # {persona_name: {"port": int, "pid": int, "marionette": Marionette}}
        self.active = "default"

    def register_default(self, pid: int):
        """Register the default Firefox started by start.sh (port 2828)."""
        m = Marionette(port=BASE_MARIONETTE_PORT)
        m.connect()
        m.new_session()
        self.instances["default"] = {
            "port": BASE_MARIONETTE_PORT,
            "pid": pid,
            "marionette": m,
            "profile": os.path.expanduser("~/.mozilla"),
        }

    def _next_port(self) -> int:
        """Find the next available Marionette port."""
        used = {info["port"] for info in self.instances.values()}
        port = BASE_MARIONETTE_PORT + 1
        while port in used:
            port += 1
        return port

    def start_persona(self, name: str) -> dict:
        """Launch a new Firefox instance for a persona."""
        if name in self.instances:
            return {"status": "already_running", "port": self.instances[name]["port"]}

        if name == "default":
            return {"status": "error", "message": "default persona is managed by start.sh"}

        if len(self.instances) >= MAX_PERSONAS:
            return {"status": "error", "message": "max personas reached ({})".format(MAX_PERSONAS)}

        port = self._next_port()
        profile_dir = os.path.join(PROFILES_DIR, name)
        os.makedirs(profile_dir, exist_ok=True)

        # Write user.js with custom Marionette port
        user_js = os.path.join(profile_dir, "user.js")
        with open(user_js, "w") as f:
            f.write('user_pref("marionette.port", {});\n'.format(port))

        # Launch Firefox
        env = os.environ.copy()
        env["DISPLAY"] = display
        proc = subprocess.Popen(
            [
                "camoufox-bin",
                "--marionette",
                "--no-remote",
                "--profile", profile_dir,
                "-width", "1024", "-height", "768",
                "about:blank",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait for Marionette to be ready
        m = Marionette(port=port)
        for attempt in range(15):
            try:
                m.connect(retries=1, delay=0.5)
                m.new_session()
                break
            except Exception:
                if attempt < 14:
                    time.sleep(1)
                else:
                    proc.kill()
                    return {"status": "error", "message": "Firefox failed to start for persona {}".format(name)}

        self.instances[name] = {
            "port": port,
            "pid": proc.pid,
            "marionette": m,
            "profile": profile_dir,
        }

        # Raise the new window to front
        self._raise_window(name)

        return {"status": "started", "port": port, "pid": proc.pid}

    def stop_persona(self, name: str) -> dict:
        """Stop a persona's Firefox instance."""
        if name not in self.instances:
            return {"status": "not_running"}
        if name == "default":
            return {"status": "error", "message": "cannot stop default persona (managed by start.sh)"}

        info = self.instances[name]
        pid = info["pid"]

        # Close Marionette
        try:
            info["marionette"].close()
        except Exception:
            pass

        # Graceful shutdown — let Firefox flush profile
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                try:
                    os.kill(pid, 0)  # check if still alive
                    time.sleep(1)
                except OSError:
                    break
            else:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

        del self.instances[name]

        # If we stopped the active persona, switch back to default
        if self.active == name:
            self.active = "default"
            self._raise_window("default")

        return {"status": "stopped"}

    def get(self, persona: Optional[str] = None) -> Marionette:
        """Get the Marionette client for a persona (default: active persona)."""
        name = persona or self.active
        if name not in self.instances:
            raise RuntimeError("Persona '{}' is not running. Start it with /persona/start".format(name))
        m = self.instances[name]["marionette"]
        # Test connection, reconnect if needed
        try:
            m.get_url()
        except Exception:
            port = self.instances[name]["port"]
            m = Marionette(port=port)
            m.connect()
            m.new_session()
            self.instances[name]["marionette"] = m
        return m

    def switch(self, name: str) -> dict:
        """Switch the active persona."""
        if name not in self.instances:
            return {"status": "error", "message": "persona '{}' not running".format(name)}
        self.active = name
        self._raise_window(name)
        return {"status": "switched", "active": name}

    def list_active(self) -> list:
        """List all running persona instances."""
        result = []
        for name, info in self.instances.items():
            result.append({
                "name": name,
                "port": info["port"],
                "pid": info["pid"],
                "active": name == self.active,
            })
        return result

    def _raise_window(self, name: str):
        """Raise a persona's Firefox window to the front."""
        try:
            env = os.environ.copy()
            env["DISPLAY"] = display
            # Find window by pid
            pid = self.instances[name]["pid"]
            result = subprocess.run(
                "xdotool search --pid {} --name ''".format(pid),
                shell=True, capture_output=True, text=True, timeout=3, env=env,
            )
            windows = result.stdout.strip().split("\n")
            if windows and windows[0]:
                subprocess.run(
                    "xdotool windowactivate --sync {}".format(windows[0]),
                    shell=True, capture_output=True, timeout=3, env=env,
                )
        except Exception:
            pass


pool = MarionettePool()


# --- Pydantic models ---

class NavigateRequest(BaseModel):
    url: str

class ClickRequest(BaseModel):
    x: int
    y: int

class TypeRequest(BaseModel):
    text: str
    delay: int = 12  # ms between chars

class KeyRequest(BaseModel):
    key: str

class MouseRequest(BaseModel):
    x: int
    y: int

class DragRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    steps: int = 20
    duration: float = 0.3  # seconds for the full drag

class ScrollRequest(BaseModel):
    direction: str = "down"  # up, down, left, right
    amount: int = 3

class ExecuteJSRequest(BaseModel):
    script: str
    args: list = []

class FindRequest(BaseModel):
    selector: str
    all: bool = False  # return all matches vs just the first

class CredsAutofillRequest(BaseModel):
    entry: str  # gopass entry path, e.g. "navvi/default/tuta"
    username_selector: str = "input[type=email], input[type=text], input[name*=user i], input[name*=email i], input[name*=login i]"
    password_selector: str = "input[type=password]"

class CredsGetRequest(BaseModel):
    entry: str
    field: str  # e.g. "username", "url", "email" — NOT "password"

class CredsGenerateRequest(BaseModel):
    entry: str  # gopass entry path, e.g. "navvi/fry-lobster/hn"
    username: str  # username to store alongside the generated password
    length: int = 24  # password length

class CredsImportEntry(BaseModel):
    entry: str
    username: str
    password: str

class CredsImportRequest(BaseModel):
    credentials: list[CredsImportEntry]


# --- Helpers ---

def run_xdotool(args: str, timeout: float = 5.0) -> str:
    """Run an xdotool command and return stdout."""
    env = os.environ.copy()
    env["DISPLAY"] = display
    result = subprocess.run(
        f"xdotool {args}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0 and result.stderr:
        raise RuntimeError(f"xdotool error: {result.stderr.strip()}")
    return result.stdout.strip()


def get_marionette(persona: Optional[str] = None) -> Marionette:
    """Get the Marionette client for a persona. Defaults to active persona."""
    return pool.get(persona)


# xdotool key name mapping (browser key names → xdotool names)
KEY_MAP = {
    "Enter": "Return",
    "Backspace": "BackSpace",
    "ArrowUp": "Up",
    "ArrowDown": "Down",
    "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Escape": "Escape",
    "Tab": "Tab",
    "Delete": "Delete",
    "Home": "Home",
    "End": "End",
    "PageUp": "Prior",
    "PageDown": "Next",
    "Space": "space",
    " ": "space",
}


# --- Endpoints ---

@app.get("/health")
async def health():
    """Check Camoufox + Xvfb are alive."""
    checks = {"xvfb": False, "firefox": False, "marionette": False}

    # Check Xvfb
    try:
        result = subprocess.run(
            ["xdpyinfo", "-display", display],
            capture_output=True, timeout=3
        )
        checks["xvfb"] = result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # xdpyinfo may not be installed; check if Xvfb process exists
        try:
            subprocess.run(
                ["pgrep", "-f", f"Xvfb {display}"],
                capture_output=True, timeout=3
            )
            checks["xvfb"] = True
        except Exception:
            pass

    # Check Camoufox process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "camoufox"],
            capture_output=True, timeout=3
        )
        checks["firefox"] = result.returncode == 0
    except Exception:
        pass

    # Check Marionette connection
    try:
        m = get_marionette()
        m.get_url()
        checks["marionette"] = True
    except Exception:
        pass

    ok = all(checks.values())
    return {"ok": ok, **checks, "personas": pool.list_active()}


# --- Persona management ---

class PersonaStartRequest(BaseModel):
    name: str

class PersonaStopRequest(BaseModel):
    name: str

class PersonaSwitchRequest(BaseModel):
    name: str

@app.post("/persona/start")
async def persona_start(req: PersonaStartRequest):
    """Start a new Firefox instance for a persona."""
    result = pool.start_persona(req.name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    pool.switch(req.name)
    return result

@app.post("/persona/stop")
async def persona_stop(req: PersonaStopRequest):
    """Stop a persona's Firefox instance."""
    result = pool.stop_persona(req.name)
    return result

@app.post("/persona/switch")
async def persona_switch(req: PersonaSwitchRequest):
    """Switch the active persona (raise its window)."""
    result = pool.switch(req.name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.get("/persona/list")
async def persona_list():
    """List all running persona instances."""
    return {"personas": pool.list_active(), "active": pool.active}


@app.post("/navigate")
async def navigate(req: NavigateRequest):
    """Navigate to a URL via Marionette."""
    try:
        m = get_marionette()
        m.navigate(req.url)
        # Give the page a moment to start loading
        await asyncio.sleep(0.5)
        url = m.get_url()
        title = m.get_title()
        return {"ok": True, "url": url, "title": title}
    except MarionetteError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/url")
async def get_url():
    """Get current page URL."""
    try:
        m = get_marionette()
        return {"url": m.get_url()}
    except MarionetteError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/title")
async def get_title():
    """Get current page title."""
    try:
        m = get_marionette()
        return {"title": m.get_title()}
    except MarionetteError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/click")
async def click(req: ClickRequest):
    """Click at (x, y) using xdotool."""
    run_xdotool(f"mousemove {req.x} {req.y}")
    await asyncio.sleep(0.05)
    run_xdotool("click 1")
    return {"ok": True, "x": req.x, "y": req.y}


@app.post("/type")
async def type_text(req: TypeRequest):
    """Type text using xdotool, chunked at 50 chars."""
    text = req.text
    chunk_size = 50
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        # Escape for shell safety
        safe_chunk = shlex.quote(chunk)
        run_xdotool(f"type --delay {req.delay} -- {safe_chunk}", timeout=30.0)
    return {"ok": True, "length": len(text)}


@app.post("/key")
async def press_key(req: KeyRequest):
    """Press a key using xdotool."""
    key = KEY_MAP.get(req.key, req.key)
    run_xdotool(f"key {shlex.quote(key)}")
    return {"ok": True, "key": key}


@app.post("/mousedown")
async def mousedown(req: MouseRequest):
    """Move to (x, y) and press mouse button down."""
    run_xdotool(f"mousemove {req.x} {req.y}")
    await asyncio.sleep(0.05)
    run_xdotool("mousedown 1")
    return {"ok": True, "x": req.x, "y": req.y}


@app.post("/mouseup")
async def mouseup(req: MouseRequest):
    """Move to (x, y) and release mouse button."""
    run_xdotool(f"mousemove {req.x} {req.y}")
    await asyncio.sleep(0.05)
    run_xdotool("mouseup 1")
    return {"ok": True, "x": req.x, "y": req.y}


class HoldRequest(BaseModel):
    x: int
    y: int
    duration_ms: int = 5000

@app.post("/hold")
async def hold(req: HoldRequest):
    """Press and hold at (x, y) for duration_ms milliseconds. For CAPTCHAs."""
    run_xdotool(f"mousemove {req.x} {req.y}")
    await asyncio.sleep(0.05)
    run_xdotool("mousedown 1")
    await asyncio.sleep(req.duration_ms / 1000.0)
    run_xdotool("mouseup 1")
    return {"ok": True, "x": req.x, "y": req.y, "duration_ms": req.duration_ms}


@app.post("/mousemove")
async def mousemove(req: MouseRequest):
    """Move mouse to (x, y)."""
    run_xdotool(f"mousemove {req.x} {req.y}")
    return {"ok": True, "x": req.x, "y": req.y}


@app.post("/drag")
async def drag(req: DragRequest):
    """Drag from (x1,y1) to (x2,y2) with interpolated mouse moves."""
    steps = max(req.steps, 2)
    step_delay = req.duration / steps

    # Move to start and press
    run_xdotool(f"mousemove {req.x1} {req.y1}")
    await asyncio.sleep(0.05)
    run_xdotool("mousedown 1")
    await asyncio.sleep(0.05)

    # Interpolate path
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(req.x1 + (req.x2 - req.x1) * t)
        cy = int(req.y1 + (req.y2 - req.y1) * t)
        run_xdotool(f"mousemove {cx} {cy}")
        await asyncio.sleep(step_delay)

    # Release
    run_xdotool("mouseup 1")
    return {"ok": True, "from": [req.x1, req.y1], "to": [req.x2, req.y2]}


@app.post("/scroll")
async def scroll(req: ScrollRequest):
    """Scroll using xdotool button clicks (4=up, 5=down, 6=left, 7=right)."""
    button_map = {"up": 4, "down": 5, "left": 6, "right": 7}
    button = button_map.get(req.direction)
    if button is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid direction: {req.direction}. Use up/down/left/right."
        )
    run_xdotool(f"click --repeat {req.amount} {button}")
    return {"ok": True, "direction": req.direction, "amount": req.amount}


@app.get("/screenshot")
async def screenshot():
    """Take a screenshot with scrot and return base64 PNG."""
    env = os.environ.copy()
    env["DISPLAY"] = display
    tmp_path = os.path.join(tempfile.gettempdir(), "navvi-shot.png")

    result = subprocess.run(
        ["scrot", "-o", "-p", tmp_path],
        capture_output=True, timeout=5, env=env
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"scrot failed: {result.stderr.decode().strip()}"
        )

    with open(tmp_path, "rb") as f:
        img_data = f.read()

    b64 = base64.b64encode(img_data).decode("ascii")
    return {"ok": True, "base64": b64, "size": len(img_data)}


@app.get("/cursor")
async def cursor():
    """Get current mouse position."""
    output = run_xdotool("getmouselocation --shell")
    # Parse: X=123\nY=456\nSCREEN=0\nWINDOW=...
    pos = {}
    for line in output.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            pos[k.lower()] = int(v) if v.isdigit() else v
    return {"ok": True, "x": pos.get("x", 0), "y": pos.get("y", 0)}


@app.post("/execute")
async def execute_js(req: ExecuteJSRequest):
    """Execute JavaScript in Firefox via Marionette."""
    try:
        m = get_marionette()
        result = m.execute_script(req.script, req.args)
        return {"ok": True, "value": result}
    except MarionetteError as e:
        raise HTTPException(status_code=500, detail=str(e))


def get_viewport_offset():
    """Get the pixel offset from screen origin to Firefox's content viewport.

    JS getBoundingClientRect() returns coords relative to the viewport.
    xdotool works with absolute screen coords. The difference is the
    browser chrome (tab bar, address bar, notification banners).

    Firefox exposes this via mozInnerScreenX/Y — the screen position
    of the top-left corner of the viewport.
    """
    try:
        m = get_marionette()
        result = m.execute_script(
            "return { x: window.mozInnerScreenX || 0, y: window.mozInnerScreenY || 0 }"
        )
        return (int(result.get("x", 0)), int(result.get("y", 0)))
    except Exception:
        return (0, 0)


@app.get("/viewport")
async def viewport():
    """Get viewport offset — the translation between JS coordinates and screen coordinates.

    Returns the pixel offset from screen origin to the browser content area.
    Add these values to any getBoundingClientRect() coordinates before
    passing them to click/mousedown/etc.
    """
    offset_x, offset_y = get_viewport_offset()
    try:
        m = get_marionette()
        dims = m.execute_script(
            "return { innerWidth: window.innerWidth, innerHeight: window.innerHeight }"
        )
    except Exception:
        dims = {}
    return {
        "ok": True,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "viewport_width": dims.get("innerWidth", 0),
        "viewport_height": dims.get("innerHeight", 0),
    }


@app.post("/find")
async def find_element(req: FindRequest):
    """Find element(s) by CSS selector and return screen-ready coordinates.

    Unlike raw executeJS + getBoundingClientRect(), this endpoint
    auto-translates viewport coordinates to screen coordinates by adding
    the browser chrome offset. The returned x/y can be passed directly
    to /click, /mousedown, etc.
    """
    try:
        m = get_marionette()
        offset_x, offset_y = get_viewport_offset()

        if req.all:
            script = """
                const els = document.querySelectorAll(arguments[0]);
                return Array.from(els).slice(0, 50).map(el => {
                    const r = el.getBoundingClientRect();
                    return {
                        tag: el.tagName,
                        id: el.id || '',
                        name: el.name || el.getAttribute('name') || '',
                        type: el.type || '',
                        role: el.getAttribute('role') || '',
                        text: (el.textContent || '').trim().slice(0, 80),
                        value: (el.value || '').slice(0, 80),
                        placeholder: el.placeholder || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        visible: r.width > 0 && r.height > 0,
                        vx: Math.round(r.x + r.width / 2),
                        vy: Math.round(r.y + r.height / 2),
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                    };
                });
            """
            elements = m.execute_script(script, [req.selector])
            if not elements:
                return {"ok": True, "found": False, "elements": []}
            # Apply screen offset
            for el in elements:
                el["x"] = el.pop("vx") + offset_x
                el["y"] = el.pop("vy") + offset_y
            return {"ok": True, "found": True, "count": len(elements), "elements": elements}
        else:
            script = """
                const el = document.querySelector(arguments[0]);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    tag: el.tagName,
                    id: el.id || '',
                    name: el.name || el.getAttribute('name') || '',
                    type: el.type || '',
                    role: el.getAttribute('role') || '',
                    text: (el.textContent || '').trim().slice(0, 80),
                    value: (el.value || '').slice(0, 80),
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    visible: r.width > 0 && r.height > 0,
                    vx: Math.round(r.x + r.width / 2),
                    vy: Math.round(r.y + r.height / 2),
                    width: Math.round(r.width),
                    height: Math.round(r.height),
                };
            """
            el = m.execute_script(script, [req.selector])
            if not el:
                return {"ok": True, "found": False}
            el["x"] = el.pop("vx") + offset_x
            el["y"] = el.pop("vy") + offset_y
            return {"ok": True, "found": True, **el}
    except MarionetteError as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Credential management (gopass) ---

def run_gopass(args: str, timeout: float = 5.0) -> str:
    """Run a gopass command and return stdout."""
    result = subprocess.run(
        f"gopass {args}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gopass failed: {result.returncode}")
    return result.stdout.strip()


@app.get("/creds/list")
async def creds_list():
    """List all credential entries (names only, no secrets)."""
    try:
        output = run_gopass("ls --flat")
        entries = [e for e in output.splitlines() if e.strip()]
        return {"ok": True, "entries": entries, "count": len(entries)}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/creds/get")
async def creds_get(req: CredsGetRequest):
    """Get a specific non-secret field from a gopass entry.

    Returns metadata fields like username, url, email.
    Refuses to return the password field — use /creds/autofill instead.
    """
    blocked = {"password", "pass", "secret", "token", "key", "recovery"}
    if req.field.lower() in blocked:
        raise HTTPException(
            status_code=403,
            detail=f"Field '{req.field}' is a secret — use /creds/autofill to fill it into the browser without exposing it."
        )
    try:
        value = run_gopass(f"show {shlex.quote(req.entry)} {shlex.quote(req.field)}")
        return {"ok": True, "entry": req.entry, "field": req.field, "value": value}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/creds/autofill")
async def creds_autofill(req: CredsAutofillRequest):
    """Autofill a login form using gopass credentials.

    Reads username and password from gopass, finds the form fields
    via CSS selectors, and types them using xdotool. The password
    NEVER appears in the API response — it goes directly from
    gopass → xdotool → browser.
    """
    try:
        # Read credentials from gopass (server-side only, never returned)
        # Try email first (most login forms want full email), fall back to username
        username = ""
        for field in ["email", "username", "login", "user"]:
            try:
                username = run_gopass(f"show {shlex.quote(req.entry)} {field}")
                if username:
                    break
            except RuntimeError:
                continue
        password = run_gopass(f"show -o {shlex.quote(req.entry)}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"gopass error: {e}")

    if not password:
        raise HTTPException(status_code=404, detail=f"Entry '{req.entry}' has no password")

    # Find form fields
    try:
        m = get_marionette()
        offset_x, offset_y = get_viewport_offset()

        find_script = """
            const el = document.querySelector(arguments[0]);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {
                x: Math.round(r.x + r.width / 2),
                y: Math.round(r.y + r.height / 2),
                visible: r.width > 0 && r.height > 0,
            };
        """

        # Find username field (optional — may not exist on password-only pages)
        username_el = None
        if username:
            username_el = m.execute_script(find_script, [req.username_selector])
            if username_el and not username_el.get("visible"):
                username_el = None

        # Find password field
        password_el = m.execute_script(find_script, [req.password_selector])
        if not password_el or not password_el.get("visible"):
            raise HTTPException(status_code=404, detail=f"Password field not found: {req.password_selector}")

        px, py = password_el["x"] + offset_x, password_el["y"] + offset_y
    except MarionetteError as e:
        raise HTTPException(status_code=500, detail=f"Browser error: {e}")

    username_filled = False
    ux, uy = 0, 0

    # Fill username (if field found and username available)
    if username_el and username:
        ux, uy = username_el["x"] + offset_x, username_el["y"] + offset_y
        run_xdotool(f"mousemove {ux} {uy}")
        await asyncio.sleep(0.05)
        run_xdotool("click 1")
        await asyncio.sleep(0.1)
        run_xdotool("key ctrl+a")
        await asyncio.sleep(0.05)
        safe_user = shlex.quote(username)
        run_xdotool(f"type --delay 15 -- {safe_user}", timeout=15.0)
        await asyncio.sleep(0.3)
        username_filled = True

    # Fill password (never logged, never returned)
    run_xdotool(f"mousemove {px} {py}")
    await asyncio.sleep(0.05)
    run_xdotool("click 1")
    await asyncio.sleep(0.1)
    run_xdotool("key ctrl+a")
    await asyncio.sleep(0.05)
    safe_pass = shlex.quote(password)
    run_xdotool(f"type --delay 15 -- {safe_pass}", timeout=15.0)

    # Scrub password from memory
    del password
    del safe_pass

    return {
        "ok": True,
        "entry": req.entry,
        "username_filled": username_filled,
        "password_filled": True,
        "username_at": [ux, uy] if username_filled else [],
        "password_at": [px, py],
        "note": "Password was typed directly into the browser — it never appeared in this response."
    }


@app.post("/creds/generate")
async def creds_generate(req: CredsGenerateRequest):
    """Generate a random password inside the container and store it in gopass.

    The password is NEVER returned in the response — it goes directly into
    gopass and can only reach the browser via /creds/autofill.
    """
    if req.length < 12 or req.length > 128:
        raise HTTPException(status_code=400, detail="Length must be between 12 and 128")

    # Check if entry already exists
    try:
        existing = run_gopass("ls --flat")
        if req.entry in existing.splitlines():
            raise HTTPException(status_code=409, detail=f"Entry '{req.entry}' already exists. Delete it first or use a different name.")
    except RuntimeError:
        pass  # Empty store, that's fine

    try:
        # Generate password (cryptic, no symbols — better form compat)
        # gopass generate creates the entry with a random password
        run_gopass(f"generate -f {shlex.quote(req.entry)} {req.length}", timeout=10.0)

        # Add username as a named field
        # gopass insert appends key-value pairs below the password line
        proc = subprocess.run(
            f"echo 'username: {shlex.quote(req.username)}' | gopass insert -a {shlex.quote(req.entry)}",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip())

        return {
            "ok": True,
            "entry": req.entry,
            "length": req.length,
            "username": req.username,
            "note": "Password generated and stored in gopass. It was NOT included in this response. Use /creds/autofill to fill it into a form."
        }
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"gopass error: {e}")


@app.post("/creds/import")
async def creds_import(req: CredsImportRequest):
    """Import credentials into gopass. Passwords appear briefly in the request
    body (localhost only) but are NEVER echoed back in the response.
    """
    if not req.credentials:
        raise HTTPException(status_code=400, detail="No credentials provided")

    imported = 0
    errors = []

    for cred in req.credentials:
        try:
            # Create entry with password on first line + username field
            payload = f"{cred.password}\nusername: {cred.username}"
            proc = subprocess.run(
                f"echo {shlex.quote(payload)} | gopass insert -m {shlex.quote(cred.entry)}",
                shell=True, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                errors.append({"entry": cred.entry, "error": proc.stderr.strip()})
            else:
                imported += 1
        except Exception as e:
            errors.append({"entry": cred.entry, "error": str(e)})

    result = {"ok": len(errors) == 0, "imported": imported}
    if errors:
        result["errors"] = errors
    return result


# --- Startup ---

def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Navvi API Server")
    parser.add_argument("--port", type=int, default=8024)
    parser.add_argument("--display", type=str, default=":1")
    args = parser.parse_args()

    global display
    display = args.display

    # Create profiles directory
    os.makedirs(PROFILES_DIR, exist_ok=True)

    # Register the default Firefox (started by start.sh on port 2828)
    try:
        # Find the default Firefox PID
        result = subprocess.run(
            ["pgrep", "-f", "camoufox-bin.*--marionette"],
            capture_output=True, text=True, timeout=3,
        )
        default_pid = int(result.stdout.strip().split("\n")[0]) if result.stdout.strip() else 0
        pool.register_default(default_pid)
        print("[navvi-server] Default persona registered (Marionette :{}, PID {})".format(BASE_MARIONETTE_PORT, default_pid))
    except Exception as e:
        print("[navvi-server] WARNING: Could not register default persona: {}".format(e))
        print("[navvi-server] Will retry on first request")

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
