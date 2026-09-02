"""Tests for the fail-closed Home Assistant and Ultrahuman MCP proxy."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import Request, urlopen

import mcp_readonly_proxy as proxy
from mcp_readonly_proxy import (
    ALLOWED_RESOURCE_URI,
    ULTRAHUMAN_DAILY_TOOL,
    ULTRAHUMAN_RECOVERY_TOOL,
    blocked_request,
    direct_tool_response,
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


def tool_call(name: str, arguments: dict, request_id: int = 1) -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    ).encode()


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

    def test_filters_tools_and_adds_read_only_tools(self) -> None:
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

        self.assertEqual(
            [tool["name"] for tool in tools],
            [
                "homeassistant__GetLiveContext",
                ULTRAHUMAN_DAILY_TOOL,
                ULTRAHUMAN_RECOVERY_TOOL,
            ],
        )
        for tool in tools:
            self.assertEqual(
                tool["annotations"],
                {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "openWorldHint": False,
                    "idempotentHint": True,
                },
            )

    def test_blocks_write_tool_call(self) -> None:
        request = tool_call("HassTurnOff", {})
        self.assertEqual(
            blocked_request(request),
            (1, "Only explicitly allowlisted read-only tools are available"),
        )

    def test_allows_each_read_only_tool_call(self) -> None:
        for name in (
            "homeassistant__GetLiveContext",
            ULTRAHUMAN_DAILY_TOOL,
            ULTRAHUMAN_RECOVERY_TOOL,
        ):
            with self.subTest(name=name):
                self.assertIsNone(blocked_request(tool_call(name, {"date": "2026-09-02"})))

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
            ["GetLiveContext", ULTRAHUMAN_DAILY_TOOL, ULTRAHUMAN_RECOVERY_TOOL],
        )

    def test_daily_metrics_tool_returns_full_response(self) -> None:
        metrics = {"data": {"recovery": 82, "sleep_score": 79}}
        with patch.object(proxy, "_fetch_ultrahuman_metrics", return_value=metrics):
            response = direct_tool_response(
                tool_call(ULTRAHUMAN_DAILY_TOOL, {"date": "2026-09-02"}, 4)
            )

        decoded = json.loads(response)
        self.assertFalse(decoded["result"]["isError"])
        self.assertEqual(json.loads(decoded["result"]["content"][0]["text"]), metrics)

    def test_recovery_summary_extracts_nested_fields(self) -> None:
        metrics = {
            "data": {
                "scores": {"recovery": 82, "sleep_score": 79},
                "sleep": {
                    "avg_sleep_hrv": 41,
                    "night_rhr": 51,
                    "deep_sleep": 91,
                },
            }
        }
        with patch.object(proxy, "_fetch_ultrahuman_metrics", return_value=metrics):
            response = direct_tool_response(
                tool_call(ULTRAHUMAN_RECOVERY_TOOL, {"date": "2026-09-02"}, 5)
            )

        summary = json.loads(json.loads(response)["result"]["content"][0]["text"])
        self.assertEqual(summary["date"], "2026-09-02")
        self.assertEqual(summary["recovery_score"], 82)
        self.assertEqual(summary["sleep_score"], 79)
        self.assertEqual(summary["average_sleep_hrv"], 41)
        self.assertEqual(summary["sleeping_resting_hr"], 51)
        self.assertEqual(summary["deep_sleep"], 91)
        self.assertIn("temperature_deviation", summary["missing_fields"])

    def test_rejects_invalid_date_without_api_request(self) -> None:
        with patch.object(proxy, "_fetch_ultrahuman_metrics") as fetch:
            response = direct_tool_response(
                tool_call(ULTRAHUMAN_DAILY_TOOL, {"date": "02-09-2026"})
            )

        decoded = json.loads(response)
        self.assertTrue(decoded["result"]["isError"])
        fetch.assert_not_called()

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
            [
                "homeassistant__GetLiveContext",
                ULTRAHUMAN_DAILY_TOOL,
                ULTRAHUMAN_RECOVERY_TOOL,
            ],
        )
        self.assertEqual(
            MockUpstreamHandler.authorization, "Bearer internal-test-token"
        )

    def test_http_proxy_does_not_forward_write_call(self) -> None:
        calls_before = MockUpstreamHandler.calls
        request = Request(
            self.proxy_url,
            data=tool_call("HassBroadcast", {}, 7),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(request) as response:
            decoded = json.loads(response.read())

        self.assertTrue(decoded["result"]["isError"])
        self.assertEqual(MockUpstreamHandler.calls, calls_before)

    def test_http_proxy_handles_ultrahuman_without_forwarding_to_home_assistant(self) -> None:
        calls_before = MockUpstreamHandler.calls
        request = Request(
            self.proxy_url,
            data=tool_call(ULTRAHUMAN_DAILY_TOOL, {"date": "2026-09-02"}, 8),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with patch.object(proxy, "_fetch_ultrahuman_metrics", return_value={"recovery": 80}):
            with urlopen(request) as response:
                decoded = json.loads(response.read())

        self.assertFalse(decoded["result"]["isError"])
        self.assertEqual(MockUpstreamHandler.calls, calls_before)


if __name__ == "__main__":
    unittest.main()
