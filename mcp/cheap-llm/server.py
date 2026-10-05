# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp>=2,<3", "httpx"]
# ///
"""cheap-llm: an MCP tool that hands plain-text work to a cheap OpenRouter model.

Claude Code stays on Claude; this only sees the prompt Claude chooses to send.
API key: OPENROUTER_API_KEY, else the OS keyring item "openrouter-api-key"
(macOS Keychain, or secret-tool on Linux).
"""
import logging
import os
import subprocess

import httpx
from mcp.server.mcpserver import MCPServer

MODEL = os.getenv("CHEAP_LLM_MODEL", "deepseek/deepseek-v4-flash")
URL = "https://openrouter.ai/api/v1/chat/completions"
logging.getLogger("httpx").setLevel(logging.WARNING)

server = MCPServer("cheap-llm")


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
async def cheap_llm(prompt: str, system: str = "", max_tokens: int = 4000, reasoning: bool = False) -> str:
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
    """
    key = _api_key()
    if not key:
        return "Error: no OpenRouter key (set OPENROUTER_API_KEY or the keyring item 'openrouter-api-key'; see the README)."
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
