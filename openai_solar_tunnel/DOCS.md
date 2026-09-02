# OpenAI Solar Tunnel

## Before installation

Confirm all of the following:

1. The Home Assistant **Model Context Protocol Server** integration is installed.
2. Assist exposes only the intended seven solar and battery sensors.
3. No GivTCP control, switch, number, select, automation, scene, or script is exposed.
4. An OpenAI Secure MCP Tunnel has been created for the correct organization and ChatGPT workspace.
5. You have a separate OpenAI runtime API key. Do not use an admin key for the running app.
6. You have generated a Personal API Token in Ultrahuman Vision Developer Access.

## Configuration

Enter three values on the app's **Configuration** tab:

- **OpenAI tunnel ID**: starts with `tunnel_`. It identifies the tunnel and is not a secret.
- **OpenAI runtime API key**: a secret key used by the running tunnel client. Its user needs Tunnels Read and Use permissions.
- **Ultrahuman API token**: the Personal API Token generated for your own Ultrahuman account.

Select **Save**, then start the app.

Both API keys are masked Home Assistant configuration values. Never paste either key into chat, screenshots, GitHub, or diagnostic logs.

## Verify the connection

Open the app's **Log** tab. A successful start should show that the read-only filter started and that the tunnel client is polling the OpenAI control plane. The app's watchdog checks `/healthz` internally.

If it does not become ready:

1. Recheck the tunnel ID for typing errors.
2. Confirm the runtime API key belongs to a user with Tunnels Read and Use permissions.
3. Confirm the Home Assistant MCP Server integration is loaded.
4. Confirm Home Assistant has internet access to both `api.openai.com` and `partner.ultrahuman.com` over HTTPS.
5. Restart the app after correcting the configuration.

## Read-only boundary

The app forwards Home Assistant requests to the built-in `/api/mcp/assist` endpoint through a fail-closed local filter. The filter exposes only `GetLiveContext`, adds explicit read-only annotations, and rejects every other Home Assistant tool call before it reaches Assist. Home Assistant's exposed-entity list remains the source of truth for which sensor states `GetLiveContext` can return.

The same filter handles two local Ultrahuman tools. Both make `GET` requests to Ultrahuman's fixed official `daily_metrics` endpoint for the authenticated user's own account:

- `GetUltrahumanDailyMetrics`: complete response for a required `YYYY-MM-DD` date.
- `GetUltrahumanRecoverySummary`: recovery, sleep score, sleeping HRV and RHR, sleep duration/stages/efficiency, temperature deviation, SpO2, and recovery index when supplied by Ultrahuman.

No Ultrahuman email parameter, write endpoint, or partner access to another user's account is supported.

The intended Home Assistant sensor set remains:

- GivTCP Power SOC
- GivTCP Power SOC kWh
- GivTCP Power PV Power
- GivTCP Power Load Power
- GivTCP Power Grid Power
- GivTCP Power Battery Power
- GivTCP Energy PV Energy Today kWh

Do not add charge schedules, charge targets, reserve settings, cutoff settings, Eco Mode, Real Time Control, or any other controllable entity.

## Uninstall or revoke access

Stop and uninstall the app in Home Assistant. Revoke the runtime API key on the OpenAI Platform and delete the Ultrahuman Personal API Token in Ultrahuman Vision. Delete the logical tunnel only if it will not be reused.
