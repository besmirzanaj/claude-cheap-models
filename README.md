# claude-cheap-models

Keeps Claude Code on Claude for the real work and hands simple work to cheaper models:

- `agents/search.md`, `agents/simple-edit.md`: user-level subagents pinned to Haiku.
- `mcp/cheap-llm/server.py`: an MCP tool, `cheap_llm`, that sends a self-contained
  text task to `deepseek/deepseek-v4-flash` on OpenRouter. Reasoning is off unless
  the caller passes `reasoning: true`. Only OpenRouter providers that don't store
  or train on prompts are used.
- `claude-md-snippet.md`: routing rules appended to `~/.claude/CLAUDE.md`.

No gateway sits in front of Claude Code; the cheap model only sees the prompt
Claude sends to the tool.

## Install

Needs [Claude Code](https://claude.com/claude-code) and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/besmirzanaj/claude-cheap-models.git
cd claude-cheap-models && ./install.sh
```

Then store your OpenRouter key (the installer prints the command for your OS):

```bash
# macOS
security add-generic-password -U -s openrouter-api-key -a "$USER" -w
# Linux
secret-tool store --label='OpenRouter API key' service openrouter-api-key
```

`OPENROUTER_API_KEY` in the environment also works and takes precedence.
Set `CHEAP_LLM_MODEL` to use a different OpenRouter model.

### Optional file access

Off by default. Set `CHEAP_LLM_ROOT=/path/to/repo` in the MCP server's environment and
the tool accepts `paths` (relative to that root) whose contents are appended to the
prompt. Paths outside the root (including via symlinks), secret-looking names (`.env`,
`*.pem`, `*.key`, `*secret*`, `.git`, `.ssh`, ...) and non-UTF-8 files are refused;
total size is capped by `CHEAP_LLM_MAX_BYTES` (default 200000). Attached files go to
OpenRouter, so enable it only for repos you are willing to send to a third party.

`./install.sh` already registers the server, so `claude mcp add` would fail with
"already exists". To enable file access, replace the registration:

```bash
claude mcp remove cheap-llm --scope user
claude mcp add --scope user -e CHEAP_LLM_ROOT=/path/to/repo cheap-llm \
  -- uv run --quiet --script ~/.claude/mcp/cheap-llm/server.py
```

Restart Claude Code afterwards. `CHEAP_LLM_ROOT` must be a single repo; to reset, run the
same two commands without `-e`.

Re-run `./install.sh` after pulling to update.
