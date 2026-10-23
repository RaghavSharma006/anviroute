> Legacy advanced setup. For the current PC-only launcher, see the root README.

<p align="center"><img src="docs/banner.svg" alt="KaggleLink — Ephemeral GPU. Stable connection." width="100%"></p>

<p align="center"><strong>Connect Claude Code to Ollama on Kaggle. Stop pasting a new tunnel URL every session.</strong></p>
<p align="center">Python 3.10+ · No runtime dependencies · Windows / macOS / Linux · MIT</p>

Kaggle restarts. Your Cloudflare URL changes. Your coding workflow shouldn't need another round of proxy configuration.

KaggleLink gives Claude Code a stable local endpoint, discovers the current Kaggle session, and adds authentication in front of Ollama. Your model runs on Kaggle; Claude Code reads files and runs approved commands on your own computer.

**Status: alpha.** The local transport and authentication tests pass against a simulated Ollama server. A live Kaggle → Cloudflare → Claude Code session has not yet been verified for this release. No PyPI release is published; install from source.

## Why a bridge?

Ollama 0.14.0+ already exposes an Anthropic-compatible Messages API. But Cloudflare's random Quick Tunnels **do not support Server-Sent Events**, the streaming transport used by Claude Code. Pointing Claude Code at a raw `trycloudflare.com` endpoint is therefore not a reliable streaming setup.

KaggleLink transports the original response as authenticated JSON batches. The local bridge reconstructs the SSE stream byte for byte. It adds a small polling round trip, without modifying prompts, tool arguments, or model output.

```text
YOUR COMPUTER                      KAGGLE
Claude Code                        Ollama :11434
     │ Anthropic API / SSE              ▲ local HTTP / SSE
     ▼                                 │
KaggleLink :17654 ── HTTPS JSON ──► KaggleLink :17655
                   Quick Tunnel         │
                                        └─ publishes current URL
                    private GitHub repo ◄───┘
                    (optional discovery)
```

- **One launch command:** the same private registry works across Kaggle restarts.
- **No OmniRoute configuration:** Ollama handles the Anthropic API format.
- **Authenticated inference:** shared token on the tunnel; a separate temporary local token.
- **Credentials stay local:** discovery contains no bridge token; Claude doesn't inherit registry credentials.
- **Small installation:** Python standard library at runtime.
- **Portable:** a Kaggle notebook example, plus CLI commands for any Linux GPU host.

## Requirements

- Your PC: Python 3.10+ and [Claude Code](https://code.claude.com/docs/en/overview) on PATH.
- Kaggle: internet enabled, a GPU suitable for your model, Ollama 0.14.0+, and [cloudflared](https://developers.cloudflare.com/tunnel/downloads/) on PATH.
- An installed Ollama model supporting tool calling. Choose a context window that fits your GPU and task. Large contexts consume GPU memory.
- Optional automatic discovery: a **separate private GitHub repository** and fine-grained access tokens.

KaggleLink does not install Ollama, download models, allocate GPUs, or keep Kaggle sessions alive. Your Kaggle account's quotas and session limits still apply. Claude Code's advanced features vary with model and Ollama compatibility.

## Install from source

Download or clone this repository, then run in its root directory on both your PC and Kaggle:

```sh
python -m pip install .
python -m kagglelink --version
```

The `kagglelink` executable is also installed. All examples use `python -m kagglelink` so they work even when Python's scripts directory isn't on PATH.

Generate a token **once on your PC**:

```sh
python -m kagglelink token
```

Store the same value as `KAGGLELINK_TOKEN` on both devices. Treat it as a password.

## Quick start: connect with today's URL

On Kaggle, start Ollama and install your chosen model first. Set `KAGGLELINK_TOKEN` using Kaggle Secrets; see [the notebook](examples/kaggle_quickstart.ipynb).

```sh
python -m kagglelink host --model YOUR_INSTALLED_MODEL
```

This starts the protected bridge, opens a Quick Tunnel to **port 17655**, verifies the public route, and prints its URL. Leave it running. Tunnel the bridge, never Ollama's raw port 11434.

On your PC, in PowerShell:

```powershell
$env:KAGGLELINK_TOKEN = Read-Host "Shared KaggleLink token"
python -m kagglelink doctor --url https://YOUR-URL.trycloudflare.com
python -m kagglelink launch --url https://YOUR-URL.trycloudflare.com
```

`Read-Host` input is visible while typing. Use your preferred secret manager for persistent storage; do not put tokens in shell scripts or commit them.

For Bash/zsh, input without echo:

```sh
read -rsp 'Shared KaggleLink token: ' KAGGLELINK_TOKEN; echo
export KAGGLELINK_TOKEN
python -m kagglelink launch --url https://YOUR-URL.trycloudflare.com
```

Inside Claude Code, run `/status`. Confirm the base URL is `http://127.0.0.1:17654` and the selected model is your Ollama model before sending a prompt. Existing Claude settings can override environment variables; see troubleshooting below.

## Automatic URL discovery: set it up once

Keep the public source-code repository separate from your private discovery repository.

1. Create a **private**, dedicated repository, for example `YOUR_USER/kagglelink-sessions`. Initialize it with a README. Do not use a public repository or a secret gist.
2. Create a fine-grained GitHub token restricted to that repository with **Contents: read and write**. Store it on Kaggle as `KAGGLELINK_GITHUB_TOKEN` using Kaggle Secrets.
3. Create a second token restricted to that repository with **Contents: read-only**. Set it on your PC as `KAGGLELINK_GITHUB_TOKEN`.
4. Set the same `KAGGLELINK_TOKEN` on both devices. This token stays out of the registry.

Start the Kaggle host:

```sh
python -m kagglelink host --model YOUR_INSTALLED_MODEL --repo YOUR_USER/kagglelink-sessions
```

Then on your PC, every session:

```powershell
$env:KAGGLELINK_TOKEN = Read-Host "Shared KaggleLink token"
$env:KAGGLELINK_GITHUB_TOKEN = Read-Host "Read-only GitHub token"
python -m kagglelink launch --repo YOUR_USER/kagglelink-sessions
```

Save environment values in your preferred secret manager to avoid entering them each time. KaggleLink writes only URL, model name, random session ID, and update time to `sessions/default.json`. It refuses repositories that aren't private.

While Claude is running, the launcher refreshes discovery before new requests, at most every 15 seconds. It keeps an in-flight request tied to its original host. If Kaggle restarts during generation, that request fails; wait for the new host and retry. **This is session discovery, not seamless inference recovery.** Keep the same model across restarts; relaunch Claude when changing models.

Use `--channel work` on both commands to keep independent sessions. Multiple hosts using the same channel overwrite each other's record; use one host per channel.

## Commands

| Command | Purpose |
| --- | --- |
| `python -m kagglelink token` | Generate a secure shared token |
| `python -m kagglelink host --model MODEL` | Start protected host and temporary tunnel |
| `python -m kagglelink host --model MODEL --repo OWNER/PRIVATE_REPO` | Also publish current session |
| `python -m kagglelink doctor --repo OWNER/PRIVATE_REPO` | Check authentication and host reachability |
| `python -m kagglelink launch --repo OWNER/PRIVATE_REPO` | Start local bridge and Claude Code |
| `python -m kagglelink launch --url HTTPS_URL` | Connect without a discovery registry |

Pass Claude Code arguments after `--`:

```sh
python -m kagglelink launch --repo OWNER/PRIVATE_REPO -- -p "Explain this repository"
```

`launch --port 17656` changes the local port. `host --port 17657` changes the Kaggle bridge port. A named or existing tunnel can be used with `host --public-url https://ai.example.com`, provided that tunnel already forwards to the host port. Run `--help` on any command for details.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `HTTP 401` | Both machines need the same `KAGGLELINK_TOKEN`; restart the host after rotating it. |
| `HTTP 404` from GitHub | Repository name, selected repository access, token permissions, and initialized default branch. |
| Claude still connects to OmniRoute | Inspect `env`, `apiKeyHelper`, and provider settings in `~/.claude/settings.json`, project `.claude/settings.json`, local settings, and managed configuration. Remove conflicting overrides. KaggleLink does not edit these files. |
| Public tunnel never becomes ready | Internet enabled, cloudflared on PATH, and no conflicting cloudflared config. Test Ollama locally first. |
| Ollama connection fails | Start `ollama serve` on Kaggle; keep it bound to loopback; check `ollama list` and `ollama --version`. |
| Model cannot edit files | Verify actual tool-calling support; transport compatibility alone does not make a model a capable coding agent. |
| Stale URL | Restart `host --repo ...`; confirm both devices use the same channel. Discovery refreshes within 15 seconds on new requests. |
| Port already in use | Stop the previous launcher or choose another `--port`. |
| Long inference times out | Reduce prompt/context size or use a model suitable for the available GPU. Upstream socket timeout is 300 seconds. |
| `HTTP 429` | Too many retained jobs or a Cloudflare limit. Stop idle requests and retry later. |

The host publishes its session only after the tunnel authenticates successfully. Stopped sessions leave their discovery record in place; `doctor` will report a connection failure until a new host publishes.

## Development and verification

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Tests exercise real loopback HTTP servers: streaming and tool argument preservation, non-streaming JSON, token counting passthrough, upstream errors, authentication, blocked administration routes, job cleanup, private-registry enforcement, and credential isolation. The CI matrix targets Python 3.10 and 3.13 across Windows, macOS, and Linux; this matrix is configured, not a claim of completed remote runs.

Before publishing a release, complete [the live smoke test](docs/LIVE_TEST.md). Contributions and real model compatibility reports are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). See [SECURITY.md](SECURITY.md) for trust boundaries and limits.

## Sources and scope

- [Ollama's Claude Code integration](https://docs.ollama.com/integrations/claude-code)
- [Cloudflare Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/#limitations)
- [GitHub repository Contents API](https://docs.github.com/en/rest/repos/contents)

Independent community project. Not affiliated with Kaggle, Ollama, Anthropic, or Cloudflare. Using non-Claude models through Claude Code is outside Anthropic's official support. KaggleLink doesn't alter your model's capabilities or content behavior. Distributed under the [MIT license](LICENSE).
