#!/usr/bin/env python3
"""
scul_mission.py — Fetches the current SCUL mission name from scul.org/missioncontrol/
and renders it as a scrolling text banner on the 32x32 RGB matrix.

Caches the result locally so it survives reboots without internet.
Updates once per day, or immediately on first run / cache miss.

Dependencies:
    pip3 install requests beautifulsoup4 Pillow
"""

import os
import json
import time
import datetime
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

SCUL_URL        = "https://scul.org/missioncontrol/"
CACHE_FILE      = "./scul_mission_cache.json"
CACHE_MAX_AGE   = 86400          # seconds — refresh once per day
FETCH_TIMEOUT   = 10             # seconds before giving up on the request
RETRY_INTERVAL  = 300            # if fetch fails, retry in 5 minutes

# Text rendering
FONT_PATH       = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SIZE       = 8              # 8px fits cleanly in 32px height
TEXT_COLOR      = (255, 200, 0)  # amber — change freely (R, G, B)
BG_COLOR        = (0, 0, 0)      # black background
SCROLL_SPEED    = 0.04           # seconds per pixel step
SCROLL_PADDING  = 32             # blank pixels of lead-in before text

MATRIX_WIDTH    = 32
MATRIX_HEIGHT   = 32


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(data: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[SCUL] Cache write failed: {e}")


def cache_is_fresh(cache: dict) -> bool:
    ts = cache.get("timestamp", 0)
    return (time.time() - ts) < CACHE_MAX_AGE


# ─────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────

def fetch_mission_name() -> str | None:
    """
    Scrape the SCUL mission control page and return the mission name.
    Returns None on failure.

    SCUL's mission control page typically has the mission name in an <h1>
    or prominent heading. We try a few selectors in order of confidence.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; pi-matrix-display/1.0)"}
        resp = requests.get(SCUL_URL, timeout=FETCH_TIMEOUT, headers=headers)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[SCUL] Fetch failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try selectors in priority order — adjust if the page structure changes
    selectors = [
        ("h1", {}),                          # most likely — main page heading
        ("h2", {}),                          # fallback heading
        (".mission-name", {}),               # possible CSS class
        (".mission_name", {}),
        ("#mission-name", {}),
        ("title", {}),                       # last resort: page title
    ]

    for tag, attrs in selectors:
        el = soup.find(tag, attrs) if attrs else soup.find(tag)
        if el:
            text = el.get_text(strip=True)
            if text and len(text) > 2:
                print(f"[SCUL] Found mission name via <{tag}>: {text!r}")
                return text

    print("[SCUL] Could not locate mission name in page.")
    # Debug: print first 500 chars of body so you can adjust selectors
    body = soup.get_text()[:500]
    print(f"[SCUL] Page preview:\n{body}")
    return None


# ─────────────────────────────────────────────
# GET MISSION (cache-aware)
# ─────────────────────────────────────────────

def get_mission_name(force_refresh: bool = False) -> str:
    """
    Return the current mission name, using cache when fresh.
    Falls back to stale cache or a placeholder if the fetch fails.
    """
    cache = load_cache()

    if not force_refresh and cache_is_fresh(cache) and "mission" in cache:
        print(f"[SCUL] Using cached mission: {cache['mission']!r}")
        return cache["mission"]

    print("[SCUL] Fetching fresh mission name...")
    name = fetch_mission_name()

    if name:
        save_cache({"mission": name, "timestamp": time.time()})
        return name

    # Fetch failed — use stale cache if we have it
    if "mission" in cache:
        print(f"[SCUL] Using stale cache: {cache['mission']!r}")
        return cache["mission"]

    # Total fallback
    return "SCUL MISSION UNKNOWN"


# ─────────────────────────────────────────────
# TEXT → IMAGE
# ─────────────────────────────────────────────

def render_text_banner(text: str) -> Image.Image:
    """
    Render text into a wide Image that can be scrolled across the matrix.
    Returns an RGB image exactly MATRIX_HEIGHT pixels tall.
    """
    # Load font — fall back to default bitmap font if path missing
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except (IOError, OSError):
        print("[SCUL] TrueType font not found, using default bitmap font.")
        font = ImageFont.load_default()

    # Measure text width
    dummy = Image.new("RGB", (1, 1))
    draw  = ImageDraw.Draw(dummy)
    bbox  = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Total banner width: padding + text + padding (so it fully scrolls off)
    total_w = SCROLL_PADDING + text_w + MATRIX_WIDTH

    banner = Image.new("RGB", (total_w, MATRIX_HEIGHT), BG_COLOR)
    draw   = ImageDraw.Draw(banner)

    # Vertically center the text
    y = (MATRIX_HEIGHT - text_h) // 2 - bbox[1]  # adjust for font descender offset
    draw.text((SCROLL_PADDING, y), text, font=font, fill=TEXT_COLOR)

    return banner


# ─────────────────────────────────────────────
# SCROLL ON MATRIX
# ─────────────────────────────────────────────

def scroll_mission_name(matrix, text: str, speed: float = SCROLL_SPEED):
    """
    Scroll the mission name text across the matrix once.
    Pass in your RGBMatrix instance.
    """
    banner = render_text_banner(text)
    canvas = matrix.CreateFrameCanvas()
    total_steps = banner.width - MATRIX_WIDTH

    for step in range(total_steps):
        crop = banner.crop((step, 0, step + MATRIX_WIDTH, MATRIX_HEIGHT))
        canvas.SetImage(crop)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(speed)


# ─────────────────────────────────────────────
# STANDALONE TEST (no matrix hardware needed)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=== SCUL Mission Scraper Test ===")
    name = get_mission_name(force_refresh="--refresh" in sys.argv)
    print(f"Mission name: {name!r}")

    # Save a preview image you can inspect on your desktop
    banner = render_text_banner(name)
    out = "scul_preview.png"
    banner.save(out)
    print(f"Banner saved to {out}  ({banner.width}x{banner.height}px)")
    print("(Copy to your desktop and open to verify font/color before running on matrix)")