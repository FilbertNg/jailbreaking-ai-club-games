import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from jailbreak.censor import CENSORED_TEXT
from jailbreak.config import RoundConfig
from jailbreak.guard import Guard, GuardBusy, GuardError, ModelChain, cut_reply


class StatusError(Exception):
    def __init__(self, code):
        super().__init__(f"status {code}")
        self.code = code


class FakeModel:
    """Returns or raises the queued outcomes in order; the last one repeats."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        out = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(out, BaseException):
            raise out
        if out == "SLOW":
            await asyncio.sleep(5)
        return AIMessage(content=out)


def make_chain(clock, models, timeout_s=30):
    return ModelChain(list(models), lambda mid, temp: models[mid], skip_s=60, timeout_s=timeout_s, now=clock)


def ask(chain):
    return asyncio.run(chain.ainvoke([HumanMessage("hi")], temperature=0.5, config={}))


def test_first_model_answers_when_healthy(clock):
    models = {"m1": FakeModel("hello"), "m2": FakeModel("other")}
    assert ask(make_chain(clock, models)) == ("hello", "m1")
    assert models["m2"].calls == []


def test_rate_limit_falls_to_next_and_skips_for_window(clock):
    models = {"m1": FakeModel(StatusError(429), "back"), "m2": FakeModel("second")}
    chain = make_chain(clock, models)
    assert ask(chain) == ("second", "m2")
    assert ask(chain) == ("second", "m2")
    assert len(models["m1"].calls) == 1
    clock.advance(61)
    assert ask(chain) == ("back", "m1")


def test_server_error_wrapped_in_cause_falls_through(clock):
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = StatusError(500)
    models = {"m1": FakeModel(wrapped), "m2": FakeModel("ok")}
    assert ask(make_chain(clock, models)) == ("ok", "m2")


def test_empty_reply_falls_through(clock):
    models = {"m1": FakeModel("   "), "m2": FakeModel("ok")}
    assert ask(make_chain(clock, models)) == ("ok", "m2")


def test_timeout_falls_through(clock):
    models = {"m1": FakeModel("SLOW"), "m2": FakeModel("ok")}
    assert ask(make_chain(clock, models, timeout_s=0.05)) == ("ok", "m2")


def test_bad_key_raises_guard_error_at_once(clock):
    models = {"m1": FakeModel(StatusError(401)), "m2": FakeModel("ok")}
    with pytest.raises(GuardError):
        ask(make_chain(clock, models))
    assert models["m2"].calls == []


def test_all_failing_raises_guard_busy(clock):
    models = {"m1": FakeModel(StatusError(429)), "m2": FakeModel(StatusError(503))}
    with pytest.raises(GuardBusy):
        ask(make_chain(clock, models))


def test_cut_reply():
    assert cut_reply("short", 160) == "short"
    long = "word " * 100
    cut = cut_reply(long, 40)
    assert len(cut) <= 41
    assert cut.endswith("…")
    assert "wor…" not in cut


ROUND = RoundConfig(name="Round 2", prompt="Code is {code}.", censor="digits",
                    memory_messages=2, max_reply_chars=200, temperature=0.7)
HISTORY = [
    {"role": "you", "text": "one", "censored": False},
    {"role": "guard", "text": "two", "censored": False},
    {"role": "you", "text": "three", "censored": False},
    {"role": "guard", "text": "four", "censored": False},
]


def reply(guard, round_cfg=ROUND, message="hi"):
    return asyncio.run(guard.reply(round_cfg=round_cfg, code="4712", history=HISTORY,
                                   message=message, tags=["t"], metadata={}))


def test_guard_builds_messages_with_memory(clock):
    model = FakeModel("fine")
    guard = Guard(make_chain(clock, {"m1": model}))
    result = reply(guard)
    sent = model.calls[0]
    assert isinstance(sent[0], SystemMessage) and sent[0].content == "Code is 4712."
    assert [m.content for m in sent[1:]] == ["three", "four", "hi"]
    assert isinstance(sent[1], HumanMessage) and isinstance(sent[2], AIMessage)
    assert (result.text, result.censored, result.model) == ("fine", False, "m1")


def test_guard_without_memory(clock):
    model = FakeModel("fine")
    guard = Guard(make_chain(clock, {"m1": model}))
    no_memory = RoundConfig(**{**ROUND.__dict__, "memory_messages": 0})
    reply(guard, round_cfg=no_memory)
    assert [m.content for m in model.calls[0][1:]] == ["hi"]


def test_guard_censors_code(clock):
    guard = Guard(make_chain(clock, {"m1": FakeModel("Fine, it is 4-7-1-2.")}))
    result = reply(guard)
    assert (result.text, result.censored) == (CENSORED_TEXT, True)


def test_guard_cuts_before_censoring(clock):
    tail = "x " * 100 + "4712"
    guard = Guard(make_chain(clock, {"m1": FakeModel(tail)}))
    short = RoundConfig(**{**ROUND.__dict__, "max_reply_chars": 40})
    result = reply(guard, round_cfg=short)
    assert result.censored is False
    assert "4712" not in result.text
