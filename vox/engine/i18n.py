"""User-visible/control phrase tables (EN + HI), parity-tested.

Control-plane phrases (L-02 closed set) live here — never hard-coded in
logic. Hindi entries include Roman (Hinglish ASR output) and Devanagari
forms. A test asserts both languages define the same categories.
"""

from __future__ import annotations

CONTROL_PHRASES: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "stop": (
            "stop",
            "cancel",
            "stop it",
            "cancel that",
            "never mind",
            "nevermind",
            "forget it",
            "abort",
        ),
        "pause": ("pause", "pause that", "wait", "hold on"),
        "resume": ("resume", "continue", "go on", "carry on"),
        "status": ("status", "what are you doing", "whats happening"),
        "mute": ("stop listening", "mute the mic", "microphone off"),
        "approve": (
            "yes",
            "yeah",
            "yep",
            "approve",
            "confirm",
            "go ahead",
            "do it",
            "okay do it",
            "ok do it",
        ),
        "deny": ("no", "nope", "deny", "do not", "dont"),
    },
    "hi": {
        "stop": ("ruko", "band karo", "cancel karo", "रुको", "बंद करो", "रद्द करो"),
        "pause": ("ruko zara", "thoda ruko", "रुको जरा", "थोड़ा रुको"),
        "resume": ("chalu karo", "jari rakho", "शुरू करो", "जारी रखो"),
        "status": ("kya kar rahe ho", "status batao", "क्या कर रहे हो"),
        "mute": ("mic band karo", "sunna band karo", "माइक बंद करो"),
        "approve": ("haan", "kar do", "haan kar do", "हाँ", "हां", "कर दो"),
        "deny": ("nahi", "nahin", "mat karo", "नहीं", "मत करो"),
    },
}

# Wake-phrase aliases (spec 4.0a, L-10). Greetings by language, plus the
# spellings small recognizers substitute for the canonical assistant name.
# "folks" is deliberately NOT a name variant: "hi folks" is a stock media
# greeting and would false-wake on videos/podcasts (LE1b decision);
# revisit with audio-bench data.
WAKE_GREETINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "strong": ("hi", "hey", "ok", "okay", "hai"),
        "weak": ("high", "hay", "he", "i"),
    },
    "hi": {
        "strong": ("हाय", "हे", "hai", "hey"),
        "weak": ("हाई",),
    },
}

WAKE_NAME_VARIANTS: dict[str, tuple[str, ...]] = {
    "vox": (
        "vox",
        "box",
        "fox",
        "walks",
        "wax",
        "vax",
        "vaux",
        "valk",
        "volks",
        "voss",
        "vos",
        "वॉक्स",
        "वोक्स",
        "बॉक्स",
    ),
}

# Tokens that make an approval response a denial, even mixed with "yes"
# (asymmetric rule, spec 4.2d: any no-like token wins).
DENY_TOKENS: dict[str, frozenset[str]] = {
    "en": frozenset({"no", "nope", "nah", "dont", "never", "cancel", "stop"}),
    "hi": frozenset({"nahi", "nahin", "नहीं", "mat", "मत"}),
}
