# Contributing

Start with an issue describing the problem and a reproducible example. Never include tokens, private registry records, prompts containing private code, or active tunnel URLs.

```sh
python -m pip install -e .
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/build_docs.py
```

Changes to transport should include an integration test exercising the host and local bridge against a fake Ollama server. Keep the runtime dependency-free. Explain user-visible behavior and verification in pull requests.

Useful contributions: testing real Kaggle GPU/model combinations, improving reconnect errors, documenting platform-specific setup, and measuring polling latency. CI coverage does not establish compatibility with every Claude Code or model release.
