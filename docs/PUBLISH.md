# Publish AnviRoute

Repository: https://github.com/RaghavSharma006/anviroute

Description: `Paste your API URL and key, then launch Claude Code. A small local adapter for Ollama and OpenAI-compatible endpoints.`

Topics: `claude-code`, `ollama`, `kaggle`, `llm`, `python`, `developer-tools`, `api-proxy`.

Publish source, tests, documentation, `anviroute.cmd`, package metadata, and the MIT license. Exclude credentials, `.env`, build caches, active session records, and local config. Put the source ZIP and wheel on a GitHub Release. Keep legacy notebooks clearly labeled as optional.

Keep releases marked alpha until docs/LIVE_TEST.md has been completed with a real model. Record the tested model, GPU, API version, and Claude Code version. Add a real demo showing the command, the two prompts, `/status`, and an approved file edit. Hide keys and private URLs. Do not claim live compatibility based only on mocked tests.

Build release assets with:

```sh
python scripts/build_docs.py
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/build_release.py
```

Upload dist/AnviRoute-Windows.zip, the versioned wheel, and SHA256SUMS.txt to the GitHub release. The README download URL uses the v0.2.0 tag; update docs/README.template.md for a future version and rebuild the docs.

There is no PyPI release. No hosted web deployment is needed for the normal local CLI workflow. Live Kaggle verification requires a running endpoint and credentials.

After any commit, update WORK_CHECKPOINT.md with its hash, verification, deployment status, and next steps.
