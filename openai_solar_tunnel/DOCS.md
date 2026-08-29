# OpenAI Solar Tunnel

## Before installation

Confirm all of the following:

1. The Home Assistant **Model Context Protocol Server** integration is installed.
2. Assist exposes only the intended read-only solar sensors.
3. No GivTCP control, switch, number, select, automation, scene, or script is exposed.
4. An OpenAI Secure MCP Tunnel has been created for the correct organization and ChatGPT workspace.
5. You have a separate OpenAI runtime API key. Do not use an admin key for the running app.

## Configuration

Enter two values on the app's **Configuration** tab:

- **OpenAI tunnel ID**: starts with `tunnel_`. It identifies the tunnel and is not a secret.
- **OpenAI runtime API key**: a secret key used by the running tunnel client. Its user needs Tunnels Read and Use permissions.

Select **Save**, then start the app.

## Verify the connection

Open the app's **Log** tab. A successful start should show that the tunnel client is polling the OpenAI control plane and is ready. The app's watchdog checks `/healthz` internally.

If it does not become ready:

1. Recheck the tunnel ID for typing errors.
2. Confirm the runtime API key belongs to a user with Tunnels Read and Use permissions.
3. Confirm the Home Assistant MCP Server integration is loaded.
4. Confirm Home Assistant itself has internet access to `api.openai.com` over HTTPS.
5. Restart the app after correcting the configuration.

Never paste the runtime API key into chat, screenshots, GitHub, or diagnostic logs.

## Read-only boundary

The app forwards requests only to Home Assistant's built-in `/api/mcp/assist` endpoint. The exposed-entity list and the MCP Server's **Control Home Assistant** option determine what Assist can provide. For this solar workflow, expose sensor entities only and keep control disabled when the option is available.

The intended sensor set is:

- GivTCP Power SOC
- GivTCP Power SOC kWh
- GivTCP Power PV Power
- GivTCP Power Load Power
- GivTCP Power Grid Power
- GivTCP Power Battery Power
- GivTCP Energy PV Energy Today kWh

Do not add charge schedules, charge targets, reserve settings, cutoff settings, Eco Mode, Real Time Control, or any other controllable entity.

## Uninstall or revoke access

Stop and uninstall the app in Home Assistant, then revoke the runtime API key on the OpenAI Platform. Delete the logical tunnel only if it will not be reused.
