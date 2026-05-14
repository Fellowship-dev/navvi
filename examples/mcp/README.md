# MCP Client Config Examples

Copy one of these examples into your MCP client config and replace the
`NAVVI_GPG_PASSPHRASE` placeholder with your own stable passphrase.

## Cursor

For project-specific tools, create `.cursor/mcp.json` in your project and use:

```json
{
  "mcpServers": {
    "navvi": {
      "command": "uvx",
      "args": ["navvi@latest"],
      "env": {
        "NAVVI_GPG_PASSPHRASE": "pick-any-random-string-here"
      }
    }
  }
}
```

The same JSON is available in `cursor.mcp.json`.

## Windsurf

Open Windsurf's raw MCP config at `~/.codeium/windsurf/mcp_config.json` and use:

```json
{
  "mcpServers": {
    "navvi": {
      "command": "uvx",
      "args": ["navvi@latest"],
      "env": {
        "NAVVI_GPG_PASSPHRASE": "pick-any-random-string-here"
      }
    }
  }
}
```

The same JSON is available in `windsurf.mcp_config.json`.

## Notes

- `NAVVI_GPG_PASSPHRASE` enables Navvi's credential vault. Keep it stable for
  the Docker volume that stores credentials.
- Restart or refresh MCP servers in your client after changing the config.
- These examples use `uvx navvi@latest`, matching the top-level README quick
  start.

References:

- Cursor MCP project configuration: https://docs.cursor.com/advanced/model-context-protocol
- Windsurf Cascade MCP configuration: https://docs.windsurf.com/windsurf/cascade/mcp
