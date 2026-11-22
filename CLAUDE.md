# Project rules

- After every change: add an entry under `## [Unreleased]` (or a new version) in `CHANGELOG.md`,
  and update `README.md` if tools, setup, or config changed.
- Run `pytest` and `ruff check .` before committing.
- MCP SDK is 2.x: use `from mcp.server.mcpserver import MCPServer` (not FastMCP).
- Never commit credentials or token files.
