# Navvi v2

Give your AI agent a real browser identity.

Persistent browser personas powered by Xvfb + Firefox + xdotool. OS-level input produces `isTrusted: true` events — undetectable by bot detection. Firefox profiles persist across sessions via Docker volumes.

## Architecture

```
MCP server (server.mjs, Node.js)
  ↓ HTTP calls to localhost:8024
Docker container
  ├── Xvfb :1 (virtual display, 1024x768)
  ├── Firefox ESR (--marionette, persistent profile)
  ├── navvi-server.py (FastAPI on :8024)
  │   ├── xdotool (click, type, mousedown/up, drag)
  │   ├── scrot (screenshots)
  │   └── marionette.py (navigate, getURL, getTitle, executeJS)
  ├── x11vnc + noVNC (:6080, live view)
  └── Volume: /home/user/.mozilla (persistent Firefox profile)
```

## Quick Start

```bash
# Build the Docker image
docker build -t navvi container/

# Start a persona
./scripts/navvi.sh start default

# Or via MCP tools
# navvi_start persona=default mode=local
# navvi_open url=https://example.com
# navvi_screenshot
```

## Structure

```
container/
├── Dockerfile           # Ubuntu + Firefox + Xvfb + xdotool + FastAPI
├── start.sh             # Entrypoint: start all services
├── navvi-server.py      # REST API for automation
├── marionette.py        # Firefox Marionette TCP client
└── requirements.txt     # fastapi, uvicorn
mcp/
├── server.mjs           # MCP server (Docker lifecycle + tool handlers)
└── mcp.json             # MCP config
personas/
└── default.yaml         # Template persona
scripts/
└── navvi.sh             # CLI wrapper
.devcontainer/
└── devcontainer.json    # Codespace config
```

## API Endpoints (navvi-server.py)

| Endpoint | Method | Backend |
|---|---|---|
| `/health` | GET | Check Firefox + Xvfb alive |
| `/navigate` | POST `{url}` | Marionette |
| `/url` | GET | Marionette |
| `/title` | GET | Marionette |
| `/click` | POST `{x, y}` | xdotool |
| `/type` | POST `{text, delay}` | xdotool |
| `/key` | POST `{key}` | xdotool |
| `/mousedown` | POST `{x, y}` | xdotool |
| `/mouseup` | POST `{x, y}` | xdotool |
| `/mousemove` | POST `{x, y}` | xdotool |
| `/drag` | POST `{x1, y1, x2, y2}` | xdotool |
| `/scroll` | POST `{direction, amount}` | xdotool |
| `/screenshot` | GET | scrot → base64 PNG |
| `/cursor` | GET | xdotool |
| `/execute` | POST `{script}` | Marionette |

## MCP Tools (19 total)

**Lifecycle:** `navvi_start`, `navvi_stop`, `navvi_status`, `navvi_list`

**Browser:** `navvi_open`, `navvi_click`, `navvi_fill`, `navvi_press`, `navvi_drag`, `navvi_mousedown`, `navvi_mouseup`, `navvi_mousemove`, `navvi_scroll`, `navvi_screenshot`, `navvi_url`, `navvi_vnc`

**Recording:** `navvi_record_start`, `navvi_record_stop`, `navvi_record_gif`

## Persona Persistence

Firefox profiles are stored in Docker named volumes (`navvi-profile-<persona>`). Stop and restart a container — cookies, logins, and browsing history are preserved.

First-time login: use `navvi_vnc` to get the noVNC URL, log in manually via the browser, then the session persists.

## Why v2?

v1 used PinchTab (Chrome/CDP). CDP is detectable — bot detection scripts check for `navigator.webdriver`, CDP protocol markers, and `isTrusted: false` events. v2 replaces all of this with:

- **Firefox** instead of Chrome (no CDP detection vectors)
- **xdotool** for all input (OS-level events, `isTrusted: true`)
- **Marionette** for navigation only (no input, no detection surface)
- **scrot** for screenshots (X11-level capture)

## License

Apache 2.0
