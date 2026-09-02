# OpenAI Solar Tunnel

Runs OpenAI's official Secure MCP Tunnel client inside Home Assistant and connects it to two read-only sources:

- Home Assistant's built-in Assist MCP endpoint through a fail-closed filter.
- Ultrahuman's official Daily Metrics API using a masked Personal API Token.

The filter advertises only `GetLiveContext`, `GetUltrahumanDailyMetrics`, and `GetUltrahumanRecoverySummary`. It adds explicit read-only safety annotations and rejects every other Home Assistant tool call before it reaches Assist.

The app is intended for local-only Home Assistant installations. It does not expose Home Assistant to the internet and does not open an inbound port.

See the **Documentation** tab after installation for configuration and testing steps.
