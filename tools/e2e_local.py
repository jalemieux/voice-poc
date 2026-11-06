"""Drives a running server in mode local over its WebSocket the way a browser would: Kokoro
speaks three utterances into the mic stream (with room noise after each, so Silero sees the
end), the third one as a barge-in. Prints the events and the per-turn latency rows.

    .venv/bin/python tools/e2e_local.py [ws://127.0.0.1:8799/ws?mode=local]
"""
import asyncio
import json
import sys
import time

import numpy as np
import websockets
from kokoro import KPipeline

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8799/ws?mode=local"
pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")


def utterance(text: str) -> bytes:
    audio = np.concatenate([np.asarray(a, dtype=np.float32) for _, _, a in pipe(text, voice="am_adam")])
    idx = np.arange(0, len(audio), 1.5)
    a16 = np.interp(idx, np.arange(len(audio)), audio)
    return (np.clip(a16, -1, 1) * 32767).astype(np.int16).tobytes()


async def main() -> None:
    async with websockets.connect(URL, max_size=None) as ws:
        audio_bytes = 0
        ready = asyncio.Event()

        async def reader():
            nonlocal audio_bytes
            async for m in ws:
                if isinstance(m, bytes):
                    audio_bytes += len(m)
                    continue
                ev = json.loads(m)
                if ev["type"] == "turn":
                    print("TURN", ev["n"], "interrupted" if ev["interrupted"] else "", ev["durations"], flush=True)
                elif ev["type"] == "event":
                    print("  event", ev["name"], {k: v for k, v in ev.items() if k not in ("type", "name", "t", "turn")}, flush=True)
                elif ev["type"] == "status":
                    print("STATUS", ev, flush=True)
                    if ev["state"] == "connected":
                        ready.set()
                elif ev["type"] == "transcript":
                    print("  transcript", ev["who"], ev["text"], flush=True)
                elif ev["type"] == "clear":
                    print("  CLEAR received", flush=True)

        asyncio.create_task(reader())
        await asyncio.wait_for(ready.wait(), 600)
        await ws.send(json.dumps({"type": "clock", "offset_ms": 0, "rtt_ms": 0}))

        async def speak(text: str) -> None:
            pcm = utterance(text)
            for i in range(0, len(pcm), 1280):
                await ws.send(pcm[i:i + 1280])
                await asyncio.sleep(0.04)
            noise = (np.random.randn(640) * 0.02 * 32767).astype(np.int16).tobytes()  # above an energy VAD's threshold
            for _ in range(40):
                await ws.send(noise)
                await asyncio.sleep(0.04)

        await speak("What is the capital of France?")
        await asyncio.sleep(8)
        print(f"-- turn 1 done: {audio_bytes / 48000:.1f}s of reply audio received", flush=True)
        audio_bytes = 0
        await speak("Tell me about the Eiffel Tower.")
        await speak("Stop, never mind.")  # barge-in, mid answer
        await asyncio.sleep(8)
        print(f"-- after barge-in: {audio_bytes / 48000:.1f}s of audio received for turns 2 and 3", flush=True)


asyncio.run(main())
