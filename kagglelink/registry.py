"""Optional discovery through a dedicated PRIVATE GitHub repository."""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .common import BridgeError, NoRedirect, remote_url


class Registry:
    def __init__(self, repo, channel="default"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise BridgeError("Registry repository must be OWNER/REPO")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", channel):
            raise BridgeError("Channel must contain 1–64 letters, digits, underscores, or hyphens")
        self.repo = repo
        self.path = f"sessions/{channel}.json"
        self.token = os.environ.get("KAGGLELINK_GITHUB_TOKEN")
        if not self.token:
            raise BridgeError("Set KAGGLELINK_GITHUB_TOKEN for private repository discovery")

    def api(self, path, data=None, missing_ok=False):
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": "application/vnd.github+json", "User-Agent": "KaggleLink/0.1",
                   "X-GitHub-Api-Version": "2022-11-28"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request("https://api.github.com/repos/" + self.repo + path,
                                     data=body, headers=headers, method="PUT" if body else "GET")
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 404 and missing_ok:
                return None
            raise BridgeError(f"GitHub returned HTTP {code}; check repository access and Contents permissions") from None
        except (OSError, ValueError):
            raise BridgeError("GitHub registry could not be reached") from None

    def require_private(self):
        if self.api("").get("private") is not True:
            raise BridgeError("Discovery requires a PRIVATE repository; public repositories are refused")

    def publish(self, url, model, session):
        self.require_private()
        path = "/contents/" + self.path
        previous = self.api(path, missing_ok=True)
        # The authentication secret is NEVER uploaded, even to this private repo.
        record = {"schema": 1, "url": remote_url(url), "model": model, "session": session,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        data = {"message": "Update KaggleLink session",
                "content": base64.b64encode(json.dumps(record).encode()).decode()}
        if previous:
            data["sha"] = previous["sha"]
        self.api(path, data)

    def resolve(self):
        self.require_private()
        item = self.api("/contents/" + self.path)
        try:
            record = json.loads(base64.b64decode(item["content"]))
            if record["schema"] != 1 or not isinstance(record["model"], str):
                raise ValueError()
            record["url"] = remote_url(record["url"])
            return record
        except (KeyError, ValueError, TypeError):
            raise BridgeError("Invalid discovery record; restart the Kaggle host") from None
