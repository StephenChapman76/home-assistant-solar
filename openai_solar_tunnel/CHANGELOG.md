# Changelog

## 0.2.0

- Added a fail-closed MCP proxy that exposes only `GetLiveContext`.
- Blocked every Home Assistant write/action tool at the server boundary.
- Added explicit read-only, non-destructive, closed-world MCP annotations.
- Limited MCP resources to the read-only Assist context snapshot.

## 0.1.0

- Initial Home Assistant app for OpenAI Secure MCP Tunnel.
- Fixed MCP target to the Home Assistant Assist endpoint.
- Added masked runtime-key configuration and internal health monitoring.
- Added read-only seven-sensor setup guidance.
