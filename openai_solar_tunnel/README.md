# OpenAI Solar Tunnel

Runs OpenAI's official Secure MCP Tunnel client inside Home Assistant and connects it to the built-in Assist MCP endpoint through a fail-closed read-only filter.

The filter exposes only `GetLiveContext`, adds explicit read-only safety annotations, and rejects every other Home Assistant tool call before it reaches Assist.

The app is intended for local-only Home Assistant installations. It does not expose Home Assistant to the internet and does not open an inbound port.

See the **Documentation** tab after installation for configuration and testing steps.
