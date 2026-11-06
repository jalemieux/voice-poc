// Plays queued 24 kHz Int16 PCM chunks at the device rate (linear resampling). "mark" tags
// following chunks with a turn id so the first sample of each turn can be reported; "clear"
// drops everything queued (interruption).
const IN_RATE = 24000;
class Player extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.cur = null;
    this.pos = 0;                      // fractional read position into cur
    this.step = IN_RATE / sampleRate;  // source samples per output sample
    this.turn = null;
    this.reported = null;
    this.port.onmessage = (e) => {
      const m = e.data;
      if (m.type === "audio") {
        const i16 = new Int16Array(m.pcm);
        const f = new Float32Array(i16.length);
        for (let i = 0; i < i16.length; i++) f[i] = i16[i] / 32768;
        this.queue.push({ f, turn: this.turn });
      } else if (m.type === "mark") {
        this.turn = m.turn;
      } else if (m.type === "clear") {
        this.queue = [];
        this.cur = null;
        this.last = null;
        this.pos = 0;
      }
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    let i = 0;
    while (i < out.length) {
      if (!this.cur) {
        const item = this.queue.shift();
        if (!item) break;
        this.cur = item.f;
        this.pos = Math.max(0, this.pos - (this.last ? this.last.length : 0)); // carry the fraction over
        this.last = null;
        if (item.turn !== null && item.turn !== this.reported) {
          this.reported = item.turn;
          this.port.postMessage({ type: "playback_start", turn: item.turn });
        }
      }
      const src = this.cur;
      while (i < out.length && this.pos < src.length) {
        const k = Math.floor(this.pos);
        const frac = this.pos - k;
        const a = src[k];
        const b = k + 1 < src.length ? src[k + 1] : a;
        out[i++] = a + (b - a) * frac;
        this.pos += this.step;
      }
      if (this.pos >= src.length) { this.last = src; this.cur = null; }
    }
    for (; i < out.length; i++) out[i] = 0;
    return true;
  }
}
registerProcessor("player", Player);
