from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from jailbreak.censor import CENSORED_TEXT, is_blocked
from jailbreak.config import GameConfig, RoundConfig

log = logging.getLogger("jailbreak.guard")

# Errors no other model can fix: the key itself is rejected.
FATAL_CODES = {401, 403}


class GuardBusy(Exception):
    """Every model in the chain is failing or skipped right now."""


class GuardError(Exception):
    """The API refused the request in a way a different model will not fix."""


@dataclass(frozen=True)
class GuardReply:
    text: str
    censored: bool
    model: str


def _status_code(exc: BaseException) -> int | None:
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < 6:
        code = getattr(current, "code", None)
        if isinstance(code, int):
            return code
        current = current.__cause__ or current.__context__
        seen += 1
    return None


def cut_reply(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,.;:") + "…"


class ModelChain:
    def __init__(
        self,
        model_ids: list[str],
        factory: Callable[[str, float], object],
        skip_s: float,
        timeout_s: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model_ids = list(model_ids)
        self._factory = factory
        self._skip_s = skip_s
        self._timeout_s = timeout_s
        self._now = now
        self._skipped_until = {m: 0.0 for m in self.model_ids}
        self._cache: dict[tuple[str, float], object] = {}

    async def ainvoke(self, messages: list[BaseMessage], *, temperature: float, config: dict) -> tuple[str, str]:
        for model_id in self.model_ids:
            if self._now() < self._skipped_until[model_id]:
                continue
            model = self._model(model_id, temperature)
            try:
                msg = await asyncio.wait_for(model.ainvoke(messages, config=config), self._timeout_s)
            except TimeoutError:
                self._skip(model_id, "timed out")
                continue
            except Exception as exc:
                code = _status_code(exc)
                if code in FATAL_CODES:
                    raise GuardError(f"{model_id} rejected the API key (HTTP {code}).") from exc
                self._skip(model_id, f"HTTP {code}" if code else type(exc).__name__)
                continue
            text = msg.text.strip()
            if not text:
                self._skip(model_id, "empty reply")
                continue
            return text, model_id
        raise GuardBusy("Every model is busy or failing.")

    def _model(self, model_id: str, temperature: float) -> object:
        key = (model_id, temperature)
        if key not in self._cache:
            self._cache[key] = self._factory(model_id, temperature)
        return self._cache[key]

    def _skip(self, model_id: str, reason: str) -> None:
        self._skipped_until[model_id] = self._now() + self._skip_s
        log.warning("Skipping %s for %ss: %s", model_id, self._skip_s, reason)


class Guard:
    def __init__(self, chain: ModelChain) -> None:
        self.chain = chain

    async def reply(
        self,
        *,
        round_cfg: RoundConfig,
        code: str,
        history: list[dict],
        message: str,
        tags: list[str],
        metadata: dict,
    ) -> GuardReply:
        memory = history[-round_cfg.memory_messages:] if round_cfg.memory_messages > 0 else []
        messages: list[BaseMessage] = [SystemMessage(round_cfg.prompt.replace("{code}", code))]
        for m in memory:
            messages.append(HumanMessage(m["text"]) if m["role"] == "you" else AIMessage(m["text"]))
        messages.append(HumanMessage(message))
        text, model_id = await self.chain.ainvoke(
            messages,
            temperature=round_cfg.temperature,
            config={"run_name": "vaultbot", "tags": tags, "metadata": metadata},
        )
        text = cut_reply(text, round_cfg.max_reply_chars)
        if is_blocked(text, code, round_cfg.censor):
            return GuardReply(CENSORED_TEXT, True, model_id)
        return GuardReply(text, False, model_id)


def build_guard(cfg: GameConfig) -> Guard:
    def factory(model_id: str, temperature: float) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=model_id,
            temperature=temperature,
            max_output_tokens=cfg.max_output_tokens,
            max_retries=0,
            timeout=cfg.model_timeout_s,
        )

    return Guard(ModelChain(list(cfg.models), factory, cfg.model_skip_s, cfg.model_timeout_s))
