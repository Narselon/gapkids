#!/usr/bin/env python3
"""
control_server.py — Web control panel for the GapKids Pi matrix display.
Access from any device on the same network: http://gapkids.local:8080

Controls:
  - Brightness slider
  - Scroll speed slider
  - Static image duration slider
  - GIF loop count
  - Pause / Resume
  - Skip current image
  - Send a custom scrolling message (with color picker)
  - Reboot / Shut down

Run on boot via cron:
    @reboot sudo python3 /home/narselon/gapkids/gapkids/shutdown_server.py &
"""

import http.server
import subprocess
import json
import os
import urllib.parse

PORT        = 8080
PASSWORD    = ""       # Change this
CONTROL_FILE = "/home/narselon/gapkids/gapkids/control.json"

DEFAULT_CONTROL = {
    "brightness":      80,
    "scroll_speed":    0.03,
    "static_duration": 8.0,
    "gif_loops":       2,
    "skip":            False,
    "message":         "",
    "message_color":   [255, 200, 0],
    "paused":          False,
}

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GapKids Pi Control</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    background: #111;
    color: #eee;
    padding: 1.2em;
    max-width: 480px;
    margin: auto;
  }
  h1 { font-size: 1.3em; margin-bottom: 1em; text-align: center; letter-spacing: 0.05em; }
  h2 { font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.1em; color: #888; margin: 1.2em 0 0.5em; }
  .card {
    background: #1e1e1e;
    border-radius: 12px;
    padding: 1em;
    margin-bottom: 0.8em;
  }
  label { display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 0.3em; }
  input[type=range] { width: 100%; accent-color: #f0a500; }
  input[type=text], input[type=password] {
    width: 100%;
    padding: 0.6em;
    border-radius: 8px;
    border: 1px solid #333;
    background: #2a2a2a;
    color: #eee;
    font-size: 0.95em;
    margin-top: 0.3em;
  }
  .row { display: flex; gap: 0.5em; margin-top: 0.6em; flex-wrap: wrap; }
  button {
    flex: 1;
    padding: 0.75em 0.5em;
    border: none;
    border-radius: 10px;
    font-size: 0.95em;
    font-weight: 600;
    cursor: pointer;
    min-width: 80px;
  }
  .btn-primary  { background: #f0a500; color: #111; }
  .btn-pause    { background: #3a7bd5; color: #fff; }
  .btn-skip     { background: #555;    color: #fff; }
  .btn-reboot   { background: #c47a00; color: #fff; }
  .btn-shutdown { background: #c0392b; color: #fff; }
  .btn-send     { background: #27ae60; color: #fff; }
  #status { margin-top: 1em; font-size: 0.85em; color: #aaa; text-align: center; min-height: 1.5em; }
  .color-row { display: flex; align-items: center; gap: 0.6em; margin-top: 0.5em; }
  input[type=color] { width: 44px; height: 36px; border: none; border-radius: 6px; cursor: pointer; background: none; }
  #pw-section { margin-bottom: 1em; }
</style>
</head>
<body>
<h1>🖥️ GapKids Pi</h1>

<div class="card">
  <h2>Brightness</h2>
  <label>Level <span id="bright-val">80</span>%</label>
  <input type="range" id="brightness" min="10" max="100" value="80"
         oninput="document.getElementById('bright-val').innerText=this.value"
         onchange="setSetting('brightness', parseInt(this.value))">
</div>

<div class="card">
  <h2>Scroll Speed</h2>
  <label>Delay <span id="speed-val">0.03</span>s per step (lower = faster)</label>
  <input type="range" id="scroll_speed" min="1" max="20" value="3"
         oninput="document.getElementById('speed-val').innerText=(this.value/100).toFixed(2)"
         onchange="setSetting('scroll_speed', this.value/100)">
</div>

<div class="card">
  <h2>Static Image Duration</h2>
  <label>Show each image for <span id="dur-val">8</span>s</label>
  <input type="range" id="static_duration" min="2" max="60" value="8"
         oninput="document.getElementById('dur-val').innerText=this.value"
         onchange="setSetting('static_duration', parseInt(this.value))">
</div>

<div class="card">
  <h2>GIF Loops</h2>
  <label>Loop count <span id="loop-val">2</span>x (auto-boosts short GIFs)</label>
  <input type="range" id="gif_loops" min="1" max="10" value="2"
         oninput="document.getElementById('loop-val').innerText=this.value"
         onchange="setSetting('gif_loops', parseInt(this.value))">
</div>

<div class="card">
  <h2>Playback</h2>
  <div class="row">
    <button class="btn-pause"  onclick="togglePause()">⏸ Pause</button>
    <button class="btn-skip"   onclick="doSkip()">⏭ Skip</button>
  </div>
  <div class="row" style="margin-top:0.5em">
    <button class="btn-send"     onclick="displayCmd('start')">▶ Start Display</button>
    <button class="btn-shutdown" onclick="displayCmd('stop')">■ Stop Display</button>
  </div>
</div>

<div class="card">
  <h2>Send Message</h2>
  <input type="text" id="msg-text" placeholder="Type a message to scroll...">
  <div class="color-row">
    <span style="font-size:0.85em">Color:</span>
    <input type="color" id="msg-color" value="#ffc800">
    <button class="btn-send" onclick="sendMessage()">▶ Send</button>
  </div>
</div>

<div class="card">
  <h2>System</h2>
  <div class="row">
    <button class="btn-reboot"   onclick="sysCmd('reboot')">↺ Reboot</button>
    <button class="btn-shutdown" onclick="sysCmd('shutdown')">⏻ Shut Down</button>
  </div>
</div>

<div id="status"></div>

<script>
function pw() { return ""; }
function msg(t) { document.getElementById('status').innerText = t; }

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return [r,g,b];
}

function api(path, body) {
  const url = path + '?pw=' + encodeURIComponent(pw());
  const opts = body
    ? { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) }
    : {};
  return fetch(url, opts).then(r => r.json()).catch(e => ({ error: e.toString() }));
}

function setSetting(key, value) {
  api('/set', { [key]: value }).then(r => msg(r.ok ? '✓ ' + key + ' updated' : '✗ ' + (r.error||'failed')));
}

function togglePause() {
  api('/toggle_pause').then(r => {
    if (r.ok) {
      document.querySelector('.btn-pause').innerText = r.paused ? '▶ Resume' : '⏸ Pause';
      msg(r.paused ? 'Paused' : 'Resumed');
    }
  });
}

function doSkip() {
  api('/skip').then(r => msg(r.ok ? '⏭ Skipped' : '✗ failed'));
}

function sendMessage() {
  const text  = document.getElementById('msg-text').value.trim();
  const color = hexToRgb(document.getElementById('msg-color').value);
  if (!text) { msg('Enter a message first.'); return; }
  api('/set', { message: text, message_color: color }).then(r => {
    msg(r.ok ? '✓ Message sent!' : '✗ ' + (r.error||'failed'));
    if (r.ok) document.getElementById('msg-text').value = '';
  });
}

function sysCmd(cmd) {
  if (!confirm('Really ' + cmd + '?')) return;
  api('/' + cmd).then(r => msg(r.message || '✗ failed'));
}

function loadState() {
  api('/state').then(r => {
    if (r.error || !r.brightness) { 
      document.getElementById('auth-status').innerText = pw() ? ' ✗' : '';
      return;
    }
    document.getElementById('auth-status').innerText = ' ✓';
    document.getElementById('brightness').value    = r.brightness;
    document.getElementById('bright-val').innerText = r.brightness;
    const spd = Math.round(r.scroll_speed * 100);
    document.getElementById('scroll_speed').value  = spd;
    document.getElementById('speed-val').innerText = r.scroll_speed.toFixed(2);
    document.getElementById('static_duration').value = r.static_duration;
    document.getElementById('dur-val').innerText   = r.static_duration;
    document.getElementById('gif_loops').value     = r.gif_loops;
    document.getElementById('loop-val').innerText  = r.gif_loops;
    document.querySelector('.btn-pause').innerText = r.paused ? '▶ Resume' : '⏸ Pause';
  });
}

function displayCmd(action) {
  fetch('/display?action=' + action)
    .then(r => r.json())
    .then(r => msg(r.message || (r.ok ? '✓ Done' : '✗ failed')));
}

loadState();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────
# CONTROL FILE HELPERS
# ─────────────────────────────────────────────

def read_control() -> dict:
    try:
        with open(CONTROL_FILE) as f:
            data = json.load(f)
            for k, v in DEFAULT_CONTROL.items():
                data.setdefault(k, v)
            return data
    except Exception:
        return dict(DEFAULT_CONTROL)


def write_control(data: dict):
    with open(CONTROL_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
# REQUEST HANDLER
# ─────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_html(self):
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def check_pw(self, qs: dict) -> bool:
        return True

    def parse_request_path(self):
        parsed = urllib.parse.urlparse(self.path)
        qs     = urllib.parse.parse_qs(parsed.query)
        return parsed.path, qs

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_GET(self):
        path, qs = self.parse_request_path()

        if path in ("/", "/index.html"):
            self.serve_html()
            return

        if not self.check_pw(qs):
            self.send_json({"error": "wrong password"}, 403)
            return

        if path == "/state":
            self.send_json(read_control())

        elif path == "/toggle_pause":
            ctrl = read_control()
            ctrl["paused"] = not ctrl["paused"]
            write_control(ctrl)
            self.send_json({"ok": True, "paused": ctrl["paused"]})

        elif path == "/skip":
            ctrl = read_control()
            ctrl["skip"] = True
            write_control(ctrl)
            self.send_json({"ok": True})
        
        elif path == "/display":
            action = qs.get("action", [""])[0]
            if action == "stop":
                subprocess.Popen(["pkill", "-f", "matrix_display.py"])
                self.send_json({"ok": True, "message": "Display stopped."})
            elif action == "start":
                subprocess.Popen([
                    "/usr/bin/python3",
                    "/home/narselon/gapkids/gapkids/matrix_display.py"
                ])
                self.send_json({"ok": True, "message": "Display starting..."})
            else:
                self.send_json({"error": "unknown action"}, 400)

        elif path == "/reboot":
            self.send_json({"ok": True, "message": "Rebooting in 3s..."})
            subprocess.Popen(["sudo", "reboot"])

        elif path == "/shutdown":
            self.send_json({"ok": True, "message": "Shutting down. Safe to unplug."})
            subprocess.Popen(["sudo", "shutdown", "now"])

        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path, qs = self.parse_request_path()

        if not self.check_pw(qs):
            self.send_json({"error": "wrong password"}, 403)
            return

        if path == "/set":
            body = self.read_body()
            ctrl = read_control()
            for key in ("brightness", "scroll_speed", "static_duration",
                        "gif_loops", "message", "message_color", "paused", "skip"):
                if key in body:
                    ctrl[key] = body[key]
            write_control(ctrl)
            self.send_json({"ok": True})
        else:
            self.send_json({"error": "not found"}, 404)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Write default control file if missing
    if not os.path.exists(CONTROL_FILE):
        write_control(DEFAULT_CONTROL)

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[Control Server] http://gapkids.local:{PORT}")
    server.serve_forever()