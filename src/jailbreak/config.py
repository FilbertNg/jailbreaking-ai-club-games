from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CENSOR_MODES = ("none", "digits", "strict")


class ConfigError(Exception):
    """config.json or .env is missing something. The message says what to fix."""


@dataclass(frozen=True)
class RoundConfig:
    name: str
    prompt: str
    censor: str
    memory_messages: int
    max_reply_chars: int
    temperature: float


@dataclass(frozen=True)
class GameConfig:
    models: tuple[str, ...]
    model_skip_s: float
    model_timeout_s: float
    max_output_tokens: int
    team_names: dict[str, str]
    game_minutes: float
    tiebreaker_minutes: float
    wrong_guess_cooldown_s: float
    tie_window_s: float
    hint_minutes: tuple[float, ...]
    hints: tuple[str, ...]
    rounds: tuple[RoundConfig, ...]
    tiebreaker: RoundConfig


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    host_pin: str | None


def _round(raw: dict, where: str) -> RoundConfig:
    try:
        rnd = RoundConfig(
            name=str(raw["name"]),
            prompt=str(raw["prompt"]),
            censor=str(raw["censor"]),
            memory_messages=int(raw["memory_messages"]),
            max_reply_chars=int(raw["max_reply_chars"]),
            temperature=float(raw["temperature"]),
        )
    except KeyError as exc:
        raise ConfigError(f"{where} is missing {exc.args[0]!r}") from None
    if "{code}" not in rnd.prompt:
        raise ConfigError(f"{where} prompt must contain {{code}}")
    if rnd.censor not in CENSOR_MODES:
        raise ConfigError(f"{where} censor must be one of {', '.join(CENSOR_MODES)}")
    return rnd


def parse_config(raw: dict) -> GameConfig:
    try:
        cfg = GameConfig(
            models=tuple(str(m) for m in raw["models"]),
            model_skip_s=float(raw["model_skip_s"]),
            model_timeout_s=float(raw["model_timeout_s"]),
            max_output_tokens=int(raw["max_output_tokens"]),
            team_names={"a": str(raw["team_names"]["a"]), "b": str(raw["team_names"]["b"])},
            game_minutes=float(raw["game_minutes"]),
            tiebreaker_minutes=float(raw["tiebreaker_minutes"]),
            wrong_guess_cooldown_s=float(raw["wrong_guess_cooldown_s"]),
            tie_window_s=float(raw["tie_window_s"]),
            hint_minutes=tuple(float(m) for m in raw["hint_minutes"]),
            hints=tuple(str(h) for h in raw["hints"]),
            rounds=tuple(_round(r, f"rounds[{i}]") for i, r in enumerate(raw["rounds"])),
            tiebreaker=_round(raw["tiebreaker"], "tiebreaker"),
        )
    except KeyError as exc:
        raise ConfigError(f"config.json is missing {exc.args[0]!r}") from None
    if not cfg.models:
        raise ConfigError("config.json needs at least one entry in 'models'")
    if not cfg.rounds:
        raise ConfigError("config.json needs at least one round")
    if len(cfg.hints) != len(cfg.hint_minutes):
        raise ConfigError("'hints' and 'hint_minutes' must have the same length")
    return cfg


def load_config(path: Path = ROOT / "config.json") -> GameConfig:
    return parse_config(json.loads(path.read_text(encoding="utf-8")))


def load_settings(env_path: Path = ROOT / ".env") -> Settings:
    load_dotenv(env_path)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ConfigError("GEMINI_API_KEY is missing. Add it to .env (see README).")
    pin = os.environ.get("HOST_PIN", "").strip() or None
    return Settings(gemini_api_key=key, host_pin=pin)
