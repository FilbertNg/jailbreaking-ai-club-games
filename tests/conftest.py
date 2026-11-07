import copy

import pytest

from jailbreak.config import parse_config

TEST_CONFIG = {
    "models": ["m1", "m2", "m3"],
    "model_skip_s": 60,
    "model_timeout_s": 30,
    "max_output_tokens": 1024,
    "team_names": {"a": "Team A", "b": "Team B"},
    "game_minutes": 10,
    "tiebreaker_minutes": 3,
    "wrong_guess_cooldown_s": 10,
    "tie_window_s": 10,
    "hint_minutes": [3, 6, 8],
    "hints": ["hint one", "hint two", "hint three"],
    "rounds": [
        {"name": "Round 1", "prompt": "R1 code {code}", "censor": "none",
         "memory_messages": 20, "max_reply_chars": 1200, "temperature": 0.9},
        {"name": "Round 2", "prompt": "R2 code {code}", "censor": "digits",
         "memory_messages": 20, "max_reply_chars": 800, "temperature": 0.7},
        {"name": "Round 3", "prompt": "R3 code {code}", "censor": "strict",
         "memory_messages": 0, "max_reply_chars": 160, "temperature": 0.3},
    ],
    "tiebreaker": {"name": "Tiebreaker", "prompt": "TB code {code}", "censor": "digits",
                   "memory_messages": 20, "max_reply_chars": 600, "temperature": 0.7},
}


class Clock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def test_config_dict():
    return copy.deepcopy(TEST_CONFIG)


@pytest.fixture
def cfg(test_config_dict):
    return parse_config(test_config_dict)


@pytest.fixture
def clock():
    return Clock()
