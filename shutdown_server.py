#!/usr/bin/env python3
"""
control_server.py - Web control panel for the GapKids Pi matrix display.
Access from any device on the same network: http://gapkids.local:8080
"""

import http.server
import subprocess
import json
import os
import uuid
import urllib.parse
from pathlib import Path

PORT         = 8080
CONTROL_FILE = "/home/narselon/gapkids/gapkids/control.json"
IMAGE_DIR    = "/home/narselon/gapkids/gapkids/images"

DEFAULT_CONTROL = {
    "brightness":      80,
    "scroll_speed":    0.03,
    "static_duration": 8.0,
    "gif_loops":       2,
    "skip":            False,
    "message":         "",
    "message_color":   [255, 200, 0],
    "paused":          False,
    "mode":            "everything",
    "message_queue":   [],
    "queue_loop":      False,
    "queue_index":     0,
}

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}

HTML = (
    '<!DOCTYPE html>'
    '<html lang="en">'
    '<head>'
    '<meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>GapKids Pi</title>'
    '<style>'
    '* { box-sizing: border-box; margin: 0; padding: 0; }'
    'body {'
    '  font-family: -apple-system, BlinkMacSystemFont, sans-serif;'
    '  background: #111; color: #eee;'
    '  padding: 1.2em; max-width: 480px; margin: auto; padding-bottom: 3em;'
    '}'
    'h1 { font-size: 1.3em; margin-bottom: 1em; text-align: center; }'
    'h2 { font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.1em; color: #888; margin: 1.2em 0 0.5em; }'
    '.card { background: #1e1e1e; border-radius: 12px; padding: 1em; margin-bottom: 0.8em; }'
    'label { display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 0.3em; }'
    'input[type=range] { width: 100%; accent-color: #f0a500; }'
    'input[type=text] {'
    '  width: 100%; padding: 0.6em; border-radius: 8px;'
    '  border: 1px solid #333; background: #2a2a2a;'
    '  color: #eee; font-size: 0.95em; margin-top: 0.3em;'
    '}'
    '.row { display: flex; gap: 0.5em; margin-top: 0.6em; flex-wrap: wrap; }'
    'button {'
    '  flex: 1; padding: 0.75em 0.5em; border: none;'
    '  border-radius: 10px; font-size: 0.9em; font-weight: 600;'
    '  cursor: pointer; min-width: 70px;'
    '}'
    '.btn-blue   { background: #3a7bd5; color: #fff; }'
    '.btn-grey   { background: #555;    color: #fff; }'
    '.btn-orange { background: #c47a00; color: #fff; }'
    '.btn-red    { background: #c0392b; color: #fff; }'
    '.btn-green  { background: #27ae60; color: #fff; }'
    '.btn-amber  { background: #f0a500; color: #111; }'
    '.mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5em; margin-top: 0.5em; }'
    '.mode-btn {'
    '  padding: 0.8em 0.4em; border: 2px solid #333;'
    '  border-radius: 10px; background: #2a2a2a;'
    '  color: #aaa; font-size: 0.85em; font-weight: 600;'
    '  cursor: pointer; text-align: center;'
    '}'
    '.mode-btn.active { border-color: #f0a500; color: #f0a500; background: #1a1500; }'
    '.upload-area {'
    '  border: 2px dashed #444; border-radius: 10px;'
    '  padding: 1.2em; text-align: center; cursor: pointer;'
    '  margin-top: 0.5em; color: #888; font-size: 0.9em;'
    '}'
    '.upload-area.drag { border-color: #f0a500; color: #f0a500; }'
    '#file-input { display: none; }'
    '.upload-list { margin-top: 0.6em; font-size: 0.82em; color: #aaa; }'
    '.upload-item { display: flex; justify-content: space-between; padding: 0.3em 0; border-bottom: 1px solid #2a2a2a; }'
    '.upload-del { color: #c0392b; cursor: pointer; font-weight: bold; padding: 0 0.3em; }'
    '.color-row { display: flex; align-items: center; gap: 0.6em; margin-top: 0.5em; }'
    'input[type=color] { width: 44px; height: 36px; border: none; border-radius: 6px; cursor: pointer; }'
    '#status { margin-top: 1em; font-size: 0.85em; color: #aaa; text-align: center; min-height: 1.5em; }'
    '.progress { height: 4px; background: #333; border-radius: 2px; margin-top: 0.5em; display: none; }'
    '.progress-bar { height: 100%; background: #f0a500; border-radius: 2px; width: 0%; }'
    '</style>'
    '</head>'
    '<body>'
    '<h1>GapKids Pi</h1>'

    '<div class="card">'
    '<h2>Display Mode</h2>'
    '<div class="mode-grid">'
    '<button class="mode-btn" id="mode-everything" onclick="setMode(\'everything\')">Everything</button>'
    '<button class="mode-btn" id="mode-text_only" onclick="setMode(\'text_only\')">Text Only</button>'
    '<button class="mode-btn" id="mode-images_only" onclick="setMode(\'images_only\')">Images Only</button>'
    '<button class="mode-btn" id="mode-off" onclick="setMode(\'off\')">Off</button>'
    '</div>'
    '</div>'

    '<div class="card">'
    '<h2>Brightness</h2>'
    '<label>Level <span id="bright-val">80</span>%</label>'
    '<input type="range" id="brightness" min="10" max="100" value="80"'
    ' oninput="document.getElementById(\'bright-val\').innerText=this.value"'
    ' onchange="setSetting(\'brightness\', parseInt(this.value))">'
    '</div>'

    '<div class="card">'
    '<h2>Scroll Speed</h2>'
    '<label>Delay <span id="speed-val">0.03</span>s/step (lower = faster)</label>'
    '<input type="range" id="scroll_speed" min="1" max="20" value="3"'
    ' oninput="document.getElementById(\'speed-val\').innerText=(this.value/100).toFixed(2)"'
    ' onchange="setSetting(\'scroll_speed\', this.value/100)">'
    '</div>'

    '<div class="card">'
    '<h2>Image Duration</h2>'
    '<label>Show each image for <span id="dur-val">8</span>s</label>'
    '<input type="range" id="static_duration" min="2" max="60" value="8"'
    ' oninput="document.getElementById(\'dur-val\').innerText=this.value"'
    ' onchange="setSetting(\'static_duration\', parseInt(this.value))">'
    '</div>'

    '<div class="card">'
    '<h2>GIF Loops</h2>'
    '<label>Loop count <span id="loop-val">2</span>x</label>'
    '<input type="range" id="gif_loops" min="1" max="10" value="2"'
    ' oninput="document.getElementById(\'loop-val\').innerText=this.value"'
    ' onchange="setSetting(\'gif_loops\', parseInt(this.value))">'
    '</div>'

    '<div class="card">'
    '<h2>Playback</h2>'
    '<div class="row">'
    '<button class="btn-blue" id="pause-btn" onclick="togglePause()">Pause</button>'
    '<button class="btn-grey" onclick="doSkip()">Skip</button>'
    '</div>'
    '<div class="row" style="margin-top:0.5em">'
    '<button class="btn-green" onclick="displayCmd(\'start\')">Start</button>'
    '<button class="btn-red" onclick="displayCmd(\'stop\')">Stop</button>'
    '</div>'
    '</div>'

    '<div class="card">'
    '<h2>Send Message</h2>'
    '<input type="text" id="msg-text" placeholder="Type a message to scroll...">'
    '<div class="color-row">'
    '<span style="font-size:0.85em">Color:</span>'
    '<input type="color" id="msg-color" value="#ffc800">'
    '<button class="btn-green" onclick="sendMessage()">Send</button>'
    '</div>'
    '</div>'

    '<div class="card">'
    '<h2>Text Playlist</h2>'
    '<div style="display:flex;gap:0.5em;margin-top:0.3em">'
    '<input type="text" id="q-text" placeholder="Add a message..." style="flex:1">'
    '<input type="color" id="q-color" value="#ffc800" style="width:44px;height:38px;border:none;border-radius:6px;cursor:pointer;flex-shrink:0">'
    '</div>'
    '<div class="row" style="margin-top:0.5em">'
    '<button class="btn-green" onclick="queueAdd()">Add</button>'
    '<button class="btn-blue" onclick="queuePlay()">Play</button>'
    '<button class="btn-grey" onclick="queueStop()">Stop</button>'
    '</div>'
    '<div style="display:flex;align-items:center;gap:0.5em;margin-top:0.6em;font-size:0.85em">'
    '<input type="checkbox" id="q-loop" onchange="queueSetLoop(this.checked)" style="width:16px;height:16px">'
    '<label for="q-loop" style="display:inline;color:#aaa">Loop playlist</label>'
    '</div>'
    '<div id="queue-list" style="margin-top:0.6em;font-size:0.82em;color:#aaa"></div>'
    '</div>'

    '<div class="card">'
    '<h2>Upload Images</h2>'
    '<div class="upload-area" id="drop-zone"'
    ' onclick="document.getElementById(\'file-input\').click()"'
    ' ondragover="event.preventDefault();this.classList.add(\'drag\')"'
    ' ondragleave="this.classList.remove(\'drag\')"'
    ' ondrop="handleDrop(event)">'
    'Tap to choose or drag and drop images here'
    '</div>'
    '<input type="file" id="file-input" multiple accept="image/*,.gif"'
    ' onchange="uploadFiles(this.files)">'
    '<div class="progress"><div class="progress-bar" id="prog-bar"></div></div>'
    '<div class="upload-list" id="upload-list"></div>'
    '</div>'

    '<div class="card">'
    '<h2>System</h2>'
    '<div class="row">'
    '<button class="btn-orange" onclick="sysCmd(\'reboot\')">Reboot</button>'
    '<button class="btn-red" onclick="sysCmd(\'shutdown\')">Shut Down</button>'
    '</div>'
    '</div>'

    '<div id="status"></div>'

    '<script>'
    'function msg(t) {'
    '  document.getElementById("status").innerText = t;'
    '  setTimeout(function(){ document.getElementById("status").innerText=""; }, 4000);'
    '}'
    'function hexToRgb(hex) {'
    '  return [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)];'
    '}'
    'function api(path, body) {'
    '  var opts = body ? { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) } : {};'
    '  return fetch(path, opts).then(function(r){ return r.json(); }).catch(function(e){ return {error:e.toString()}; });'
    '}'
    'function setSetting(key, value) {'
    '  api("/set", { [key]: value }).then(function(r){ msg(r.ok ? "OK" : "Failed"); });'
    '}'
    'function setMode(mode) {'
    '  api("/set", { mode: mode }).then(function(r) {'
    '    if (r.ok) {'
    '      document.querySelectorAll(".mode-btn").forEach(function(b){ b.classList.remove("active"); });'
    '      var mb = document.getElementById("mode-" + mode);'
    '      if (mb) mb.classList.add("active");'
    '      msg("Mode: " + mode.replace("_"," "));'
    '    }'
    '  });'
    '}'
    'function togglePause() {'
    '  api("/toggle_pause").then(function(r) {'
    '    if (r.ok) {'
    '      document.getElementById("pause-btn").innerText = r.paused ? "Resume" : "Pause";'
    '      msg(r.paused ? "Paused" : "Resumed");'
    '    }'
    '  });'
    '}'
    'function doSkip() {'
    '  api("/skip").then(function(r){ msg(r.ok ? "Skipped" : "Failed"); });'
    '}'
    'function sendMessage() {'
    '  var text = document.getElementById("msg-text").value.trim();'
    '  var color = hexToRgb(document.getElementById("msg-color").value);'
    '  if (!text) { msg("Enter a message first."); return; }'
    '  api("/set", { message: text, message_color: color }).then(function(r) {'
    '    if (r.ok) { msg("Message sent!"); document.getElementById("msg-text").value = ""; }'
    '    else msg("Failed: " + (r.error||"unknown"));'
    '  });'
    '}'
    'function sysCmd(cmd) {'
    '  if (!confirm("Really " + cmd + "?")) return;'
    '  api("/" + cmd).then(function(r){ msg(r.message || "Failed"); });'
    '}'
    'function displayCmd(action) {'
    '  api("/display?action=" + action).then(function(r){ msg(r.message || (r.ok ? "Done" : "Failed")); });'
    '}'
    'function handleDrop(e) {'
    '  e.preventDefault();'
    '  document.getElementById("drop-zone").classList.remove("drag");'
    '  uploadFiles(e.dataTransfer.files);'
    '}'
    'function uploadFiles(files) {'
    '  if (!files.length) return;'
    '  var prog = document.querySelector(".progress");'
    '  var bar = document.getElementById("prog-bar");'
    '  prog.style.display = "block"; bar.style.width = "0%";'
    '  var done = 0;'
    '  Array.from(files).forEach(function(file) {'
    '    var fd = new FormData(); fd.append("file", file);'
    '    fetch("/upload", { method:"POST", body:fd })'
    '      .then(function(r){ return r.json(); })'
    '      .then(function(r) {'
    '        done++;'
    '        bar.style.width = (done / files.length * 100) + "%";'
    '        if (r.ok) { msg("Uploaded: " + r.filename); loadImageList(); }'
    '        else msg("Upload failed: " + (r.error||"unknown"));'
    '        if (done === files.length) setTimeout(function(){ prog.style.display="none"; }, 1000);'
    '      })'
    '      .catch(function(){ done++; msg("Upload error"); });'
    '  });'
    '}'
    'function loadImageList() {'
    '  api("/images").then(function(r) {'
    '    var list = document.getElementById("upload-list");'
    '    if (!r.files || !r.files.length) { list.innerHTML = "<div style=\'color:#555;padding:0.3em 0\'>No local uploads yet.</div>"; return; }'
    '    list.innerHTML = r.files.map(function(f) {'
    '      return "<div class=\'upload-item\'><span>" + f + "</span><span class=\'upload-del\' onclick=\'deleteImage(\\\"" + f + "\\\")\'>X</span></div>";'
    '    }).join("");'
    '  });'
    '}'
    'function deleteImage(filename) {'
    '  if (!confirm("Delete " + filename + "?")) return;'
    '  api("/delete_image", { filename: filename }).then(function(r) {'
    '    msg(r.ok ? "Deleted " + filename : "Failed");'
    '    if (r.ok) loadImageList();'
    '  });'
    '}'
    'function queueAdd() {'
    '  var text = document.getElementById("q-text").value.trim();'
    '  var color = hexToRgb(document.getElementById("q-color").value);'
    '  if (!text) { msg("Enter a message first."); return; }'
    '  api("/state").then(function(r) {'
    '    var queue = r.message_queue || [];'
    '    queue.push({ text: text, color: color });'
    '    api("/set", { message_queue: queue }).then(function(r2) {'
    '      if (r2.ok) { msg("Added to playlist."); document.getElementById("q-text").value = ""; loadQueue(); }'
    '    });'
    '  });'
    '}'
    'function queuePlay() {'
    '  api("/set", { queue_index: 0 }).then(function(){ loadQueue(); msg("Playing playlist..."); });'
    '}'
    'function queueStop() {'
    '  api("/set", { message_queue: [], queue_index: 0 }).then(function(r) {'
    '    if (r.ok) { msg("Playlist cleared."); loadQueue(); }'
    '  });'
    '}'
    'function queueSetLoop(val) {'
    '  api("/set", { queue_loop: val }).then(function(r) {'
    '    if (r.ok) msg(val ? "Looping on." : "Looping off.");'
    '  });'
    '}'
    'function queueRemove(index) {'
    '  api("/state").then(function(r) {'
    '    var queue = r.message_queue || [];'
    '    queue.splice(index, 1);'
    '    api("/set", { message_queue: queue, queue_index: 0 }).then(function(r2) {'
    '      if (r2.ok) loadQueue();'
    '    });'
    '  });'
    '}'
    'function loadQueue() {'
    '  api("/state").then(function(r) {'
    '    var queue = r.message_queue || [];'
    '    var current = r.queue_index || 0;'
    '    var list = document.getElementById("queue-list");'
    '    document.getElementById("q-loop").checked = r.queue_loop || false;'
    '    if (!queue.length) {'
    '      list.innerHTML = "<div style=\'color:#555;padding:0.3em 0\'>Playlist is empty.</div>";'
    '      return;'
    '    }'
    '    list.innerHTML = queue.map(function(item, i) {'
    '      var col = item.color ? "rgb(" + item.color.join(",") + ")" : "#ffc800";'
    '      var active = i === current ? "font-weight:bold;color:#f0a500;" : "";'
    '      return "<div class=\'upload-item\' style=\'" + active + "\'>"'
    '        + "<span style=\'color:" + col + "\'>" + item.text + "</span>"'
    '        + "<span class=\'upload-del\' onclick=\'queueRemove(" + i + ")\'>X</span>"'
    '        + "</div>";'
    '    }).join("");'
    '  });'
    '}'
    'function loadState() {'
    '  api("/state").then(function(r) {'
    '    if (!r.brightness) return;'
    '    document.getElementById("brightness").value = r.brightness;'
    '    document.getElementById("bright-val").innerText = r.brightness;'
    '    var spd = Math.round(r.scroll_speed * 100);'
    '    document.getElementById("scroll_speed").value = spd;'
    '    document.getElementById("speed-val").innerText = r.scroll_speed.toFixed(2);'
    '    document.getElementById("static_duration").value = r.static_duration;'
    '    document.getElementById("dur-val").innerText = r.static_duration;'
    '    document.getElementById("gif_loops").value = r.gif_loops;'
    '    document.getElementById("loop-val").innerText = r.gif_loops;'
    '    document.getElementById("pause-btn").innerText = r.paused ? "Resume" : "Pause";'
    '    var mode = r.mode || "everything";'
    '    document.querySelectorAll(".mode-btn").forEach(function(b){ b.classList.remove("active"); });'
    '    var mb = document.getElementById("mode-" + mode);'
    '    if (mb) mb.classList.add("active");'
    '  });'
    '}'
    'loadState(); loadImageList(); loadQueue();'
    '</script>'
    '</body>'
    '</html>'
)


# ─────────────────────────────────────────────
# HELPERS
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


def local_images() -> list:
    p = Path(IMAGE_DIR)
    if not p.exists():
        return []
    return sorted(f.name for f in p.iterdir()
                  if f.name.startswith("local_") and f.suffix.lower() in ALLOWED_EXTENSIONS)


# ─────────────────────────────────────────────
# HANDLER
# ─────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except Exception:
            pass

    def serve_html(self):
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except Exception:
            pass

    def parse_path(self):
        parsed = urllib.parse.urlparse(self.path)
        qs     = urllib.parse.parse_qs(parsed.query)
        return parsed.path, qs

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            try:
                return json.loads(self.rfile.read(length))
            except Exception:
                return {}
        return {}

    def do_GET(self):
        path, qs = self.parse_path()

        if path in ("/", "/index.html"):
            self.serve_html()
            return

        if path == "/state":
            self.send_json(read_control())

        elif path == "/images":
            self.send_json({"files": local_images()})

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
            self.send_json({"ok": True, "message": "Rebooting..."})
            subprocess.Popen(["sudo", "reboot"])

        elif path == "/shutdown":
            self.send_json({"ok": True, "message": "Shutting down. Safe to unplug."})
            subprocess.Popen(["sudo", "shutdown", "now"])

        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        path, qs = self.parse_path()

        if path == "/set":
            body = self.read_body()
            ctrl = read_control()
            for key in ("brightness", "scroll_speed", "static_duration",
                        "gif_loops", "message", "message_color",
                        "paused", "skip", "mode",
                        "message_queue", "queue_loop", "queue_index"):
                if key in body:
                    ctrl[key] = body[key]
            write_control(ctrl)
            self.send_json({"ok": True})

        elif path == "/upload":
            try:
                ct = self.headers.get("Content-Type", "")
                if "multipart" not in ct:
                    self.send_json({"error": "expected multipart"}, 400)
                    return
                boundary = None
                for part in ct.split(";"):
                    part = part.strip()
                    if part.startswith("boundary="):
                        boundary = part[9:].strip()
                        break
                if not boundary:
                    self.send_json({"error": "no boundary"}, 400)
                    return
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                delimiter = ("--" + boundary).encode()
                parts = body.split(delimiter)
                filename = None
                filedata = None
                for part in parts:
                    if b"Content-Disposition" not in part:
                        continue
                    header_end = part.find(b"\r\n\r\n")
                    if header_end == -1:
                        continue
                    headers = part[:header_end].decode(errors="ignore")
                    data = part[header_end+4:]
                    if data.endswith(b"\r\n"):
                        data = data[:-2]
                    if 'filename="' in headers:
                        start = headers.find('filename="') + 10
                        end = headers.find('"', start)
                        filename = headers[start:end]
                        filedata = data
                if not filename or filedata is None:
                    self.send_json({"error": "no file found"}, 400)
                    return
                ext = Path(filename).suffix.lower()
                if ext not in ALLOWED_EXTENSIONS:
                    self.send_json({"error": "unsupported file type"}, 400)
                    return
                safe_name = "local_" + str(uuid.uuid4())[:8] + ext
                dest = os.path.join(IMAGE_DIR, safe_name)
                os.makedirs(IMAGE_DIR, exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(filedata)
                self.send_json({"ok": True, "filename": safe_name})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif path == "/delete_image":
            body = self.read_body()
            filename = body.get("filename", "")
            if not filename.startswith("local_"):
                self.send_json({"error": "can only delete local uploads"}, 403)
                return
            dest = os.path.join(IMAGE_DIR, filename)
            if os.path.exists(dest):
                os.remove(dest)
                self.send_json({"ok": True})
            else:
                self.send_json({"error": "file not found"}, 404)

        else:
            self.send_json({"error": "not found"}, 404)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(IMAGE_DIR, exist_ok=True)
    if not os.path.exists(CONTROL_FILE):
        write_control(DEFAULT_CONTROL)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("[Control Server] http://gapkids.local:8080")
    server.serve_forever()