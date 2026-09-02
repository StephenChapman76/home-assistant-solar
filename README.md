# Home Assistant Solar and Ultrahuman Tunnel

A small Home Assistant app that connects two read-only data sources to an OpenAI Secure MCP Tunnel:

- The built-in Home Assistant MCP Server, through a fail-closed local filter.
- Ultrahuman's official Daily Metrics API, using a Personal API Token stored in masked Home Assistant configuration.

It is designed for a local-only Home Assistant installation and needs no inbound router port, public Home Assistant URL, Nabu Casa subscription, or long-lived Home Assistant access token.

The companion `home-assistant-solar` skill retains a strict read-only workflow for seven GivTCP solar and battery sensors.

## Security model

- The app makes outbound HTTPS connections to OpenAI and Ultrahuman.
- Home Assistant injects a short-lived internal Supervisor token when the app starts.
- A local filter sits between the tunnel and `http://supervisor/core/api/mcp/assist`.
- Only `GetLiveContext`, `GetUltrahumanDailyMetrics`, and `GetUltrahumanRecoverySummary` are advertised or callable.
- Every other Home Assistant action is blocked server-side.
- Ultrahuman access is fixed to the authenticated user's own `daily_metrics` endpoint; no email parameter, write method, or partner-user access is supported.
- Home Assistant remains the source of truth for which entities are exposed.
- The intended Assist exposure list contains sensors only; no inverter controls are included.
- OpenAI runtime and Ultrahuman API keys are entered in Home Assistant's masked app configuration and are never stored in this repository.

## Install

1. In Home Assistant, open **Settings → Apps → App store**.
2. Open the app-store menu and select **Repositories**.
3. Add `https://github.com/StephenChapman76/home-assistant-solar`.
4. Install **OpenAI Solar Tunnel**.
5. On the Configuration tab, enter the OpenAI tunnel ID, a runtime API key with tunnel Read and Use access, and your Ultrahuman Personal API Token.
6. Start the app and inspect its log before testing the ChatGPT app connection.

Detailed instructions are in [`openai_solar_tunnel/DOCS.md`](openai_solar_tunnel/DOCS.md).

## Components

- `openai_solar_tunnel/`: Home Assistant app that runs OpenAI's official tunnel client and the read-only Ultrahuman tools.
- `skills/home-assistant-solar/`: read-only solar interpretation and safety instructions.
- `.codex-plugin/plugin.json`: personal plugin manifest.

## Upstream software

The container copies the official [`openai/tunnel-client`](https://github.com/openai/tunnel-client) binary from OpenAI's pinned container image. That project is licensed under Apache-2.0.
