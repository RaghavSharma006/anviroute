"""Kaggle cell 2: authenticated inference proxy + a Cloudflare Quick Tunnel."""

import os
import sys
import time
import re
import signal
import secrets
import subprocess
import requests

WORK = "/tmp/rea"
os.makedirs(WORK, exist_ok=True)
MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"
CF = "/usr/local/bin/cloudflared"

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "flask", "requests"],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

token_file = WORK + "/token"
if os.path.exists(token_file):
    with open(token_file) as stored:
        API_KEY = stored.read().strip()
else:
    API_KEY = secrets.token_urlsafe(32)
    descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stored:
        stored.write(API_KEY)
os.chmod(token_file, 0o600)


def stop_previous(name, expected_command):
    # Only stop this notebook's recorded process, never arbitrary port owners/tunnels.
    path = WORK + "/" + name + ".pid"
    try:
        with open(path) as stored:
            pid = int(stored.read())
        with open(f"/proc/{pid}/cmdline", "rb") as process:
            command = process.read().replace(b"\0", b" ").decode(errors="replace")
        if expected_command in command:
            os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass


stop_previous("proxy", WORK + "/proxy.py")
stop_previous("tunnel", CF + " tunnel")
time.sleep(2)

proxy_code = r'''
import hmac
import os
import requests
from flask import Flask, request, Response, jsonify

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
with open("/tmp/rea/token") as stored:
    TOKEN = stored.read().strip()
MODEL = os.environ["ANVIROUTE_MODEL"]
ALLOWED = {
    ("GET", "v1/models"), ("GET", "api/tags"), ("GET", "api/version"),
    ("POST", "v1/chat/completions"), ("POST", "v1/messages"),
    ("POST", "v1/messages/count_tokens"),
}

@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def forward(path):
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not supplied.isascii() or not hmac.compare_digest(supplied, TOKEN):
        return jsonify({"error": "Unauthorized"}), 401
    if (request.method, path) not in ALLOWED:
        return jsonify({"error": "Unsupported inference route"}), 404
    try:
        # Regular JSON, never SSE over the random Cloudflare tunnel.
        payload = None
        if request.method == "POST":
            payload = request.get_json()
            if not isinstance(payload, dict):
                return jsonify({"error": "Expected JSON object"}), 400
            payload["model"] = MODEL
            payload["stream"] = False
        with requests.request(
            request.method, "http://127.0.0.1:11434/" + path,
            params=request.args, json=payload,
            headers={"Content-Type": "application/json", "anthropic-version": "2023-06-01"},
            timeout=(10, 600),
        ) as upstream:
            if upstream.ok and path == "v1/models":
                data = upstream.json()
                data["data"] = [item for item in data.get("data", []) if item.get("id") == MODEL]
                return jsonify(data)
            return Response(upstream.content, status=upstream.status_code,
                            content_type=upstream.headers.get("Content-Type", "application/json"))
    except requests.RequestException:
        return jsonify({"error": "Ollama request failed; check /tmp/rea/ollama.log"}), 502

app.run(host="127.0.0.1", port=11435, threaded=True)
'''

with open(WORK + "/proxy.py", "w") as source:
    source.write(proxy_code)
with open(WORK + "/proxy.log", "w") as log:
    proxy_proc = subprocess.Popen(
        [sys.executable, WORK + "/proxy.py"], stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True, env={**os.environ, "ANVIROUTE_MODEL": MODEL},
    )
with open(WORK + "/proxy.pid", "w") as stored:
    stored.write(str(proxy_proc.pid))

proxy_ready = False
for _ in range(20):
    time.sleep(1)
    if proxy_proc.poll() is not None:
        break
    try:
        unauthorized = requests.get("http://127.0.0.1:11435/v1/models", timeout=3)
        authorized = requests.get("http://127.0.0.1:11435/v1/models",
                                  headers={"Authorization": "Bearer " + API_KEY}, timeout=10)
        if unauthorized.status_code == 401 and authorized.ok and authorized.json().get("data"):
            proxy_ready = True
            break
    except requests.RequestException:
        pass
if not proxy_ready:
    raise RuntimeError("Proxy startup/model check failed; inspect /tmp/rea/proxy.log and ollama list")

if not os.path.exists(CF):
    download = requests.get(
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        timeout=60,
    )
    download.raise_for_status()
    with open(CF, "wb") as binary:
        binary.write(download.content)
    os.chmod(CF, 0o755)

with open(WORK + "/tunnel.log", "w") as log:
    tunnel_proc = subprocess.Popen(
        [CF, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", "http://127.0.0.1:11435"],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
with open(WORK + "/tunnel.pid", "w") as stored:
    stored.write(str(tunnel_proc.pid))

PUBLIC_URL = None
for _ in range(60):
    time.sleep(2)
    with open(WORK + "/tunnel.log", errors="ignore") as log:
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log.read())
    if urls:
        PUBLIC_URL = urls[-1]
        break
    if tunnel_proc.poll() is not None:
        break
if not PUBLIC_URL:
    raise RuntimeError("Cloudflare failed; inspect /tmp/rea/tunnel.log")

for _ in range(30):
    try:
        response = requests.get(PUBLIC_URL + "/v1/models",
                                headers={"Authorization": "Bearer " + API_KEY}, timeout=5)
        if response.ok and response.json().get("data"):
            break
    except (requests.RequestException, ValueError):
        pass
    time.sleep(2)
else:
    raise RuntimeError("Tunnel URL assigned but not reachable; inspect /tmp/rea/tunnel.log and rerun cell 2")

print("✅ Proxy and tunnel ready")
print("Base URL:", PUBLIC_URL + "/v1")
print("Model:", MODEL)
print("API key:", API_KEY)
print("Keep this Kaggle session running. Keep the API key and these outputs private.")
