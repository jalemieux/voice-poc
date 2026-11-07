import asyncio

import server
from board_voice import BoardError
from server import BoardVoiceSession
from test_local_session import FakeSpeech, FakeWs, events


class FakeBrain:
    def __init__(self, messages=(), delay=0.0, error=None):
        self.messages, self.delay, self.error, self.asked = messages, delay, error, []

    async def ask(self, text):
        self.asked.append(text)
        await asyncio.sleep(self.delay)
        for m in self.messages:
            yield m
        if self.error:
            raise BoardError(self.error)


def make(brain):
    s = BoardVoiceSession(FakeWs(), http=None, speech=FakeSpeech("what is waiting"), brain=brain)
    s.vad = s.speech.turn_detector()
    return s


def test_every_bot_message_is_spoken_in_order():
    brain = FakeBrain(["Two things wait on you. The first is the repo question.", "The second is a review."])
    s = make(brain)
    asyncio.run(s.respond(s.turn, b"\x00" * 32000))
    assert brain.asked == ["what is waiting"]
    assert s.speech.synthesized == ["Two things wait on you.", "The first is the repo question.", "The second is a review."]
    assert events(s) == ["stt_done", "glm_first_token", "first_audio_chunk", "glm_done", "turn_complete"]


def test_a_slow_bot_gets_a_filler_a_fast_one_does_not(monkeypatch):
    monkeypatch.setattr(BoardVoiceSession, "FILLER_AFTER_S", 0.05)
    slow = make(FakeBrain(["Done."], delay=0.2))
    asyncio.run(slow.respond(slow.turn, b"\x00" * 32000))
    assert slow.speech.synthesized == [BoardVoiceSession.FILLER, "Done."]
    fast = make(FakeBrain(["Done."], delay=0.0))
    asyncio.run(fast.respond(fast.turn, b"\x00" * 32000))
    assert fast.speech.synthesized == ["Done."]


def test_a_board_error_is_spoken():
    s = make(FakeBrain(error="voice did not answer in 90 seconds"))
    asyncio.run(s.respond(s.turn, b"\x00" * 32000))
    assert s.speech.synthesized == ["Sorry, the board did not answer."]
    assert "glm_error" in events(s) and events(s)[-1] == "turn_complete"
