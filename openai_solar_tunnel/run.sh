#!/usr/bin/with-contenv bashio
set -euo pipefail

export CONTROL_PLANE_TUNNEL_ID
CONTROL_PLANE_TUNNEL_ID="$(bashio::config 'tunnel_id')"

export CONTROL_PLANE_API_KEY
CONTROL_PLANE_API_KEY="$(bashio::config 'openai_runtime_api_key')"

export MCP_PROXY_UPSTREAM_AUTHORIZATION="Bearer ${SUPERVISOR_TOKEN}"
export MCP_PROXY_UPSTREAM_URL="http://supervisor/core/api/mcp/assist"
export MCP_PROXY_LISTEN_HOST="127.0.0.1"
export MCP_PROXY_LISTEN_PORT="8090"
export MCP_SERVER_URL="http://127.0.0.1:8090/mcp"
export MCP_STARTUP_WAIT_TIMEOUT="60s"
export CONTROL_PLANE_POLL_CHANNELS="main"
export HEALTH_LISTEN_ADDR=":8080"
export LOG_LEVEL="info"
export LOG_FORMAT="struct-text"

bashio::log.info "Starting the read-only Home Assistant MCP filter"
bashio::log.info "Allowing GetLiveContext only; all Home Assistant actions are blocked"
bashio::log.info "Home Assistant remains local; no inbound port is opened"

python3 /usr/local/bin/mcp_readonly_proxy.py &
proxy_pid=$!

/usr/local/bin/tunnel-client run &
tunnel_pid=$!

cleanup() {
  kill "${tunnel_pid}" "${proxy_pid}" 2>/dev/null || true
  wait "${tunnel_pid}" "${proxy_pid}" 2>/dev/null || true
}

trap 'cleanup; exit 0' TERM INT

while kill -0 "${proxy_pid}" 2>/dev/null && kill -0 "${tunnel_pid}" 2>/dev/null; do
  sleep 1
done

if ! kill -0 "${proxy_pid}" 2>/dev/null; then
  bashio::log.error "The read-only MCP filter stopped unexpectedly"
  exit_status=1
else
  set +e
  wait "${tunnel_pid}"
  exit_status=$?
  set -e
fi

cleanup
exit "${exit_status}"
