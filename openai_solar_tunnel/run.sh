#!/usr/bin/with-contenv bashio
set -euo pipefail

export CONTROL_PLANE_TUNNEL_ID
CONTROL_PLANE_TUNNEL_ID="$(bashio::config 'tunnel_id')"

export CONTROL_PLANE_API_KEY
CONTROL_PLANE_API_KEY="$(bashio::config 'openai_runtime_api_key')"

export HOME_ASSISTANT_AUTH_HEADER="Bearer ${SUPERVISOR_TOKEN}"
export MCP_SERVER_URL="http://supervisor/core/api/mcp/assist"
export MCP_EXTRA_HEADERS="Authorization: env:HOME_ASSISTANT_AUTH_HEADER"
export MCP_DISCOVERY_EXTRA_HEADERS="Authorization: env:HOME_ASSISTANT_AUTH_HEADER"
export MCP_STARTUP_WAIT_TIMEOUT="60s"
export CONTROL_PLANE_POLL_CHANNELS="main"
export HEALTH_LISTEN_ADDR=":8080"
export LOG_LEVEL="info"
export LOG_FORMAT="struct-text"

bashio::log.info "Starting the OpenAI Secure MCP Tunnel for Home Assistant Assist"
bashio::log.info "Home Assistant remains local; no inbound port is opened"

exec /usr/local/bin/tunnel-client run
