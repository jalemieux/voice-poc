"""Mode E: the brain is a bot on the bot_board message board.

The transcript is posted into a direct conversation between the person and a voice bot
(a bot with the `voice` profile). The bot answers in that thread with short spoken
sentences; every message it posts there is handed back to be spoken. Speech never leaves
this machine except as the transcript, and the board shows the whole exchange.

Env: BOARD_URL, BOARD_TOKEN (the person's token), VOICE_BOT (the bot's handle).
"""
from __future__ import annotations

import os
import time
from typing import AsyncIterator

import httpx

BOARD_URL = os.getenv("BOARD_URL", "").rstrip("/")
BOARD_TOKEN = os.getenv("BOARD_TOKEN", "")
VOICE_BOT = os.getenv("VOICE_BOT", "voice")
# After the bot's last message, how long to wait for another before the turn is over.
VOICE_QUIET_S = int(os.getenv("VOICE_QUIET_S", "4"))
# How long to wait for the bot's first message before giving up.
VOICE_TIMEOUT_S = int(os.getenv("VOICE_TIMEOUT_S", "90"))
LONG_POLL_S = 25


class BoardError(Exception):
    pass


class BoardBrain:
    def __init__(self, http: httpx.AsyncClient, base: str = "", token: str = "", bot: str = "",
                 quiet_s: int = VOICE_QUIET_S, timeout_s: int = VOICE_TIMEOUT_S):
        self.http = http
        self.base = (base or BOARD_URL).rstrip("/")
        self.headers = {"Authorization": f"Bearer {token or BOARD_TOKEN}"}
        self.bot = bot or VOICE_BOT
        self.quiet_s, self.timeout_s = quiet_s, timeout_s
        self.channel: str | None = None
        self.thread: int | None = None      # the first utterance opens it; later ones reply in it
        self.cursor = 0

    def configured(self) -> bool:
        return bool(self.base and self.headers["Authorization"] != "Bearer ")

    async def _call(self, method: str, path: str, **kw) -> dict:
        try:
            r = await self.http.request(method, self.base + path, headers=self.headers, timeout=LONG_POLL_S + 10, **kw)
        except httpx.HTTPError as e:
            raise BoardError(f"board unreachable: {e}") from e
        if r.status_code >= 400:
            raise BoardError(f"board refused {method} {path}: {r.status_code} {r.text[:120]}")
        return r.json()

    async def _conversation(self) -> str:
        if not self.channel:
            d = await self._call("POST", "/api/conversations", json={"participants": [self.bot], "topic": "voice"})
            conv = d.get("conversation") or {}
            self.channel = conv.get("slug") or conv.get("channel") or d.get("channel")
            if not self.channel:
                raise BoardError("the board returned no conversation slug")
        return self.channel

    async def ask(self, text: str) -> AsyncIterator[str]:
        """Post `text`; yield each message the bot posts in the thread, as it arrives."""
        channel = await self._conversation()
        # a mention is what wakes the bot: a bare message in a direct conversation is claimed by nobody
        body = {"channel": channel, "body": f"@{self.bot} {text}"}
        if self.thread:
            body["reply_to"] = self.thread
        msg = (await self._call("POST", "/api/messages", json=body))["message"]
        self.thread = self.thread or msg["id"]
        self.cursor = max(self.cursor, msg["id"])
        start = last = time.monotonic()
        got = False
        while True:
            now = time.monotonic()
            if got and now - last >= self.quiet_s:
                return
            if not got and now - start >= self.timeout_s:
                raise BoardError(f"{self.bot} did not answer in {self.timeout_s} seconds")
            wait = max(1, min(LONG_POLL_S, self.quiet_s if got else self.timeout_s - int(now - start)))
            d = await self._call("GET", f"/api/messages?channel={channel}&since={self.cursor}&wait={wait}&hide_events=true")
            for m in d.get("messages", []):
                self.cursor = max(self.cursor, m["id"])
                if m.get("author") == self.bot and m.get("thread_id") == self.thread and (m.get("body") or "").strip():
                    got, last = True, time.monotonic()
                    yield m["body"].strip()
