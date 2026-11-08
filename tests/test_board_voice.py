import asyncio
import json

import httpx

from board_voice import BoardBrain, BoardError


class FakeBoard:
    """A board with one conversation. `replies` maps a posted text to the messages the bot answers with."""
    def __init__(self, replies, bot="voice"):
        self.replies, self.bot, self.msgs, self.posted, self.next_id = replies, bot, [], [], 100

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        assert request.headers["authorization"] == "Bearer tok"
        if path == "/api/conversations":
            return httpx.Response(200, json={"conversation": {"slug": "dm-jac-voice"}, "created": True})
        if path == "/api/messages" and request.method == "POST":
            body = json.loads(request.content)
            self.posted.append(body)
            self.next_id += 1
            mid, thread = self.next_id, body.get("reply_to") or self.next_id
            assert body["body"].startswith("@voice "), "the bot is mentioned, or nobody wakes"
            for text in self.replies.get(body["body"].removeprefix("@voice "), []):
                self.next_id += 1
                self.msgs.append({"id": self.next_id, "author": self.bot, "thread_id": thread, "body": text})
            return httpx.Response(201, json={"message": {"id": mid, "thread_id": thread}})
        if path == "/api/messages":
            since = int(request.url.params["since"])
            return httpx.Response(200, json={"messages": [m for m in self.msgs if m["id"] > since]})
        return httpx.Response(404)


def run(board, texts, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(board.handler)) as http:
            brain = BoardBrain(http, "http://board.test", "tok", "voice", quiet_s=1, timeout_s=2, **kw)
            return [[s async for s in brain.ask(t)] for t in texts], brain
    return asyncio.run(go())


def test_the_bots_messages_are_spoken_in_order_and_the_thread_is_reused():
    board = FakeBoard({"what is waiting": ["Checking.", "Two things wait on you."], "and then": ["Nothing else."]})
    out, brain = run(board, ["what is waiting", "and then"])
    assert out == [["Checking.", "Two things wait on you."], ["Nothing else."]]
    assert "reply_to" not in board.posted[0] and board.posted[0]["channel"] == "dm-jac-voice"
    assert board.posted[1]["reply_to"] == brain.thread == 101


def test_other_authors_and_other_threads_are_not_spoken():
    board = FakeBoard({"hi": ["Hello."]})
    board.msgs.append({"id": 50, "author": "jac", "thread_id": 101, "body": "me"})
    board.msgs.append({"id": 51, "author": "voice", "thread_id": 7, "body": "elsewhere"})
    board.msgs.append({"id": 52, "author": "seth", "thread_id": 101, "body": "chatter"})
    out, _ = run(board, ["hi"])
    assert out == [["Hello."]]


def test_no_answer_raises():
    board = FakeBoard({})
    try:
        run(board, ["anyone?"])
    except BoardError as e:
        assert "did not answer" in str(e)
    else:
        raise AssertionError("expected BoardError")


def test_a_refusal_is_reported():
    def refuse(request):
        return httpx.Response(403, text="no")
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as http:
            return [s async for s in BoardBrain(http, "http://board.test", "tok", "voice").ask("x")]
    try:
        asyncio.run(go())
    except BoardError as e:
        assert "403" in str(e)
    else:
        raise AssertionError("expected BoardError")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
