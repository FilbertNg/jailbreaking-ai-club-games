import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from jailbreak.guard import GuardBusy, GuardReply
from jailbreak.main import create_app

PIN = {"X-Host-Pin": "1234"}


class EchoGuard:
    def __init__(self):
        self.calls = []

    async def reply(self, **kwargs):
        self.calls.append(kwargs)
        return GuardReply(f"echo: {kwargs['message']}", False, "m1")


class BusyGuard:
    async def reply(self, **kwargs):
        raise GuardBusy("busy")


class SlowGuard:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def reply(self, **kwargs):
        self.started.set()
        await self.release.wait()
        return GuardReply("done", False, "m1")


def make_app(tmp_path, cfg, clock, guard=None, pin="1234"):
    return create_app(cfg, guard or EchoGuard(), pin, tmp_path / "state.json",
                      tmp_path / "results.jsonl", now=clock)


@pytest.fixture
def client(tmp_path, cfg, clock):
    return TestClient(make_app(tmp_path, cfg, clock))


def start(client, **body):
    res = client.post("/api/host/start-round", json=body, headers=PIN)
    assert res.status_code == 200, res.text


def codes(client):
    game = client.app.state.game
    return [c for t in game.teams.values() for c in t.codes]


def test_pages_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/team/a").status_code == 200
    assert client.get("/results").status_code == 200
    assert client.get("/team/c").status_code == 404


def test_state_never_contains_codes(client):
    start(client)
    res = client.get("/api/state", params={"team": "a"})
    assert res.status_code == 200
    assert res.json()["phase"] == "round"
    assert res.json()["busy"] is False
    for code in codes(client):
        assert code not in res.text


def test_unknown_team_is_404(client):
    assert client.get("/api/state", params={"team": "z"}).status_code == 404


def test_host_needs_the_right_pin(client):
    assert client.post("/api/host/start-round", json={}).status_code == 401
    assert client.post("/api/host/start-round", json={}, headers={"X-Host-Pin": "9"}).status_code == 401
    assert client.post("/api/host/check", json={}, headers=PIN).status_code == 200


def test_host_off_without_pin(tmp_path, cfg, clock):
    client = TestClient(make_app(tmp_path, cfg, clock, pin=None))
    res = client.post("/api/host/start-round", json={}, headers=PIN)
    assert res.status_code == 403
    assert "HOST_PIN" in res.json()["detail"]


def test_rule_errors_are_409_with_reason(client):
    res = client.post("/api/chat", json={"team": "a", "message": "hi"})
    assert res.status_code == 409
    assert "closed" in res.json()["detail"]


def test_chat_round_trip(client):
    start(client)
    res = client.post("/api/chat", json={"team": "a", "message": "  hello  "})
    assert res.status_code == 200
    assert res.json() == {"reply": "echo: hello", "censored": False, "stored": True}
    chat = client.get("/api/state", params={"team": "a"}).json()["chat"]
    assert [m["text"] for m in chat] == ["hello", "echo: hello"]
    call = client.app.state.guard.calls[0]
    assert call["code"] == client.app.state.game.code_for("a")
    assert "session-1" in call["tags"] and "team-a" in call["tags"]


def test_blank_message_is_rejected(client):
    start(client)
    assert client.post("/api/chat", json={"team": "a", "message": "   "}).status_code == 422


def test_guard_busy_becomes_503(tmp_path, cfg, clock):
    client = TestClient(make_app(tmp_path, cfg, clock, guard=BusyGuard()))
    start(client)
    res = client.post("/api/chat", json={"team": "a", "message": "hi"})
    assert res.status_code == 503
    assert res.json()["detail"] == "The guard is busy. Wait a few seconds and send again."


def test_second_message_while_waiting_is_409(tmp_path, cfg, clock):
    guard = SlowGuard()
    app = make_app(tmp_path, cfg, clock, guard=guard)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/host/start-round", json={}, headers=PIN)
            first = asyncio.create_task(client.post("/api/chat", json={"team": "a", "message": "hi"}))
            await asyncio.wait_for(guard.started.wait(), 5)
            busy = (await client.get("/api/state", params={"team": "a"})).json()["busy"]
            second = await client.post("/api/chat", json={"team": "a", "message": "again"})
            other_team = asyncio.create_task(client.post("/api/chat", json={"team": "b", "message": "hi"}))
            guard.release.set()
            return busy, (await first).status_code, second.status_code, (await other_team).status_code

    assert asyncio.run(scenario()) == (True, 200, 409, 200)


def test_guess_flow(client):
    start(client)
    game = client.app.state.game
    assert client.post("/api/guess", json={"team": "a", "code": "0000"}).json()["result"] == "wrong"
    res = client.post("/api/guess", json={"team": "b", "code": game.code_for("b")})
    assert res.json()["result"] == "correct"


def test_new_session_needs_both_names(client):
    res = client.post("/api/host/new-session", json={"a": "Kopi"}, headers=PIN)
    assert res.status_code == 409


def test_results_reveal_ended_codes_but_hide_live_ones_and_chats(client):
    start(client)
    game = client.app.state.game
    client.post("/api/chat", json={"team": "a", "message": "secret chat"})
    ended_codes = codes(client)
    client.post("/api/guess", json={"team": "a", "code": game.code_for("a")})
    client.post("/api/host/new-session", json={"a": "Kopi", "b": "Teh"}, headers=PIN)
    start(client)
    live_codes = [c for c in codes(client) if c not in ended_codes]
    res = client.get("/api/results")
    data = res.json()
    assert data["sessions"][0]["how_ended"] == "stopped_early"
    assert data["sessions"][0]["teams"]["a"]["rounds_cleared"] == 1
    assert {r["code"] for r in data["sessions"][0]["reveals"]} == set(ended_codes)
    assert data["current"]["session"] == 2
    assert data["current"]["teams"]["a"]["name"] == "Kopi"
    assert "secret chat" not in res.text
    for code in live_codes:
        assert code not in res.text


def test_state_survives_restart(tmp_path, cfg, clock):
    first = TestClient(make_app(tmp_path, cfg, clock))
    first.post("/api/host/new-session", json={"a": "Kopi", "b": "Teh"}, headers=PIN)
    start(first)
    second = TestClient(make_app(tmp_path, cfg, clock))
    state = second.get("/api/state", params={"team": "a"}).json()
    assert state["phase"] == "round"
    assert state["team_names"]["a"] == "Kopi"


def test_unknown_host_action_is_404(client):
    assert client.post("/api/host/explode", json={}, headers=PIN).status_code == 404


def host(client, action, **body):
    return client.post(f"/api/host/{action}", json=body, headers=PIN)


def seconds_left(client):
    return client.get("/api/state", params={"team": "a"}).json()["seconds_left"]


def test_round_minutes_and_custom_start(client):
    assert host(client, "round-minutes", round_minutes=[2, 3, 4]).status_code == 200
    assert client.get("/api/state", params={"team": "a"}).json()["base_minutes"] == [2, 3, 4]
    start(client, minutes=5)
    assert seconds_left(client) == 300


def test_clock_controls(client, clock):
    start(client)
    assert host(client, "add-time", seconds=60).status_code == 200
    assert seconds_left(client) == 240
    assert host(client, "pause").status_code == 200
    clock.advance(100)
    state = client.get("/api/state", params={"team": "a"}).json()
    assert state["paused"] is True and state["seconds_left"] == 240
    assert client.post("/api/chat", json={"team": "a", "message": "hi"}).status_code == 409
    assert host(client, "set-time", seconds=90).status_code == 200
    assert host(client, "resume").status_code == 200
    assert seconds_left(client) == 90
    assert host(client, "show-hint").status_code == 200
    assert host(client, "end-round").status_code == 200
    assert client.get("/api/state", params={"team": "a"}).json()["phase"] == "intermission"


def test_round_three_variant_via_api(client):
    for _ in range(2):
        start(client)
        host(client, "end-round")
    assert host(client, "start-round", variant=1).status_code == 409
    start(client, variant=2)
    state = client.get("/api/state", params={"team": "a"}).json()
    assert (state["round_number"], state["difficulty"]) == (3, "Medium")


def test_chat_is_tagged_with_round(client):
    start(client)
    client.post("/api/chat", json={"team": "b", "message": "hi"})
    call = client.app.state.guard.calls[0]
    assert "round-1" in call["tags"]
    assert call["metadata"]["round"] == "Round 1: Friendly"
    assert call["metadata"]["difficulty"] == "Easy"
