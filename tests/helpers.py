import json
import urllib.request
import urllib.error
from anviroute.common import BridgeError, NoRedirect

def request(url, token=None, data=None, method=None, timeout=30):
    headers = {"Accept": "application/json", "User-Agent": "AnviRoute tests"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise BridgeError(f"HTTP {code}: check credentials, session, and configuration") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise BridgeError("Connection failed: check that Kaggle and the tunnel are running") from None
