from __future__ import annotations

import math
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from jailbreak.config import GameConfig, RoundConfig

TEAMS = ("a", "b")
PLAY_PHASES = ("round", "tiebreaker")
MAX_SECONDS = 3600


class GameRuleError(Exception):
    """The current phase does not allow this action. The message is shown to people."""


@dataclass
class TeamState:
    name: str
    codes: list[str] = field(default_factory=list)
    crack_times: list[float | None] = field(default_factory=list)
    points: list[int] = field(default_factory=list)
    tiebreak_code: str = ""
    chat: list[dict] = field(default_factory=list)
    wrong_guesses: int = 0
    tiebreak_wrong: int = 0
    cooldown_until: float = 0.0

    @property
    def rounds_cleared(self) -> int:
        return sum(1 for t in self.crack_times if t is not None)

    @property
    def total_points(self) -> int:
        return sum(self.points)

    @property
    def total_time(self) -> float:
        return round(sum(t for t in self.crack_times if t is not None), 1)


@dataclass(frozen=True)
class ChatContext:
    key: tuple
    round: RoundConfig
    code: str
    history: list[dict]
    tag: str
    name: str


def _clean_names(names: dict) -> dict[str, str]:
    clean = {}
    for t in TEAMS:
        name = str(names.get(t) or "").strip()
        if not 1 <= len(name) <= 24:
            raise GameRuleError("Each team name needs 1 to 24 characters.")
        clean[t] = name
    return clean


def _check_seconds(seconds: float, what: str) -> float:
    seconds = float(seconds)
    if not 0 < seconds <= MAX_SECONDS:
        raise GameRuleError(f"{what} must be more than 0 and at most 60 minutes.")
    return seconds


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
        self.base_minutes = [r.minutes for r in cfg.rounds]
        self._reset_session(dict(cfg.team_names))

    def _reset_session(self, names: dict[str, str]) -> None:
        self.phase = "lobby"
        self.teams = {t: TeamState(name=names[t]) for t in TEAMS}
        self.round_no = -1
        self.plan: list[int] = []
        self.started_at: float | None = None
        self.ends_at: float | None = None
        self.paused_left: float | None = None
        self.play_elapsed = 0.0
        self.resumed_at: float | None = None
        self.hint_given = False
        self.hints_shown: list[str] = []
        self.winner: str | None = None
        self.how_ended: str | None = None
        self.reveals: list[dict] = []

    # Reading the state

    @property
    def paused(self) -> bool:
        return self.paused_left is not None

    def current_round(self, team: str | None = None) -> RoundConfig:
        if self.phase in ("tiebreaker", "tiebreak_over"):
            return self.cfg.tiebreaker
        if self.round_no < 0:
            return self.cfg.rounds[0]
        return self.cfg.rounds[self.plan[self.round_no]]

    def code_for(self, team: str) -> str:
        t = self.teams[team]
        if self.phase in ("tiebreaker", "tiebreak_over"):
            return t.tiebreak_code
        return t.codes[self.round_no] if 0 <= self.round_no < len(t.codes) else ""

    def public_state(self, team: str) -> dict:
        self.tick()
        t = self.teams[team]
        playing = self.phase in PLAY_PHASES
        in_tiebreak = self.phase in ("tiebreaker", "tiebreak_over")
        cooldown = t.cooldown_until - self._now() if playing else 0
        return {
            "session": self.session,
            "phase": self.phase,
            "paused": self.paused,
            "team": team,
            "team_names": {k: v.name for k, v in self.teams.items()},
            "seconds_left": math.ceil(self._remaining()) if playing else None,
            "rounds_total": len(self.cfg.rounds),
            "rounds_cleared": {k: v.rounds_cleared for k, v in self.teams.items()},
            "points": {k: v.total_points for k, v in self.teams.items()},
            "round_points": self._round_points(),
            "rule_broken_points": self.cfg.rule_broken_points,
            "total_time": {k: v.total_time for k, v in self.teams.items()},
            "round_number": None if in_tiebreak else max(1, self.round_no + 1),
            "round_name": self._round_name(),
            "difficulty": self.current_round().difficulty,
            "cracked_this_round": {k: self._cracked_now(k) for k in TEAMS},
            "next_round": self._next_round_info(),
            "base_minutes": list(self.base_minutes),
            "tiebreaker_minutes": self.cfg.tiebreaker.minutes,
            "hint_given": self.hint_given,
            "chat": [dict(m) for m in t.chat],
            "hints": list(self.hints_shown),
            "cooldown_s": max(0, math.ceil(cooldown)),
            "winner": self.winner,
            "how_ended": self.how_ended,
            "reveals": [dict(r) for r in self.reveals],
            "wrong_guesses": {k: v.wrong_guesses for k, v in self.teams.items()},
            "tiebreak_wrong": {k: v.tiebreak_wrong for k, v in self.teams.items()},
            "speech_lang": self.cfg.speech_lang,
        }

    def live_standing(self) -> dict:
        self.tick()
        playing = self.phase in PLAY_PHASES
        return {
            "session": self.session,
            "phase": self.phase,
            "paused": self.paused,
            "round_number": None if self.round_no < 0 else self.round_no + 1,
            "rounds_total": len(self.cfg.rounds),
            "seconds_left": math.ceil(self._remaining()) if playing else None,
            "winner": self.winner,
            "how_ended": self.how_ended,
            "teams": {k: {"name": v.name, "rounds_cleared": v.rounds_cleared, "points": v.total_points}
                      for k, v in self.teams.items()},
        }

    # Host: setting up

    def rename(self, names: dict) -> None:
        clean = _clean_names(names)
        self.tick()
        if self.phase != "lobby":
            raise GameRuleError("Team names can only change before the session starts.")
        for t in TEAMS:
            self.teams[t].name = clean[t]
        self._changed()

    def set_round_minutes(self, minutes: list) -> None:
        if self.phase != "lobby":
            raise GameRuleError("Base times are set before the session starts. During the game, use the clock buttons.")
        if len(minutes) != len(self.cfg.rounds):
            raise GameRuleError(f"Give a time for each of the {len(self.cfg.rounds)} rounds.")
        values = [_check_seconds(float(m) * 60, "Each round time") / 60 for m in minutes]
        self.base_minutes = values
        self._changed()

    def new_session(self, names: dict) -> None:
        clean = _clean_names(names)
        self.tick()
        if self.phase == "lobby":
            for t in TEAMS:
                self.teams[t].name = clean[t]
            self._changed()
            return
        if self.phase != "finished":
            self._reveal_unsolved()
            self._stop_clock()
            self._finish(None, "stopped_early")
        self.session += 1
        self._reset_session(clean)
        self._changed()

    # Host: rounds and clock

    def start_round(self, minutes: float | None = None, variant: int | None = None) -> None:
        self.tick()
        if self.phase in PLAY_PHASES:
            raise GameRuleError("A round is already running.")
        if self.phase not in ("lobby", "intermission"):
            raise GameRuleError("There is no next round to start.")
        options = self._next_options()
        variant = options[0] if variant is None else int(variant)
        if variant not in options:
            raise GameRuleError("That difficulty is not offered for this round.")
        k = self.round_no + 1
        seconds = _check_seconds((self.base_minutes[k] if minutes is None else float(minutes)) * 60, "Round time")
        a, b = self._new_code_pair()
        for team, code in (("a", a), ("b", b)):
            t = self.teams[team]
            t.codes.append(code)
            t.crack_times.append(None)
            t.points.append(0)
            t.chat = []
            t.cooldown_until = 0.0
        self.plan.append(variant - 1)
        self.round_no = k
        if self.started_at is None:
            self.started_at = self._now()
        self._start_clock(seconds)
        self.phase = "round"
        self._changed()

    def end_round(self) -> None:
        self.tick()
        if self.phase != "round":
            raise GameRuleError("No round is running.")
        self._end_round()

    def rule_broken(self, team: str) -> None:
        self.tick()
        if self.phase != "round":
            raise GameRuleError("A team can only lose a round while that round is running.")
        k = self.round_no
        offender = self.teams[team]
        other = self.teams["b" if team == "a" else "a"]
        offender.points[k] = 0
        offender.crack_times[k] = None
        other.points[k] = max(other.points[k], self.cfg.rule_broken_points)
        self.reveals = [r for r in self.reveals if not (r["team"] == team and r["vault"] == k + 1)]
        self._reveal(team, k + 1, "rule_broken")
        self._end_round()

    def pause(self) -> None:
        self.tick()
        if self.phase not in PLAY_PHASES:
            raise GameRuleError("There is no clock to pause right now.")
        if self.paused:
            raise GameRuleError("The game is already paused.")
        now = self._now()
        self.paused_left = max(0.0, self.ends_at - now)
        self.play_elapsed += now - self.resumed_at
        self.ends_at = None
        self.resumed_at = None
        self._changed()

    def resume(self) -> None:
        self.tick()
        if self.phase not in PLAY_PHASES or not self.paused:
            raise GameRuleError("The game is not paused.")
        now = self._now()
        self.ends_at = now + self.paused_left
        self.resumed_at = now
        self.paused_left = None
        self._changed()

    def add_time(self, seconds: float) -> None:
        self.tick()
        self._require_clock()
        seconds = _check_seconds(seconds, "Added time")
        if self.paused:
            self.paused_left += seconds
        else:
            self.ends_at += seconds
        self._changed()

    def set_time(self, seconds: float) -> None:
        self.tick()
        self._require_clock()
        seconds = _check_seconds(seconds, "Time left")
        if self.paused:
            self.paused_left = seconds
        else:
            self.ends_at = self._now() + seconds
        self._changed()

    def show_hint(self) -> None:
        self.tick()
        if self.phase != "round":
            raise GameRuleError("Hints are given only during a round.")
        if self.hint_given:
            raise GameRuleError("This round's hint is already showing.")
        self._give_hint()

    def start_tiebreaker(self, minutes: float | None = None) -> None:
        self.tick()
        if self.phase != "tie":
            raise GameRuleError("A tiebreaker can only start after a tie.")
        seconds = _check_seconds((self.cfg.tiebreaker.minutes if minutes is None else float(minutes)) * 60,
                                 "Tiebreaker time")
        a, b = self._new_code_pair()
        self.teams["a"].tiebreak_code = a
        self.teams["b"].tiebreak_code = b
        for t in self.teams.values():
            t.chat = []
            t.cooldown_until = 0.0
        self._start_clock(seconds)
        self.phase = "tiebreaker"
        self._changed()

    def award(self, team: str) -> None:
        self.tick()
        if self.phase not in ("tie", "tiebreak_over"):
            raise GameRuleError("Award the win only after a tie, or after a tiebreaker with no winner.")
        self._finish(team, "host_award")

    # Teams: playing

    def tick(self) -> None:
        if self.phase in PLAY_PHASES and not self.paused and self._now() >= self.ends_at:
            if self.phase == "round":
                self._end_round()
            else:
                self._reveal_unsolved()
                self._stop_clock()
                self.phase = "tiebreak_over"
                self._changed()
            return
        self._maybe_give_hint()

    def guess(self, team: str, code: str) -> dict:
        self.tick()
        self._require_playing(team)
        code = code.strip()
        if len(code) != 4 or not code.isdigit():
            return {"result": "invalid", "cooldown_s": 0}
        t = self.teams[team]
        now = self._now()
        if now < t.cooldown_until:
            return {"result": "cooldown", "cooldown_s": round(t.cooldown_until - now, 1)}
        if code == self.code_for(team):
            earned = 0
            if self.phase == "tiebreaker":
                self._reveal(team, None, "cracked")
                self._reveal_unsolved()
                self._stop_clock()
                self._finish(team, "tiebreaker")
            else:
                earned = self._points_for_crack(team)
                t.points[self.round_no] = earned
                t.crack_times[self.round_no] = round(self._elapsed(), 1)
                self._reveal(team, self.round_no + 1, "cracked")
                if all(self._cracked_now(k) for k in TEAMS):
                    self._end_round()
                else:
                    self._changed()
            return {"result": "correct", "cooldown_s": 0, "points": earned}
        if self.phase == "tiebreaker":
            t.tiebreak_wrong += 1
        else:
            t.wrong_guesses += 1
        t.cooldown_until = now + self.cfg.wrong_guess_cooldown_s
        self._changed()
        return {"result": "wrong", "cooldown_s": self.cfg.wrong_guess_cooldown_s}

    def chat_context(self, team: str) -> ChatContext:
        self.tick()
        self._require_playing(team)
        tag = "tiebreaker" if self.phase == "tiebreaker" else f"round-{self.round_no + 1}"
        return ChatContext(
            key=self._round_key(),
            round=self.current_round(),
            code=self.code_for(team),
            history=list(self.teams[team].chat),
            tag=tag,
            name=self._round_name(),
        )

    def add_exchange(self, team: str, key: tuple, message: str, reply: str, censored: bool) -> bool:
        self.tick()
        if self.phase not in PLAY_PHASES or key != self._round_key():
            return False
        self.teams[team].chat.extend([
            {"role": "you", "text": message, "censored": False},
            {"role": "guard", "text": reply, "censored": censored},
        ])
        self._changed()
        return True

    # Saving

    def to_dict(self) -> dict:
        return {
            "session": self.session,
            "phase": self.phase,
            "base_minutes": list(self.base_minutes),
            "round_no": self.round_no,
            "plan": list(self.plan),
            "started_at": self.started_at,
            "ends_at": self.ends_at,
            "paused_left": self.paused_left,
            "play_elapsed": self.play_elapsed,
            "resumed_at": self.resumed_at,
            "hint_given": self.hint_given,
            "hints_shown": list(self.hints_shown),
            "winner": self.winner,
            "how_ended": self.how_ended,
            "reveals": [dict(r) for r in self.reveals],
            "teams": {t: asdict(s) for t, s in self.teams.items()},
        }

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
        for key in ("session", "phase", "base_minutes", "round_no", "plan", "started_at", "ends_at",
                    "paused_left", "play_elapsed", "resumed_at", "hint_given", "hints_shown",
                    "winner", "how_ended", "reveals"):
            setattr(game, key, data[key])
        game.teams = {t: TeamState(**data["teams"][t]) for t in TEAMS}
        for t in game.teams.values():
            t.points += [0] * (len(t.crack_times) - len(t.points))
        return game

    # Internals

    def _round_name(self) -> str:
        if self.phase in ("tiebreaker", "tiebreak_over"):
            return f"Tiebreaker: {self.cfg.tiebreaker.title}"
        return f"Round {max(1, self.round_no + 1)}: {self.current_round().title}"

    def _round_points(self) -> dict | None:
        if self.phase != "round":
            return None
        slot = self.cfg.rounds[self.round_no]
        return {"first": slot.points_first, "second": slot.points_second}

    def _points_for_crack(self, team: str) -> int:
        # Scored by round position, so a Round 3 played on the Medium guard is still double.
        slot = self.cfg.rounds[self.round_no]
        other = self.teams["b" if team == "a" else "a"]
        return slot.points_second if other.crack_times[self.round_no] is not None else slot.points_first

    def _next_options(self) -> list[int]:
        k = self.round_no + 1
        options = [k + 1]
        easier = self.cfg.rounds[k].easier_option
        if easier:
            options.append(easier)
        return options

    def _next_round_info(self) -> dict | None:
        if self.phase not in ("lobby", "intermission"):
            return None
        k = self.round_no + 1
        return {
            "number": k + 1,
            "minutes": self.base_minutes[k],
            "options": [
                {"variant": v, "difficulty": self.cfg.rounds[v - 1].difficulty, "title": self.cfg.rounds[v - 1].title}
                for v in self._next_options()
            ],
        }

    def _cracked_now(self, team: str) -> bool:
        t = self.teams[team]
        return self.phase == "round" and 0 <= self.round_no < len(t.crack_times) and t.crack_times[self.round_no] is not None

    def _require_playing(self, team: str) -> None:
        if self.phase not in PLAY_PHASES:
            raise GameRuleError("The vault is closed right now. Wait for the host.")
        if self.paused:
            raise GameRuleError("The host paused the game. Wait a moment.")
        if self._cracked_now(team):
            raise GameRuleError("You cracked this vault. Wait for the next round.")

    def _require_clock(self) -> None:
        if self.phase not in PLAY_PHASES:
            raise GameRuleError("No clock is running right now.")

    def _round_key(self) -> tuple:
        return (self.session, self.phase, self.round_no)

    def _start_clock(self, seconds: float) -> None:
        now = self._now()
        self.ends_at = now + seconds
        self.resumed_at = now
        self.paused_left = None
        self.play_elapsed = 0.0
        self.hint_given = False

    def _stop_clock(self) -> None:
        self.ends_at = None
        self.resumed_at = None
        self.paused_left = None
        self.play_elapsed = 0.0

    def _remaining(self) -> float:
        if self.paused_left is not None:
            return self.paused_left
        if self.ends_at is None:
            return 0.0
        return max(0.0, self.ends_at - self._now())

    def _elapsed(self) -> float:
        running = self._now() - self.resumed_at if self.resumed_at is not None else 0.0
        return self.play_elapsed + running

    def _maybe_give_hint(self) -> None:
        if self.phase != "round" or self.hint_given:
            return
        elapsed = self._elapsed()
        if elapsed >= (elapsed + self._remaining()) / 2:
            self._give_hint()

    def _give_hint(self) -> None:
        self.hint_given = True
        hint = self.current_round().hint
        if hint:
            self.hints_shown.append(hint)
        self._changed()

    def _end_round(self) -> None:
        k = self.round_no
        for team, t in self.teams.items():
            if t.crack_times[k] is None:
                self._reveal(team, k + 1, "unsolved")
        self._stop_clock()
        if k + 1 >= len(self.cfg.rounds):
            self._decide_winner()
        else:
            self.phase = "intermission"
            self._changed()

    def _decide_winner(self) -> None:
        a, b = self.teams["a"], self.teams["b"]
        if a.total_points != b.total_points:
            self._finish("a" if a.total_points > b.total_points else "b", "more_points")
        elif a.rounds_cleared != b.rounds_cleared:
            self._finish("a" if a.rounds_cleared > b.rounds_cleared else "b", "more_vaults")
        elif a.rounds_cleared == 0 or abs(a.total_time - b.total_time) <= self.cfg.tie_window_s:
            self.phase = "tie"
            self._changed()
        else:
            self._finish("a" if a.total_time < b.total_time else "b", "faster_total")

    def _reveal(self, team: str, vault: int | None, how: str) -> None:
        if any(r["team"] == team and r["vault"] == vault for r in self.reveals):
            return
        t = self.teams[team]
        code = t.tiebreak_code if vault is None else t.codes[vault - 1]
        self.reveals.append({"team": team, "vault": vault, "code": code, "how": how})

    def _reveal_unsolved(self) -> None:
        for team, t in self.teams.items():
            for i, cracked in enumerate(t.crack_times):
                if cracked is None:
                    self._reveal(team, i + 1, "unsolved")
            if t.tiebreak_code:
                self._reveal(team, None, "unsolved")

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
            "plan": [self.cfg.rounds[i].difficulty for i in self.plan],
            "winner": self.winner,
            "how_ended": self.how_ended,
            "reveals": [dict(r) for r in self.reveals],
            "teams": {
                t: {
                    "name": s.name,
                    "rounds_cleared": s.rounds_cleared,
                    "crack_times": list(s.crack_times),
                    "points": list(s.points),
                    "total_points": s.total_points,
                    "total_time": s.total_time,
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
