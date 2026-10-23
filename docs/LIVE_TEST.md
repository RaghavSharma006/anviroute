# AnviRoute live smoke test

Local simulated tests have passed. A real Kaggle inference session has not yet been verified for AnviRoute 0.2.0.

1. Keep your existing Kaggle model server and tunnel running. Confirm it exposes `/v1/models` and a Chat Completions API (or select native Anthropic mode explicitly).
2. On your PC, open a terminal in a disposable project folder. Run the full path to `anviroute.cmd run claude`.
3. Enter your current URL and actual bearer API key. Leave the key blank only if the endpoint requires none. Do not share credentials here or in a public issue.
4. Verify no model prompt appears and the detected model is the intended one. In Claude Code, `/status` must show `http://127.0.0.1:20128`.
5. Ask for a short greeting, then ask Claude to create `hello.txt` containing `Hello from AnviRoute`. Approve the file tool. Inspect the actual file.
6. Responses arrive after upstream generation completes; this mode is buffered, not live token streaming. Confirm text and tool calls both complete successfully.
7. Exit Claude. Rerun the launcher, enter a deliberately incorrect key, and confirm a clean authentication error if the endpoint enforces authentication. The key must not be echoed or saved in config.
8. Restart Kaggle's tunnel. Rerun the same launcher and paste the new URL/key. Confirm it launches without any provider/combo configuration.
9. Exit Claude and confirm the local bridge closes.

Record date, model, GPU, Claude Code version, API server version, and operating system before promoting beyond alpha. Never put API keys or active private session URLs in the public report.
