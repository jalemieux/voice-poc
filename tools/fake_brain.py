"""A stand-in for OpenRouter: streams a fixed answer over SSE with a fixed think time.
Point the POC at it with AGENT_BASE_URL=http://127.0.0.1:8798/v1 to measure everything but the brain.

    .venv/bin/python -m uvicorn --app-dir tools fake_brain:app --port 8798
"""
import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()
ANSWER = ("Paris is the capital of France. It sits on the river Seine and has about two million people. "
          "Its best known landmark is the Eiffel Tower.")
THINK_S = 0.4


@app.post("/v1/chat/completions")
async def chat(body: dict):
    async def gen():
        await asyncio.sleep(THINK_S)
        for word in ANSWER.split(" "):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": word + " "}}]}) + "\n\n"
            await asyncio.sleep(0.03)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
