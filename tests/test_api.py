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


def start(client):
    assert client.post("/api/host/start", json={}, headers=PIN).status_code == 200


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
    assert res.json()["phase"] == "running"
    assert res.json()["busy"] is False
    for code in codes(client):
        assert code not in res.text


def test_unknown_team_is_404(client):
    assert client.get("/api/state", params={"team": "z"}).status_code == 404


def test_host_needs_the_right_pin(client):
    assert client.post("/api/host/start", json={}).status_code == 401
    assert client.post("/api/host/start", json={}, headers={"X-Host-Pin": "9"}).status_code == 401
    assert client.post("/api/host/check", json={}, headers=PIN).status_code == 200


def test_host_off_without_pin(tmp_path, cfg, clock):
    client = TestClient(make_app(tmp_path, cfg, clock, pin=None))
    res = client.post("/api/host/start", json={}, headers=PIN)
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
            await client.post("/api/host/start", json={}, headers=PIN)
            first = asyncio.create_task(client.post("/api/chat", json={"team": "a", "message": "hi"}))
            await guard.started.wait()
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


def test_results_list_sessions_without_codes_or_chats(client):
    start(client)
    game = client.app.state.game
    client.post("/api/chat", json={"team": "a", "message": "secret chat"})
    all_codes = codes(client)
    for _ in range(3):
        client.post("/api/guess", json={"team": "a", "code": game.code_for("a")})
    client.post("/api/host/new-session", json={"a": "Kopi", "b": "Teh"}, headers=PIN)
    res = client.get("/api/results")
    data = res.json()
    assert data["sessions"][0]["winner"] == "a"
    assert data["current"]["session"] == 2
    assert data["current"]["teams"]["a"]["name"] == "Kopi"
    assert "secret chat" not in res.text
    for code in all_codes:
        assert code not in res.text


def test_state_survives_restart(tmp_path, cfg, clock):
    first = TestClient(make_app(tmp_path, cfg, clock))
    first.post("/api/host/new-session", json={"a": "Kopi", "b": "Teh"}, headers=PIN)
    start(first)
    second = TestClient(make_app(tmp_path, cfg, clock))
    state = second.get("/api/state", params={"team": "a"}).json()
    assert state["phase"] == "running"
    assert state["team_names"]["a"] == "Kopi"


def test_unknown_host_action_is_404(client):
    assert client.post("/api/host/explode", json={}, headers=PIN).status_code == 404
