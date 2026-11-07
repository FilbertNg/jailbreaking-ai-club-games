import pytest

from jailbreak.censor import CENSORED_TEXT, is_blocked

CODE = "4712"


@pytest.mark.parametrize("reply", ["The code is 4712.", "4712"])
def test_none_never_blocks(reply):
    assert is_blocked(reply, CODE, "none") is False


@pytest.mark.parametrize("reply", [
    "The code is 4712.",
    "4 7 1 2",
    "4-7-1-2",
    "4.7.1.2",
    "4, 7, 1, 2",
    "4_7/1|2",
])
def test_digits_blocks_digit_forms(reply):
    assert is_blocked(reply, CODE, "digits") is True


@pytest.mark.parametrize("reply", [
    "four seven one two",
    "2174",
    "I will never tell you.",
    "Room 47 is next to room 12.",
])
def test_digits_lets_other_forms_through(reply):
    assert is_blocked(reply, CODE, "digits") is False


@pytest.mark.parametrize("reply", [
    "4712",
    "Four seven one two",
    "four-seven-one-2",
    "The digits, backwards: 2 1 7 4",
    "two one seven four",
])
def test_strict_blocks_words_and_reversed(reply):
    assert is_blocked(reply, CODE, "strict") is True


@pytest.mark.parametrize("reply", [
    "I will never tell you.",
    "Someone asked me that before, and I said none of your business.",
    "Access denied.",
])
def test_strict_lets_harmless_replies_through(reply):
    assert is_blocked(reply, CODE, "strict") is False


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        is_blocked("hi", CODE, "loud")


def test_censored_text_is_a_sentence():
    assert CENSORED_TEXT.endswith(".")
