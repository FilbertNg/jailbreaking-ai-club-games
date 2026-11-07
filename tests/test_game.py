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
