#!/usr/bin/env bash
# Installs the Haiku subagents, the cheap-llm MCP server and the routing rules
# into ~/.claude for the current user. Safe to re-run.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
claude_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

for tool in claude uv; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool' on PATH. Install it first." >&2; exit 1; }
done

mkdir -p "$claude_dir/agents" "$claude_dir/mcp/cheap-llm"
cp "$here"/agents/*.md "$claude_dir/agents/"
cp "$here/mcp/cheap-llm/server.py" "$claude_dir/mcp/cheap-llm/server.py"
echo "Installed agents and server into $claude_dir"

claude mcp remove --scope user cheap-llm >/dev/null 2>&1 || true
claude mcp add --scope user cheap-llm -- uv run --quiet --script "$claude_dir/mcp/cheap-llm/server.py"

md="$claude_dir/CLAUDE.md"
if ! grep -q '^## Cheap models for simple work' "$md" 2>/dev/null; then
  { [ -s "$md" ] && echo; cat "$here/claude-md-snippet.md"; } >> "$md"
  echo "Added routing rules to $md"
fi

has_key() {
  [ -n "${OPENROUTER_API_KEY:-}" ] && return 0
  security find-generic-password -s openrouter-api-key -w 2>/dev/null | grep -q . && return 0
  secret-tool lookup service openrouter-api-key 2>/dev/null | grep -q . && return 0
  return 1
}
if has_key; then
  echo "OpenRouter key found."
else
  echo
  echo "No OpenRouter key yet. Store one (you'll be prompted; it isn't echoed):"
  if [ "$(uname)" = Darwin ]; then
    echo "  security add-generic-password -U -s openrouter-api-key -a \"\$USER\" -w"
  else
    echo "  secret-tool store --label='OpenRouter API key' service openrouter-api-key"
    echo "  (or export OPENROUTER_API_KEY in your shell profile)"
  fi
fi
echo "Done. Start a new Claude Code session; /mcp should list cheap-llm."
