"""Tests for the fail-closed Home Assistant MCP proxy."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

import mcp_readonly_proxy as proxy
from mcp_readonly_proxy import (
    ALLOWED_RESOURCE_URI,
    blocked_request,
    filter_response_payload,
    filter_sse_line,
)


class MockUpstreamHandler(BaseHTTPRequestHandler):
    calls = 0
    authorization = ""

    def do_POST(self) -> None:  # noqa: N802
        type(self).calls += 1
        type(self).authorization = self.headers.get("Authorization", "")
        content_length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(content_length))
        if request.get("method") == "tools/list":
            result = {
                "tools": [
                    {"name": "homeassistant__GetLiveContext"},
                    {"name": "HassTurnOn"},
                ]
            }
        else:
            result = {"content": [{"type": "text", "text": "safe"}]}
        response = json.dumps(
            {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, _message: str, *_args: object) -> None:
        return


class ReadOnlyProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), MockUpstreamHandler)
        cls.upstream_thread = threading.Thread(
            target=cls.upstream.serve_forever, daemon=True
        )
        cls.upstream_thread.start()

        proxy.UPSTREAM_URL = (
            f"http://127.0.0.1:{cls.upstream.server_address[1]}/api/mcp/assist"
        )
        proxy.UPSTREAM_AUTHORIZATION = "Bearer internal-test-token"
        cls.proxy_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), proxy.ReadOnlyProxyHandler
        )
        cls.proxy_thread = threading.Thread(
            target=cls.proxy_server.serve_forever, daemon=True
        )
        cls.proxy_thread.start()
        cls.proxy_url = f"http://127.0.0.1:{cls.proxy_server.server_address[1]}/mcp"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.proxy_server.shutdown()
        cls.proxy_server.server_close()
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def test_filters_tools_and_adds_read_only_annotations(self) -> None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {"name": "GetDateTime"},
                        {"name": "homeassistant__GetLiveContext"},
                        {"name": "HassTurnOn"},
                    ]
                },
            }
        ).encode()

        decoded = json.loads(filter_response_payload(payload))
        tools = decoded["result"]["tools"]

        self.assertEqual([tool["name"] for tool in tools], ["homeassistant__GetLiveContext"])
        self.assertEqual(
            tools[0]["annotations"],
            {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
        )

    def test_blocks_write_tool_call(self) -> None:
        request = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "HassTurnOff", "arguments": {}},
            }
        ).encode()

        self.assertEqual(
            blocked_request(request),
            (8, "Only read-only Home Assistant live context is allowed"),
        )

    def test_allows_live_context_tool_call(self) -> None:
        request = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "homeassistant__GetLiveContext",
                    "arguments": {},
                },
            }
        ).encode()

        self.assertIsNone(blocked_request(request))

    def test_filters_resources(self) -> None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "resources": [
                        {"uri": ALLOWED_RESOURCE_URI},
                        {"uri": "homeassistant://unsafe"},
                    ]
                },
            }
        ).encode()

        decoded = json.loads(filter_response_payload(payload))
        self.assertEqual(
            decoded["result"]["resources"], [{"uri": ALLOWED_RESOURCE_URI}]
        )

    def test_filters_sse_data_line(self) -> None:
        line = (
            b'data: {"jsonrpc":"2.0","id":1,"result":{"tools":'
            b'[{"name":"HassTurnOn"},{"name":"GetLiveContext"}]}}\n'
        )

        filtered = filter_sse_line(line)
        decoded = json.loads(filtered.removeprefix(b"data: "))
        self.assertEqual(
            [tool["name"] for tool in decoded["result"]["tools"]],
            ["GetLiveContext"],
        )

    def test_http_proxy_filters_discovery_and_injects_internal_auth(self) -> None:
        request = Request(
            self.proxy_url,
            data=json.dumps(
                {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(request) as response:
            decoded = json.loads(response.read())

        self.assertEqual(
            [tool["name"] for tool in decoded["result"]["tools"]],
            ["homeassistant__GetLiveContext"],
        )
        self.assertEqual(
            MockUpstreamHandler.authorization, "Bearer internal-test-token"
        )

    def test_http_proxy_does_not_forward_write_call(self) -> None:
        calls_before = MockUpstreamHandler.calls
        request = Request(
            self.proxy_url,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "HassBroadcast", "arguments": {}},
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(request) as response:
            decoded = json.loads(response.read())

        self.assertTrue(decoded["result"]["isError"])
        self.assertEqual(MockUpstreamHandler.calls, calls_before)


if __name__ == "__main__":
    unittest.main()
