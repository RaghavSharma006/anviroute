# AnviRoute live smoke test

Local simulated tests and the installed Claude Code client smoke pass for AnviRoute 0.6.0. Real Kaggle inference remains unverified.

1. Keep your existing Kaggle model server and tunnel running. Confirm it exposes `/v1/models` and a Chat Completions API (or select native Anthropic mode explicitly).
2. Run `anviroute`. Give your model a name, paste Kaggle's output, and click **Save & connect**. Detection and inference checks run automatically.
3. In a second terminal in a disposable project, run `anviroute run claude --modename NAME`. No credential or model prompts should appear.
4. Verify no model prompt appears and the detected model is the intended one. In Claude Code, `/status` must show `http://127.0.0.1:20128`.
5. Ask for a short greeting, then ask Claude to create `hello.txt` containing `Hello from AnviRoute`. Approve the file tool. Inspect the actual file.
6. Responses arrive after upstream generation completes; this mode is buffered, not live token streaming. Confirm text and tool calls both complete successfully.
7. In the saved model, paste output with an incorrect key and click **Update & reconnect**. Confirm an error in **Error logs** and restore the correct key. Restart `anviroute` and verify encrypted Windows credentials restore.
8. Restart Kaggle's tunnel. Paste its new output into the saved model's update box and click **Update & reconnect**. Keep the same saved name and Claude command. Confirm subsequent named requests use the new address.
9. Exit Claude and confirm the router stays available until terminal 1 is stopped with Ctrl+C.

Record date, model, GPU, Claude Code version, API server version, and operating system before promoting beyond alpha. Never put API keys or active private session URLs in the public report.
