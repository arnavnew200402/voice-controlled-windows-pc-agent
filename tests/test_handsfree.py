"""Hands-free wake loop, endpointing and wake model handling with fakes.

No microphone, speaker, network or real Vosk model is involved.
"""

import io
import struct
import threading
import time
import wave
import zipfile

import pytest

from vox.agent.provider import ProviderError
from vox.agent.tools import ToolResult
from vox.voice import audio, wake
from vox.voice.audio import NoSpeechError, frame_rms, record_until_silence
from vox.voice.handsfree import HandsFreeController
from vox.voice.service import Outcome
from vox.voice.wake import WakeError, contains_wake_phrase, ensure_model


def pcm(level: float, samples: int = 4000) -> bytes:
    value = int(level * 32767)
    return struct.pack(f"<{samples}h", *([value] * samples))


@pytest.mark.parametrize(
    "text",
    [
        "hi vox",
        "Hi Vox!",
        "hey vox open notepad",
        "okay vox",
        "hi box",
        "hey fox",
        "um hi vox please",
        # Mis-hearings from small recognizers / accents.
        "i vox",
        "high vox",
        "hey walks",
        "hi wax",
        "ok voss",
        "hivox",
    ],
)
def test_wake_phrases_match(text):
    assert contains_wake_phrase(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "vox",
        "hello world",
        "hi there",
        "a box of foxes",
        "i walks every day",
        "a box",
        "say hi to the fox",
        "hey there box",
    ],
)
def test_non_wake_text_does_not_match(text):
    assert not contains_wake_phrase(text)


def test_frame_rms_levels():
    assert frame_rms(pcm(0.0)) == 0.0
    assert frame_rms(pcm(0.5)) > 0.4
    assert frame_rms(b"") == 0.0


def fake_frames(frames):
    def source(cancelled):
        yield from frames

    return source


def test_record_until_silence_stops_after_speech(monkeypatch):
    frames = [pcm(0.4), pcm(0.4)] + [pcm(0.0)] * 10
    monkeypatch.setattr(audio, "iter_microphone_frames", fake_frames(frames))
    wav = record_until_silence(lambda: False)
    with wave.open(io.BytesIO(wav), "rb") as reader:
        # 2 loud frames + the trailing silence needed to decide speech ended.
        assert 2 * 4000 < reader.getnframes() <= 7 * 4000


def test_record_until_silence_requires_speech(monkeypatch):
    monkeypatch.setattr(audio, "iter_microphone_frames", fake_frames([pcm(0.0)] * 3))
    with pytest.raises(NoSpeechError):
        record_until_silence(lambda: False)


class FakeEngine:
    def __init__(self):
        self.fed = []

    def feed(self, frame):
        self.fed.append(frame)
        return frame == b"WAKE"


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_controller(*, frame_batches, capture, process, speak=None):
    events = {"states": [], "outcomes": [], "errors": [], "spoken": [], "levels": []}
    engine = FakeEngine()
    batches = iter(frame_batches)

    def frame_source(cancelled):
        yield from next(batches, [])

    controller = HandsFreeController(
        engine_factory=lambda: engine,
        frame_source=frame_source,
        capture_command=capture,
        process_audio=process,
        speak_result=speak or (lambda evidence, cancelled: events["spoken"].append(evidence)),
        on_state=events["states"].append,
        on_outcome=events["outcomes"].append,
        on_error=events["errors"].append,
        on_level=events["levels"].append,
        pause_after_speak=0,
    )
    return controller, engine, events


def test_full_handsfree_turn_then_back_to_listening():
    calls = []

    def capture(cancelled):
        calls.append("capture")
        return b"wav-bytes"

    def process(wav, dry_run, cancelled):
        calls.append(("process", wav, dry_run))
        return Outcome(result=ToolResult(ok=True, evidence="Calculator opened."))

    controller, _engine, events = make_controller(
        frame_batches=[[b"noise", b"WAKE"], []],
        capture=capture,
        process=process,
    )
    controller.start(dry_run=False, speak=True)
    assert wait_until(lambda: "off" in events["states"])
    assert events["states"] == [
        "starting",
        "wake",
        "command",
        "processing",
        "speaking",
        "wake",
        "off",
    ]
    assert calls == ["capture", ("process", b"wav-bytes", False)]
    assert events["spoken"] == ["Calculator opened."]
    assert [o.result.evidence for o in events["outcomes"]] == ["Calculator opened."]
    assert events["errors"] == []
    assert events["levels"] and all(0.0 <= level <= 1.0 for level in events["levels"])


def test_no_wake_phrase_means_no_capture_or_cloud_call():
    def forbidden(*args):
        raise AssertionError("must not run before the wake phrase")

    controller, engine, events = make_controller(
        frame_batches=[[b"noise", b"more noise"]], capture=forbidden, process=forbidden
    )
    controller.start(dry_run=False, speak=True)
    assert wait_until(lambda: "off" in events["states"])
    assert events["outcomes"] == [] and events["errors"] == []
    assert engine.fed == [b"noise", b"more noise"]


def test_no_speech_after_wake_returns_to_listening():
    captures = []

    def capture(cancelled):
        captures.append(1)
        if len(captures) == 1:
            raise NoSpeechError("I didn't hear a request.")
        return b"wav"

    controller, _engine, events = make_controller(
        frame_batches=[[b"WAKE"], [b"WAKE"], []],
        capture=capture,
        process=lambda wav, dry, cx: Outcome(result=ToolResult(ok=True, evidence="Done.")),
    )
    controller.start(dry_run=False, speak=False)
    assert wait_until(lambda: "off" in events["states"])
    assert len(captures) == 2
    assert len(events["outcomes"]) == 1 and events["errors"] == []


def test_provider_error_ends_turn_not_session():
    attempts = []

    def process(wav, dry_run, cancelled):
        attempts.append(1)
        if len(attempts) == 1:
            raise ProviderError("Groq is unavailable.")
        return Outcome(result=ToolResult(ok=True, evidence="Done."))

    controller, _engine, events = make_controller(
        frame_batches=[[b"WAKE"], [b"WAKE"], []],
        capture=lambda cx: b"wav",
        process=process,
    )
    controller.start(dry_run=False, speak=False)
    assert wait_until(lambda: "off" in events["states"])
    assert events["errors"] == ["Groq is unavailable."]
    assert len(events["outcomes"]) == 1


def test_pending_approval_pauses_wake_spotting():
    from vox.agent.groq_tools import PlannedAction, WebsiteArgs
    from vox.approvals import Tier

    pending_gate = threading.Event()
    allow_second_wake = threading.Event()
    attempts = []

    def live_silence_then_wake():
        # Like a real microphone: a continuing stream, not a finite batch.
        while not allow_second_wake.is_set():
            yield b"noise"
            time.sleep(0.01)
        yield b"WAKE"

    def process(wav, dry_run, cancelled):
        attempts.append(1)
        if len(attempts) == 1:
            return Outcome(
                pending=PlannedAction(
                    "open_website",
                    WebsiteArgs(url="https://example.com/"),
                    Tier.CONFIRM,
                )
            )
        return Outcome(result=ToolResult(ok=True, evidence="Done."))

    controller, engine, events = make_controller(
        frame_batches=[[b"WAKE"], live_silence_then_wake(), []],
        capture=lambda cx: b"wav",
        process=process,
    )
    original_outcome = events["outcomes"].append

    def on_outcome(outcome):
        original_outcome(outcome)
        pending_gate.set()

    controller._on_outcome = on_outcome
    controller.start(dry_run=False, speak=False)
    assert pending_gate.wait(timeout=5)
    fed_at_pause = len(engine.fed)
    time.sleep(0.25)
    # While the approval card is unresolved, frames must not reach the spotter.
    assert len(engine.fed) == fed_at_pause
    controller.resume()
    assert wait_until(lambda: len(engine.fed) > fed_at_pause)
    allow_second_wake.set()
    assert wait_until(lambda: "off" in events["states"])
    assert len(events["outcomes"]) == 2


def test_stop_ends_wake_listening():
    controller, engine, events = make_controller(
        frame_batches=[[]], capture=lambda cx: b"", process=lambda *a: Outcome()
    )
    never_ending = threading.Event()

    def frame_source(cancelled):
        while not cancelled():
            never_ending.wait(timeout=0.02)
            yield b"noise"

    controller._frame_source = frame_source
    controller.start(dry_run=False, speak=False)
    assert wait_until(lambda: engine.fed)
    controller.stop()
    assert wait_until(lambda: not controller.running)
    assert events["states"][-1] == "off"


def _model_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{wake.MODEL_NAME}/am/final.mdl", "x")
        archive.writestr(f"{wake.MODEL_NAME}/conf/mfcc.conf", "x")
    return buffer.getvalue()


def test_ensure_model_downloads_and_caches(tmp_path, monkeypatch):
    target = tmp_path / wake.MODEL_NAME
    monkeypatch.setattr(wake, "cached_model_path", lambda: target)
    monkeypatch.setattr(wake, "_model_root_candidates", list)
    downloads = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_open(url, timeout):
        downloads.append(url)
        return Response(_model_zip())

    monkeypatch.setattr(wake.urllib.request, "urlopen", fake_open)
    assert ensure_model() == target
    assert (target / "am").is_dir()
    # Second call must use the cache, not download again.
    assert ensure_model() == target
    assert len(downloads) == 1


def test_ensure_model_rejects_zip_slip(tmp_path, monkeypatch):
    target = tmp_path / wake.MODEL_NAME
    monkeypatch.setattr(wake, "cached_model_path", lambda: target)
    monkeypatch.setattr(wake, "_model_root_candidates", list)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.txt", "x")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        wake.urllib.request, "urlopen", lambda url, timeout: Response(buffer.getvalue())
    )
    with pytest.raises(WakeError):
        ensure_model()
    assert not (tmp_path.parent / "evil.txt").exists()


def test_vosk_engine_feed_parses_results_and_reports_heard(monkeypatch):
    import json
    import types
    from pathlib import Path

    class FakeRecognizer:
        def __init__(self):
            self.resets = 0

        def SetWords(self, value):
            pass

        def AcceptWaveform(self, frame):
            return frame == b"final"

        def Result(self):
            return json.dumps({"text": "hi box"})

        def PartialResult(self):
            return json.dumps({"partial": "hi"})

        def Reset(self):
            self.resets += 1

    recognizer = FakeRecognizer()
    fake_vosk = types.SimpleNamespace(
        Model=lambda path: object(),
        KaldiRecognizer=lambda model, rate: recognizer,
        SetLogLevel=lambda level: None,
    )
    monkeypatch.setattr(wake.importlib, "import_module", lambda name: fake_vosk)
    engine = wake.VoskWakeEngine(model_path=Path("fake-model"))
    heard = []
    engine.set_on_heard(heard.append)
    assert engine.feed(b"partial-frame") is False
    assert heard == ["hi"]
    assert engine.feed(b"final") is True
    assert heard[-1] == "hi box"
    assert recognizer.resets == 1


def test_vosk_engine_without_vosk_installed_fails_closed(monkeypatch):
    from pathlib import Path

    def missing(name):
        raise ImportError("no vosk")

    monkeypatch.setattr(wake.importlib, "import_module", missing)
    with pytest.raises(WakeError, match="not installed"):
        wake.VoskWakeEngine(model_path=Path("fake-model"))


def test_winsound_player_stop_reports_spoken_prefix(monkeypatch):
    import io
    import sys
    import types
    import wave as wave_module

    calls = []
    fake_winsound = types.SimpleNamespace(
        SND_MEMORY=4,
        SND_ASYNC=1,
        SND_PURGE=64,
        PlaySound=lambda data, flags: calls.append((data is None, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    buffer = io.BytesIO()
    with wave_module.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 32000)  # 2 seconds of silence

    player = audio.WinsoundPlayer()
    player.play(buffer.getvalue(), "Calculator opened just now successfully")
    assert player.playing
    player._started -= 1.0  # pretend half the clip has played
    spoken = player.stop()
    assert calls[-1][0] is True  # PlaySound(None, SND_PURGE) silenced it
    assert spoken.startswith("Calculator opened")
    assert len(spoken) < len("Calculator opened just now successfully")
    assert not player.playing
    assert player.wait() == ""


def test_winsound_player_rejects_invalid_wav(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(
        sys.modules,
        "winsound",
        types.SimpleNamespace(SND_MEMORY=4, SND_ASYNC=1, SND_PURGE=64, PlaySound=lambda d, f: None),
    )
    with pytest.raises(audio.AudioError):
        audio.WinsoundPlayer().play(b"not a wav")
