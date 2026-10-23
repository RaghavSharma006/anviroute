"""Kaggle cell 1: install Ollama, start it, and pull the selected model."""

import os
import time
import shutil
import subprocess
import requests

MODEL = "orcarouter/Qwen3.8-27B-Uncensored:q4_K_M"
# 32K is a memory compromise; larger projects may need 64K+ and more VRAM.
CONTEXT_LENGTH = 32768
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
# Re-running this cell applies settings to the Ollama process this notebook owns.
previous_ollama = globals().get("ollama_proc")
if isinstance(previous_ollama, subprocess.Popen) and previous_ollama.poll() is None:
    previous_ollama.terminate()
    previous_ollama.wait(timeout=30)
try:
    requests.get(OLLAMA + "/api/tags", timeout=3).raise_for_status()
except requests.RequestException:
    with open(WORK + "/ollama.log", "a") as log:
        ollama_proc = subprocess.Popen(
            ["ollama", "serve"], stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434",
                "OLLAMA_KEEP_ALIVE": "30m", "OLLAMA_NUM_PARALLEL": "1",
                "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_CONTEXT_LENGTH": str(CONTEXT_LENGTH)},
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

# Warm the model locally before the tunnel is used; report actual placement.
warm = requests.post(OLLAMA + "/api/generate", json={
    "model": MODEL, "keep_alive": "30m", "stream": False,
    "options": {"num_ctx": CONTEXT_LENGTH},
}, timeout=(10, 600))
warm.raise_for_status()
print("Loaded model / CPU-GPU placement:")
subprocess.run(["ollama", "ps"], check=True)
print("Context requested:", CONTEXT_LENGTH)
print("If Ollama was already running, restart the Kaggle session to apply server settings.")
print("✅ Ollama ready")
print("✅ Model:", MODEL)
