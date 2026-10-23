<p align="center"><img src="docs/banner.svg" alt="AnviRoute — Paste your API. Use Claude Code." width="100%"></p>

<p align="center">
  <a href="https://github.com/RaghavSharma006/anviroute/actions/workflows/ci.yml"><img src="https://github.com/RaghavSharma006/anviroute/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-60e9c8" alt="MIT license"></a>
</p>

<h1 align="center">AnviRoute</h1>
<p align="center"><strong>Your Kaggle model. Your Claude Code. One command.</strong></p>

```cmd
anviroute.cmd run claude
```

Paste your **API URL** and **API key**. AnviRoute detects the model and starts Claude Code in your current project folder. No model argument. No provider combos. No GitHub discovery setup.

<p align="center">
  <a href="https://github.com/RaghavSharma006/anviroute/releases/download/v0.2.0/AnviRoute-Windows.zip"><strong>⬇ Download AnviRoute for Windows</strong></a>
  &nbsp;·&nbsp;
  <a href="examples/kaggle_anviroute.ipynb">Kaggle setup notebook</a>
  &nbsp;·&nbsp;
  <a href="https://github.com/RaghavSharma006/anviroute/releases">All releases</a>
</p>

## What it does

AnviRoute is a small local API adapter. Your model runs on Kaggle (or another OpenAI-compatible server); Claude Code reads files, edits code, and runs approved commands on your computer.

```text
Your project → Claude Code → AnviRoute on your PC → your API URL → Ollama on Kaggle
```

```text
  AnviRoute
  Paste your API. Use Claude Code.

API URL: https://your-session.trycloudflare.com/v1
API key (hidden; Enter if none):

  Model: orcarouter/Qwen3.8-27B-Uncensored:q4_K_M
  Local API: http://127.0.0.1:20128
  Starting Claude Code…
```

**Release status:** alpha. Automated tests cover the local adapter, launcher, and Kaggle proxy against simulated APIs. A real Kaggle inference session has not yet been verified for this release. Model/tool compatibility varies; complete the [live test](docs/LIVE_TEST.md) before relying on it.

## 1. Install on Windows — once

You need:

- **[Python 3.10+](https://www.python.org/downloads/windows/)**. Enable **Add Python to PATH** during installation.
- **[Claude Code](https://code.claude.com/docs/en/overview)** installed and available as `claude`.

Check in Command Prompt:

```cmd
python --version
claude --version
```

Then:

1. [Download AnviRoute-Windows.zip](https://github.com/RaghavSharma006/anviroute/releases/download/v0.2.0/AnviRoute-Windows.zip).
2. Right-click the ZIP → **Extract All**.
3. In the extracted folder, double-click **`install.cmd`**. No administrator terminal is needed. Source ZIP users can run the same installer.
4. Wait for **AnviRoute installed successfully**.
5. **Close and reopen Command Prompt.** If using VS Code's integrated terminal, restart VS Code too.

The installer creates an isolated Python environment and adds `%LOCALAPPDATA%\AnviRoute\bin` to your **user PATH**. It does not modify your system PATH. After installation, you can delete the extracted download; the installed runtime is self-contained apart from your Python installation.

Verify from any folder:

```cmd
anviroute.cmd --version
```

To update, download a newer release and run its `install.cmd` again.

## 2. Start your Kaggle API

If you already have an API URL and bearer key, skip to [Run Claude Code](#3-run-claude-code--every-session).

Otherwise, create a Kaggle Python notebook, enable **Internet**, choose a suitable GPU, and run the **two cells below in order**. You can also import [kaggle_anviroute.ipynb](examples/kaggle_anviroute.ipynb), which contains exactly these cells.

The example uses your selected model:

```text
orcarouter/Qwen3.8-27B-Uncensored:q4_K_M
```

The model's [Ollama listing](https://ollama.com/orcarouter/Qwen3.8-27B-Uncensored:q4_K_M) reports approximately **18 GB of weights**, before context/KV-cache memory. A 16 GB GPU may require CPU offloading and be slow; two GPUs are not automatically a single memory pool. Pick a smaller model if your available hardware cannot run it. Changing models means changing `MODEL` in **both cells**.

### Cell 1 — install Ollama and load the model

This installs required Linux packages, starts Ollama if needed, and downloads the model only if missing. The first download can take several minutes. Keep the notebook private; its second cell prints a live credential.

<details>
<summary><strong>Expand and copy cell 1</strong></summary>

```python
"""Kaggle cell 1: install Ollama, start it, and pull the selected model."""

import os
import time
import shutil
import subprocess
import requests

MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"
OLLAMA = "http://127.0.0.1:11434"
WORK = "/tmp/rea"
os.makedirs(WORK, exist_ok=True)


def quiet(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if not shutil.which("ollama"):
    quiet(["apt-get", "update", "-qq"])
    quiet(["apt-get", "install", "-y", "-qq", "curl", "zstd"])
    quiet(["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"])
else:
    quiet(["apt-get", "install", "-y", "-qq", "zstd"])

# Keep the model API local; the second cell adds authentication before exposing it.
try:
    requests.get(OLLAMA + "/api/tags", timeout=3).raise_for_status()
except requests.RequestException:
    with open(WORK + "/ollama.log", "a") as log:
        ollama_proc = subprocess.Popen(
            ["ollama", "serve"], stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        )
    ollama_ready = False
    for _ in range(60):
        time.sleep(2)
        try:
            requests.get(OLLAMA + "/api/tags", timeout=3).raise_for_status()
            ollama_ready = True
            break
        except requests.RequestException:
            if ollama_proc.poll() is not None:
                break
    if not ollama_ready:
        raise RuntimeError("Ollama failed to start; check /tmp/rea/ollama.log")

response = requests.get(OLLAMA + "/api/tags", timeout=15)
response.raise_for_status()
models = response.json()["models"]
if not any(m.get("name") == MODEL or m.get("model") == MODEL for m in models):
    print("Downloading model quietly; this can take several minutes...", flush=True)
    quiet(["ollama", "pull", MODEL])

print("✅ Ollama ready")
print("✅ Model:", MODEL)
```

</details>

### Cell 2 — protect the API and open Cloudflare

This creates a bearer API key, starts an inference-only proxy on port 11435, and opens a Cloudflare Quick Tunnel. It verifies the model list before printing the connection details. Rerunning the cell reuses the token within the same Kaggle session and replaces only its own recorded proxy/tunnel processes.

<details>
<summary><strong>Expand and copy cell 2</strong></summary>

```python
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
```

</details>

Wait for:

```text
✅ Proxy and tunnel ready
Base URL: https://your-session.trycloudflare.com/v1
Model: orcarouter/Qwen3.8-27B-Uncensored:q4_K_M
API key: <your generated secret>
```

Copy **Base URL** and **API key**. Keep Kaggle running. Do not publish the notebook outputs, token file, or API key. The generated scripts/logs are in `/tmp/rea`; errors can be inspected in `/tmp/rea/ollama.log`, `proxy.log`, or `tunnel.log`.

## 3. Run Claude Code — every session

Open **Command Prompt in the project folder you want Claude to work on**. For example:

```cmd
cd /d D:\my-project
anviroute.cmd run claude
```

You can run the same command from any folder after installing. In PowerShell, `anviroute.cmd run claude` also works through PATH.

1. Paste the Kaggle **Base URL**.
2. Paste its **API key**. Input is hidden; press Enter after pasting.
3. Claude Code starts automatically. You do not need to type a model name.

In Claude Code, run `/status`. Confirm your detected model and the local endpoint **`http://127.0.0.1:20128`**. Then ask for a small file edit and approve the usual Claude permission request.

The launcher reuses the previous model if it is still listed by the endpoint; otherwise it uses the first model returned by `/v1/models`. The included Kaggle proxy lists only the configured model, so it is selected automatically.

When Kaggle restarts and the URL changes, close Claude, run **the same command**, and paste the new URL/key. This workflow uses manual URL entry; it does not automatically discover new sessions in the background.

## How credentials and replies work

- The last URL, model, and API format are saved as convenience defaults. **The API key is not saved.** Press Enter to reuse the URL if it has not changed.
- AnviRoute sends the upstream key as `Authorization: Bearer ...`; Claude gets a separate temporary local token.
- The local server binds to `127.0.0.1`. The Kaggle proxy exposes inference/model-list routes and refuses model administration routes.
- Cloudflare Quick Tunnels [do not support SSE](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/#limitations). AnviRoute requests a **complete JSON response**, then builds Claude's event stream locally. **Replies appear after upstream generation finishes**, rather than live token-by-token.
- The default upstream timeout is 110 seconds. Larger/slow models can exceed tunnel timeouts. Increasing AnviRoute's timeout cannot override Cloudflare's own limits.
- Basic chat, client-side tool calls/results, and image input on compatible models are supported. Hosted tools, document blocks, deferred tools, and every advanced Claude feature are not supported by the OpenAI adapter. OpenAI-mode token counting is approximate.

See [SECURITY.md](SECURITY.md) for trust boundaries and limitations. This adapter does not make a model more capable, change its content behavior, or bypass Kaggle quotas.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `'anviroute.cmd' is not recognized` | Run `install.cmd`, close/reopen Command Prompt, and restart VS Code if needed. Check `%LOCALAPPDATA%\AnviRoute\bin\anviroute.cmd` exists. |
| Python is not found | Install Python 3.10+ with **Add Python to PATH**, then reopen your terminal. |
| Claude is not found | Install Claude Code and verify `claude --version`. |
| API key looks like it is not pasting | Key entry is hidden; paste once and press Enter. |
| No models listed | Check the URL/key and that Ollama has loaded the model. The endpoint must expose `/v1/models`. |
| HTTP 401/403 | Copy the actual Kaggle API key; old/new sessions may have different keys. |
| Proxy failed to start | Inspect `/tmp/rea/proxy.log`. Stop an unrelated process manually if it owns port 11435. |
| HTML instead of JSON | Wrong URL, an expired tunnel, or browser-only access protection. |
| Out of memory / very slow | The 27B Q4 example is large; use appropriate hardware or a smaller tool-capable model. |
| HTTP 429 | Provider/tunnel rate limit; wait before retrying. |
| Still connects to OmniRoute | Check Claude settings for conflicting `ANTHROPIC_BASE_URL`, provider flags, or `apiKeyHelper`. AnviRoute does not edit existing settings. |

## Optional settings

The everyday command stays `anviroute.cmd run claude`. These flags are only for special cases:

```cmd
anviroute.cmd run claude --port 20129
anviroute.cmd run claude --timeout 180
anviroute.cmd run claude --api-format anthropic
anviroute.cmd run claude -- -p "Explain this project"
```

Other platforms can install from source with `python -m pip install .`, then run `python -m anviroute run claude`. The Windows PATH installer is specifically for Windows.

## Development and contributing

```sh
python -m pip install -e .
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/build_docs.py
```

Tests cover the launcher, automatic model selection, translation, tools/results, local authentication, proxy route restrictions, and legacy transport. CI also tests Windows installation and invoking the command from another directory. Live compatibility is recorded separately through [docs/LIVE_TEST.md](docs/LIVE_TEST.md).

Contributions, reproducible bug reports, and tested model reports are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). If this saves you setup time, a star helps others find it.

The older KaggleLink host/discovery implementation is retained for compatibility; it is not part of the normal AnviRoute setup. [Legacy guide](docs/LEGACY_KAGGLELINK.md).

Independent community project. Not affiliated with Anthropic, Ollama, Kaggle, or Cloudflare. Non-Claude models in Claude Code are outside Anthropic's official support. [MIT license](LICENSE).
