"""Keep the README's copyable cells and executable notebook in sync."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    first = (ROOT / "examples/kaggle/01_start_ollama.py").read_text(encoding="utf-8").rstrip()
    second = (ROOT / "examples/kaggle/02_start_tunnel.py").read_text(encoding="utf-8").rstrip()
    template = (ROOT / "docs/README.template.md").read_text(encoding="utf-8")
    (ROOT / "README.md").write_text(template.replace("{{OLLAMA_CELL}}", first).replace("{{TUNNEL_CELL}}", second), encoding="utf-8")
    intro = """# AnviRoute · Kaggle API setup

Enable Internet and select a suitable GPU before running these two cells in order.
The selected 27B Q4 model has approximately 18 GB of weights before context memory;
a 16 GB GPU may require CPU offloading. Change MODEL in both cells for another model.

Cell 2 prints a real API key. Keep the notebook and outputs private. After both cells
finish, keep Kaggle running. On your PC install AnviRoute, open your project folder,
and run `anviroute`. Paste the printed output in the frontend and save a name.
In another terminal run `anviroute run claude --modename YOUR_NAME`.
Use Send test message to verify an actual reply.
"""
    cells = [{"id": "instructions", "cell_type": "markdown", "metadata": {}, "source": intro.splitlines(keepends=True)}]
    for index, source in enumerate((first, second), 1):
        cells.append({"id": f"setup-{index}", "cell_type": "code", "metadata": {}, "execution_count": None,
                      "outputs": [], "source": (source + "\n").splitlines(keepends=True)})
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                           "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    (ROOT / "examples/kaggle_anviroute.ipynb").write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("README and Kaggle notebook generated.")


if __name__ == "__main__":
    build()
