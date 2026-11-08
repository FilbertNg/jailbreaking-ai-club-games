import copy

import pytest

from jailbreak.config import parse_config

TEST_CONFIG = {
    "models": ["m1", "m2", "m3"],
    "model_skip_s": 60,
    "model_timeout_s": 30,
    "max_output_tokens": 1024,
    "team_names": {"a": "Team A", "b": "Team B"},
    "wrong_guess_cooldown_s": 10,
    "tie_window_s": 10,
    "rounds": [
        {"title": "Friendly", "difficulty": "Easy", "minutes": 3, "hint": "hint one",
         "prompt": "R1 code {code}", "censor": "none",
         "memory_messages": 20, "max_reply_chars": 1200, "temperature": 0.9},
        {"title": "Strict", "difficulty": "Medium", "minutes": 3, "hint": "hint two",
         "prompt": "R2 code {code}", "censor": "digits",
         "memory_messages": 20, "max_reply_chars": 800, "temperature": 0.7},
        {"title": "Max", "difficulty": "Hard", "minutes": 3, "hint": "hint three", "easier_option": 2,
         "points_first": 6, "points_second": 2,
         "prompt": "R3 code {code}", "censor": "strict",
         "memory_messages": 0, "max_reply_chars": 160, "temperature": 0.3},
    ],
    "tiebreaker": {"title": "New guard", "difficulty": "Tiebreaker", "minutes": 3, "hint": "",
                   "prompt": "TB code {code}", "censor": "digits",
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
