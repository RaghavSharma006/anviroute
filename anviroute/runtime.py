"""Process setup with no optional integrations or third-party dependencies."""

import os
import threading


def start_server(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def claude_environment(base, model, local_token, environ=None):
    env = dict(os.environ if environ is None else environ)
    for key in ("KAGGLELINK_GITHUB_TOKEN", "KAGGLELINK_TOKEN", "ANVIROUTE_API_KEY",
                "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
        env.pop(key, None)
    env.update({"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": local_token,
                "ANTHROPIC_API_KEY": "", "ANTHROPIC_MODEL": model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": model, "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": model, "CLAUDE_CODE_SUBAGENT_MODEL": model})
    return env
