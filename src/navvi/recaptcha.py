"""reCAPTCHA handler — checkbox click + optional image challenge solver."""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile


CHALLENGE_PROMPT = (
    "You are analyzing a reCAPTCHA image challenge. The image shows a grid of tiles "
    "(typically 3x3 or 4x4). Each tile may or may not contain the target object.\n\n"
    "Given the screenshot, identify:\n"
    "1. What object are you asked to select? (e.g. 'traffic lights', 'bicycles', 'crosswalks')\n"
    "2. Which tiles contain that object? Number tiles left-to-right, top-to-bottom starting at 1.\n\n"
    "Respond with ONLY a JSON object:\n"
    '{"target": "the object to find", "grid": "3x3" or "4x4", "tiles": [1, 4, 7]}\n'
    "where tiles is the list of tile numbers that contain the target object."
)


async def try_recaptcha_checkbox(api_call_fn, api_base: str) -> str:
    """Try clicking the reCAPTCHA checkbox. Returns status string.

    Returns:
        "passed" — checkbox accepted, no challenge
        "challenge" — image challenge appeared (needs solve_image_challenge)
        "not_found" — no reCAPTCHA on page
        "failed" — click failed
    """
    # Find reCAPTCHA iframe
    try:
        resp = await api_call_fn("POST", "/find", {"selector": "iframe[src*='recaptcha']"}, api_base)
    except Exception:
        return "not_found"

    if not resp.get("found"):
        # Try alternate selector
        try:
            resp = await api_call_fn("POST", "/find", {"selector": "div.g-recaptcha iframe, iframe[title*='reCAPTCHA']"}, api_base)
        except Exception:
            return "not_found"
        if not resp.get("found"):
            return "not_found"

    # Click the checkbox area inside the iframe
    # The checkbox is at approximately (28, 28) from the iframe's top-left corner
    iframe_x = resp["x"]
    iframe_y = resp["y"]
    iframe_w = resp.get("width", 300)
    iframe_h = resp.get("height", 78)

    # iframe coords are center-based from navvi_find; checkbox is near top-left
    checkbox_x = iframe_x - (iframe_w // 2) + 28
    checkbox_y = iframe_y - (iframe_h // 2) + 28

    try:
        await api_call_fn("POST", "/click", {"x": checkbox_x, "y": checkbox_y}, api_base)
    except Exception:
        return "failed"

    # Wait for response (green checkmark or image challenge)
    await asyncio.sleep(3)

    # Check if a challenge iframe appeared (larger iframe = image grid)
    try:
        challenge = await api_call_fn(
            "POST", "/find",
            {"selector": "iframe[src*='recaptcha'][style*='height'], iframe[title*='recaptcha challenge']"},
            api_base,
        )
        if challenge.get("found") and challenge.get("height", 0) > 200:
            return "challenge"
    except Exception:
        pass

    # Check for the green checkmark by looking for the checked state
    try:
        resp2 = await api_call_fn("POST", "/find", {"selector": "iframe[src*='recaptcha']"}, api_base)
        # If we can still find the iframe and no challenge appeared, likely passed
        if resp2.get("found"):
            return "passed"
    except Exception:
        pass

    return "passed"


async def solve_image_challenge(api_call_fn, api_base: str, max_rounds: int = 3) -> str:
    """Attempt to solve a reCAPTCHA image challenge using vision analysis.

    Takes a screenshot, asks the vision tier to identify target tiles,
    clicks them, and verifies. Repeats up to max_rounds.

    Returns:
        "solved" — challenge completed successfully
        "failed" — could not solve after max_rounds
        "no_vision" — no vision tier available (ANTHROPIC_API_KEY or claude CLI needed)
    """
    has_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_cli = bool(shutil.which("claude"))

    if not has_api and not has_cli:
        return "no_vision"

    for round_num in range(max_rounds):
        # Screenshot the challenge
        try:
            shot = await api_call_fn("GET", "/screenshot", api_base=api_base)
            screenshot_b64 = shot.get("base64", "")
        except Exception:
            return "failed"

        if not screenshot_b64:
            return "failed"

        # Analyze with vision
        analysis = await _analyze_challenge(screenshot_b64, has_api, has_cli)
        if not analysis or not analysis.get("tiles"):
            return "failed"

        tiles = analysis["tiles"]
        grid = analysis.get("grid", "3x3")

        # Find the challenge iframe to get its bounds
        try:
            challenge_frame = await api_call_fn(
                "POST", "/find",
                {"selector": "iframe[src*='recaptcha'][style*='height'], iframe[title*='recaptcha challenge'], div.rc-imageselect-response-field"},
                api_base,
            )
        except Exception:
            return "failed"

        if not challenge_frame.get("found"):
            # Maybe already solved?
            return "solved"

        # Calculate tile positions and click them
        await _click_tiles(api_call_fn, api_base, challenge_frame, tiles, grid)

        # Wait a moment then click verify/submit
        await asyncio.sleep(1)

        try:
            verify_btn = await api_call_fn(
                "POST", "/find",
                {"selector": "button#recaptcha-verify-button, button.rc-button-default"},
                api_base,
            )
            if verify_btn.get("found"):
                await api_call_fn("POST", "/click", {"x": verify_btn["x"], "y": verify_btn["y"]}, api_base)
        except Exception:
            pass

        await asyncio.sleep(3)

        # Check if challenge is gone (solved) or still showing (new round)
        try:
            still_there = await api_call_fn(
                "POST", "/find",
                {"selector": "iframe[src*='recaptcha'][style*='height'], div.rc-imageselect-instructions"},
                api_base,
            )
            if not still_there.get("found") or still_there.get("height", 0) < 200:
                return "solved"
        except Exception:
            return "solved"

    return "failed"


async def _analyze_challenge(screenshot_b64: str, has_api: bool, has_cli: bool) -> dict:
    """Use vision to identify which tiles to click."""
    if has_api:
        result = await _analyze_api(screenshot_b64)
        if result and result.get("tiles"):
            return result

    if has_cli:
        result = await _analyze_cli(screenshot_b64)
        if result and result.get("tiles"):
            return result

    return {}


async def _analyze_api(screenshot_b64: str) -> dict:
    """Use Anthropic API for challenge analysis."""
    try:
        import anthropic
    except ImportError:
        return {}

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=CHALLENGE_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64},
                    },
                    {"type": "text", "text": "Which tiles should I click?"},
                ],
            }],
        )
        text = message.content[0].text if message.content else ""
        return _parse_json(text)
    except Exception:
        return {}


async def _analyze_cli(screenshot_b64: str) -> dict:
    """Use claude -p for challenge analysis."""
    tmp_path = os.path.join(tempfile.gettempdir(), ".navvi-recaptcha-tmp.png")
    try:
        with open(tmp_path, "wb") as f:
            f.write(base64.b64decode(screenshot_b64))

        prompt = (
            CHALLENGE_PROMPT
            + "\n\nThe screenshot is at: " + tmp_path
            + "\nUse the Read tool to view it, then respond with the JSON."
        )

        env = {k: v for k, v in os.environ.items()
               if k not in ("CLAUDECODE", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_ENTRYPOINT")}

        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read"],
            env=env, capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )

        if result.returncode == 0 and result.stdout:
            return _parse_json(result.stdout)
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return {}


async def _click_tiles(api_call_fn, api_base: str, frame: dict, tiles: list, grid: str):
    """Click the specified tile numbers in the challenge grid."""
    cols, rows = 3, 3
    if grid == "4x4":
        cols, rows = 4, 4

    # The challenge grid is inside the iframe
    # frame x,y is center; we need to find the grid area
    # Typical reCAPTCHA: grid starts ~60px from top of iframe (instruction text)
    # and occupies most of the width
    frame_x = frame["x"]
    frame_y = frame["y"]
    frame_w = frame.get("width", 400)
    frame_h = frame.get("height", 500)

    # Grid area: roughly centered, with padding
    grid_left = frame_x - (frame_w // 2) + 15
    grid_top = frame_y - (frame_h // 2) + 100  # skip instruction header
    grid_w = frame_w - 30
    grid_h = frame_h - 160  # skip header and button area

    tile_w = grid_w // cols
    tile_h = grid_h // rows

    for tile_num in tiles:
        if tile_num < 1 or tile_num > cols * rows:
            continue
        row = (tile_num - 1) // cols
        col = (tile_num - 1) % cols

        click_x = grid_left + (col * tile_w) + (tile_w // 2)
        click_y = grid_top + (row * tile_h) + (tile_h // 2)

        try:
            await api_call_fn("POST", "/click", {"x": click_x, "y": click_y}, api_base)
            await asyncio.sleep(0.3)
        except Exception:
            pass


def _parse_json(text: str) -> dict:
    """Extract JSON from text response."""
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    for marker in ("```json", "```"):
        if marker in text:
            start = text.index(marker) + len(marker)
            end_pos = text.find("```", start)
            end = end_pos if end_pos != -1 else len(text)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first:last + 1])
        except (json.JSONDecodeError, ValueError):
            pass
    return {}
