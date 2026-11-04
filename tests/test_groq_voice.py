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
from vox.agent.groq_tools import GroqRegistry, PlannedAction, WebsiteArgs
from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
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


def test_chat_and_transcription_wire_formats():
    transport = Transport(response(tool_message()))
    client = GroqClient(transport)
    assert client.chat("Open Calculator", GroqRegistry(FakeBackend()).schemas()) == tool_message()
    path, body, content_type, _ = transport.calls[0]
    payload = json.loads(body)
    assert path == "/openai/v1/chat/completions" and content_type == "application/json"
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["messages"][-1]["content"] == "Open Calculator"
    assert {x["function"]["name"] for x in payload["tools"]} == {"open_app", "open_website"}
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
