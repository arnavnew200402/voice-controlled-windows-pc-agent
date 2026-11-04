"""Recorded Responses streams; no real API calls or user credentials."""

import io
import json
import time

import pytest

from vox.agent.auth_storage import Session
from vox.agent.chatgpt import ChatGPTProvider, OpenAITransport
from vox.agent.provider import ProviderError
from vox.agent.tools import DryRunBackend, ToolRegistry
from vox.agent.turn import run_turn


def session():
    return Session(
        "test-client", "subject", "fake-access", "fake-refresh", "fake-id", time.time() + 300
    )


class FakeTransport:
    def __init__(self, output):
        self.output = output
        self.body = None

    def models(self, token):
        assert token == "fake-access"
        return ["test-model"]

    def response(self, token, body):
        assert token == "fake-access"
        self.body = body
        return {"status": "completed", "output": self.output}


def test_chatgpt_tool_call_through_registry():
    transport = FakeTransport(
        [
            {
                "type": "function_call",
                "namespace": "desktop",
                "name": "open_app",
                "arguments": '{"name":"Notepad"}',
            }
        ]
    )
    result = run_turn(
        "Open Notepad",
        ChatGPTProvider(session(), transport=transport),
        ToolRegistry(DryRunBackend()),
    )
    assert result.ok and result.simulated
    body = transport.body
    assert body["store"] is False and body["stream"] is True
    assert body["tools"][0]["type"] == "namespace"
    assert body["tools"][0]["tools"][0]["name"] == "open_app"
    assert not {"temperature", "previous_response_id", "max_output_tokens"} & body.keys()


@pytest.mark.parametrize(
    "output",
    [
        [
            {
                "type": "function_call",
                "namespace": "other",
                "name": "open_app",
                "arguments": '{"name":"Notepad"}',
            }
        ],
        [
            {
                "type": "function_call",
                "namespace": "desktop",
                "name": "run_command",
                "arguments": "{}",
            }
        ],
        [
            {
                "type": "function_call",
                "namespace": "desktop",
                "name": "open_app",
                "arguments": '{"name":"Notepad","approved":true}',
            }
        ],
        [{"type": "message", "content": [{"text": "Opened Notepad"}]}],
    ],
)
def test_chatgpt_invalid_or_unverified_output_is_not_executed(output):
    result = run_turn(
        "test",
        ChatGPTProvider(session(), transport=FakeTransport(output)),
        ToolRegistry(DryRunBackend()),
    )
    assert not result.ok
    assert "Opened Notepad" not in result.evidence


def test_expired_session_does_not_call_transport():
    expired = Session("client", "subject", "a", "r", "i", time.time() - 1)
    with pytest.raises(ProviderError, match="expired"):
        ChatGPTProvider(expired, transport=FakeTransport([])).chat("test", [])


class Response:
    status = 200

    def __init__(self, payload):
        self.stream = io.BytesIO(payload)

    def getheader(self, name, default=""):
        return "text/event-stream"

    def readline(self, limit):
        return self.stream.readline(limit)


def event(value):
    return b"data: " + json.dumps(value).encode() + b"\n\n"


def install_connection(monkeypatch, payload):
    import vox.agent.chatgpt as provider

    calls = []

    class Connection:
        def __init__(self, host, timeout):
            calls.append((host, timeout))

        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body), headers["Authorization"]))

        def getresponse(self):
            return Response(payload)

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(provider.http.client, "HTTPSConnection", Connection)
    return calls


def test_sse_requires_completed_event_and_fixed_https_host(monkeypatch):
    payload = (
        event({"type": "response.completed", "response": {"status": "completed", "output": []}})
        + b"data: [DONE]\n\n"
    )
    calls = install_connection(monkeypatch, payload)
    assert OpenAITransport().response("fake-access", {"stream": True})["status"] == "completed"
    assert calls[0][0] == "api.openai.com"
    assert calls[1][:2] == ("POST", "/v1/responses")
    assert calls[-1] == "closed"


@pytest.mark.parametrize(
    "payload",
    [
        b"data: [DONE]\n\n",
        event({"type": "response.output_item.done", "item": {"type": "function_call"}}),
        event({"type": "response.failed", "response": {"status": "failed"}}),
        event({"type": "response.completed", "response": {"status": "incomplete"}}),
        b"data: " + b"x" * 65537 + b"\n\n",
    ],
    # Short IDs are required on Windows: pytest puts the node ID in the
    # PYTEST_CURRENT_TEST environment variable, which is capped at 32767
    # characters there, so the 65537-byte value must not appear in the ID.
    ids=[
        "done-without-completed",
        "no-completed-event",
        "failed-event",
        "incomplete-status",
        "oversized-line",
    ],
)
def test_incomplete_failed_and_oversized_sse_fails_closed(monkeypatch, payload):
    install_connection(monkeypatch, payload)
    with pytest.raises(ProviderError):
        OpenAITransport().response("fake-access", {"stream": True})


def test_cli_defaults_to_chatgpt_with_dry_run(monkeypatch, capsys):
    import sys

    import vox.__main__ as cli
    import vox.agent.auth_storage as storage
    from vox.agent import chatgpt

    transport = FakeTransport(
        [
            {
                "type": "function_call",
                "namespace": "desktop",
                "name": "open_app",
                "arguments": '{"name":"Notepad"}',
            }
        ]
    )

    class Store:
        def load(self):
            return "test-host", session()

    monkeypatch.setattr(storage, "windows_store", lambda: Store())
    monkeypatch.setattr(
        chatgpt, "ChatGPTProvider", lambda saved, model: ChatGPTProvider(saved, model, transport)
    )
    monkeypatch.setattr(sys, "argv", ["vox", "--text", "Open Notepad", "--dry-run"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    assert "no application was launched" in capsys.readouterr().out


def test_model_catalog_uses_only_visible_slugs(monkeypatch):
    from vox.agent import chatgpt

    class CatalogResponse:
        status = 200

        def read(self, limit):
            return json.dumps(
                {
                    "models": [
                        {"visibility": "list", "slug": "visible"},
                        {"visibility": "hidden", "slug": "hidden"},
                        {"visibility": "list", "slug": ""},
                    ]
                }
            ).encode()

    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.openai.com"

        def request(self, method, path, headers):
            assert (method, path) == ("GET", "/v1/models")

        def getresponse(self):
            return CatalogResponse()

        def close(self):
            pass

    monkeypatch.setattr(chatgpt.http.client, "HTTPSConnection", Connection)
    assert OpenAITransport().models("fake-access") == ["visible"]
