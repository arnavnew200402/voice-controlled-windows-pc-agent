"""LE1-B: endpointing decisions, pre-roll, control plane (EN+HI parity)."""

from vox.engine.control import ControlAction, classify_control
from vox.engine.endpointing import Decision, Endpointer, PreRollBuffer, is_dangling
from vox.engine.i18n import CONTROL_PHRASES


def test_dangling_detection_en_and_hi():
    assert is_dangling("")
    assert is_dangling("move this window to the")
    assert is_dangling("open chrome and")
    assert is_dangling("chrome kholo aur")
    assert not is_dangling("open calculator")
    assert not is_dangling("volume kam karo")


def test_soft_then_hard_end_for_complete_partial():
    endpointer = Endpointer()
    endpointer.reset(100.0)
    endpointer.on_partial("open calculator", 100.1)
    assert endpointer.poll(100.2) is Decision.NONE
    assert endpointer.poll(100.45) is Decision.SOFT_END
    assert endpointer.soft_ended
    assert endpointer.poll(100.55) is Decision.NONE  # soft fires once
    assert endpointer.poll(100.62) is Decision.HARD_END
    assert endpointer.poll(100.9) is Decision.NONE


def test_dangling_partial_waits_longer_and_never_soft_ends():
    endpointer = Endpointer()
    endpointer.reset(0.0)
    endpointer.on_partial("move this window to the", 0.1)
    assert endpointer.poll(0.5) is Decision.NONE
    assert endpointer.poll(0.7) is Decision.NONE  # past complete hard-end, still waiting
    endpointer.on_partial("move this window to the right monitor", 0.8)
    assert endpointer.poll(1.2) is Decision.SOFT_END
    assert endpointer.poll(1.35) is Decision.HARD_END


def test_speech_after_soft_end_resumes_same_utterance():
    endpointer = Endpointer()
    endpointer.reset(0.0)
    endpointer.on_partial("open chrome", 0.1)
    assert endpointer.poll(0.4) is Decision.SOFT_END
    endpointer.on_partial("open chrome and search", 0.45)
    assert endpointer.consume_resumed() is True
    assert not endpointer.soft_ended
    assert endpointer.poll(0.5) is Decision.NONE


def test_speech_rms_alone_does_not_endpoint_without_partial():
    endpointer = Endpointer()
    endpointer.reset(0.0)
    endpointer.on_speech(0.5, 0.1)
    assert endpointer.poll(5.0) is Decision.NONE


def test_preroll_keeps_only_recent_window_and_slices_by_time():
    buffer = PreRollBuffer(seconds=1.5, frame_seconds=0.25)
    for index in range(10):  # 2.5 s of frames, capacity 6
        buffer.push(bytes([index]), at=index * 0.25)
    assert len(buffer) == 6
    assert buffer.audio_from(2.0) == bytes([8, 9])
    assert buffer.audio_from(0.0) == bytes([4, 5, 6, 7, 8, 9])
    buffer.clear()
    assert len(buffer) == 0


def test_i18n_parity_en_hi():
    assert set(CONTROL_PHRASES) == {"en", "hi"}
    assert set(CONTROL_PHRASES["en"]) == set(CONTROL_PHRASES["hi"])
    for categories in CONTROL_PHRASES.values():
        assert all(phrases for phrases in categories.values())


def test_control_categories_en():
    assert classify_control("stop").action is ControlAction.STOP
    assert classify_control("never mind").action is ControlAction.STOP
    assert classify_control("hold on").action is ControlAction.PAUSE
    assert classify_control("continue").action is ControlAction.RESUME
    assert classify_control("What are you doing?").action is ControlAction.STATUS
    assert classify_control("stop listening").action is ControlAction.MUTE
    assert classify_control("cancel the download").action is ControlAction.STOP


def test_control_categories_hi():
    assert classify_control("ruko").action is ControlAction.STOP
    assert classify_control("बंद करो").action is ControlAction.STOP
    assert classify_control("chalu karo").action is ControlAction.RESUME
    assert classify_control("kya kar rahe ho").action is ControlAction.STATUS
    assert classify_control("mic band karo").action is ControlAction.MUTE


def test_control_rejects_non_control_speech():
    assert classify_control("") is None
    assert classify_control("open stopwatch") is None
    assert classify_control("please do not stop the music") is None
    assert classify_control("open calculator") is None
    assert classify_control("yes") is None  # nothing pending
    assert classify_control("no") is None


def test_approval_responses_only_while_pending_and_no_wins():
    assert classify_control("yes", approval_pending=True).action is ControlAction.APPROVE
    assert classify_control("haan kar do", approval_pending=True).action is ControlAction.APPROVE
    assert classify_control("no", approval_pending=True).action is ControlAction.DENY
    assert classify_control("nahi", approval_pending=True).action is ControlAction.DENY
    # Asymmetric: any no-like token beats a yes.
    assert classify_control("yes no wait", approval_pending=True).action is ControlAction.DENY
    assert classify_control("stop", approval_pending=True).action is ControlAction.STOP
    # Long speech is not an approval response.
    assert classify_control("yes please open the other thing now", approval_pending=True) is None
