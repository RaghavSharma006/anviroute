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
