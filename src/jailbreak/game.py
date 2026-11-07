from __future__ import annotations

import math
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from jailbreak.config import GameConfig, RoundConfig

TEAMS = ("a", "b")
ACTIVE_PHASES = ("running", "tiebreaker")


class GameRuleError(Exception):
    """The current phase does not allow this action. The message is shown to people."""


@dataclass
class TeamState:
    name: str
    codes: list[str] = field(default_factory=list)
    tiebreak_code: str = ""
    round_index: int = 0
    rounds_cleared: int = 0
    clear_times: list[float] = field(default_factory=list)
    chat: list[dict] = field(default_factory=list)
    wrong_guesses: int = 0
    tiebreak_wrong: int = 0
    cooldown_until: float = 0.0


@dataclass(frozen=True)
class ChatContext:
    key: tuple
    round: RoundConfig
    code: str
    history: list[dict]


def _clean_names(names: dict) -> dict[str, str]:
    clean = {}
    for t in TEAMS:
        name = str(names.get(t) or "").strip()
        if not 1 <= len(name) <= 24:
            raise GameRuleError("Each team name needs 1 to 24 characters.")
        clean[t] = name
    return clean


class Game:
    def __init__(
        self,
        cfg: GameConfig,
        now: Callable[[], float] = time.time,
        on_change: Callable[[dict], None] | None = None,
        on_result: Callable[[dict], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self._now = now
        self._on_change = on_change or (lambda data: None)
        self._on_result = on_result or (lambda record: None)
        self.session = 1
        self._reset_session(dict(cfg.team_names))

    def _reset_session(self, names: dict[str, str]) -> None:
        self.phase = "lobby"
        self.teams = {t: TeamState(name=names[t]) for t in TEAMS}
        self.started_at: float | None = None
        self.ends_at: float | None = None
        self.tiebreak_ends_at: float | None = None
        self.extra_hints = 0
        self.winner: str | None = None
        self.how_ended: str | None = None

    def code_for(self, team: str) -> str:
        t = self.teams[team]
        if self.phase in ("tiebreaker", "tiebreak_over"):
            return t.tiebreak_code
        return t.codes[t.round_index] if t.codes else ""

    def current_round(self, team: str) -> RoundConfig:
        if self.phase in ("tiebreaker", "tiebreak_over"):
            return self.cfg.tiebreaker
        return self.cfg.rounds[self.teams[team].round_index]

    def start(self) -> None:
        self.tick()
        if self.phase != "lobby":
            raise GameRuleError("This session has already started.")
        for _ in self.cfg.rounds:
            a, b = self._new_code_pair()
            self.teams["a"].codes.append(a)
            self.teams["b"].codes.append(b)
        now = self._now()
        self.started_at = now
        self.ends_at = now + self.cfg.game_minutes * 60
        self.phase = "running"
        self._changed()

    def tick(self) -> None:
        now = self._now()
        if self.phase == "running" and now >= self.ends_at:
            self._time_up()
        elif self.phase == "tiebreaker" and now >= self.tiebreak_ends_at:
            self.phase = "tiebreak_over"
            self._changed()

    def guess(self, team: str, code: str) -> dict:
        self.tick()
        self._require_active()
        code = code.strip()
        if len(code) != 4 or not code.isdigit():
            return {"result": "invalid", "cooldown_s": 0}
        t = self.teams[team]
        now = self._now()
        if now < t.cooldown_until:
            return {"result": "cooldown", "cooldown_s": round(t.cooldown_until - now, 1)}
        if code == self.code_for(team):
            if self.phase == "tiebreaker":
                self._finish(team, "tiebreaker")
            else:
                self._clear(team)
            return {"result": "correct", "cooldown_s": 0}
        if self.phase == "tiebreaker":
            t.tiebreak_wrong += 1
        else:
            t.wrong_guesses += 1
        t.cooldown_until = now + self.cfg.wrong_guess_cooldown_s
        self._changed()
        return {"result": "wrong", "cooldown_s": self.cfg.wrong_guess_cooldown_s}

    def to_dict(self) -> dict:
        return {
            "session": self.session,
            "phase": self.phase,
            "started_at": self.started_at,
            "ends_at": self.ends_at,
            "tiebreak_ends_at": self.tiebreak_ends_at,
            "extra_hints": self.extra_hints,
            "winner": self.winner,
            "how_ended": self.how_ended,
            "teams": {t: asdict(s) for t, s in self.teams.items()},
        }

    def start_tiebreaker(self) -> None:
        self.tick()
        if self.phase != "tie":
            raise GameRuleError("A tiebreaker can only start after a tie.")
        a, b = self._new_code_pair()
        self.teams["a"].tiebreak_code = a
        self.teams["b"].tiebreak_code = b
        for t in self.teams.values():
            t.chat = []
            t.cooldown_until = 0.0
        self.tiebreak_ends_at = self._now() + self.cfg.tiebreaker_minutes * 60
        self.phase = "tiebreaker"
        self._changed()

    def award(self, team: str) -> None:
        self.tick()
        if self.phase not in ("tie", "tiebreak_over"):
            raise GameRuleError("Award the win only after a tie, or after a tiebreaker with no winner.")
        self._finish(team, "host_award")

    def skip_round(self, team: str) -> None:
        self.tick()
        if self.phase != "running":
            raise GameRuleError("Skip works only during the main game.")
        self._clear(team)

    def next_hint(self) -> None:
        self.tick()
        if self.phase != "running":
            raise GameRuleError("Hints are given only during the main game.")
        if self.hints_revealed() >= len(self.cfg.hints):
            raise GameRuleError("All hints are already showing.")
        self.extra_hints += 1
        self._changed()

    def hints_revealed(self) -> int:
        if self.started_at is None:
            return 0
        elapsed_min = (self._now() - self.started_at) / 60
        by_time = sum(1 for m in self.cfg.hint_minutes if elapsed_min >= m)
        return min(len(self.cfg.hints), by_time + self.extra_hints)

    @classmethod
    def from_dict(
        cls,
        cfg: GameConfig,
        data: dict,
        now: Callable[[], float] = time.time,
        on_change: Callable[[dict], None] | None = None,
        on_result: Callable[[dict], None] | None = None,
    ) -> Game:
        game = cls(cfg, now=now, on_change=on_change, on_result=on_result)
        game.session = data["session"]
        game.phase = data["phase"]
        game.started_at = data["started_at"]
        game.ends_at = data["ends_at"]
        game.tiebreak_ends_at = data["tiebreak_ends_at"]
        game.extra_hints = data["extra_hints"]
        game.winner = data["winner"]
        game.how_ended = data["how_ended"]
        game.teams = {t: TeamState(**data["teams"][t]) for t in TEAMS}
        return game

    def new_session(self, names: dict) -> None:
        clean = _clean_names(names)
        self.tick()
        if self.phase == "lobby":
            for t in TEAMS:
                self.teams[t].name = clean[t]
            self._changed()
            return
        if self.phase != "finished":
            self._finish(None, "stopped_early")
        self.session += 1
        self._reset_session(clean)
        self._changed()

    def rename(self, names: dict) -> None:
        clean = _clean_names(names)
        self.tick()
        if self.phase != "lobby":
            raise GameRuleError("Team names can only change before the session starts.")
        for t in TEAMS:
            self.teams[t].name = clean[t]
        self._changed()

    def chat_context(self, team: str) -> ChatContext:
        self.tick()
        self._require_active()
        return ChatContext(
            key=self._round_key(team),
            round=self.current_round(team),
            code=self.code_for(team),
            history=list(self.teams[team].chat),
        )

    def add_exchange(self, team: str, key: tuple, message: str, reply: str, censored: bool) -> bool:
        self.tick()
        if self.phase not in ACTIVE_PHASES or key != self._round_key(team):
            return False
        self.teams[team].chat.extend([
            {"role": "you", "text": message, "censored": False},
            {"role": "guard", "text": reply, "censored": censored},
        ])
        self._changed()
        return True

    def public_state(self, team: str) -> dict:
        self.tick()
        t = self.teams[team]
        now = self._now()
        in_tiebreak = self.phase in ("tiebreaker", "tiebreak_over")
        cooldown = t.cooldown_until - now if self.phase in ACTIVE_PHASES else 0
        return {
            "session": self.session,
            "phase": self.phase,
            "team": team,
            "team_names": {k: v.name for k, v in self.teams.items()},
            "seconds_left": self._seconds_left(),
            "rounds_total": len(self.cfg.rounds),
            "rounds_cleared": {k: v.rounds_cleared for k, v in self.teams.items()},
            "round_number": None if in_tiebreak else t.round_index + 1,
            "round_name": self.current_round(team).name,
            "chat": [dict(m) for m in t.chat],
            "hints": list(self.cfg.hints[: self.hints_revealed()]),
            "hints_total": len(self.cfg.hints),
            "cooldown_s": max(0, math.ceil(cooldown)),
            "winner": self.winner,
            "how_ended": self.how_ended,
            "wrong_guesses": {k: v.wrong_guesses for k, v in self.teams.items()},
            "tiebreak_wrong": {k: v.tiebreak_wrong for k, v in self.teams.items()},
        }

    def live_standing(self) -> dict:
        self.tick()
        return {
            "session": self.session,
            "phase": self.phase,
            "rounds_total": len(self.cfg.rounds),
            "seconds_left": self._seconds_left(),
            "winner": self.winner,
            "how_ended": self.how_ended,
            "teams": {k: {"name": v.name, "rounds_cleared": v.rounds_cleared} for k, v in self.teams.items()},
        }

    def _seconds_left(self) -> int | None:
        if self.phase == "running":
            return max(0, math.ceil(self.ends_at - self._now()))
        if self.phase == "tiebreaker":
            return max(0, math.ceil(self.tiebreak_ends_at - self._now()))
        return None

    def _round_key(self, team: str) -> tuple:
        return (self.session, self.phase, self.teams[team].round_index)

    def _require_active(self) -> None:
        if self.phase not in ACTIVE_PHASES:
            raise GameRuleError("The vault is closed right now. Wait for the host.")

    def _clear(self, team: str) -> None:
        t = self.teams[team]
        t.clear_times.append(round(self._now() - self.started_at, 1))
        t.rounds_cleared += 1
        t.chat = []
        if t.rounds_cleared >= len(self.cfg.rounds):
            self._finish(team, "cracked_all")
        else:
            t.round_index += 1
            self._changed()

    def _time_up(self) -> None:
        a, b = self.teams["a"], self.teams["b"]
        if a.rounds_cleared != b.rounds_cleared:
            leader = "a" if a.rounds_cleared > b.rounds_cleared else "b"
            self._finish(leader, "more_rounds")
            return
        if a.rounds_cleared == 0 or abs(a.clear_times[-1] - b.clear_times[-1]) <= self.cfg.tie_window_s:
            self.phase = "tie"
            self._changed()
            return
        self._finish("a" if a.clear_times[-1] < b.clear_times[-1] else "b", "faster_clear")

    def _finish(self, team: str | None, how: str) -> None:
        self.phase = "finished"
        self.winner = team
        self.how_ended = how
        self._on_result(self._result_record())
        self._changed()

    def _result_record(self) -> dict:
        return {
            "session": self.session,
            "started_at": self.started_at,
            "ended_at": self._now(),
            "rounds_total": len(self.cfg.rounds),
            "winner": self.winner,
            "how_ended": self.how_ended,
            "teams": {
                t: {
                    "name": s.name,
                    "rounds_cleared": s.rounds_cleared,
                    "clear_times": list(s.clear_times),
                    "wrong_guesses": s.wrong_guesses,
                    "tiebreak_wrong": s.tiebreak_wrong,
                }
                for t, s in self.teams.items()
            },
        }

    def _new_code_pair(self) -> tuple[str, str]:
        while True:
            a = str(1000 + secrets.randbelow(9000))
            b = str(1000 + secrets.randbelow(9000))
            if a != b:
                return a, b

    def _changed(self) -> None:
        self._on_change(self.to_dict())
