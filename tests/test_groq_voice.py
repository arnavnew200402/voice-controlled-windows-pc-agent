"""Groq API, voice, key storage and approvals with fakes; no real network or desktop."""

import io
import json
import sys
import threading
import types
import wave

import pytest

from vox.agent.auth_storage import StorageError
from vox.agent.groq import GroqClient, HTTPSGroqTransport
from vox.agent.groq_key import GroqKeyStore
from vox.agent.groq_tools import (
    FolderBound,
    GroqRegistry,
    PlannedAction,
    TypingBound,
    TypingRequest,
    WebsiteArgs,
)
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.agent.windows_control import WindowRef
from vox.approvals import Tier
from vox.voice.audio import AudioError, record_wav
from vox.voice.service import GroqVoiceService


class Transport:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def post(self, path, data, content_type, limit):
        self.calls.append((path, data, content_type, limit))
        return self.data


def tool_message(name="open_app", args='{"name":"Calculator"}'):
    return {"tool_calls": [{"type": "function", "function": {"name": name, "arguments": args}}]}


def response(message):
    return json.dumps({"choices": [{"finish_reason": "tool_calls", "message": message}]}).encode()


class FakeBackend:
    def __init__(self):
        self.calls = []

    def open_app(self, name):
        self.calls.append(("app", name))
        return ToolResult(ok=True, evidence=f"{name} verified.")

    def open_website(self, url):
        self.calls.append(("url", url))
        return ToolResult(ok=True, evidence="Browser asked to open URL.")

    def resolve_folder(self, target):
        self.calls.append(("resolve", target))
        return r"C:\Users\tester\Downloads"

    def open_folder(self, path):
        self.calls.append(("folder", path))
        return ToolResult(ok=True, evidence="Explorer asked to open the approved folder.")

    def list_windows(self):
        self.calls.append(("windows",))
        return [
            WindowRef(
                hwnd=10, pid=100, created=1, focus_hwnd=20, title="Notepad", window_class="Notepad"
            ),
            WindowRef(
                hwnd=11,
                pid=101,
                created=2,
                focus_hwnd=21,
                title="Calculator",
                window_class="CalcFrame",
            ),
        ]

    def type_text(self, target, text):
        self.calls.append(("typing", target.title, text))
        return ToolResult(ok=True, evidence="Input sent to the selected window.")


def test_chat_and_transcription_wire_formats():
    transport = Transport(response(tool_message()))
    client = GroqClient(transport)
    assert client.chat("Open Calculator", GroqRegistry(FakeBackend()).schemas()) == tool_message()
    path, body, content_type, _ = transport.calls[0]
    payload = json.loads(body)
    assert path == "/openai/v1/chat/completions" and content_type == "application/json"
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["messages"][-1]["content"] == "Open Calculator"
    assert {x["function"]["name"] for x in payload["tools"]} == {
        "open_app",
        "open_website",
        "open_folder",
        "type_text",
    }
    transport.data = b'{"text":"Open Notepad"}'
    wav = b"RIFF" + b"x" * 50
    assert client.transcribe(wav) == "Open Notepad"
    path, body, content_type, _ = transport.calls[-1]
    assert path == "/openai/v1/audio/transcriptions"
    assert "multipart/form-data; boundary=vox-" in content_type
    assert b"whisper-large-v3-turbo" in body and wav in body
    transport.data = b"RIFF-response"
    assert client.speech("Done.") == b"RIFF-response"
    assert transport.calls[-1][0] == "/openai/v1/audio/speech"
    assert json.loads(transport.calls[-1][1])["model"] == "canopylabs/orpheus-v1-english"


def test_http_limits_reject_redirect_and_do_not_expose_key(monkeypatch):
    from vox.agent import groq

    seen = []

    class Response:
        status = 302

        def read(self, limit):
            return b"x"

    class Connection:
        def __init__(self, host, timeout):
            seen.append(host)

        def request(self, method, path, body, headers):
            assert headers["Authorization"] == "Bearer fake-secret"

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(groq.http.client, "HTTPSConnection", Connection)
    with pytest.raises(ProviderError) as exc:
        HTTPSGroqTransport("fake-secret").post(
            "/openai/v1/chat/completions", b"{}", "application/json", 20
        )
    assert seen == ["api.groq.com"] and "fake-secret" not in str(exc.value)
    with pytest.raises(ProviderError):
        HTTPSGroqTransport("fake-secret").post("/evil", b"", "application/json", 20)
    Response.status = 200
    with pytest.raises(ProviderError):
        HTTPSGroqTransport("fake-secret").post(
            "/openai/v1/chat/completions", b"{}", "application/json", 0
        )


def test_key_store_atomic_and_private_with_fake_cipher(tmp_path):
    store = GroqKeyStore(
        tmp_path / "p" / "key", encrypt=lambda b: b[::-1], decrypt=lambda b: b[::-1]
    )
    store.save("fake-secret")
    assert b"fake-secret" not in store.path.read_bytes()
    assert store.load() == "fake-secret"
    with pytest.raises(ValueError):
        store.save("fake\nsecret")
    assert store.load() == "fake-secret"
    store.delete()
    with pytest.raises(StorageError):
        store.load()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com/",
        "https://127.0.0.1/",
        "https://127.1/",
        "https://localhost/",
        "https://printer.local/",
        "https://example.com:444/",
        "https://example.com\\@evil.com/",
        "https://example.com/\nX",
    ],
)
def test_invalid_urls_fail_closed(url):
    registry = GroqRegistry(FakeBackend())
    with pytest.raises(ProviderError):
        registry.plan(tool_message("open_website", json.dumps({"url": url})))


def test_website_approval_binds_exact_args_is_single_use_and_cancelled():
    backend = FakeBackend()
    registry = GroqRegistry(backend)
    action = registry.plan(tool_message("open_website", '{"url":"https://example.com/a"}'))
    assert action.tier is Tier.CONFIRM
    assert not registry.execute(action).ok
    approval = registry.request_approval(action)
    assert registry.resolve_approval(approval, True)
    changed = PlannedAction("open_website", WebsiteArgs(url="https://example.com/b"), Tier.CONFIRM)
    assert not registry.execute(changed, approval).ok
    assert registry.execute(action, approval).ok
    assert not registry.execute(action, approval).ok
    assert backend.calls == [("url", "https://example.com/a")]
    approval = registry.request_approval(action)
    assert registry.resolve_approval(approval, True)
    registry.approvals.deny_all()
    assert not registry.execute(action, approval).ok


def test_known_and_absolute_folder_resolution_binds_resolved_path():
    backend = FakeBackend()
    registry = GroqRegistry(backend)
    action = registry.plan(tool_message("open_folder", json.dumps({"target": "Downloads"})))
    assert action.tier is Tier.CONFIRM and isinstance(action.args, FolderBound)
    assert action.args.path == r"C:\Users\tester\Downloads"
    assert not registry.execute(action).ok
    approval = registry.request_approval(action)
    assert registry.resolve_approval(approval, True)
    changed = PlannedAction(
        "open_folder", FolderBound(path=r"C:\Users\tester\Documents"), Tier.CONFIRM
    )
    assert not registry.execute(changed, approval).ok
    assert registry.execute(action, approval).ok
    assert not registry.execute(action, approval).ok
    assert backend.calls[:2] == [
        ("resolve", "Downloads"),
        ("folder", r"C:\Users\tester\Downloads"),
    ]


@pytest.mark.parametrize("target", ["downloads", "Downloads"])
def test_folder_known_aliases_resolve(target):
    backend = FakeBackend()
    action = GroqRegistry(backend).plan(tool_message("open_folder", json.dumps({"target": target})))
    assert action.args.path == r"C:\Users\tester\Downloads"


@pytest.mark.parametrize(
    "target",
    [
        "%LOCALAPPDATA%\\Downloads",
        "\\\\server\\share",
        "C:\\Downloads\\..\\Secrets",
    ],
)
def test_folder_request_rejects_unsafe_targets(target):
    with pytest.raises(ProviderError):
        GroqRegistry(FakeBackend()).plan(
            tool_message("open_folder", json.dumps({"target": target}))
        )


def test_typing_request_binds_selected_window_and_text_is_single_use():
    backend = FakeBackend()
    registry = GroqRegistry(backend)
    action = registry.plan(
        tool_message("type_text", json.dumps({"text": "hello", "target_hint": "Notepad"}))
    )
    assert action.tier is Tier.CONFIRM and isinstance(action.args, TypingRequest)
    window = backend.list_windows()[0]
    bound = registry.bind_typing(action, window)
    assert isinstance(bound.args, TypingBound) and bound.args.window == window
    approval = registry.request_approval(bound)
    assert registry.resolve_approval(approval, True)
    changed_window = registry.bind_typing(action, backend.list_windows()[1])
    assert not registry.execute(changed_window, approval).ok
    changed_text = registry.bind_typing(action, window).args.model_copy(
        update={"text": "hello; rm -rf"}
    )
    assert not registry.execute(PlannedAction("type_text", changed_text, Tier.CONFIRM), approval).ok
    assert registry.execute(bound, approval).ok
    assert not registry.execute(bound, approval).ok
    assert backend.calls[-2:] == [("windows",), ("typing", "Notepad", "hello")]


@pytest.mark.parametrize(
    "text", ["hello\nworld", "hello\ttab", "hello\u200eworld", "hello\u202eworld"]
)
def test_typing_request_rejects_control_and_bidi_characters(text):
    with pytest.raises(ProviderError):
        GroqRegistry(FakeBackend()).plan(tool_message("type_text", json.dumps({"text": text})))


@pytest.mark.parametrize(
    "message",
    [
        tool_message("open_folder", json.dumps({"target": "relative\\secrets"})),
        tool_message("type_text", json.dumps({"text": "hello\nworld"})),
    ],
)
def test_folder_and_typing_injection_fail_closed(message):
    backend = FakeBackend()
    with pytest.raises(ProviderError):
        GroqRegistry(backend).plan(message)
    assert backend.calls == []


@pytest.mark.parametrize(
    "message",
    [
        tool_message("open_app", '{"name":"cmd.exe"}'),
        tool_message("open_app", '{"name":"Notepad","path":"evil"}'),
        tool_message("open_app", '{"name":"Notepad","name":"Paint"}'),
        tool_message("shell", "{}"),
        {"tool_calls": [tool_message()["tool_calls"][0]] * 2},
        {"content": "I opened it."},
    ],
)
def test_no_unsupported_or_model_claimed_action_runs(message):
    backend = FakeBackend()
    with pytest.raises(ProviderError):
        GroqRegistry(backend).plan(message)
    assert backend.calls == []


def test_voice_pipeline_fake_audio_transcript_dry_run_and_cancel(monkeypatch):
    from vox.voice import service

    backend = FakeBackend()
    svc = GroqVoiceService()
    svc.registry = GroqRegistry(backend)
    client = GroqClient(Transport(b'{"text":"Open Calculator"}'))

    class FakeClient:
        def transcribe(self, wav):
            assert wav == b"fake audio"
            return "Open Calculator"

        def chat(self, text, schemas):
            assert text == "Open Calculator"
            return tool_message()

    monkeypatch.setattr(svc, "_client", lambda: FakeClient())
    monkeypatch.setattr(service, "record_wav", lambda *args: b"fake audio")
    progress = []
    outcome = svc.voice(lambda: True, lambda: False, True, lambda: progress.append("mic closed"))
    assert outcome.transcript == "Open Calculator" and outcome.result.simulated
    assert progress == ["mic closed"] and backend.calls == []
    cancel = threading.Event()

    class CancellingClient(FakeClient):
        def chat(self, text, schemas):
            cancel.set()
            return tool_message()

    with pytest.raises(ProviderError):
        svc.submit("open", False, cancel.is_set, client=CancellingClient())
    assert backend.calls == []
    assert client is not None


def test_recording_is_bounded_and_memory_only(monkeypatch):
    finish = threading.Event()

    class Stream:
        def __init__(self, **kwargs):
            assert kwargs["samplerate"] == 16000 and kwargs["channels"] == 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, frames):
            finish.set()
            return (b"\0\0" * frames, False)

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=Stream))
    wav = record_wav(finish.is_set, lambda: False)
    with wave.open(io.BytesIO(wav), "rb") as f:
        assert f.getframerate() == 16000 and f.getnframes() == 1600
    with pytest.raises(AudioError):
        record_wav(lambda: False, lambda: True)
