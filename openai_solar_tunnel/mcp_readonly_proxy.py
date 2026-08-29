#!/usr/bin/env python3
"""Fail-closed MCP proxy that exposes only Home Assistant live context."""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("mcp-readonly-proxy")

LISTEN_HOST = os.environ.get("MCP_PROXY_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("MCP_PROXY_LISTEN_PORT", "8090"))
UPSTREAM_URL = os.environ.get(
    "MCP_PROXY_UPSTREAM_URL", "http://supervisor/core/api/mcp/assist"
)
UPSTREAM_AUTHORIZATION = os.environ.get("MCP_PROXY_UPSTREAM_AUTHORIZATION", "")

ALLOWED_TOOL_SUFFIX = "GetLiveContext"
ALLOWED_RESOURCE_URI = "homeassistant://assist/context-snapshot"

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


def _tool_is_allowed(name: Any) -> bool:
    """Return whether a tool is the read-only live-context tool."""
    return isinstance(name, str) and name.split("__")[-1] == ALLOWED_TOOL_SUFFIX


def _resource_is_allowed(uri: Any) -> bool:
    """Return whether a resource is the read-only Assist context snapshot."""
    return uri == ALLOWED_RESOURCE_URI


def _filter_result(message: Any) -> Any:
    """Filter tool and resource discovery results in one JSON-RPC message."""
    if not isinstance(message, dict):
        return message

    result = message.get("result")
    if not isinstance(result, dict):
        return message

    tools = result.get("tools")
    if isinstance(tools, list):
        filtered_tools = []
        for tool in tools:
            if not isinstance(tool, dict) or not _tool_is_allowed(tool.get("name")):
                continue
            safe_tool = dict(tool)
            safe_tool["annotations"] = {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            }
            filtered_tools.append(safe_tool)
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
            return message.get("id"), "Only read-only Home Assistant live context is allowed"
        if method == "resources/read" and not _resource_is_allowed(params.get("uri")):
            return message.get("id"), "Only the read-only Assist context snapshot is allowed"
    return None


def blocked_response(request_id: Any, reason: str) -> bytes:
    """Build an MCP tool error response for a blocked request."""
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": reason}],
                "isError": True,
            },
        },
        separators=(",", ":"),
    ).encode()


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
        "Read-only MCP proxy listening on %s:%d; allowed tool=%s",
        LISTEN_HOST,
        LISTEN_PORT,
        ALLOWED_TOOL_SUFFIX,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
