// Runs the two AudioWorklet processors in node at a 48 kHz device rate (what iPhones use) and
// checks that the mic path yields 16 kHz PCM and the player path plays 24 kHz PCM at device rate.
// node tests/js/worklets.test.mjs
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

function load(file, rate) {
  const registered = {};
  const src = readFileSync(new URL(`../../static/${file}`, import.meta.url), "utf8");
  const fn = new Function("AudioWorkletProcessor", "registerProcessor", "sampleRate", "currentTime", src);
  fn(class { constructor() { this.port = { postMessage: () => {}, onmessage: null }; } },
     (name, cls) => (registered[name] = cls), rate, 0);
  return registered;
}

function sine(hz, rate, n) { return Float32Array.from({ length: n }, (_, i) => 0.5 * Math.sin((2 * Math.PI * hz * i) / rate)); }

// ---- mic: 48 kHz in, 16 kHz Int16 out
{
  const { mic: Mic } = load("mic-worklet.js", 48000);
  const m = new Mic();
  const chunks = [];
  m.port = { postMessage: (msg) => { if (msg.type === "pcm") chunks.push(new Int16Array(msg.buf)); } };
  const input = sine(440, 48000, 48000); // 1 s
  for (let i = 0; i < input.length; i += 128) m.process([[input.subarray(i, i + 128)]]);
  const out = Int16Array.from(chunks.flatMap((c) => Array.from(c)));
  assert.ok(Math.abs(out.length - 16000) <= 640, `expected ~16000 samples, got ${out.length}`);
  const expected = sine(440, 16000, out.length);
  let err = 0;
  for (let i = 0; i < out.length; i++) err += Math.abs(out[i] / 32768 - expected[i]);
  assert.ok(err / out.length < 0.01, `mean resampling error ${err / out.length}`);
}

// ---- player: 24 kHz Int16 in, 48 kHz float out, turn reported once
{
  const { player: Player } = load("player-worklet.js", 48000);
  const p = new Player();
  const reports = [];
  const port = p.port;
  p.port = { postMessage: (m) => reports.push(m), onmessage: port.onmessage };
  const src = sine(440, 24000, 2400); // 100 ms
  const pcm = Int16Array.from(src, (v) => v * 32767);
  p.port.onmessage({ data: { type: "mark", turn: 7 } });
  p.port.onmessage({ data: { type: "audio", pcm: pcm.buffer } });
  const out = [];
  for (let i = 0; i < 60; i++) { const buf = new Float32Array(128); p.process([], [[buf]]); out.push(...buf); }
  const played = out.slice(0, 4800);
  const expected = sine(440, 48000, 4800);
  let err = 0;
  for (let i = 0; i < 4800; i++) err += Math.abs(played[i] - expected[i]);
  assert.ok(err / 4800 < 0.01, `mean playback error ${err / 4800}`);
  assert.ok(out.slice(4800).every((v) => v === 0), "silence after the chunk");
  assert.deepEqual(reports, [{ type: "playback_start", turn: 7 }]);
  p.port.onmessage({ data: { type: "audio", pcm: pcm.buffer.slice(0) } });
  p.port.onmessage({ data: { type: "clear" } });
  const buf = new Float32Array(128); p.process([], [[buf]]);
  assert.ok(buf.every((v) => v === 0), "clear drops queued audio");
}
console.log("worklet tests ok");
