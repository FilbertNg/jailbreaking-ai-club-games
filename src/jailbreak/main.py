from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jailbreak.config import ROOT, ConfigError, GameConfig, load_config, load_settings
from jailbreak.game import TEAMS, Game, GameRuleError
from jailbreak.guard import GuardBusy, GuardError, build_guard

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("jailbreak")


class ChatIn(BaseModel):
    team: str
    message: str = Field(min_length=1, max_length=500)


class GuessIn(BaseModel):
    team: str
    code: str = Field(max_length=10)


class HostIn(BaseModel):
    team: str | None = None
    a: str | None = None
    b: str | None = None
    minutes: float | None = None
    variant: int | None = None
    seconds: float | None = None
    round_minutes: list[float] | None = None


def _save_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def _append_line(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read_results(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("Skipping a broken line in %s", path.name)
    return list(reversed(records))


def _load_game(cfg: GameConfig, state_path: Path, results_path: Path, now: Callable[[], float]) -> Game:
    def on_change(data: dict) -> None:
        _save_json(state_path, data)

    def on_result(record: dict) -> None:
        _append_line(results_path, record)

    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return Game.from_dict(cfg, data, now=now, on_change=on_change, on_result=on_result)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning("Could not load %s (%s). Starting a fresh game.", state_path.name, exc)
    return Game(cfg, now=now, on_change=on_change, on_result=on_result)


def create_app(
    cfg: GameConfig,
    guard,
    host_pin: str | None,
    state_path: Path,
    results_path: Path,
    now: Callable[[], float] = time.time,
) -> FastAPI:
    app = FastAPI(title="Break the AI")
    game = _load_game(cfg, state_path, results_path, now)
    locks = {t: asyncio.Lock() for t in TEAMS}
    app.state.game = game
    app.state.guard = guard
    app.state.locks = locks

    @app.exception_handler(GameRuleError)
    async def rule_error(request: Request, exc: GameRuleError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    def check_team(team: str | None) -> str:
        if team not in TEAMS:
            raise HTTPException(404, "Unknown team. Use a or b.")
        return team

    def check_pin(pin: str | None) -> None:
        if not host_pin:
            raise HTTPException(403, "Host controls are off. Set HOST_PIN in .env and restart the server.")
        if not pin or not secrets.compare_digest(pin, host_pin):
            raise HTTPException(401, "Wrong host PIN.")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/team/{team}")
    async def team_page(team: str) -> FileResponse:
        check_team(team)
        return FileResponse(STATIC / "team.html")

    @app.get("/results")
    async def results_page() -> FileResponse:
        return FileResponse(STATIC / "results.html")

    @app.get("/api/state")
    async def state(team: str) -> dict:
        check_team(team)
        data = game.public_state(team)
        data["busy"] = locks[team].locked()
        return data

    @app.post("/api/chat")
    async def chat(body: ChatIn) -> dict:
        team = check_team(body.team)
        message = body.message.strip()
        if not message:
            raise HTTPException(422, "Write a message first.")
        if locks[team].locked():
            raise HTTPException(409, "VaultBot is still answering your last message.")
        async with locks[team]:
            ctx = game.chat_context(team)
            try:
                reply = await guard.reply(
                    round_cfg=ctx.round,
                    code=ctx.code,
                    history=ctx.history,
                    message=message,
                    tags=[f"session-{game.session}", f"team-{team}", ctx.tag],
                    metadata={
                        "session": game.session,
                        "team": team,
                        "team_name": game.teams[team].name,
                        "round": ctx.name,
                        "difficulty": ctx.round.difficulty,
                    },
                )
            except GuardBusy:
                raise HTTPException(503, "The guard is busy. Wait a few seconds and send again.") from None
            except GuardError as exc:
                log.error("Guard error: %s", exc)
                raise HTTPException(503, "The guard did not answer. Try again.") from None
            stored = game.add_exchange(team, ctx.key, message, reply.text, reply.censored)
        return {"reply": reply.text, "censored": reply.censored, "stored": stored}

    @app.post("/api/guess")
    async def guess(body: GuessIn) -> dict:
        return game.guess(check_team(body.team), body.code)

    @app.post("/api/host/{action}")
    async def host(action: str, body: HostIn, x_host_pin: str | None = Header(default=None)) -> dict:
        check_pin(x_host_pin)
        names = {"a": body.a, "b": body.b}

        def need(value, what: str):
            if value is None:
                raise HTTPException(422, f"Send {what}.")
            return value

        if action == "check":
            pass
        elif action == "start-round":
            game.start_round(minutes=body.minutes, variant=body.variant)
        elif action == "end-round":
            game.end_round()
        elif action == "pause":
            game.pause()
        elif action == "resume":
            game.resume()
        elif action == "add-time":
            game.add_time(need(body.seconds, "the seconds to add"))
        elif action == "set-time":
            game.set_time(need(body.seconds, "the seconds left"))
        elif action == "show-hint":
            game.show_hint()
        elif action == "round-minutes":
            game.set_round_minutes(need(body.round_minutes, "a time for each round"))
        elif action == "tiebreaker":
            game.start_tiebreaker(minutes=body.minutes)
        elif action == "award":
            game.award(check_team(body.team))
        elif action == "new-session":
            game.new_session(names)
        elif action == "rename":
            game.rename(names)
        else:
            raise HTTPException(404, "Unknown host action.")
        return {"ok": True, "session": game.session, "phase": game.phase}

    @app.get("/api/results")
    async def results() -> dict:
        return {"sessions": read_results(results_path), "current": game.live_standing()}

    return app


def _lan_addresses() -> list[str]:
    found = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # picks the outgoing interface; no packet is sent
            found.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        found.update(ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127."))
    except OSError:
        pass
    return sorted(found)


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
        cfg = load_config()
    except ConfigError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    app = create_app(cfg, build_guard(cfg), settings.host_pin, ROOT / "state.json", ROOT / "results.jsonl")
    port = int(os.environ.get("PORT", "8000"))
    print("\nBreak the AI is running. Keep this window open.\n")
    print(f"  Laptop A (this one):  http://localhost:{port}/team/a")
    for ip in _lan_addresses():
        print(f"  Laptop B:             http://{ip}:{port}/team/b")
        print(f"  Results page:         http://{ip}:{port}/results")
    if not settings.host_pin:
        print("\n  HOST_PIN is not set in .env, so the Host button will not work.")
    print(flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
