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
  <a href="https://github.com/RaghavSharma006/anviroute/releases/latest/download/AnviRoute.cmd"><strong>⬇ Download AnviRoute.cmd · about 16 KB</strong></a>
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

## 1. Download and open

**[Download AnviRoute.cmd](https://github.com/RaghavSharma006/anviroute/releases/latest/download/AnviRoute.cmd)** → **open it** → paste your URL and key.

That is the entire setup. The single file installs itself and starts Claude Code. No ZIP extraction, separate installer, pip, dependency downloads, or private Python environment.

**Requirements:** your existing **[Python 3.10+](https://www.python.org/downloads/windows/)** and **[Claude Code](https://code.claude.com/docs/en/overview)**. The tiny download does not bundle either runtime. If Python is not installed yet, enable **Add Python to PATH** during its installation.

| Footprint | Size |
| --- | --- |
| Single downloadable command | About **16 KB** |
| Installed compressed application | About **9 KB** |
| Third-party runtime dependencies | **None** |
| Extra Python environments / pip installs | **None** |

Sizes exclude the Python and Claude Code installations you already have. The application uses Python's standard library; this is a disk/download measurement, not a RAM usage claim.

On first open, AnviRoute copies its tiny application into `%LOCALAPPDATA%\AnviRoute` and adds the command to your user PATH. It then starts immediately. You can delete the downloaded file after that.

For later use, reopen your terminal in **your project folder** and run:

```cmd
anviroute.cmd run claude
```

That command works from any folder. If using VS Code's terminal, restart VS Code once after initial setup so it receives the updated PATH. Updating is equally simple: download and open the new file.

Upgrading from v0.2? Its old `%LOCALAPPDATA%\AnviRoute\runtime` environment may remain on disk. The new launcher does not use it; it can be removed manually after verifying the new version works.

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
| `'anviroute.cmd' is not recognized` | Open the downloaded `AnviRoute.cmd` once, reopen Command Prompt, and restart VS Code if needed. Check `%LOCALAPPDATA%\AnviRoute\bin\anviroute.cmd` exists. |
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
