# Publish AnviRoute

Repository: https://github.com/RaghavSharma006/anviroute

The primary release is one self-installing `AnviRoute.cmd`, with a tiny compressed Python zipapp embedded. It uses existing Python; no pip or virtual environment is installed. The normal flow is download → open → URL/key.

Build and check:

```sh
python scripts/build_release.py
python scripts/build_docs.py
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Commit and push after checks. Update local WORK_CHECKPOINT.md after every commit. Create a new version tag and upload `dist/AnviRoute.cmd`, `anviroute.pyz`, optional `AnviRoute-Windows.zip`, and `SHA256SUMS.txt`. Make the release latest so the README's stable download link resolves to the new command. Verify server asset SHA-256 digests and public downloads.

Keep alpha status until docs/LIVE_TEST.md is completed with a real model. Record model/GPU/API/Claude versions. Never claim real inference passed based only on simulated tests.

The source repository contains tests, docs, and Kaggle examples; those are intentionally excluded from the tiny runtime. There is no PyPI release and no hosted web deployment. Existing model hosting remains on Kaggle.
