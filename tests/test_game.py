import pytest

from jailbreak.game import TEAMS, Game, GameRuleError

WRONG = "0000"  # codes are 1000 to 9999, so this is always wrong


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


def test_new_game_waits_in_lobby(game):
    assert game.phase == "lobby"
    assert game.session == 1
    assert game.teams["a"].name == "Team A"


def test_start_sets_codes_and_timer(game, clock):
    game.start()
    assert game.phase == "running"
    assert game.ends_at == clock() + 600
    for team in TEAMS:
        assert len(game.teams[team].codes) == 3
        assert all(len(c) == 4 and c.isdigit() and c[0] != "0" for c in game.teams[team].codes)
    for i in range(3):
        assert game.teams["a"].codes[i] != game.teams["b"].codes[i]


def test_start_twice_is_rejected(game):
    game.start()
    with pytest.raises(GameRuleError):
        game.start()


def test_guess_in_lobby_is_rejected(game):
    with pytest.raises(GameRuleError):
        game.guess("a", "1234")


def test_invalid_guess_does_not_count(game):
    game.start()
    assert game.guess("a", "12a4")["result"] == "invalid"
    assert game.guess("a", "123")["result"] == "invalid"
    assert game.teams["a"].wrong_guesses == 0


def test_wrong_guess_counts_and_starts_cooldown(game, clock):
    game.start()
    assert game.guess("a", WRONG) == {"result": "wrong", "cooldown_s": 10}
    assert game.teams["a"].wrong_guesses == 1
    clock.advance(4)
    blocked = crack(game, "a")
    assert blocked["result"] == "cooldown"
    assert blocked["cooldown_s"] == 6
    clock.advance(6)
    assert crack(game, "a")["result"] == "correct"


def test_cooldown_is_per_team(game):
    game.start()
    game.guess("a", WRONG)
    assert crack(game, "b")["result"] == "correct"


def test_correct_guess_moves_to_next_round(game, clock):
    game.start()
    game.teams["a"].chat.append({"role": "you", "text": "hi", "censored": False})
    first_code = game.code_for("a")
    clock.advance(30)
    assert crack(game, "a")["result"] == "correct"
    team = game.teams["a"]
    assert team.round_index == 1
    assert team.rounds_cleared == 1
    assert team.clear_times == [30.0]
    assert team.chat == []
    assert game.code_for("a") == team.codes[1] != first_code
    assert game.current_round("a").name == "Round 2"


def test_clearing_last_round_wins_at_once(game, results):
    game.start()
    for _ in range(3):
        crack(game, "a")
    assert game.phase == "finished"
    assert game.winner == "a"
    assert game.how_ended == "cracked_all"
    assert len(results) == 1
    assert results[0]["winner"] == "a"
    assert results[0]["teams"]["a"]["rounds_cleared"] == 3
    assert "codes" not in results[0]["teams"]["a"]


def test_time_up_more_rounds_wins(game, clock):
    game.start()
    crack(game, "b")
    clock.advance(600)
    game.tick()
    assert (game.phase, game.winner, game.how_ended) == ("finished", "b", "more_rounds")


def test_time_up_same_rounds_earlier_clear_wins(game, clock):
    game.start()
    clock.advance(30)
    crack(game, "a")
    clock.advance(70)
    crack(game, "b")
    clock.advance(500)
    game.tick()
    assert (game.phase, game.winner, game.how_ended) == ("finished", "a", "faster_clear")


def test_time_up_clears_within_ten_seconds_is_tie(game, clock):
    game.start()
    clock.advance(30)
    crack(game, "a")
    clock.advance(10)
    crack(game, "b")
    clock.advance(560)
    game.tick()
    assert game.phase == "tie"
    assert game.winner is None


def test_time_up_zero_zero_is_tie(game, clock, results):
    game.start()
    clock.advance(600)
    game.tick()
    assert game.phase == "tie"
    assert results == []


def test_every_change_is_saved(game, saved):
    game.start()
    assert saved[-1]["phase"] == "running"
    assert saved[-1]["teams"]["a"]["codes"] == game.teams["a"].codes


def make_tie(game, clock):
    game.start()
    clock.advance(600)
    game.tick()
    assert game.phase == "tie"


def test_tiebreaker_gives_new_codes_and_clock(game, clock):
    make_tie(game, clock)
    game.teams["a"].chat.append({"role": "you", "text": "hi", "censored": False})
    game.start_tiebreaker()
    assert game.phase == "tiebreaker"
    assert game.tiebreak_ends_at == clock() + 180
    assert game.code_for("a") == game.teams["a"].tiebreak_code
    assert game.code_for("a") != game.code_for("b")
    assert game.teams["a"].chat == []
    assert game.current_round("a").name == "Tiebreaker"


def test_tiebreaker_only_after_tie(game):
    game.start()
    with pytest.raises(GameRuleError):
        game.start_tiebreaker()


def test_first_correct_tiebreak_code_wins(game, clock, results):
    make_tie(game, clock)
    game.start_tiebreaker()
    game.guess("a", WRONG)
    assert game.teams["a"].tiebreak_wrong == 1
    assert game.teams["a"].wrong_guesses == 0
    crack(game, "b")
    assert (game.phase, game.winner, game.how_ended) == ("finished", "b", "tiebreaker")
    assert len(results) == 1


def test_tiebreak_timeout_then_award(game, clock, results):
    make_tie(game, clock)
    game.start_tiebreaker()
    clock.advance(180)
    game.tick()
    assert game.phase == "tiebreak_over"
    game.award("a")
    assert (game.phase, game.winner, game.how_ended) == ("finished", "a", "host_award")
    assert results[-1]["how_ended"] == "host_award"


def test_award_straight_from_tie(game, clock):
    make_tie(game, clock)
    game.award("b")
    assert game.winner == "b"


def test_award_not_allowed_while_running(game):
    game.start()
    with pytest.raises(GameRuleError):
        game.award("a")


def test_skip_counts_as_clear(game, clock):
    game.start()
    clock.advance(45)
    game.skip_round("a")
    assert game.teams["a"].rounds_cleared == 1
    assert game.teams["a"].clear_times == [45.0]


def test_skip_only_in_main_game(game, clock):
    make_tie(game, clock)
    game.start_tiebreaker()
    with pytest.raises(GameRuleError):
        game.skip_round("a")


def test_hints_unlock_by_time(game, clock):
    game.start()
    assert game.hints_revealed() == 0
    clock.advance(180)
    assert game.hints_revealed() == 1
    clock.advance(180)
    assert game.hints_revealed() == 2
    clock.advance(120)
    assert game.hints_revealed() == 3


def test_next_hint_adds_one_now(game, clock):
    game.start()
    game.next_hint()
    assert game.hints_revealed() == 1
    clock.advance(180)
    assert game.hints_revealed() == 2


def test_next_hint_stops_at_last(game):
    game.start()
    for _ in range(3):
        game.next_hint()
    with pytest.raises(GameRuleError):
        game.next_hint()


from jailbreak.game import ChatContext  # noqa: E402

NAMES = {"a": "Kopi", "b": "Teh"}


def test_new_session_from_lobby_only_renames(game, results):
    game.new_session(NAMES)
    assert game.session == 1
    assert game.teams["a"].name == "Kopi"
    assert results == []


def test_new_session_after_finish_starts_fresh(game, results):
    game.start()
    for _ in range(3):
        crack(game, "a")
    game.new_session(NAMES)
    assert game.session == 2
    assert game.phase == "lobby"
    assert game.teams["b"].name == "Teh"
    assert game.teams["a"].rounds_cleared == 0
    assert game.teams["a"].codes == []
    assert len(results) == 1


def test_new_session_mid_game_saves_stopped_early(game, results):
    game.start()
    crack(game, "b")
    game.new_session(NAMES)
    assert game.session == 2
    assert len(results) == 1
    assert results[0]["how_ended"] == "stopped_early"
    assert results[0]["winner"] is None
    assert results[0]["teams"]["b"]["rounds_cleared"] == 1


def test_new_session_needs_both_names(game):
    with pytest.raises(GameRuleError):
        game.new_session({"a": "Kopi", "b": "  "})
    with pytest.raises(GameRuleError):
        game.new_session({"a": "x" * 25, "b": "Teh"})


def test_rename_only_in_lobby(game):
    game.rename(NAMES)
    assert game.teams["a"].name == "Kopi"
    game.start()
    with pytest.raises(GameRuleError):
        game.rename({"a": "New", "b": "Names"})


def test_chat_context_and_exchange(game):
    game.start()
    ctx = game.chat_context("a")
    assert isinstance(ctx, ChatContext)
    assert ctx.code == game.code_for("a")
    assert ctx.round.name == "Round 1"
    assert game.add_exchange("a", ctx.key, "hello", "hi there", False) is True
    assert game.teams["a"].chat == [
        {"role": "you", "text": "hello", "censored": False},
        {"role": "guard", "text": "hi there", "censored": False},
    ]


def test_exchange_dropped_when_round_changed(game):
    game.start()
    ctx = game.chat_context("a")
    crack(game, "a")
    assert game.add_exchange("a", ctx.key, "hello", "late reply", False) is False
    assert game.teams["a"].chat == []


def test_chat_context_rejected_outside_play(game):
    with pytest.raises(GameRuleError):
        game.chat_context("a")


def test_save_and_load_round_trip(game, cfg, clock, saved):
    game.start()
    crack(game, "a")
    game.new_session(NAMES)
    game.start()
    loaded = Game.from_dict(cfg, saved[-1], now=clock)
    assert loaded.session == 2
    assert loaded.phase == "running"
    assert loaded.teams["a"].name == "Kopi"
    assert loaded.code_for("a") == game.code_for("a")


def test_public_state_hides_codes(game, clock):
    game.start()
    clock.advance(200)
    state = game.public_state("a")
    text = repr(state)
    for team in TEAMS:
        for code in game.teams[team].codes:
            assert code not in text
    assert state["seconds_left"] == 400
    assert state["round_number"] == 1
    assert state["round_name"] == "Round 1"
    assert state["hints"] == ["hint one"]
    assert state["hints_total"] == 3
    assert state["team_names"] == {"a": "Team A", "b": "Team B"}


def test_public_state_shows_cooldown(game, clock):
    game.start()
    game.guess("a", WRONG)
    clock.advance(2.5)
    assert game.public_state("a")["cooldown_s"] == 8
    assert game.public_state("b")["cooldown_s"] == 0


def test_public_state_in_tiebreaker(game, clock):
    make_tie(game, clock)
    game.start_tiebreaker()
    state = game.public_state("b")
    assert state["round_number"] is None
    assert state["round_name"] == "Tiebreaker"
    assert state["seconds_left"] == 180


def test_live_standing(game):
    game.start()
    crack(game, "b")
    live = game.live_standing()
    assert live["teams"]["b"] == {"name": "Team B", "rounds_cleared": 1}
    assert live["phase"] == "running"
    assert "codes" not in repr(live)
