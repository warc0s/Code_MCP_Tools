# MCP Integrations With Editors

This guide summarizes how to connect this MCP server to coding tools. You can also use the `Dashboard -> Integrations` tab to copy snippets with the current URL of your instance.

## Codex CLI

Edit `~/.codex/config.toml` and paste:

```toml
rmcp_client = true

[mcp_servers.contextarium_local]
url = "http://127.0.0.1:8000/mcp"
startup_timeout_sec = 2
tool_timeout_sec = 60
```

Adjust `url` and timeouts for your environment.

## Claude Code

Add the HTTP MCP server:

```bash
claude mcp add --transport http contextarium http://127.0.0.1:8000/mcp
```

Verify with:

```bash
claude mcp list
```

You can change the `name` and `--scope user|project|local`.

## GitHub Copilot (VS Code)

Configure the server through a project file:

```json
{
  "servers": {
    "contextarium": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Save it as `.vscode/mcp.json` and use “MCP: List Servers” from the Command Palette to verify it.
