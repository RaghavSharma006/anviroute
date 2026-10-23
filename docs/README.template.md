<p align="center"><img src="docs/banner.svg" alt="AnviRoute — Paste your API. Use Claude Code." width="100%"></p>

<p align="center">
  <a href="https://github.com/RaghavSharma006/anviroute/actions/workflows/ci.yml"><img src="https://github.com/RaghavSharma006/anviroute/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-60e9c8" alt="MIT license"></a>
</p>

<h1 align="center">AnviRoute</h1>
<p align="center"><strong>Your Kaggle model. Your Claude Code. One command.</strong></p>

Two commands. One saved model name.

**1. Open the frontend:**

```cmd
anviroute
```

Name your model (for example `qwen`), paste your Kaggle output, and click **Save & connect**. AnviRoute extracts the URL/key, detects the model, and checks the connection automatically.

**2. In another terminal, from any project folder:**

```cmd
anviroute run claude --modename qwen
```

**Kaggle restarted?** Paste the new output into the saved model's update box and click **Update & reconnect**. Keep the same name and Claude command. No separate activation or manual check step. Existing named routes use the updated address on the next request.

Windows encrypts saved API keys for your account. Other platforms keep keys in memory only.

![Two-command setup and quick session updates](docs/quick-setup.png)

<p align="center">
  <a href="https://github.com/RaghavSharma006/anviroute/releases/latest/download/AnviRoute.cmd"><strong>⬇ Download AnviRoute.cmd · about 32 KB</strong></a>
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

**Release status:** alpha. Automated tests cover the local adapter, launcher, and Kaggle proxy against simulated APIs. A real Kaggle inference session has not yet been verified for this release. Model/tool compatibility varies; complete the [live test](docs/LIVE_TEST.md) before relying on it.

## 1. Download and open

**[Download AnviRoute.cmd](https://github.com/RaghavSharma006/anviroute/releases/latest/download/AnviRoute.cmd)** → **open it** → add your connection in the dashboard.

That is the entire setup. The single file installs itself and starts the local dashboard service. No ZIP extraction, separate installer, pip, dependency downloads, or private Python environment.

**Requirements:** your existing **[Python 3.10+](https://www.python.org/downloads/windows/)** and **[Claude Code](https://code.claude.com/docs/en/overview)**. The tiny download does not bundle either runtime. If Python is not installed yet, enable **Add Python to PATH** during its installation.

| Footprint | Size |
| --- | --- |
| Single downloadable command | About **32 KB** |
| Installed compressed application | About **21 KB** |
| Third-party runtime dependencies | **None** |
| Extra Python environments / pip installs | **None** |

Sizes exclude the Python and Claude Code installations you already have. The application uses Python's standard library; this is a disk/download measurement, not a RAM usage claim.

On first open, AnviRoute copies its tiny application into `%LOCALAPPDATA%\AnviRoute` and adds the command to your user PATH. It then starts immediately. You can delete the downloaded file after that.

For later use, reopen your terminal in **your project folder** and run:

```cmd
anviroute run claude --modename qwen
```

That command works from any folder. If using VS Code's terminal, restart VS Code once after initial setup so it receives the updated PATH. Updating is equally simple: download and open the new file.

Upgrading from v0.2? Its old `%LOCALAPPDATA%\AnviRoute\runtime` environment may remain on disk. The new launcher does not use it; it can be removed manually after verifying the new version works.

## 2. Start your Kaggle API

If you already have an API URL and bearer key, skip to [Two-terminal workflow](#3-two-terminal-workflow).

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
{{OLLAMA_CELL}}
```

</details>

### Cell 2 — protect the API and open Cloudflare

This creates a bearer API key, starts an inference-only proxy on port 11435, and opens a Cloudflare Quick Tunnel. It verifies the model list before printing the connection details. Rerunning the cell reuses the token within the same Kaggle session and replaces only its own recorded proxy/tunnel processes.

<details>
<summary><strong>Expand and copy cell 2</strong></summary>

```python
{{TUNNEL_CELL}}
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

## 3. Two-terminal workflow

Keep `anviroute` running in terminal 1. It opens **http://127.0.0.1:20128** with the model setup form. Enter a saved name and paste the Kaggle output; **Save & connect** handles model detection and inference checks together.

In terminal 2, run `anviroute run claude --modename qwen` from your project. Replace `qwen` with your saved name. Each named Claude session keeps its own route even when another saved model is selected in the dashboard.

When Kaggle regenerates the URL/key, paste its new output into the saved model's update box and click **Update & reconnect**. No need to recreate the model or change the Claude command. Keep your Kaggle notebook private because its output includes a credential. AnviRoute cannot discover a random tunnel URL without receiving the new address.

Opening `anviroute` again reuses the running router and opens the frontend. Windows credentials restore after restart. Other platforms require entering the key again.

### Error logs and design

The **Error logs** page offers stage filters, message search, an errors-only view, and JSON export. Logs survive restarts, retain up to 500 visible events, and rotate at approximately 768 KB total. Prompts, replies, and credentials are excluded.

![Warm console and error logs](docs/dashboard-errors.png)

The ivory, charcoal, and olive console follows our [editable Canva design reference](https://canva.link/fz09319do9daxlp). The app uses local HTML/CSS/JavaScript with no UI libraries or external fonts.

## How credentials and replies work

- Named profiles save the URL, model, and format. Windows saves the key encrypted with DPAPI; the dashboard never returns it. Other platforms keep keys in memory only.
- AnviRoute sends the upstream key as `Authorization: Bearer ...`; Claude gets a separate temporary local token.
- The local server binds to `127.0.0.1`. The Kaggle proxy exposes inference/model-list routes and refuses model administration routes.
- Cloudflare Quick Tunnels [do not support SSE](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/#limitations). AnviRoute requests a **complete JSON response**, then builds Claude's event stream locally. **Replies appear after upstream generation finishes**, rather than live token-by-token.
- The default upstream timeout is 110 seconds. Larger/slow models can exceed tunnel timeouts. Increasing AnviRoute's timeout cannot override Cloudflare's own limits.
- Basic chat, client-side tool calls/results, and image input on compatible models are supported. Hosted tools, document blocks, deferred tools, and every advanced Claude feature are not supported by the OpenAI adapter. OpenAI-mode token counting is approximate.

See [SECURITY.md](SECURITY.md) for trust boundaries and limitations. This adapter does not make a model more capable, change its content behavior, or bypass Kaggle quotas.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `'anviroute.cmd' is not recognized` | Open the downloaded `AnviRoute.cmd` once, reopen Command Prompt, and restart VS Code if needed. Check `%LOCALAPPDATA%\AnviRoute\bin\anviroute.cmd` exists. |
| Python is not found | Install Python 3.10+ with **Add Python to PATH**, then reopen your terminal. |
| Claude is not found | Install Claude Code and verify `claude --version`. |
| Key field is blank after saving | Keys are deliberately never returned to the browser. Leave blank to keep the saved key. |
| No models listed | Check the URL/key and that Ollama has loaded the model. The endpoint must expose `/v1/models`. |
| HTTP 401/403 | Copy the actual Kaggle API key; old/new sessions may have different keys. |
| Proxy failed to start | Inspect `/tmp/rea/proxy.log`. Stop an unrelated process manually if it owns port 11435. |
| HTML instead of JSON | Wrong URL, an expired tunnel, or browser-only access protection. |
| Out of memory / very slow | The 27B Q4 example is large; use appropriate hardware or a smaller tool-capable model. |
| HTTP 429 | Provider/tunnel rate limit; wait before retrying. |
| Still connects to OmniRoute | Check Claude settings for conflicting `ANTHROPIC_BASE_URL`, provider flags, or `apiKeyHelper`. AnviRoute does not edit existing settings. |

## Other platforms

Install from source with `python -m pip install .`, then use the same two commands. The single-download installer is for Windows.

## Development and contributing

```sh
python -m pip install -e .
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/build_docs.py
python scripts/smoke_claude.py
```

Tests cover saved-profile restart, encrypted credentials, log redaction, launcher attachment, translation, tools/results, local authentication, and proxy restrictions. CI also tests Windows installation and invoking the command from another directory. Live compatibility is recorded separately through [docs/LIVE_TEST.md](docs/LIVE_TEST.md).

Contributions, reproducible bug reports, and tested model reports are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). If this saves you setup time, a star helps others find it.

Independent community project. Not affiliated with Anthropic, Ollama, Kaggle, or Cloudflare. Non-Claude models in Claude Code are outside Anthropic's official support. [MIT license](LICENSE).


## Connection checks and performance

Use **Send test message** on a saved model to see a real reply, elapsed time and input/output tokens. Each Claude launch rechecks the model endpoint; failed requests invalidate readiness. Error logs include duration and tool counts, never prompt text. Pasting an API key with a `Bearer ` prefix is accepted.

The notebook warms the model, keeps it loaded for 30 minutes, and configures one inference slot with a 32K context. Existing Ollama processes must restart for server settings to apply. Check `ollama ps`: CPU offloading is a common cause of slow inference. A 27B model plus context may exceed your GPU memory. Increase context only when memory allows; Ollama recommends 64K+ for larger Claude projects. AnviRoute does not silently truncate your conversation or tools; OpenAI token counting is an estimate.

Quick Tunnels do not support SSE, so replies are buffered until generation finishes. Keeping the model warm cannot extend Kaggle session limits or revive a stopped notebook. After shutdown, rerun the cells and paste their fresh output into the same saved profile. No key or URL can repair an offline backend.

References: [Ollama memory and concurrency](https://docs.ollama.com/faq), [Claude context guidance](https://docs.ollama.com/integrations/claude-code), [Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
