"""Command line lifecycle for the Kaggle host and the local Claude launcher."""

import argparse
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time

from . import __version__
from .client import Connection, LocalServer
from .common import BridgeError, remote_url, request, token_from_env
from .host import HostServer
from .registry import Registry


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def stop_process(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start_tunnel(port):
    executable = shutil.which("cloudflared")
    if not executable:
        raise BridgeError("Install cloudflared on Kaggle and put it on PATH, or use --public-url")
    process = subprocess.Popen([executable, "tunnel", "--url", f"http://127.0.0.1:{port}"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    urls = queue.Queue()

    def consume():
        for line in process.stdout:
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if match:
                urls.put(match.group())
        urls.put(None)

    threading.Thread(target=consume, daemon=True).start()
    try:
        url = urls.get(timeout=60)
        if not url:
            raise BridgeError("cloudflared exited before assigning a URL")
        return process, url
    except (queue.Empty, BridgeError):
        stop_process(process)
        raise BridgeError("Cloudflare did not assign a tunnel URL within 60 seconds; check cloudflared configuration") from None
    except BaseException:
        stop_process(process)
        raise


def host(args):
    token = token_from_env("KAGGLELINK_TOKEN")
    registry = Registry(args.repo, args.channel) if args.repo else None
    if registry:
        registry.require_private()
    version = request(args.ollama.rstrip("/") + "/api/version").get("version", "")
    numbers = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not numbers or tuple(map(int, numbers.groups())) < (0, 14, 0):
        raise BridgeError("Ollama 0.14.0 or newer is required")
    models = request(args.ollama.rstrip("/") + "/api/tags").get("models", [])
    names = {m.get("name") for m in models}
    if args.model not in names and args.model + ":latest" not in names:
        raise BridgeError("Selected model is not installed; run ollama pull MODEL on Kaggle first")
    server = HostServer(("127.0.0.1", args.port), token, args.model, args.ollama)
    start_server(server)
    process = None
    try:
        if args.public_url:
            url = remote_url(args.public_url)
        else:
            process, url = start_tunnel(server.server_port)
        print("Checking tunnel readiness…", flush=True)
        ready = False
        for _ in range(30):
            try:
                info = request(url + "/bridge/info", token, timeout=5)
                ready = info.get("session") == server.session
                if ready:
                    break
            except BridgeError:
                pass
            time.sleep(1)
        if not ready:
            raise BridgeError("Public tunnel could not reach this host; check the tunnel target and network")
        if registry:
            registry.publish(url, args.model, server.session)
            print(f"Discovery updated: {args.repo} / {args.channel}", flush=True)
        print(f"KaggleLink ready · {args.model}\n{url}\nKeep this process and Kaggle running. Ctrl+C stops the host.", flush=True)
        while process is None or process.poll() is None:
            time.sleep(1)
        raise BridgeError("Cloudflare tunnel exited; restart the host to publish a fresh URL")
    finally:
        stop_process(process)
        server.shutdown()
        server.server_close()


def connection(args):
    token = token_from_env("KAGGLELINK_TOKEN")
    registry = Registry(args.repo, args.channel) if args.repo else None
    url = remote_url(args.url) if args.url else None
    return Connection(token, url, registry)


def doctor(args):
    remote = connection(args)
    info = remote.info()
    if info.get("schema") != 1 or info.get("transport") != "json-poll":
        raise BridgeError("Incompatible KaggleLink host")
    print(f"Host reachable · authenticated · model: {info['model']} · transport: JSON polling")


def claude_environment(base, model, local_token, environ=None):
    env = dict(os.environ if environ is None else environ)
    # Discovery credentials belong to the launcher, not to Claude or its subprocesses.
    env.pop("KAGGLELINK_GITHUB_TOKEN", None)
    env.pop("KAGGLELINK_TOKEN", None)
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    for key in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        env.pop(key, None)
    env.update({"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": local_token,
                "ANTHROPIC_API_KEY": "", "ANTHROPIC_MODEL": model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": model, "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": model, "CLAUDE_CODE_SUBAGENT_MODEL": model})
    return env


def launch(args):
    executable = shutil.which("claude")
    if not executable:
        raise BridgeError("Claude Code is not installed or is not on PATH")
    remote = connection(args)
    info = remote.info()
    if info.get("schema") != 1 or info.get("transport") != "json-poll":
        raise BridgeError("Incompatible KaggleLink host")
    model = info["model"]
    local_token = secrets.token_urlsafe(32)
    server = LocalServer(("127.0.0.1", args.port), remote, model, local_token)
    start_server(server)
    base = f"http://127.0.0.1:{server.server_port}"
    extra = args.claude_args
    if extra and extra[0] == "--":
        extra = extra[1:]
    print(f"KaggleLink → {model}\nLocal endpoint: {base}\nUse /status in Claude Code to confirm the endpoint.", flush=True)
    try:
        return subprocess.call([executable, "--model", model, *extra],
                               env=claude_environment(base, model, local_token))
    finally:
        server.shutdown()
        server.server_close()


def parser():
    root = argparse.ArgumentParser(description="KaggleLink · ephemeral GPU, stable Claude Code connection")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("token", help="Generate a shared token; save it securely on both devices")
    host_cmd = commands.add_parser("host", help="Run beside Ollama on Kaggle")
    host_cmd.add_argument("--model", required=True, help="Exact installed Ollama model name")
    host_cmd.add_argument("--ollama", default="http://127.0.0.1:11434")
    host_cmd.add_argument("--port", type=int, default=17655)
    host_cmd.add_argument("--public-url", help="Use an existing tunnel pointing to the host port")
    for cmd in (host_cmd,):
        cmd.add_argument("--repo", help="Dedicated private discovery repository: OWNER/REPO")
        cmd.add_argument("--channel", default="default")
    for name, help_text in (("launch", "Connect and launch Claude Code on your PC"),
                            ("doctor", "Check remote reachability and authentication")):
        cmd = commands.add_parser(name, help=help_text)
        source = cmd.add_mutually_exclusive_group(required=True)
        source.add_argument("--url", help="Current KaggleLink HTTPS tunnel URL")
        source.add_argument("--repo", help="Private discovery repository: OWNER/REPO")
        cmd.add_argument("--channel", default="default")
        if name == "launch":
            cmd.add_argument("--port", type=int, default=17654)
            cmd.add_argument("claude_args", nargs=argparse.REMAINDER, help="Arguments after -- are passed to Claude")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "token":
            print(secrets.token_urlsafe(32))
            return 0
        return {"host": host, "launch": launch, "doctor": doctor}[args.command](args) or 0
    except KeyboardInterrupt:
        print("\nKaggleLink stopped.", file=sys.stderr)
        return 130
    except (BridgeError, OSError) as exc:
        print(f"KaggleLink: {exc}", file=sys.stderr)
        return 1
