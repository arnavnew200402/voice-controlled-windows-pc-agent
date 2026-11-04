"""LE1b: wake settings/phrase config (two-stage session tests follow)."""

from vox.engine.config import WakeSensitivity, WakeSettings
from vox.engine.i18n import WAKE_GREETINGS
from vox.voice.wake import contains_wake_phrase, strip_wake_tokens


def test_wake_i18n_parity():
    assert set(WAKE_GREETINGS) == {"en", "hi"}
    for table in WAKE_GREETINGS.values():
        assert set(table) == {"strong", "weak"} and all(table.values())


def test_phrase_sets_default_accept_hi_and_hey_not_ok():
    sets = WakeSettings(enabled=True).phrase_sets()
    assert contains_wake_phrase("hi vox", **sets)
    assert contains_wake_phrase("hey vox", **sets)
    assert contains_wake_phrase("hai vox", **sets)
    assert contains_wake_phrase("हाय वॉक्स", **sets)
    assert not contains_wake_phrase("okay vox", **sets)  # not a configured greeting
    assert not contains_wake_phrase("hi folks", **sets)  # media greeting, excluded
    assert strip_wake_tokens("hai vox open chrome", **sets) == "open chrome"


def test_custom_name_uses_exact_name_only():
    settings = WakeSettings(enabled=True, name="Jarvis")
    sets = settings.phrase_sets()
    assert settings.uses_custom_name
    assert contains_wake_phrase("hi jarvis", **sets)
    assert not contains_wake_phrase("hi vox", **sets)
    assert not contains_wake_phrase("hi box", **sets)  # no variants for custom names


def test_sensitivity_presets_and_calibration_offset():
    balanced = WakeSettings()
    assert balanced.gate_rms == 0.03 and balanced.min_confidence == 0.7
    assert WakeSettings(sensitivity=WakeSensitivity.HIGH).gate_rms < balanced.gate_rms
    assert WakeSettings(sensitivity=WakeSensitivity.LOW).min_confidence > balanced.min_confidence
    assert WakeSettings(calibration_offset=0.02).gate_rms == 0.05
