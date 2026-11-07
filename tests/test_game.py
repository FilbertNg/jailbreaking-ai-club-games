import pytest

from jailbreak.game import TEAMS, ChatContext, Game, GameRuleError

WRONG = "0000"  # codes are 1000 to 9999, so this is always wrong
NAMES = {"a": "Kopi", "b": "Teh"}


@pytest.fixture
def results():
    return []


@pytest.fixture
def saved():
    return []


@pytest.fixture
def game(cfg, clock, results, saved):
    return Game(cfg, now=clock, on_change=saved.append, on_result=results.append)


def crack(game, team):
    return game.guess(team, game.code_for(team))


def revealed(game):
    return {(r["team"], r["vault"]): (r["code"], r["how"]) for r in game.reveals}


def play_round(game, clock, a_at=None, b_at=None, **start):
    """Start the next round; crack for each team after the given seconds (None = never)."""
    game.start_round(**start)
    order = sorted([(t, s) for t, s in (("a", a_at), ("b", b_at)) if s is not None], key=lambda x: x[1])
    used = 0
    for team, at in order:
        clock.advance(at - used)
        used = at
        crack(game, team)
    if game.phase == "round":
        clock.advance(game._remaining())
        game.tick()


# Lobby and starting

def test_new_game_waits_in_lobby(game):
    assert game.phase == "lobby"
    assert game.session == 1
    assert game.teams["a"].name == "Team A"
    assert game.base_minutes == [3, 3, 3]


def test_start_round_one(game):
    game.start_round()
    assert game.phase == "round"
    assert game.round_no == 0
    assert game.public_state("a")["seconds_left"] == 180
    a, b = game.code_for("a"), game.code_for("b")
    assert len(a) == 4 and a.isdigit() and a[0] != "0"
    assert a != b


def test_start_round_twice_is_rejected(game):
    game.start_round()
    with pytest.raises(GameRuleError):
        game.start_round()


def test_guess_in_lobby_is_rejected(game):
    with pytest.raises(GameRuleError):
        game.guess("a", "1234")


def test_set_round_minutes_in_lobby(game):
    game.set_round_minutes([2, 3, 5])
    game.start_round()
    assert game.public_state("a")["seconds_left"] == 120
    with pytest.raises(GameRuleError):
        game.set_round_minutes([3, 3, 3])


def test_set_round_minutes_is_validated(game):
    with pytest.raises(GameRuleError):
        game.set_round_minutes([3, 3])
    with pytest.raises(GameRuleError):
        game.set_round_minutes([3, 0, 3])
    with pytest.raises(GameRuleError):
        game.set_round_minutes([3, 3, 61])


def test_start_round_with_custom_minutes(game):
    game.start_round(minutes=4.5)
    assert game.public_state("a")["seconds_left"] == 270


# Guessing inside a round

def test_invalid_guess_does_not_count(game):
    game.start_round()
    assert game.guess("a", "12a4")["result"] == "invalid"
    assert game.guess("a", "123")["result"] == "invalid"
    assert game.teams["a"].wrong_guesses == 0


def test_wrong_guess_counts_and_starts_cooldown(game, clock):
    game.start_round()
    assert game.guess("a", WRONG) == {"result": "wrong", "cooldown_s": 10}
    assert game.teams["a"].wrong_guesses == 1
    clock.advance(4)
    blocked = crack(game, "a")
    assert blocked["result"] == "cooldown"
    assert blocked["cooldown_s"] == 6
    clock.advance(6)
    assert crack(game, "a")["result"] == "correct"


def test_crack_waits_for_other_team(game, clock):
    game.start_round()
    code = game.code_for("a")
    clock.advance(40)
    assert crack(game, "a")["result"] == "correct"
    assert game.phase == "round"
    assert game.teams["a"].crack_times == [40.0]
    assert revealed(game) == {("a", 1): (code, "cracked")}
    with pytest.raises(GameRuleError):
        game.guess("a", WRONG)
    with pytest.raises(GameRuleError):
        game.chat_context("a")
    assert game.public_state("b")["cracked_this_round"] == {"a": True, "b": False}
    game.chat_context("b")


def test_round_ends_when_both_teams_crack(game, clock):
    play_round(game, clock, a_at=20, b_at=50)
    assert game.phase == "intermission"
    assert game.teams["b"].crack_times == [50.0]


def test_time_out_ends_round_and_reveals_uncracked(game, clock):
    game.start_round()
    b_code = game.code_for("b")
    crack(game, "a")
    clock.advance(180)
    game.tick()
    assert game.phase == "intermission"
    assert revealed(game)[("b", 1)] == (b_code, "unsolved")
    assert game.teams["b"].crack_times == [None]


def test_next_round_gets_new_codes_and_fresh_chat(game, clock):
    play_round(game, clock, a_at=10)
    game.teams["a"].chat.append({"role": "you", "text": "old", "censored": False})
    game.start_round()
    assert game.round_no == 1
    assert len(game.teams["a"].codes) == 2
    assert game.code_for("a") == game.teams["a"].codes[1]
    assert game.teams["a"].chat == []
    assert game.current_round("a").title == "Strict"


def test_end_round_now(game):
    game.start_round()
    game.end_round()
    assert game.phase == "intermission"
    assert {how for _, how in revealed(game).values()} == {"unsolved"}
    with pytest.raises(GameRuleError):
        game.end_round()


# Clock controls

def test_pause_freezes_clock_and_blocks_play(game, clock):
    game.start_round()
    clock.advance(30)
    game.pause()
    clock.advance(500)
    game.tick()
    state = game.public_state("a")
    assert state["phase"] == "round"
    assert state["paused"] is True
    assert state["seconds_left"] == 150
    with pytest.raises(GameRuleError):
        crack(game, "a")
    with pytest.raises(GameRuleError):
        game.chat_context("a")
    game.resume()
    clock.advance(10)
    crack(game, "a")
    assert game.teams["a"].crack_times == [40.0]


def test_pause_and_resume_only_when_valid(game):
    with pytest.raises(GameRuleError):
        game.pause()
    game.start_round()
    with pytest.raises(GameRuleError):
        game.resume()
    game.pause()
    with pytest.raises(GameRuleError):
        game.pause()


def test_add_time(game, clock):
    game.start_round()
    clock.advance(100)
    game.add_time(60)
    assert game.public_state("a")["seconds_left"] == 140
    game.pause()
    game.add_time(180)
    assert game.public_state("a")["seconds_left"] == 320


def test_set_time(game, clock):
    game.start_round()
    game.set_time(600)
    assert game.public_state("a")["seconds_left"] == 600
    game.pause()
    game.set_time(30)
    assert game.public_state("a")["seconds_left"] == 30
    with pytest.raises(GameRuleError):
        game.set_time(0)


def test_time_controls_need_a_running_round(game):
    with pytest.raises(GameRuleError):
        game.add_time(60)
    with pytest.raises(GameRuleError):
        game.set_time(60)


# Round 3 difficulty

def test_round_three_offers_hard_or_medium(game, clock):
    play_round(game, clock)
    play_round(game, clock)
    nxt = game.public_state("a")["next_round"]
    assert nxt["number"] == 3
    assert [(o["variant"], o["difficulty"]) for o in nxt["options"]] == [(3, "Hard"), (2, "Medium")]
    game.start_round(variant=2)
    rnd = game.current_round("a")
    assert (rnd.title, rnd.difficulty, rnd.censor) == ("Strict", "Medium", "digits")
    state = game.public_state("a")
    assert state["round_number"] == 3
    assert state["difficulty"] == "Medium"


def test_round_three_defaults_to_hard(game, clock):
    play_round(game, clock)
    play_round(game, clock)
    game.start_round()
    assert game.current_round("a").difficulty == "Hard"


def test_variant_must_be_offered(game, clock):
    with pytest.raises(GameRuleError):
        game.start_round(variant=2)
    play_round(game, clock)
    play_round(game, clock)
    with pytest.raises(GameRuleError):
        game.start_round(variant=1)


# Winner

def test_more_vaults_wins(game, clock, results):
    play_round(game, clock, a_at=30, b_at=20)
    play_round(game, clock, a_at=30)
    play_round(game, clock)
    assert (game.phase, game.winner, game.how_ended) == ("finished", "a", "more_vaults")
    assert len(results) == 1
    assert results[0]["teams"]["a"]["rounds_cleared"] == 2
    assert results[0]["plan"] == ["Easy", "Medium", "Hard"]


def test_same_vaults_lower_total_time_wins(game, clock):
    play_round(game, clock, a_at=30, b_at=100)
    play_round(game, clock, a_at=60, b_at=40)
    play_round(game, clock)
    assert (game.winner, game.how_ended) == ("a", "faster_total")


def test_totals_within_ten_seconds_tie(game, clock, results):
    play_round(game, clock, a_at=30, b_at=35)
    play_round(game, clock, a_at=50, b_at=50)
    play_round(game, clock)
    assert game.phase == "tie"
    assert results == []


def test_zero_zero_is_tie(game, clock):
    for _ in range(3):
        play_round(game, clock)
    assert game.phase == "tie"
    assert len(game.reveals) == 6


def test_medium_plan_is_recorded(game, clock, results):
    play_round(game, clock, a_at=10)
    play_round(game, clock)
    play_round(game, clock, variant=2)
    assert results[0]["plan"] == ["Easy", "Medium", "Medium"]


# Tiebreaker

def make_tie(game, clock):
    for _ in range(3):
        play_round(game, clock)
    assert game.phase == "tie"


def test_tiebreaker_first_correct_wins(game, clock, results):
    make_tie(game, clock)
    game.start_tiebreaker(minutes=2)
    assert game.public_state("a")["seconds_left"] == 120
    assert game.current_round("a").difficulty == "Tiebreaker"
    a_tb, b_tb = game.code_for("a"), game.code_for("b")
    game.guess("a", WRONG)
    assert game.teams["a"].tiebreak_wrong == 1
    crack(game, "b")
    assert (game.phase, game.winner, game.how_ended) == ("finished", "b", "tiebreaker")
    got = revealed(game)
    assert got[("b", None)] == (b_tb, "cracked")
    assert got[("a", None)] == (a_tb, "unsolved")
    assert len(results) == 1


def test_tiebreaker_only_after_tie(game):
    game.start_round()
    with pytest.raises(GameRuleError):
        game.start_tiebreaker()


def test_tiebreak_timeout_then_award(game, clock, results):
    make_tie(game, clock)
    game.start_tiebreaker()
    clock.advance(180)
    game.tick()
    assert game.phase == "tiebreak_over"
    assert revealed(game)[("a", None)][1] == "unsolved"
    game.award("a")
    assert (game.phase, game.winner, game.how_ended) == ("finished", "a", "host_award")
    assert results[-1]["how_ended"] == "host_award"


def test_tiebreaker_clock_can_pause_and_extend(game, clock):
    make_tie(game, clock)
    game.start_tiebreaker()
    game.add_time(60)
    game.pause()
    assert game.public_state("a")["seconds_left"] == 240


def test_award_not_allowed_while_playing(game):
    game.start_round()
    with pytest.raises(GameRuleError):
        game.award("a")


# Hints

def test_hint_shows_at_halfway(game, clock):
    game.start_round()
    assert game.public_state("a")["hints"] == []
    clock.advance(89)
    assert game.public_state("a")["hints"] == []
    clock.advance(1)
    assert game.public_state("a")["hints"] == ["hint one"]


def test_show_hint_now_and_hints_add_up(game, clock):
    game.start_round()
    game.show_hint()
    assert game.public_state("b")["hints"] == ["hint one"]
    with pytest.raises(GameRuleError):
        game.show_hint()
    clock.advance(180)
    game.tick()
    game.start_round()
    game.show_hint()
    assert game.public_state("a")["hints"] == ["hint one", "hint two"]


def test_medium_round_three_uses_round_two_hint(game, clock):
    play_round(game, clock)
    play_round(game, clock)
    game.start_round(variant=2)
    game.show_hint()
    assert game.public_state("a")["hints"][-1] == "hint two"


def test_halfway_follows_extended_time(game, clock):
    game.start_round()
    game.add_time(120)
    clock.advance(100)
    assert game.public_state("a")["hints"] == []
    clock.advance(50)
    assert game.public_state("a")["hints"] == ["hint one"]


# Sessions

def test_new_session_from_lobby_only_renames(game, results):
    game.new_session(NAMES)
    assert game.session == 1
    assert game.teams["a"].name == "Kopi"
    assert results == []


def test_new_session_after_finish_starts_fresh(game, clock, results):
    play_round(game, clock, a_at=5)
    play_round(game, clock)
    play_round(game, clock)
    game.new_session(NAMES)
    assert game.session == 2
    assert game.phase == "lobby"
    assert game.teams["b"].name == "Teh"
    assert game.teams["a"].codes == []
    assert game.reveals == []
    assert len(results) == 1


def test_new_session_mid_round_saves_stopped_early(game, clock, results):
    game.start_round()
    crack(game, "b")
    game.new_session(NAMES)
    assert game.session == 2
    assert results[0]["how_ended"] == "stopped_early"
    assert results[0]["winner"] is None
    assert results[0]["teams"]["b"]["rounds_cleared"] == 1
    assert revealed_from(results[0])[("a", 1)][1] == "unsolved"


def revealed_from(record):
    return {(r["team"], r["vault"]): (r["code"], r["how"]) for r in record["reveals"]}


def test_new_session_needs_both_names(game):
    with pytest.raises(GameRuleError):
        game.new_session({"a": "Kopi", "b": "  "})
    with pytest.raises(GameRuleError):
        game.new_session({"a": "x" * 25, "b": "Teh"})


def test_rename_only_in_lobby(game):
    game.rename(NAMES)
    assert game.teams["a"].name == "Kopi"
    game.start_round()
    with pytest.raises(GameRuleError):
        game.rename({"a": "New", "b": "Names"})


# Chat context

def test_chat_context_and_exchange(game):
    game.start_round()
    ctx = game.chat_context("a")
    assert isinstance(ctx, ChatContext)
    assert ctx.code == game.code_for("a")
    assert ctx.round.title == "Friendly"
    assert ctx.tag == "round-1"
    assert game.add_exchange("a", ctx.key, "hello", "hi there", False) is True
    assert game.teams["a"].chat == [
        {"role": "you", "text": "hello", "censored": False},
        {"role": "guard", "text": "hi there", "censored": False},
    ]


def test_exchange_dropped_when_round_ended(game):
    game.start_round()
    ctx = game.chat_context("a")
    game.end_round()
    assert game.add_exchange("a", ctx.key, "hello", "late reply", False) is False


def test_chat_context_rejected_between_rounds(game, clock):
    play_round(game, clock)
    with pytest.raises(GameRuleError):
        game.chat_context("a")


# Saving and public state

def test_save_and_load_round_trip(game, cfg, clock, saved):
    play_round(game, clock, a_at=10)
    game.start_round(minutes=5)
    clock.advance(20)
    game.pause()
    loaded = Game.from_dict(cfg, saved[-1], now=clock)
    assert loaded.round_no == 1
    assert loaded.public_state("a")["paused"] is True
    assert loaded.public_state("a")["seconds_left"] == 280
    assert loaded.code_for("a") == game.code_for("a")
    assert loaded.reveals == game.reveals


def test_public_state_hides_unrevealed_codes(game, clock):
    game.start_round()
    clock.advance(20)
    crack(game, "a")
    state = game.public_state("b")
    text = repr(state)
    assert game.teams["a"].codes[0] in text
    assert game.teams["b"].codes[0] not in text
    assert state["round_number"] == 1
    assert state["round_name"] == "Round 1: Friendly"
    assert state["difficulty"] == "Easy"
    assert state["team_names"] == {"a": "Team A", "b": "Team B"}
    assert state["rounds_cleared"] == {"a": 1, "b": 0}


def test_public_state_shows_cooldown(game, clock):
    game.start_round()
    game.guess("a", WRONG)
    clock.advance(2.5)
    assert game.public_state("a")["cooldown_s"] == 8
    assert game.public_state("b")["cooldown_s"] == 0


def test_public_state_next_round_in_lobby_and_between_rounds(game, clock):
    nxt = game.public_state("a")["next_round"]
    assert nxt == {"number": 1, "minutes": 3, "options": [{"variant": 1, "difficulty": "Easy", "title": "Friendly"}]}
    play_round(game, clock)
    assert game.public_state("a")["next_round"]["number"] == 2
    game.start_round()
    assert game.public_state("a")["next_round"] is None


def test_live_standing(game, clock):
    game.start_round()
    crack(game, "b")
    live = game.live_standing()
    assert live["teams"]["b"] == {"name": "Team B", "rounds_cleared": 1}
    assert live["phase"] == "round"
    assert live["round_number"] == 1
    assert "codes" not in repr(live)
