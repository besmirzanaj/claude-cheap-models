"""End to end: run the real installer into a throwaway config directory, then
drive the installed MCP server over stdio against a fake OpenRouter."""
import asyncio
import json
import os
import pathlib
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = pathlib.Path(__file__).resolve().parents[1]
UV = shutil.which("uv")


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sandbox(tmp_path):
    """A fake home with a stub `claude` that records how it was called."""
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    home.mkdir()
    bin_dir.mkdir()
    calls = tmp_path / "claude-calls.log"
    stub = bin_dir / "claude"
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n')
    stub.chmod(0o755)
    # Only uv is linked in, so a real `claude` next to it can never be picked up
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "uv").symlink_to(UV)
    env = {
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "PATH": f"{bin_dir}:{tools}:/usr/bin:/bin",
        # uv's cache and Pythons live under the real home; keep using them
        "UV_CACHE_DIR": subprocess.run([UV, "cache", "dir"], capture_output=True, text=True).stdout.strip(),
        "UV_PYTHON_INSTALL_DIR": subprocess.run([UV, "python", "dir"], capture_output=True, text=True).stdout.strip(),
    }
    return {"home": home, "config": home / ".claude", "calls": calls, "env": env, "tools": tools}


def install(sandbox):
    return subprocess.run([str(REPO / "install.sh")], env=sandbox["env"],
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def openrouter():
    """A local stand-in for OpenRouter that records each request."""
    seen = []
    reply = {"status": 200, "body": {
        "choices": [{"message": {"content": "pong"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
            data = json.dumps(reply["body"]).encode()
            self.send_response(reply["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"url": f"http://127.0.0.1:{server.server_port}/api/v1/chat/completions", "seen": seen, "reply": reply}
    server.shutdown()


def call_tool(sandbox, arguments, **env):
    """Start the installed server the way Claude Code does and call cheap_llm."""
    server = sandbox["config"] / "mcp" / "cheap-llm" / "server.py"
    params = StdioServerParameters(command=UV, args=["run", "--quiet", "--script", str(server)],
                                   env={**sandbox["env"], **env})

    async def go():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = [t.name for t in (await session.list_tools()).tools]
                result = await session.call_tool("cheap_llm", arguments)
                return tools, result.content[0].text
    return asyncio.run(go())


# ── Installer ───────────────────────────────────────────────────────────────

def test_install_puts_everything_in_place(sandbox):
    run = install(sandbox)
    assert run.returncode == 0, run.stderr
    config = sandbox["config"]
    for agent in ("search.md", "simple-edit.md"):
        assert "model: haiku" in (config / "agents" / agent).read_text()
    assert (config / "mcp" / "cheap-llm" / "server.py").exists()
    assert "## Cheap models for simple work" in (config / "CLAUDE.md").read_text()
    calls = sandbox["calls"].read_text()
    assert "mcp add --scope user cheap-llm" in calls
    assert str(config / "mcp" / "cheap-llm" / "server.py") in calls


def test_install_twice_changes_nothing_and_keeps_existing_instructions(sandbox):
    sandbox["config"].mkdir()
    (sandbox["config"] / "CLAUDE.md").write_text("# Mine\n\n- keep this\n")
    assert install(sandbox).returncode == 0
    first = (sandbox["config"] / "CLAUDE.md").read_text()
    assert install(sandbox).returncode == 0
    again = (sandbox["config"] / "CLAUDE.md").read_text()
    assert again == first
    assert again.startswith("# Mine\n\n- keep this\n")
    assert again.count("## Cheap models for simple work") == 1


def test_install_says_how_to_store_a_key_when_there_is_none(sandbox):
    out = install(sandbox).stdout
    assert "No OpenRouter key yet" in out and "openrouter-api-key" in out


def test_install_stops_when_claude_is_missing(sandbox):
    env = {**sandbox["env"], "PATH": f"{sandbox['tools']}:/usr/bin:/bin"}
    run = subprocess.run([str(REPO / "install.sh")], env=env, capture_output=True, text=True)
    assert run.returncode != 0 and "Missing 'claude'" in run.stderr
    assert not sandbox["config"].exists()


# ── The installed tool ──────────────────────────────────────────────────────

def test_cheap_llm_answers_through_the_installed_server(sandbox, openrouter):
    install(sandbox)
    tools, text = call_tool(sandbox, {"prompt": "Reply with exactly: pong", "system": "Be brief"},
                            OPENROUTER_API_KEY="sk-or-test", CHEAP_LLM_URL=openrouter["url"])
    assert tools == ["cheap_llm"]
    assert text.startswith("pong") and "10 in / 3 out tokens" in text
    sent = openrouter["seen"][0]
    assert sent["auth"] == "Bearer sk-or-test"
    body = sent["body"]
    assert body["model"] == "deepseek/deepseek-v4-flash"
    assert body["messages"] == [{"role": "system", "content": "Be brief"},
                                {"role": "user", "content": "Reply with exactly: pong"}]
    assert body["reasoning"] == {"enabled": False}          # off unless asked for
    assert body["provider"] == {"data_collection": "deny"}  # never a provider that keeps prompts


def test_reasoning_and_model_can_be_changed(sandbox, openrouter):
    install(sandbox)
    call_tool(sandbox, {"prompt": "hard one", "reasoning": True, "max_tokens": 50},
              OPENROUTER_API_KEY="sk-or-test", CHEAP_LLM_URL=openrouter["url"],
              CHEAP_LLM_MODEL="some/other-model")
    body = openrouter["seen"][0]["body"]
    assert body["reasoning"] == {"enabled": True}
    assert body["model"] == "some/other-model" and body["max_tokens"] == 50


def test_an_upstream_error_is_reported_not_raised(sandbox, openrouter):
    install(sandbox)
    openrouter["reply"].update(status=402, body={"error": {"message": "Insufficient credits"}})
    _, text = call_tool(sandbox, {"prompt": "x"}, OPENROUTER_API_KEY="sk-or-test", CHEAP_LLM_URL=openrouter["url"])
    assert text.startswith("Error: OpenRouter 402") and "Insufficient credits" in text


def test_without_a_key_nothing_is_sent(sandbox, openrouter):
    install(sandbox)
    _, text = call_tool(sandbox, {"prompt": "x"}, CHEAP_LLM_URL=openrouter["url"])
    assert text.startswith("Error: no OpenRouter key")
    assert openrouter["seen"] == []


@pytest.mark.skipif(not os.getenv("OPENROUTER_LIVE_KEY"), reason="set OPENROUTER_LIVE_KEY to call the real OpenRouter")
def test_live_call_to_openrouter(sandbox):
    install(sandbox)
    _, text = call_tool(sandbox, {"prompt": "Reply with exactly: pong", "max_tokens": 20},
                        OPENROUTER_API_KEY=os.environ["OPENROUTER_LIVE_KEY"])
    assert "pong" in text.lower()
