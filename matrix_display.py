#!/usr/bin/env python3
"""
32x32 RGB Matrix Display Manager
Supports: static images, scrolling images, animated GIFs, and SCUL mission name scroll.
Requires: rpi-rgb-led-matrix, Pillow, requests, beautifulsoup4
"""

import os
import time
import random
import json
import signal
import sys
from pathlib import Path
from PIL import Image, ImageSequence
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from scul_mission import get_mission_name, scroll_mission_name

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

MATRIX_WIDTH  = 32
MATRIX_HEIGHT = 32
IMAGE_FOLDER  = "./images"          # Folder containing your images/gifs
CONFIG_FILE   = "./display_config.json"  # Optional per-image config

# Default display timings
DEFAULT_STATIC_DURATION  = 8.0    # seconds to show a static image
DEFAULT_SCROLL_SPEED     = 0.03   # seconds between scroll steps
DEFAULT_GIF_LOOPS        = 2      # how many times to loop a GIF before moving on
DEFAULT_GIF_FRAME_DELAY  = 0.08   # fallback frame delay if GIF has none

# Supported file types
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
GIF_EXTENSIONS   = {".gif"}

# SCUL mission name scroll
SCUL_ENABLED          = True   # Set False to disable entirely
SCUL_EVERY_N_IMAGES   = 5      # Show mission scroll after every N images


# ─────────────────────────────────────────────
# MATRIX SETUP
# ─────────────────────────────────────────────

def create_matrix() -> RGBMatrix:
    options = RGBMatrixOptions()
    options.rows                 = MATRIX_HEIGHT
    options.cols                 = MATRIX_WIDTH
    options.chain_length         = 1
    options.parallel             = 1
    options.hardware_mapping     = "adafruit-hat"  # Change to "regular" if not using Adafruit HAT
    options.brightness           = 80              # 0–100
    options.gpio_slowdown        = 2               # Increase to 3-4 if you see flickering
    options.drop_privileges      = True
    return RGBMatrix(options=options)


# ─────────────────────────────────────────────
# CONFIG LOADER
# ─────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """
    Load optional per-image config from JSON.

    Example config format:
    {
        "sunset.png":    { "mode": "scroll",  "direction": "left", "speed": 0.04 },
        "logo.png":      { "mode": "static",  "duration": 10 },
        "sparkle.gif":   { "mode": "gif",     "loops": 3 },
        "banner.jpg":    { "mode": "scroll",  "direction": "up",   "duration": 12 }
    }
    Modes: "static" | "scroll" | "gif"
    Directions (scroll): "left" | "right" | "up" | "down"
    """
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# IMAGE HELPERS
# ─────────────────────────────────────────────

def fit_to_matrix(img: Image.Image) -> Image.Image:
    """Resize image to fit within matrix dimensions, preserving aspect ratio."""
    img = img.convert("RGB")
    img.thumbnail((MATRIX_WIDTH, MATRIX_HEIGHT), Image.LANCZOS)
    # Pad to exact matrix size with black background
    canvas = Image.new("RGB", (MATRIX_WIDTH, MATRIX_HEIGHT), (0, 0, 0))
    x = (MATRIX_WIDTH  - img.width)  // 2
    y = (MATRIX_HEIGHT - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def prepare_scroll_image(img: Image.Image, direction: str) -> Image.Image:
    """
    For scrolling: resize so the image fills the scroll axis fully
    while the cross-axis fits in the matrix.
    """
    img = img.convert("RGB")
    if direction in ("left", "right"):
        # Height must match matrix; width can be anything
        ratio  = MATRIX_HEIGHT / img.height
        new_w  = max(int(img.width * ratio), MATRIX_WIDTH + 1)
        img    = img.resize((new_w, MATRIX_HEIGHT), Image.LANCZOS)
    else:  # up / down
        ratio  = MATRIX_WIDTH / img.width
        new_h  = max(int(img.height * ratio), MATRIX_HEIGHT + 1)
        img    = img.resize((MATRIX_WIDTH, new_h), Image.LANCZOS)
    return img


# ─────────────────────────────────────────────
# DISPLAY MODES
# ─────────────────────────────────────────────

def display_static(matrix: RGBMatrix, img: Image.Image, duration: float):
    """Show a static image for a fixed duration."""
    frame = fit_to_matrix(img)
    canvas = matrix.CreateFrameCanvas()
    canvas.SetImage(frame)
    matrix.SwapOnVSync(canvas)
    time.sleep(duration)


def display_scroll(matrix: RGBMatrix, img: Image.Image,
                   direction: str = "left", speed: float = DEFAULT_SCROLL_SPEED,
                   duration: float = None):
    """
    Scroll an image across the matrix.
    If duration is set, scroll for that many seconds.
    Otherwise scroll through the whole image once.
    """
    scrollable = prepare_scroll_image(img, direction)
    canvas     = matrix.CreateFrameCanvas()
    start_time = time.time()

    if direction == "left":
        total_steps = scrollable.width - MATRIX_WIDTH
        for step in range(total_steps):
            if duration and (time.time() - start_time) >= duration:
                break
            crop = scrollable.crop((step, 0, step + MATRIX_WIDTH, MATRIX_HEIGHT))
            canvas.SetImage(crop)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(speed)

    elif direction == "right":
        total_steps = scrollable.width - MATRIX_WIDTH
        for step in range(total_steps - 1, -1, -1):
            if duration and (time.time() - start_time) >= duration:
                break
            crop = scrollable.crop((step, 0, step + MATRIX_WIDTH, MATRIX_HEIGHT))
            canvas.SetImage(crop)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(speed)

    elif direction == "up":
        total_steps = scrollable.height - MATRIX_HEIGHT
        for step in range(total_steps):
            if duration and (time.time() - start_time) >= duration:
                break
            crop = scrollable.crop((0, step, MATRIX_WIDTH, step + MATRIX_HEIGHT))
            canvas.SetImage(crop)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(speed)

    elif direction == "down":
        total_steps = scrollable.height - MATRIX_HEIGHT
        for step in range(total_steps - 1, -1, -1):
            if duration and (time.time() - start_time) >= duration:
                break
            crop = scrollable.crop((0, step, MATRIX_WIDTH, step + MATRIX_HEIGHT))
            canvas.SetImage(crop)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(speed)


def display_gif(matrix: RGBMatrix, img: Image.Image, loops: int = DEFAULT_GIF_LOOPS):
    """Play an animated GIF. Short GIFs automatically loop more times."""
    frames = []
    delays = []

    for frame in ImageSequence.Iterator(img):
        rgb_frame = frame.convert("RGB").resize(
            (MATRIX_WIDTH, MATRIX_HEIGHT), Image.LANCZOS
        )
        frames.append(rgb_frame)
        delay = frame.info.get("duration", int(DEFAULT_GIF_FRAME_DELAY * 1000)) / 1000.0
        delays.append(delay)

    if not frames:
        return

    # Auto-boost loops for short GIFs so they don't just flash by
    total_duration = sum(delays)
    if total_duration < 2.0:
        loops = max(loops, 8)   # very short — loop lots
    elif total_duration < 5.0:
        loops = max(loops, 4)   # medium short — loop a few times

    print(f"[GIF] {len(frames)} frames, {total_duration:.1f}s total, looping {loops}x")

    canvas = matrix.CreateFrameCanvas()
    for _ in range(loops):
        for frame, delay in zip(frames, delays):
            canvas.SetImage(frame)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(delay)


# ─────────────────────────────────────────────
# FILE SCANNER
# ─────────────────────────────────────────────

def scan_images(folder: str) -> list:
    """Return a list of all supported image/gif paths in the folder."""
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"[ERROR] Image folder not found: {folder}")
        sys.exit(1)

    files = []
    for ext in IMAGE_EXTENSIONS | GIF_EXTENSIONS:
        files.extend(folder_path.glob(f"*{ext}"))
        files.extend(folder_path.glob(f"*{ext.upper()}"))

    if not files:
        print(f"[WARN] No images found in {folder}")
    return list(set(files))  # deduplicate


# ─────────────────────────────────────────────
# DISPLAY DISPATCHER
# ─────────────────────────────────────────────

def display_file(matrix: RGBMatrix, filepath: Path, config: dict):
    """Determine display mode and show the file."""
    name      = filepath.name
    file_cfg  = config.get(name, {})
    ext       = filepath.suffix.lower()
    is_gif    = ext in GIF_EXTENSIONS

    try:
        img = Image.open(str(filepath))
    except Exception as e:
        print(f"[WARN] Could not open {name}: {e}")
        return

    # Determine mode
    if "mode" in file_cfg:
        mode = file_cfg["mode"]
    elif is_gif:
        mode = "gif"
    else:
        # If image is wider or taller than matrix, default to scroll
        if img.width > MATRIX_WIDTH * 1.5 or img.height > MATRIX_HEIGHT * 1.5:
            mode = "scroll"
        else:
            mode = "static"

    print(f"[DISPLAY] {name} → mode={mode}")

    if mode == "static":
        duration = file_cfg.get("duration", DEFAULT_STATIC_DURATION)
        display_static(matrix, img, duration)

    elif mode == "scroll":
        direction = file_cfg.get("direction", "left")
        speed     = file_cfg.get("speed", DEFAULT_SCROLL_SPEED)
        duration  = file_cfg.get("duration", None)
        display_scroll(matrix, img, direction=direction, speed=speed, duration=duration)

    elif mode == "gif":
        loops = file_cfg.get("loops", DEFAULT_GIF_LOOPS)
        display_gif(matrix, img, loops=loops)

    else:
        print(f"[WARN] Unknown mode '{mode}' for {name}, showing as static.")
        display_static(matrix, img, DEFAULT_STATIC_DURATION)


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

running = True

def handle_signal(sig, frame):
    global running
    print("\n[INFO] Signal received, shutting down...")
    running = False

signal.signal(signal.SIGINT,  handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def main():
    global running

    print("[INFO] Starting RGB Matrix Display Manager")
    matrix = create_matrix()
    config = load_config(CONFIG_FILE)
    files  = scan_images(IMAGE_FOLDER)

    if not files:
        print("[ERROR] No displayable files found. Exiting.")
        sys.exit(1)

    # Shuffle on first run
    random.shuffle(files)
    index             = 0
    images_since_scul = 0

    # Pre-fetch mission name at startup (uses cache if fresh)
    mission_name = None
    if SCUL_ENABLED:
        mission_name = get_mission_name()

    print(f"[INFO] Found {len(files)} file(s). Starting display loop.")

    while running:
        # ── SCUL mission scroll ──────────────────────────────────────
        if SCUL_ENABLED and images_since_scul >= SCUL_EVERY_N_IMAGES:
            # get_mission_name() uses cache; only hits network when >24h old
            mission_name = get_mission_name()
            if mission_name and running:
                print(f"[INFO] Scrolling SCUL mission: {mission_name!r}")
                scroll_mission_name(matrix, mission_name)
            images_since_scul = 0

        # ── Next image ───────────────────────────────────────────────
        if not running:
            break

        filepath = files[index]
        display_file(matrix, filepath, config)
        images_since_scul += 1

        index += 1
        if index >= len(files):
            # Re-shuffle when we've gone through all images
            random.shuffle(files)
            index = 0

    # Clear matrix on exit
    matrix.Clear()
    print("[INFO] Matrix cleared. Goodbye.")


if __name__ == "__main__":
    main()