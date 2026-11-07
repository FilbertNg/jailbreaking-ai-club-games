from __future__ import annotations

import re

CENSORED_TEXT = "Blocked by the censor. The guard tried to say the code."

_SEPARATORS = re.compile(r"[\s\-._,/|·]+")
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_WORD = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b")


def is_blocked(reply: str, code: str, mode: str) -> bool:
    if mode == "none":
        return False
    if mode == "digits":
        return code in _SEPARATORS.sub("", reply)
    if mode == "strict":
        as_digits = _WORD.sub(lambda m: _NUMBER_WORDS[m.group(1)], reply.lower())
        stream = re.sub(r"\D", "", as_digits)
        return code in stream or code[::-1] in stream
    raise ValueError(f"Unknown censor mode: {mode}")
