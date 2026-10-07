# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp>=2,<3", "httpx"]
# ///
"""cheap-llm: an MCP tool that hands plain-text work to a cheap OpenRouter model.

Claude Code stays on Claude; this only sees the prompt Claude chooses to send.
API key: OPENROUTER_API_KEY, else the OS keyring item "openrouter-api-key"
(macOS Keychain, or secret-tool on Linux).

Opt-in file access: set CHEAP_LLM_ROOT to a directory and the `paths` argument can
attach files under it to the prompt. Unset, `paths` is refused. Files that look like
secrets are never read, and total size is capped (CHEAP_LLM_MAX_BYTES, default 200000).
"""
import fnmatch
import logging
import os
import subprocess
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

MODEL = os.getenv("CHEAP_LLM_MODEL", "deepseek/deepseek-v4-flash")
URL = "https://openrouter.ai/api/v1/chat/completions"
logging.getLogger("httpx").setLevel(logging.WARNING)

MAX_BYTES = int(os.getenv("CHEAP_LLM_MAX_BYTES", "200000"))
# Matched against every path component, case-insensitively.
DENY = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.kdbx", "id_rsa*", "id_ed25519*",
        "*secret*", "*credential*", "*.tfstate", "*.tfvars", ".netrc", ".npmrc", ".pypirc", ".git", ".ssh", ".aws")

server = MCPServer("cheap-llm")


def _read_paths(paths: list[str]) -> str:
    """Return the files as a prompt block. Raises ValueError if any path is refused."""
    root_env = os.getenv("CHEAP_LLM_ROOT", "")
    if not root_env:
        raise ValueError("file access is off; set CHEAP_LLM_ROOT to a directory to enable `paths`")
    root = Path(root_env).expanduser().resolve()
    blocks, total = [], 0
    for raw in paths:
        p = (root / raw).resolve()  # resolves symlinks and ".."; absolute paths replace root and fail below
        if not p.is_relative_to(root):
            raise ValueError(f"{raw}: outside CHEAP_LLM_ROOT")
        rel = p.relative_to(root)
        for part in rel.parts:
            if any(fnmatch.fnmatch(part.lower(), pat) for pat in DENY):
                raise ValueError(f"{raw}: refused (looks like a secret or VCS/credential path)")
        if not p.is_file():
            raise ValueError(f"{raw}: not a file")
        data = p.read_bytes()
        total += len(data)
        if total > MAX_BYTES:
            raise ValueError(f"attached files exceed {MAX_BYTES} bytes")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"{raw}: not UTF-8 text") from None
        blocks.append(f"=== {rel} ===\n{text}")
    return "\n\n".join(blocks)


def _api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if key:
        return key
    lookups = (
        ["security", "find-generic-password", "-s", "openrouter-api-key", "-w"],  # macOS
        ["secret-tool", "lookup", "service", "openrouter-api-key"],  # Linux
    )
    for cmd in lookups:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        if out:
            return out
    return ""


@server.tool()
async def cheap_llm(prompt: str, system: str = "", max_tokens: int = 4000, reasoning: bool = False,
                    paths: list[str] | None = None) -> str:
    """Send a self-contained text task to a cheap non-Claude model (DeepSeek V4 Flash via OpenRouter) and return its answer.

    Use it for bulk, low-stakes text work where the full input fits in the prompt:
    summarising long logs or docs, drafting boilerplate, translating, reformatting,
    extracting fields, first-pass classification. Check its output before relying on it.

    Don't use it for anything that needs the repository, tools, or careful judgement,
    and never put secrets, credentials, API keys, customer data or private source code
    in the prompt: it leaves the machine for a third-party provider.

    Args:
        prompt: The full task and input text; the model sees nothing else.
        system: Optional system instruction.
        max_tokens: Output cap (default 4000), reasoning tokens included.
        reasoning: Let the model think first (slower, more tokens); off by default.
        paths: Optional files, relative to CHEAP_LLM_ROOT, whose contents are appended to the
            prompt. Only works when the user has set CHEAP_LLM_ROOT; their contents leave the
            machine, so attach only what the user has cleared for a third party.
    """
    key = _api_key()
    if not key:
        return "Error: no OpenRouter key (set OPENROUTER_API_KEY or the keyring item 'openrouter-api-key'; see the README)."
    if paths:
        try:
            prompt = f"{prompt}\n\nAttached files:\n\n{_read_paths(paths)}"
        except (ValueError, OSError) as e:
            return f"Error: {e}"
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "reasoning": {"enabled": reasoning},
        # Only providers that don't store or train on prompts
        "provider": {"data_collection": "deny"},
    }
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(URL, json=body, headers={"Authorization": f"Bearer {key}", "X-Title": "claude-code cheap-llm"})
        if r.status_code != 200:
            return f"Error: OpenRouter {r.status_code}: {r.text[:500]}"
        data = r.json()
        text = data["choices"][0]["message"]["content"] or ""
        u = data.get("usage") or {}
        return f"{text}\n\n[{MODEL} · {u.get('prompt_tokens', '?')} in / {u.get('completion_tokens', '?')} out tokens]"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


if __name__ == "__main__":
    server.run()
