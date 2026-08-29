---
name: home-assistant-solar
description: "Read and interpret the user's live Home Assistant GivTCP solar and GivEnergy battery sensors for solar forecasts, battery state checks, and force-charge recommendations. Use when a request needs current PV output, household load, grid power, battery power, state of charge, stored energy, or today's PV generation, or when setting up or diagnosing the Home Assistant Solar connection. This integration is strictly read-only."
---

# Home Assistant Solar

Use the Home Assistant MCP connection only as a read-only source of live solar and battery context.

## Safety boundary

- Call only read, list, snapshot, or context tools and resources.
- Never call a tool that turns on, turns off, sets, changes, runs, executes, schedules, creates, updates, or deletes anything in Home Assistant.
- Never change a GivTCP charge target, schedule, reserve, cutoff, Eco Mode, Real Time Control setting, or any switch, number, select, automation, scene, script, or service.
- Do not broaden the exposed entity list.
- If asked to control the inverter or Home Assistant, explain that this plugin is read-only and give manual guidance only.
- Treat the tunnel ID as non-secret. Treat OpenAI API keys, Home Assistant tokens, and authorization headers as secrets; never display or log them.

## Approved entities

Use data only from these seven entities:

| Exposed Home Assistant name | Meaning | Unit |
| --- | --- | --- |
| `GivTCP Power SOC` | Primary battery state of charge | `%` |
| `GivTCP Power SOC kWh` | Energy currently stored | `kWh` |
| `GivTCP Power PV Power` | Current total PV output | `W` |
| `GivTCP Power Load Power` | Current household load | `W` |
| `GivTCP Power Grid Power` | Current signed grid power | `W` |
| `GivTCP Power Battery Power` | Current signed battery power | `W` |
| `GivTCP Energy PV Energy Today kWh` | PV energy generated today | `kWh` |

Do not substitute the battery-module diagnostic SOC sensor; it is not the primary inverter SOC used by this workflow and should remain unexposed.

## Read workflow

1. Prefer the read-only `homeassistant://assist/context-snapshot` resource when the client exposes it. Otherwise use the available live-context read tool.
2. Extract only the seven approved entities. Ignore all unrelated entities, even if returned in the same snapshot.
3. Confirm values are numeric and units match the table. Report `unknown`, `unavailable`, missing, or stale values explicitly; do not invent replacements.
4. Use SOC percent as the primary charge state. Use SOC kWh as a consistency check and for energy calculations.
5. Interpret positive GivTCP battery power as battery discharge. Interpret negative battery power as charging.
6. Until the grid-power sign has been calibrated against a known import/export event, report it as a signed value without labelling it import or export.
7. Include the observation time or say that Home Assistant supplied a live snapshot when no entity timestamp is available.

## Recommendations

- Use live Home Assistant data as the starting state, not as the solar forecast itself.
- Combine it with the forecast method supplied by the user's scheduled solar workflow when making a force-charge recommendation.
- State any missing data or sign uncertainty that could materially change the recommendation.
- A recommendation is advisory only. Do not implement it in Home Assistant or GivEnergy.

## Setup diagnostics

For connection problems, check in this order:

1. The Home Assistant MCP Server integration is loaded.
2. Exactly the seven approved entities are exposed to Assist.
3. The OpenAI Solar Tunnel app is running and its log reports a healthy tunnel connection.
4. The ChatGPT app points to the correct tunnel.
5. No secret is pasted into chat or committed to the repository.
