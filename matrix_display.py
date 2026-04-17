#!/usr/bin/env python3
"""
32x32 RGB Matrix Display Manager
Supports: static images, scrolling images, animated GIFs, SCUL mission scroll,
          and live control via control.json (written by the web control panel).
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
IMAGE_FOLDER  = "./images"
CONFIG_FILE   = "./display_config.json"
CONTROL_FILE  = "./control.json"

DEFAULT_BRIGHTNESS       = 80
DEFAULT_STATIC_DURATION  = 8.0
DEFAULT_SCROLL_SPEED     = 0.03
DEFAULT_GIF_LOOPS        = 2
DEFAULT_GIF_FRAME_DELAY  = 0.08

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
GIF_EXTENSIONS   = {".gif"}

SCUL_ENABLED        = True
SCUL_EVERY_N_IMAGES = 5


# ─────────────────────────────────────────────
# CONTROL FILE
# ─────────────────────────────────────────────

DEFAULT_CONTROL = {
    "brightness":      DEFAULT_BRIGHTNESS,
    "scroll_speed":    DEFAULT_SCROLL_SPEED,
    "static_duration": DEFAULT_STATIC_DURATION,
    "gif_loops":       DEFAULT_GIF_LOOPS,
    "skip":            False,
    "message":         "",
    "message_color":   [255, 200, 0],
    "paused":          False,
}

def read_control() -> dict:
    try:
        with open(CONTROL_FILE) as f:
            data = json.load(f)
            for k, v in DEFAULT_CONTROL.items():
                data.setdefault(k, v)
            return data
    except Exception:
        return dict(DEFAULT_CONTROL)

def clear_flag(key: str):
    ctrl = read_control()
    ctrl[key] = False if key != "message" else ""
    with open(CONTROL_FILE, "w") as f:
        json.dump(ctrl, f, indent=2)


# ─────────────────────────────────────────────
# MATRIX SETUP
# ─────────────────────────────────────────────

def create_matrix(brightness: int = DEFAULT_BRIGHTNESS) -> RGBMatrix:
    options = RGBMatrixOptions()
    options.rows             = MATRIX_HEIGHT
    options.cols             = MATRIX_WIDTH
    options.chain_length     = 1
    options.parallel         = 1
    options.hardware_mapping = "adafruit-hat"
    options.brightness       = brightness
    options.gpio_slowdown    = 2
    options.drop_privileges  = True
    return RGBMatrix(options=options)


# ─────────────────────────────────────────────
# CONFIG LOADER
# ─────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


# ─────────────────────────────────────────────
# IMAGE HELPERS
# ─────────────────────────────────────────────

def fit_to_matrix(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    img.thumbnail((MATRIX_WIDTH, MATRIX_HEIGHT), Image.LANCZOS)
    canvas = Image.new("RGB", (MATRIX_WIDTH, MATRIX_HEIGHT), (0, 0, 0))
    x = (MATRIX_WIDTH  - img.width)  // 2
    y = (MATRIX_HEIGHT - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def prepare_scroll_image(img: Image.Image, direction: str) -> Image.Image:
    img = img.convert("RGB")
    if direction in ("left", "right"):
        ratio = MATRIX_HEIGHT / img.height
        new_w = max(int(img.width * ratio), MATRIX_WIDTH + 1)
        img   = img.resize((new_w, MATRIX_HEIGHT), Image.LANCZOS)
    else:
        ratio = MATRIX_WIDTH / img.width
        new_h = max(int(img.height * ratio), MATRIX_HEIGHT + 1)
        img   = img.resize((MATRIX_WIDTH, new_h), Image.LANCZOS)
    return img


# ─────────────────────────────────────────────
# DISPLAY MODES
# ─────────────────────────────────────────────

def should_interrupt() -> bool:
    ctrl = read_control()
    return ctrl["skip"] or bool(ctrl["message"]) or not running

def display_static(matrix: RGBMatrix, img: Image.Image, duration: float):
    frame  = fit_to_matrix(img)
    canvas = matrix.CreateFrameCanvas()
    canvas.SetImage(frame)
    matrix.SwapOnVSync(canvas)
    deadline = time.time() + duration
    while time.time() < deadline:
        if should_interrupt():
            return
        ctrl = read_control()
        if ctrl["paused"]:
            time.sleep(0.2)
            continue
        time.sleep(0.2)


def display_scroll(matrix: RGBMatrix, img: Image.Image,
                   direction: str = "left", speed: float = DEFAULT_SCROLL_SPEED,
                   duration: float = None):
    scrollable = prepare_scroll_image(img, direction)
    canvas     = matrix.CreateFrameCanvas()
    start_time = time.time()

    if direction in ("left", "right"):
        total_steps = scrollable.width - MATRIX_WIDTH
        step_range  = range(total_steps) if direction == "left" else range(total_steps - 1, -1, -1)
    else:
        total_steps = scrollable.height - MATRIX_HEIGHT
        step_range  = range(total_steps) if direction == "up" else range(total_steps - 1, -1, -1)

    for step in step_range:
        if should_interrupt():
            return
        ctrl = read_control()
        if ctrl["paused"]:
            time.sleep(0.2)
            continue
        if duration and (time.time() - start_time) >= duration:
            break
        if direction in ("left", "right"):
            crop = scrollable.crop((step, 0, step + MATRIX_WIDTH, MATRIX_HEIGHT))
        else:
            crop = scrollable.crop((0, step, MATRIX_WIDTH, step + MATRIX_HEIGHT))
        canvas.SetImage(crop)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(ctrl.get("scroll_speed", speed))


def display_gif(matrix: RGBMatrix, img: Image.Image, loops: int = DEFAULT_GIF_LOOPS):
    frames, delays = [], []
    for frame in ImageSequence.Iterator(img):
        frames.append(frame.convert("RGB").resize((MATRIX_WIDTH, MATRIX_HEIGHT), Image.LANCZOS))
        delays.append(frame.info.get("duration", int(DEFAULT_GIF_FRAME_DELAY * 1000)) / 1000.0)
    if not frames:
        return
    total_duration = sum(delays)
    if total_duration < 2.0:
        loops = max(loops, 8)
    elif total_duration < 5.0:
        loops = max(loops, 4)
    canvas = matrix.CreateFrameCanvas()
    for _ in range(loops):
        for frame, delay in zip(frames, delays):
            if should_interrupt():
                return
            ctrl = read_control()
            if ctrl["paused"]:
                time.sleep(0.2)
                continue
            canvas.SetImage(frame)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(delay)


# ─────────────────────────────────────────────
# CUSTOM MESSAGE SCROLL
# ─────────────────────────────────────────────

def display_message(matrix: RGBMatrix, text: str, color: list):
    from scul_mission import render_text_banner, SCROLL_SPEED
    import scul_mission as sm
    orig = sm.TEXT_COLOR
    sm.TEXT_COLOR = tuple(color)
    banner = render_text_banner(text)
    sm.TEXT_COLOR = orig

    canvas      = matrix.CreateFrameCanvas()
    total_steps = banner.width - MATRIX_WIDTH
    ctrl        = read_control()
    speed       = ctrl.get("scroll_speed", SCROLL_SPEED)

    for step in range(total_steps):
        if not running:
            break
        crop = banner.crop((step, 0, step + MATRIX_WIDTH, MATRIX_HEIGHT))
        canvas.SetImage(crop)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(speed)

    clear_flag("message")


# ─────────────────────────────────────────────
# FILE SCANNER & DISPATCHER
# ─────────────────────────────────────────────

def scan_images(folder: str) -> list:
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"[ERROR] Image folder not found: {folder}")
        sys.exit(1)
    files = []
    for ext in IMAGE_EXTENSIONS | GIF_EXTENSIONS:
        files.extend(folder_path.glob(f"*{ext}"))
        files.extend(folder_path.glob(f"*{ext.upper()}"))
    return list(set(files))


def display_file(matrix: RGBMatrix, filepath: Path, config: dict):
    ctrl     = read_control()
    name     = filepath.name
    file_cfg = config.get(name, {})
    ext      = filepath.suffix.lower()
    is_gif   = ext in GIF_EXTENSIONS

    try:
        img = Image.open(str(filepath))
    except Exception as e:
        print(f"[WARN] Could not open {name}: {e}")
        return

    if "mode" in file_cfg:
        mode = file_cfg["mode"]
    elif is_gif:
        mode = "gif"
    elif img.width > MATRIX_WIDTH * 1.5 or img.height > MATRIX_HEIGHT * 1.5:
        mode = "scroll"
    else:
        mode = "static"

    print(f"[DISPLAY] {name} → mode={mode}")

    if mode == "static":
        duration = file_cfg.get("duration", ctrl.get("static_duration", DEFAULT_STATIC_DURATION))
        display_static(matrix, img, duration)
    elif mode == "scroll":
        direction = file_cfg.get("direction", "left")
        speed     = file_cfg.get("speed", ctrl.get("scroll_speed", DEFAULT_SCROLL_SPEED))
        duration  = file_cfg.get("duration", None)
        display_scroll(matrix, img, direction=direction, speed=speed, duration=duration)
    elif mode == "gif":
        loops = file_cfg.get("loops", ctrl.get("gif_loops", DEFAULT_GIF_LOOPS))
        display_gif(matrix, img, loops=loops)
    else:
        display_static(matrix, img, ctrl.get("static_duration", DEFAULT_STATIC_DURATION))


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
    ctrl   = read_control()
    matrix = create_matrix(brightness=ctrl.get("brightness", DEFAULT_BRIGHTNESS))
    config = load_config(CONFIG_FILE)
    files  = scan_images(IMAGE_FOLDER)

    if not files:
        print("[ERROR] No displayable files found. Exiting.")
        sys.exit(1)

    random.shuffle(files)
    index             = 0
    images_since_scul = 0
    last_brightness   = ctrl.get("brightness", DEFAULT_BRIGHTNESS)
    mission_name      = get_mission_name() if SCUL_ENABLED else None

    print(f"[INFO] Found {len(files)} file(s). Starting display loop.")

    while running:
        ctrl = read_control()

        # Brightness change
        new_brightness = ctrl.get("brightness", DEFAULT_BRIGHTNESS)
        if new_brightness != last_brightness:
            print(f"[INFO] Brightness → {new_brightness}")
            matrix.Clear()
            matrix = create_matrix(brightness=new_brightness)
            last_brightness = new_brightness

        # Custom message takes priority
        if ctrl.get("message"):
            print(f"[INFO] Message: {ctrl['message']!r}")
            display_message(matrix, ctrl["message"], ctrl.get("message_color", [255, 200, 0]))
            continue

        # Paused
        if ctrl.get("paused"):
            time.sleep(0.2)
            continue

        # Skip
        if ctrl.get("skip"):
            print("[INFO] Skip.")
            clear_flag("skip")
            index = (index + 1) % len(files)
            continue

        # SCUL scroll
        if SCUL_ENABLED and images_since_scul >= SCUL_EVERY_N_IMAGES:
            mission_name = get_mission_name()
            if mission_name and running:
                scroll_mission_name(matrix, mission_name)
            images_since_scul = 0

        if not running:
            break

        # Rescan folder on each cycle to pick up new Drive syncs
        if index == 0:
            new_files = scan_images(IMAGE_FOLDER)
            if new_files:
                files = new_files
                random.shuffle(files)

        display_file(matrix, files[index], config)
        images_since_scul += 1
        index = (index + 1) % len(files)

    matrix.Clear()
    print("[INFO] Matrix cleared. Goodbye.")


if __name__ == "__main__":
    main()