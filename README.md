# RGB Matrix Display Manager
### 32×32 LED Array · Raspberry Pi 3 · Adafruit RGB Matrix HAT

---

## Hardware Assumptions
- Raspberry Pi 3 (any variant)
- Adafruit RGB Matrix Bonnet or HAT (or compatible)
- 32×32 HUB75 LED matrix panel
- DS3231 or similar RTC (handled by the OS, not this script)

---

## Installation

### 1. Install the RGB Matrix library
```bash
curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh > rgb-matrix.sh
sudo bash rgb-matrix.sh
# Choose: Adafruit HAT, PWM quality
```

Or build manually:
```bash
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make build-python PYTHON=$(which python3)
sudo make install-python PYTHON=$(which python3)
```

### 2. Install Python dependencies
```bash
pip3 install Pillow
```

### 3. Disable sound (required for matrix timing)
Add to `/boot/config.txt`:
```
dtparam=audio=off
```
Then reboot.

---

## Project Layout
```
your_project/
├── matrix_display.py       # Main script
├── display_config.json     # Per-image settings (optional)
└── images/                 # Put your images/GIFs here
    ├── logo.png
    ├── banner.jpg
    ├── sparkle.gif
    └── ...
```

---

## Running
```bash
sudo python3 matrix_display.py
```
`sudo` is required for GPIO access. Stop with `Ctrl+C` — the matrix will clear cleanly.

### Run on boot (systemd)
```bash
sudo nano /etc/systemd/system/matrix-display.service
```
Paste:
```ini
[Unit]
Description=RGB Matrix Display
After=multi-user.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/your_project/matrix_display.py
WorkingDirectory=/home/pi/your_project
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```
Then:
```bash
sudo systemctl enable matrix-display
sudo systemctl start matrix-display
```

---

## Configuration Reference

Edit the top of `matrix_display.py` to change global defaults:

| Variable | Default | Description |
|---|---|---|
| `IMAGE_FOLDER` | `./images` | Where to look for images |
| `DEFAULT_STATIC_DURATION` | `8.0` | Seconds to show each static image |
| `DEFAULT_SCROLL_SPEED` | `0.03` | Seconds between scroll steps (lower = faster) |
| `DEFAULT_GIF_LOOPS` | `2` | Times to loop each GIF |
| `DEFAULT_GIF_FRAME_DELAY` | `0.08` | Fallback frame delay if GIF has none |

### Per-image overrides (`display_config.json`)

```json
{
    "banner.png":   { "mode": "scroll", "direction": "left", "speed": 0.03 },
    "logo.png":     { "mode": "static", "duration": 10 },
    "anim.gif":     { "mode": "gif",    "loops": 4 },
    "tall.jpg":     { "mode": "scroll", "direction": "up", "duration": 15 }
}
```

**Modes:** `static` · `scroll` · `gif`  
**Scroll directions:** `left` · `right` · `up` · `down`  
**Auto-detection (no config entry):** GIFs → gif mode · Wide/tall images → scroll · Others → static

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Flickering / noise | Increase `gpio_slowdown` to 3 or 4 in `create_matrix()` |
| Wrong colors | Check your panel is HUB75, try `hardware_mapping = "regular"` |
| Permission denied | Run with `sudo` |
| Image looks squished | Adjust `fit_to_matrix()` or resize images before loading |
| GIF too fast/slow | Add a `display_config.json` entry with custom `loops` value |

---

## Image Tips
- **Static:** best at exactly 32×32px, or any square image
- **Scroll horizontal:** make the image 32px tall, any width (wider = longer scroll)
- **Scroll vertical:** make the image 32px wide, any height
- **GIFs:** 32×32 recommended; larger GIFs are resized automatically