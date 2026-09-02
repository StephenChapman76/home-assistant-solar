# Changelog

## 0.3.1

- Fixed recovery-summary extraction for Ultrahuman's typed metric objects.
- Added automatic extraction of average sleep HRV, sleeping resting HR, and Recovery Index.
- Continues to report an overall Recovery Score as missing when Ultrahuman does not supply one.

## 0.3.0

- Added read-only access to the official Ultrahuman Daily Metrics API.
- Added `GetUltrahumanDailyMetrics` for a complete single-day response.
- Added `GetUltrahumanRecoverySummary` for concise training-readiness metrics.
- Stored the Ultrahuman Personal API Token only in masked Home Assistant app configuration.
- Kept the Home Assistant server boundary fail-closed; no new Home Assistant actions are exposed.

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
