# AnviRoute live smoke test

Local simulated tests and the installed Claude Code client smoke pass for AnviRoute 0.5.0. Real Kaggle inference remains unverified.

1. Keep your existing Kaggle model server and tunnel running. Confirm it exposes `/v1/models` and a Chat Completions API (or select native Anthropic mode explicitly).
2. Run `anviroute.cmd start`. In the dashboard, save a named profile with your current URL, key, and model. Activate it and click **Check API and model**.
3. Open a second terminal in a disposable project folder. Run `anviroute.cmd run claude`. No credential or model prompts should appear.
4. Verify no model prompt appears and the detected model is the intended one. In Claude Code, `/status` must show `http://127.0.0.1:20128`.
5. Ask for a short greeting, then ask Claude to create `hello.txt` containing `Hello from AnviRoute`. Approve the file tool. Inspect the actual file.
6. Responses arrive after upstream generation completes; this mode is buffered, not live token streaming. Confirm text and tool calls both complete successfully.
7. In the test profile, enter an incorrect key and check it. Confirm a useful authentication error in **Error logs**. Restore the correct key. On Windows, restart with `anviroute.cmd start --modelname PROFILE` and verify encrypted credentials restore.
8. Restart Kaggle's tunnel. Edit the existing profile with the new URL/key, check it, and start Claude again.
9. Exit Claude and confirm the router stays available until terminal 1 is stopped with Ctrl+C.

Record date, model, GPU, Claude Code version, API server version, and operating system before promoting beyond alpha. Never put API keys or active private session URLs in the public report.
