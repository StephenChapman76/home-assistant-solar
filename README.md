# Home Assistant Solar Tunnel

A small Home Assistant app that connects the built-in Home Assistant MCP Server to an OpenAI Secure MCP Tunnel. It is designed for a local-only Home Assistant installation and needs no inbound router port, public Home Assistant URL, Nabu Casa subscription, or long-lived Home Assistant access token.

The companion `home-assistant-solar` skill adds a strict read-only workflow for seven GivTCP solar and battery sensors.

## Security model

- The app makes outbound HTTPS connections to OpenAI.
- Home Assistant injects a short-lived internal Supervisor token when the app starts.
- The tunnel target is fixed to `http://supervisor/core/api/mcp/assist`.
- Home Assistant remains the source of truth for which entities are exposed.
- The intended Assist exposure list contains sensors only; no inverter controls are included.
- OpenAI runtime API keys are entered in Home Assistant's masked app configuration and are never stored in this repository.

## Install

1. In Home Assistant, open **Settings → Apps → App store**.
2. Open the app-store menu and select **Repositories**.
3. Add `https://github.com/StephenChapman76/home-assistant-solar`.
4. Install **OpenAI Solar Tunnel**.
5. On the Configuration tab, enter the OpenAI tunnel ID and a runtime API key with tunnel Read and Use access.
6. Start the app and inspect its log before creating the ChatGPT app connection.

Detailed instructions are in [`openai_solar_tunnel/DOCS.md`](openai_solar_tunnel/DOCS.md).

## Components

- `openai_solar_tunnel/`: Home Assistant app that runs OpenAI's official tunnel client.
- `skills/home-assistant-solar/`: read-only solar interpretation and safety instructions.
- `.codex-plugin/plugin.json`: personal plugin manifest.

## Upstream software

The container copies the official [`openai/tunnel-client`](https://github.com/openai/tunnel-client) binary from OpenAI's pinned container image. That project is licensed under Apache-2.0.
