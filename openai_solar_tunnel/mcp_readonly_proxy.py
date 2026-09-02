#!/usr/bin/env python3
"""Fail-closed MCP proxy for Home Assistant and read-only Ultrahuman data."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date as date_type
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("mcp-readonly-proxy")

LISTEN_HOST = os.environ.get("MCP_PROXY_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("MCP_PROXY_LISTEN_PORT", "8090"))
UPSTREAM_URL = os.environ.get(
    "MCP_PROXY_UPSTREAM_URL", "http://supervisor/core/api/mcp/assist"
)
UPSTREAM_AUTHORIZATION = os.environ.get("MCP_PROXY_UPSTREAM_AUTHORIZATION", "")
ULTRAHUMAN_API_TOKEN = os.environ.get("ULTRAHUMAN_API_TOKEN", "")
ULTRAHUMAN_API_URL = (
    "https://partner.ultrahuman.com/api/v1/partner/daily_metrics"
)
ULTRAHUMAN_MAX_RESPONSE_BYTES = 10 * 1024 * 1024

HOME_ASSISTANT_TOOL = "GetLiveContext"
ULTRAHUMAN_DAILY_TOOL = "GetUltrahumanDailyMetrics"
ULTRAHUMAN_RECOVERY_TOOL = "GetUltrahumanRecoverySummary"
ALLOWED_TOOL_SUFFIXES = {
    HOME_ASSISTANT_TOOL,
    ULTRAHUMAN_DAILY_TOOL,
    ULTRAHUMAN_RECOVERY_TOOL,
}
ALLOWED_RESOURCE_URI = "homeassistant://assist/context-snapshot"
MISSING = object()

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "openWorldHint": False,
    "idempotentHint": True,
}

ULTRAHUMAN_TOOLS = [
    {
        "name": ULTRAHUMAN_DAILY_TOOL,
        "description": (
            "Retrieve the authenticated user's full Ultrahuman daily metrics for "
            "one date. Read-only; does not alter Ultrahuman data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "format": "date",
                    "description": "Date in YYYY-MM-DD format.",
                }
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": ULTRAHUMAN_RECOVERY_TOOL,
        "description": (
            "Retrieve a concise Ultrahuman sleep and recovery summary for one "
            "date. Read-only; intended for training-readiness assessment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "format": "date",
                    "description": "Date in YYYY-MM-DD format.",
                }
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        "annotations": READ_ONLY_ANNOTATIONS,
    },
]


def _tool_suffix(name: Any) -> str | None:
    if not isinstance(name, str):
        return None
    return name.split("__")[-1]


def _tool_is_allowed(name: Any) -> bool:
    """Return whether a tool is on the explicit read-only allowlist."""
    return _tool_suffix(name) in ALLOWED_TOOL_SUFFIXES


def _ultrahuman_tool(name: Any) -> str | None:
    suffix = _tool_suffix(name)
    if suffix in {ULTRAHUMAN_DAILY_TOOL, ULTRAHUMAN_RECOVERY_TOOL}:
        return suffix
    return None


def _resource_is_allowed(uri: Any) -> bool:
    """Return whether a resource is the read-only Assist context snapshot."""
    return uri == ALLOWED_RESOURCE_URI


def _filter_result(message: Any) -> Any:
    """Filter tool/resource discovery and inject the Ultrahuman read tools."""
    if not isinstance(message, dict):
        return message

    result = message.get("result")
    if not isinstance(result, dict):
        return message

    tools = result.get("tools")
    if isinstance(tools, list):
        filtered_tools = []
        for tool in tools:
            if not isinstance(tool, dict) or _tool_suffix(tool.get("name")) != HOME_ASSISTANT_TOOL:
                continue
            safe_tool = dict(tool)
            safe_tool["annotations"] = READ_ONLY_ANNOTATIONS
            filtered_tools.append(safe_tool)
        filtered_tools.extend(dict(tool) for tool in ULTRAHUMAN_TOOLS)
        result["tools"] = filtered_tools

    resources = result.get("resources")
    if isinstance(resources, list):
        result["resources"] = [
            resource
            for resource in resources
            if isinstance(resource, dict) and _resource_is_allowed(resource.get("uri"))
        ]

    resource_templates = result.get("resourceTemplates")
    if isinstance(resource_templates, list):
        result["resourceTemplates"] = []

    return message


def filter_response_payload(payload: bytes) -> bytes:
    """Filter discovery information in a JSON or JSON-RPC batch response."""
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return payload

    if isinstance(decoded, list):
        filtered = [_filter_result(message) for message in decoded]
    else:
        filtered = _filter_result(decoded)
    return json.dumps(filtered, separators=(",", ":"), ensure_ascii=False).encode()


def filter_sse_line(line: bytes) -> bytes:
    """Filter the JSON payload in one Server-Sent Events data line."""
    stripped = line.rstrip(b"\r\n")
    ending = line[len(stripped) :]
    if not stripped.startswith(b"data:"):
        return line
    prefix, separator, value = stripped.partition(b":")
    if not separator:
        return line
    value = value.lstrip(b" ")
    return prefix + b": " + filter_response_payload(value) + ending


def _request_messages(payload: bytes) -> list[dict[str, Any]]:
    """Parse JSON-RPC request messages, returning an empty list on invalid JSON."""
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    if isinstance(decoded, dict):
        return [decoded]
    if isinstance(decoded, list) and all(isinstance(item, dict) for item in decoded):
        return decoded
    return []


def blocked_request(payload: bytes) -> tuple[Any, str] | None:
    """Return the JSON-RPC id and reason when a request must be blocked."""
    for message in _request_messages(payload):
        method = message.get("method")
        params = message.get("params")
        if not isinstance(params, dict):
            params = {}

        if method == "tools/call" and not _tool_is_allowed(params.get("name")):
            return message.get("id"), "Only explicitly allowlisted read-only tools are available"
        if method == "resources/read" and not _resource_is_allowed(params.get("uri")):
            return message.get("id"), "Only the read-only Assist context snapshot is allowed"
    return None


def _mcp_result(request_id: Any, data: Any, *, is_error: bool = False) -> bytes:
    """Build an MCP JSON-RPC tool result with a JSON text payload."""
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            },
        },
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def blocked_response(request_id: Any, reason: str) -> bytes:
    """Build an MCP tool error response for a blocked request."""
    return _mcp_result(request_id, reason, is_error=True)


def _validated_date(arguments: Any) -> str:
    if not isinstance(arguments, dict) or set(arguments) != {"date"}:
        raise ValueError("Exactly one argument is required: date in YYYY-MM-DD format")
    value = arguments.get("date")
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must use YYYY-MM-DD format")
    try:
        parsed = date_type.fromisoformat(value)
    except ValueError as error:
        raise ValueError("date is not a valid calendar date") from error
    if parsed.isoformat() != value:
        raise ValueError("date must use YYYY-MM-DD format")
    return value


def _fetch_ultrahuman_metrics(metric_date: str) -> Any:
    """Fetch one day's metrics using the fixed Ultrahuman read-only endpoint."""
    if not ULTRAHUMAN_API_TOKEN:
        raise RuntimeError("Ultrahuman API token is not configured")

    url = f"{ULTRAHUMAN_API_URL}?{urlencode({'date': metric_date})}"
    request = Request(
        url,
        headers={
            "Authorization": ULTRAHUMAN_API_TOKEN,
            "Accept": "application/json",
            "User-Agent": "home-assistant-solar-ultrahuman/0.3.1",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read(ULTRAHUMAN_MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        if error.code in {401, 403}:
            raise RuntimeError("Ultrahuman rejected the configured API token") from error
        if error.code == 404:
            raise RuntimeError(f"Ultrahuman returned no data for {metric_date}") from error
        if error.code == 429:
            raise RuntimeError("Ultrahuman rate limit reached; try again later") from error
        raise RuntimeError(f"Ultrahuman API request failed with HTTP {error.code}") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Ultrahuman API is temporarily unavailable") from error

    if len(payload) > ULTRAHUMAN_MAX_RESPONSE_BYTES:
        raise RuntimeError("Ultrahuman response exceeded the safe size limit")
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("Ultrahuman returned an invalid JSON response") from error


def _normal_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower()) if isinstance(value, str) else ""


def _metric_entry_value(value: Any) -> Any:
    """Return the concise value from an Ultrahuman typed metric object."""
    if not isinstance(value, dict):
        return value
    for key in ("value", "avg", "score", "percentage", "minutes", "celsius"):
        if key in value:
            return value[key]
    return value


def _find_metric(value: Any, candidate_keys: tuple[str, ...]) -> Any:
    """Find the first named metric in a nested API response."""
    wanted = {_normal_key(key) for key in candidate_keys}
    if isinstance(value, dict):
        if _normal_key(value.get("type")) in wanted and "object" in value:
            return _metric_entry_value(value["object"])
        for key, item in value.items():
            if _normal_key(key) in wanted:
                return _metric_entry_value(item)
        for item in value.values():
            found = _find_metric(item, candidate_keys)
            if found is not MISSING:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_metric(item, candidate_keys)
            if found is not MISSING:
                return found
    return MISSING


def _recovery_summary(metric_date: str, metrics: Any) -> dict[str, Any]:
    fields = {
        "recovery_score": ("recovery_score", "recovery"),
        "sleep_score": ("sleep_score",),
        "average_sleep_hrv": ("avg_sleep_hrv", "average_sleep_hrv"),
        "sleeping_resting_hr": ("sleep_rhr", "night_rhr"),
        "total_sleep": ("total_sleep",),
        "deep_sleep": ("deep_sleep",),
        "rem_sleep": ("rem_sleep",),
        "sleep_efficiency": ("sleep_efficiency",),
        "temperature_deviation": ("temperature_deviation",),
        "spo2": ("spo2",),
        "recovery_index": ("recovery_index",),
    }
    summary: dict[str, Any] = {"date": metric_date}
    missing = []
    for output_name, candidates in fields.items():
        value = _find_metric(metrics, candidates)
        if value is MISSING:
            missing.append(output_name)
        else:
            summary[output_name] = value
    if missing:
        summary["missing_fields"] = missing
    return summary


def direct_tool_response(payload: bytes) -> bytes | None:
    """Handle one Ultrahuman tool call locally; return None for other requests."""
    messages = _request_messages(payload)
    if len(messages) != 1:
        return None
    message = messages[0]
    if message.get("method") != "tools/call":
        return None
    params = message.get("params")
    if not isinstance(params, dict):
        return None
    tool = _ultrahuman_tool(params.get("name"))
    if tool is None:
        return None

    request_id = message.get("id")
    try:
        metric_date = _validated_date(params.get("arguments"))
        metrics = _fetch_ultrahuman_metrics(metric_date)
        if tool == ULTRAHUMAN_RECOVERY_TOOL:
            metrics = _recovery_summary(metric_date, metrics)
        return _mcp_result(request_id, metrics)
    except (ValueError, RuntimeError) as error:
        return _mcp_result(request_id, str(error), is_error=True)


class ReadOnlyProxyHandler(BaseHTTPRequestHandler):
    """Proxy MCP HTTP requests while enforcing a server-side read-only allowlist."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._forward(b"")

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward(b"")

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(content_length)
        direct_response = direct_tool_response(payload)
        if direct_response is not None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(direct_response)))
            self.end_headers()
            self.wfile.write(direct_response)
            return
        blocked = blocked_request(payload)
        if blocked is not None:
            request_id, reason = blocked
            response = blocked_response(request_id, reason)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self._forward(payload)

    def _upstream_url(self) -> str:
        """Return the fixed upstream MCP URL with the incoming query string."""
        upstream = urlsplit(UPSTREAM_URL)
        incoming = urlsplit(self.path)
        return urlunsplit(
            (upstream.scheme, upstream.netloc, upstream.path, incoming.query, "")
        )

    def _upstream_headers(self) -> dict[str, str]:
        """Copy safe request headers and inject Home Assistant internal auth."""
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS
            and name.lower() not in {"authorization", "host", "content-length"}
        }
        headers["Authorization"] = UPSTREAM_AUTHORIZATION
        return headers

    def _forward(self, payload: bytes) -> None:
        """Forward a request and filter discovery responses."""
        request = Request(
            self._upstream_url(),
            data=payload if self.command == "POST" else None,
            headers=self._upstream_headers(),
            method=self.command,
        )
        try:
            response = urlopen(request, timeout=90)
        except HTTPError as error:
            self._relay_response(error)
            return
        except (URLError, TimeoutError) as error:
            LOGGER.error(
                "Home Assistant MCP upstream unavailable: %s",
                getattr(error, "reason", str(error)),
            )
            body = b"Home Assistant MCP upstream unavailable"
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._relay_response(response)

    def _relay_response(self, response: Any) -> None:
        """Relay an upstream response, filtering JSON and SSE discovery payloads."""
        content_type = response.headers.get("Content-Type", "")
        status = response.status

        if content_type.startswith("text/event-stream"):
            self.send_response(status)
            self._copy_response_headers(response.headers, omit={"content-length"})
            self.send_header("Connection", "close")
            self.end_headers()
            for line in response:
                self.wfile.write(filter_sse_line(line))
                self.wfile.flush()
            self.close_connection = True
            return

        body = response.read()
        if "json" in content_type:
            body = filter_response_payload(body)

        self.send_response(status)
        self._copy_response_headers(
            response.headers,
            omit={"content-length", "transfer-encoding", "connection"},
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _copy_response_headers(self, headers: Any, omit: set[str]) -> None:
        """Copy end-to-end upstream response headers."""
        for name, value in headers.items():
            if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() not in omit:
                self.send_header(name, value)

    def log_message(self, message: str, *args: Any) -> None:
        """Log request metadata without headers or bodies."""
        LOGGER.info("%s - %s", self.address_string(), message % args)


def main() -> None:
    """Run the read-only MCP proxy."""
    if not UPSTREAM_AUTHORIZATION.startswith("Bearer "):
        LOGGER.error("MCP_PROXY_UPSTREAM_AUTHORIZATION is missing or invalid")
        sys.exit(1)

    logging.basicConfig(
        level=os.environ.get("MCP_PROXY_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ReadOnlyProxyHandler)
    LOGGER.info(
        "Read-only MCP proxy listening on %s:%d; allowed tools=%s",
        LISTEN_HOST,
        LISTEN_PORT,
        ",".join(sorted(ALLOWED_TOOL_SUFFIXES)),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
