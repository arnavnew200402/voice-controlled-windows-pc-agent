"""Local-provider and restricted tool contracts; no real desktop actions."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vox.agent.ollama import LoopbackTransport, OllamaProvider, ProviderError
from vox.agent.tools import DryRunBackend, ToolRegistry, ToolResult
from vox.agent.turn import run_turn
from vox.agent.windows import WindowsNotepadBackend


def response(name="open_app", args=None):
    return {
        "message": {
            "tool_calls": [{"function": {"name": name, "arguments": args or {"name": "Notepad"}}}]
        }
    }


class FakeTransport:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def post(self, body):
        self.calls.append(body)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeBackend:
    def __init__(self):
        self.count = 0

    def open_notepad(self):
        self.count += 1
        return ToolResult(ok=True, evidence="Verified virtual foreground.")


def test_llm_first_uses_only_registry_and_evidence():
    backend = FakeBackend()
    transport = FakeTransport(response())
    result = run_turn(
        "Open Notepad", OllamaProvider("test-model", transport), ToolRegistry(backend)
    )
    assert result.ok and backend.count == 1
    assert result.evidence == "Verified virtual foreground."
    body = transport.calls[0]
    assert len(transport.calls) == 1
    assert body["messages"][-1]["content"] == "Open Notepad"
    assert [tool["function"]["name"] for tool in body["tools"]] == ["open_app"]
    assert body["tools"][0]["function"]["parameters"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "output",
    [
        response("run_command", {"command": "format c:"}),
        response(args={"name": "calc.exe"}),
        response(args={"name": "Notepad", "tier": 0}),
        response(args={"name": "Notepad", "path": "C:/evil.exe"}),
        {
            "message": {
                "tool_calls": [
                    {"function": {"name": "open_app", "arguments": '{"name":"Notepad"}'}}
                ]
            }
        },
        {
            "message": {
                "tool_calls": [{"function": {"name": "open_app", "arguments": {"name": "Notepad"}}}]
                * 2
            }
        },
        {"message": {"content": "Notepad is open!"}},
        {"message": {"tool_calls": "invalid"}},
        {"message": None},
        {},
    ],
)
def test_invalid_and_unverified_model_output_never_executes(output):
    backend = FakeBackend()
    result = run_turn("test", OllamaProvider("test", FakeTransport(output)), ToolRegistry(backend))
    assert not result.ok
    assert backend.count == 0
    assert "Notepad is open!" not in result.evidence


def test_provider_failure_invalid_input_and_dry_run():
    backend = FakeBackend()
    provider = OllamaProvider("test", FakeTransport(ProviderError("private details")))
    assert not run_turn("", provider, ToolRegistry(backend)).ok
    result = run_turn("hello", provider, ToolRegistry(backend))
    assert not result.ok and "private details" not in result.evidence
    result = run_turn(
        "open", OllamaProvider("test", FakeTransport(response())), ToolRegistry(DryRunBackend())
    )
    assert result.ok and result.simulated and "no application was launched" in result.evidence
    assert backend.count == 0


class FakeProcess:
    pid = 123

    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


def test_windows_backend_uses_fixed_system_path_and_verifies_foreground():
    paths = []
    backend = WindowsNotepadBackend(
        platform="nt",
        system_dir=lambda: r"C:\Windows\System32",
        launcher=lambda path: paths.append(path) or FakeProcess(),
        foreground=lambda: 123,
    )
    result = backend.open_notepad()
    assert result.ok
    assert len(paths) == 1 and paths[0].endswith("notepad.exe")
    assert "foreground" in result.evidence


def test_windows_backend_fails_closed_without_foreground_or_windows():
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    backend = WindowsNotepadBackend(
        platform="nt",
        system_dir=lambda: r"C:\Windows\System32",
        launcher=lambda _: FakeProcess(),
        foreground=lambda: 999,
        clock=lambda: clock[0],
        sleep=sleep,
    )
    result = backend.open_notepad()
    assert not result.ok and "could not verify" in result.evidence
    backend = WindowsNotepadBackend(
        platform="posix", launcher=lambda _: pytest.fail("must not launch")
    )
    assert not backend.open_notepad().ok


def test_transport_uses_loopback_and_rejects_bad_ports():
    for port in (0, 65536, True):
        with pytest.raises(ValueError):
            LoopbackTransport(port=port)
    assert LoopbackTransport().port == 11434


def test_cli_with_recorded_local_server_and_dry_run():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                (self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            )
            body = json.dumps(response()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vox",
                "--text",
                "Open Notepad",
                "--provider",
                "ollama",
                "--model",
                "recorded",
                "--dry-run",
                "--ollama-port",
                str(server.server_port),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=os.environ.copy(),
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "no application was launched" in result.stdout
        assert len(requests) == 1 and requests[0][0] == "/api/chat"
        assert requests[0][1]["stream"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "status,content", [(302, b"{}"), (200, b"[1]"), (200, b"invalid"), (200, b"x" * 1_048_577)]
)
def test_transport_rejects_redirects_and_invalid_or_oversized_responses(
    monkeypatch, status, content
):
    from vox.agent import ollama

    calls = []

    class Response:
        def __init__(self):
            self.status = status

        def read(self, limit):
            assert limit == ollama.MAX_RESPONSE + 1
            return content

    class Connection:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def request(self, method, path, body, headers):
            calls.append((method, path))

        def getresponse(self):
            return Response()

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(ollama.http.client, "HTTPConnection", Connection)
    with pytest.raises(ProviderError):
        LoopbackTransport(port=11434).post({"model": "test"})
    assert calls[0][0] == "127.0.0.1"
    assert calls[1] == ("POST", "/api/chat")
    assert calls[-1] == "closed"


def test_foreground_verification_requires_process_still_alive():
    class VanishingProcess:
        pid = 123
        calls = 0

        def poll(self):
            self.calls += 1
            return None if self.calls == 1 else 0

    backend = WindowsNotepadBackend(
        platform="nt",
        system_dir=lambda: r"C:\Windows\System32",
        launcher=lambda _: VanishingProcess(),
        foreground=lambda: 123,
        sleep=lambda _: None,
    )
    assert not backend.open_notepad().ok


def test_windows_launcher_never_uses_shell(monkeypatch):
    from vox.agent import windows

    captured = []

    def fake_popen(arguments, **kwargs):
        captured.append((arguments, kwargs))
        return FakeProcess()

    monkeypatch.setattr(windows.subprocess, "Popen", fake_popen)
    windows.launch(r"C:\Windows\System32\notepad.exe")
    assert captured == [([r"C:\Windows\System32\notepad.exe"], {"shell": False, "close_fds": True})]


def test_launch_errors_do_not_claim_success():
    def fail(_):
        raise OSError("details not suitable for display")

    backend = WindowsNotepadBackend(platform="nt", system_dir=lambda: "system", launcher=fail)
    result = backend.open_notepad()
    assert not result.ok
    assert "details not suitable" not in result.evidence


def test_cancellation_after_model_response_blocks_tool_execution():
    import threading

    cancel = threading.Event()
    backend = FakeBackend()

    class CancelTransport(FakeTransport):
        def post(self, body):
            cancel.set()
            return response()

    result = run_turn(
        "Open Notepad",
        OllamaProvider("test", CancelTransport(None)),
        ToolRegistry(backend),
        cancelled=cancel.is_set,
    )
    assert not result.ok and "cancelled" in result.evidence
    assert backend.count == 0
