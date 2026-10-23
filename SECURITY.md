# AnviRoute security

AnviRoute's normal workflow is PC-only. Named profiles save URL, model, and format. Windows saves API keys encrypted with user-bound DPAPI. Other platforms keep keys in memory only. The dashboard never returns saved keys, and upstream credentials are removed from Claude's child environment. Processes running as your Windows user may decrypt DPAPI data. Protect your account and profile folder.

The single-file Windows download contains a compressed standard-library application and its per-user setup script. It uses your existing Python, installs no third-party packages, and verifies the embedded payload's SHA-256 before writing it. This checksum detects corruption; it is not a publisher signature. Download from the project's official GitHub releases.

The local API binds to 127.0.0.1 and uses a random token per launch. It does not expose the upstream administration API. Public upstream URLs must be HTTPS; redirects are refused to avoid forwarding keys to a different origin. The upstream service and any TLS-terminating tunnel provider remain part of the trust boundary. This does not protect against malware running as your user.

AnviRoute does not add authentication to your existing Kaggle server. An empty key works only if that server permits it. Protect the upstream separately. Browser login flows and custom Cloudflare Access authentication are not supported.

Claude's own settings can override environment variables. Check `/status` before real use. Keep Claude's usual permission checks enabled. Requests are buffered with a 16 MiB response cap; long inference can fail at provider/tunnel timeouts. OpenAI-mode token counts are heuristics, not billing counts.

Report issues privately to the repository owner using GitHub security advisories when available. Never post working credentials or private source in a public issue.

The dashboard checks Host and Origin and requires a local control token. Local HTML contains this token; processes running as your user are trusted. Rotating event logs record metadata only, redact known keys and the current token, and exclude request/response bodies. Profile names and timestamps can appear in exported logs; review exports before sharing.
