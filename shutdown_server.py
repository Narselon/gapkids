#!/usr/bin/env python3
"""
shutdown_server.py — Tiny web server that lets you shut down the Pi from a browser.
Access from any device on the same network: http://gapkids.local:8080

Run on boot via cron:
    @reboot sudo python3 /home/narselon/gapkids/gapkids/shutdown_server.py &
"""

import http.server
import subprocess
import os

PORT = 8080
PASSWORD = "gapkids"  # Change this to whatever you want

HTML = """<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GapKids Pi</title>
    <style>
        body {{
            font-family: sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background: #1a1a1a;
            color: white;
        }}
        h1 {{ font-size: 1.5em; margin-bottom: 2em; }}
        button {{
            padding: 1em 2em;
            font-size: 1.2em;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            margin: 0.5em;
            width: 200px;
        }}
        .shutdown  {{ background: #e74c3c; color: white; }}
        .reboot    {{ background: #e67e22; color: white; }}
        .status    {{ background: #27ae60; color: white; }}
        input {{
            padding: 0.8em;
            font-size: 1em;
            border-radius: 8px;
            border: none;
            margin-bottom: 1em;
            width: 200px;
            text-align: center;
        }}
        #msg {{ margin-top: 1em; color: #aaa; }}
    </style>
</head>
<body>
    <h1>🖥️ GapKids Pi</h1>
    <input type="password" id="pw" placeholder="Password" />
    <br>
    <button class="shutdown" onclick="send('/shutdown')">⏻ Shut Down</button>
    <button class="reboot"   onclick="send('/reboot')">↺ Reboot</button>
    <button class="status"   onclick="send('/status')">✓ Status</button>
    <p id="msg"></p>
    <script>
        function send(action) {{
            const pw = document.getElementById('pw').value;
            fetch(action + '?pw=' + encodeURIComponent(pw))
                .then(r => r.text())
                .then(t => document.getElementById('msg').innerText = t);
        }}
    </script>
</body>
</html>
""".format()


class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress default request logging

    def respond(self, text, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode())

    def serve_page(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(HTML.encode())

    def check_password(self, path) -> bool:
        if "?pw=" in path:
            pw = path.split("?pw=")[-1]
            return pw == PASSWORD
        return False

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_page()

        elif self.path.startswith("/shutdown"):
            if not self.check_password(self.path):
                self.respond("Wrong password.", 403)
                return
            self.respond("Shutting down in 3 seconds... safe to unplug.")
            subprocess.Popen(["sudo", "shutdown", "now"])

        elif self.path.startswith("/reboot"):
            if not self.check_password(self.path):
                self.respond("Wrong password.", 403)
                return
            self.respond("Rebooting in 3 seconds...")
            subprocess.Popen(["sudo", "reboot"])

        elif self.path.startswith("/status"):
            if not self.check_password(self.path):
                self.respond("Wrong password.", 403)
                return
            uptime = subprocess.check_output(["uptime", "-p"]).decode().strip()
            temp   = subprocess.check_output(["vcgencmd", "measure_temp"]).decode().strip()
            self.respond(f"Online ✓\n{uptime}\n{temp}")

        else:
            self.respond("Not found.", 404)


if __name__ == "__main__":
    # Allow sudo shutdown without password for this script
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[Shutdown Server] Running on port {PORT}")
    server.serve_forever()
