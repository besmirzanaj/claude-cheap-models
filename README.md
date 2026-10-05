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
git clone git@github.com:besmirzanaj/claude-cheap-models.git
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

Re-run `./install.sh` after pulling to update.
