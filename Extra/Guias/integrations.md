# Integraciones MCP con editores

Esta guía resume cómo conectar este servidor MCP con herramientas de coding. También puedes usar la pestaña `Dashboard → Integrations` para copiar snippets con la URL actual de tu instancia.

## Codex CLI
- Edita `~/.codex/config.toml` y pega:

```toml
rmcp_client = true

[mcp_servers.contextarium_local]
url = "http://127.0.0.1:8000/mcp"
startup_timeout_sec = 2
tool_timeout_sec = 60
```

Ajusta `url` y timeouts según tu entorno.

## Claude Code
Añade el servidor MCP HTTP:

```bash
claude mcp add --transport http contextarium http://127.0.0.1:8000/mcp
```

Verifica con:

```bash
claude mcp list
```

Puedes cambiar el `name` y `--scope user|project|local`.

## GitHub Copilot (VS Code)
Configura el servidor vía archivo del proyecto:

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

Guarda como `.vscode/mcp.json` y usa “MCP: List Servers” en la paleta de comandos para verificar.
