"""LE4-B: Groq SSE streaming + incremental tool-call assembly."""

import json

import pytest

from vox.agent.groq import GroqClient, StreamDone, StreamUsage, TextDelta, ToolCallComplete
from vox.agent.provider import ProviderError


class FakeStreamTransport:
    def __init__(self, lines):
        self._lines = lines
        self.requests = []

    def post(self, path, data, content_type, limit):  # pragma: no cover
        raise AssertionError("streaming tests must not use post")

    def post_stream(self, path, data, content_type, limit):
        self.requests.append(json.loads(data))
        yield from self._lines


def sse(payload) -> bytes:
    return ("data: " + json.dumps(payload) + "\n").encode()


def delta(content=None, calls=None, finish=None):
    delta_body = {}
    if content is not None:
        delta_body["content"] = content
    if calls is not None:
        delta_body["tool_calls"] = calls
    return {"choices": [{"delta": delta_body, "finish_reason": finish}]}


def run(lines):
    client = GroqClient(FakeStreamTransport(lines))
    return list(client.chat_stream([{"role": "user", "content": "hi"}], []))


def test_text_deltas_and_done():
    events = run([sse(delta(content="Calcu")), sse(delta(content="lator opened.")), b"data: [DONE]\n"])
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Calcu", "lator opened."]
    assert isinstance(events[-1], StreamDone)


def test_tool_call_fragments_assemble_and_emit_once_complete():
    events = run(
        [
            sse(delta(calls=[{"index": 0, "function": {"name": "open_app", "arguments": ""}}])),
            sse(delta(calls=[{"index": 0, "function": {"arguments": '{"name": "Calcu'}}])),
            sse(delta(calls=[{"index": 0, "function": {"arguments": 'lator"}'}}])),
            sse(delta(finish="tool_calls")),
            b"data: [DONE]\n",
        ]
    )
    complete = [e for e in events if isinstance(e, ToolCallComplete)]
    assert len(complete) == 1
    assert complete[0].name == "open_app"
    assert json.loads(complete[0].arguments) == {"name": "Calculator"}


def test_second_call_seals_the_first_before_stream_end():
    events = run(
        [
            sse(delta(calls=[{"index": 0, "function": {"name": "a", "arguments": "{}"}}])),
            sse(delta(calls=[{"index": 1, "function": {"name": "b", "arguments": "{}"}}])),
            sse(delta(content="done text")),
            b"data: [DONE]\n",
        ]
    )
    names = [e.name for e in events if isinstance(e, ToolCallComplete)]
    assert names == ["a", "b"]  # a sealed by b's start; b sealed by text


def test_no_premature_dispatch_on_partial_arguments():
    events = run(
        [
            sse(delta(calls=[{"index": 0, "function": {"name": "x", "arguments": "{"}}])),
            b"data: [DONE]\n",
        ]
    )
    assert not [e for e in events if isinstance(e, ToolCallComplete)]


def test_usage_and_cached_tokens_parsed():
    events = run(
        [
            sse(delta(content="hi")),
            sse(
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 1200,
                        "completion_tokens": 20,
                        "prompt_tokens_details": {"cached_tokens": 900},
                    },
                }
            ),
            b"data: [DONE]\n",
        ]
    )
    usage = next(e for e in events if isinstance(e, StreamUsage))
    assert usage.prompt_tokens == 1200 and usage.cached_tokens == 900


def test_malformed_lines_skipped_and_empty_stream_fails():
    events = run([b"garbage\n", b"data: {not json\n", sse(delta(content="ok")), b"data: [DONE]\n"])
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["ok"]
    with pytest.raises(ProviderError):
        run([b"data: [DONE]\n"])


def test_request_is_streaming_with_messages():
    transport = FakeStreamTransport([sse(delta(content="x")), b"data: [DONE]\n"])
    list(GroqClient(transport).chat_stream([{"role": "system", "content": "s"}], [{"type": "function"}]))
    body = transport.requests[0]
    assert body["stream"] is True and body["messages"][0]["content"] == "s"
    assert body["tools"] == [{"type": "function"}]
