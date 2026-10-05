## Cheap models for simple work

- Delegate read-only searches to the `search` subagent and already-decided mechanical edits to `simple-edit` (both Haiku). Keep design, debugging and judgement in the main session.
- The `cheap_llm` MCP tool (DeepSeek V4 Flash via OpenRouter) is for self-contained text tasks: summarising logs or docs, boilerplate, translation, reformatting. Never send it secrets, keys, customer data or private source code; it goes to a third party.
