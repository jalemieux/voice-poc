// Captures mono float audio at the device rate, resamples to 16 kHz, posts 40 ms Int16 PCM
// chunks, and runs a simple energy VAD whose speech_end message is the fallback "user stopped
// talking" timestamp.
const OUT_RATE = 16000;
const CHUNK = 640;            // samples at 16 kHz = 40 ms
const THRESHOLD = 0.015;      // RMS above this counts as voice
const SILENCE_S = 0.6;        // this much silence after voice ends the utterance

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Int16Array(CHUNK);
    this.n = 0;
    this.speaking = false;
    this.lastVoice = 0;
    this.lastLevel = 0;
    this.step = sampleRate / OUT_RATE; // input samples per output sample
    this.pos = 0;                      // fractional read position into the current input block
    this.prev = 0;                     // last input sample of the previous block, for interpolation
  }

  // Linear-interpolation resampler, carrying the fractional position across blocks.
  resample(ch) {
    const out = [];
    let pos = this.pos;
    while (pos < ch.length) {
      const i = Math.floor(pos);
      const frac = pos - i;
      const a = i < 0 ? this.prev : ch[i];
      const b = i + 1 < ch.length ? ch[i + 1] : ch[ch.length - 1];
      out.push(a + (b - a) * frac);
      pos += this.step;
    }
    this.pos = pos - ch.length;
    this.prev = ch[ch.length - 1];
    return out;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let energy = 0;
    const samples = this.step === 1 ? ch : this.resample(ch);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      energy += s * s;
      this.buf[this.n++] = s < 0 ? s * 32768 : s * 32767;
      if (this.n === CHUNK) {
        this.port.postMessage({ type: "pcm", buf: this.buf.buffer }, [this.buf.buffer]);
        this.buf = new Int16Array(CHUNK);
        this.n = 0;
      }
    }
    const rms = Math.sqrt(energy / Math.max(1, samples.length));
    if (currentTime - this.lastLevel > 0.1) {
      this.lastLevel = currentTime;
      this.port.postMessage({ type: "level", rms, speaking: this.speaking });
    }
    if (rms > THRESHOLD) {
      if (!this.speaking) { this.speaking = true; this.port.postMessage({ type: "speech_start" }); }
      this.lastVoice = currentTime;
    } else if (this.speaking && currentTime - this.lastVoice > SILENCE_S) {
      this.speaking = false;
      this.port.postMessage({ type: "speech_end", silence_ms: SILENCE_S * 1000 });
    }
    return true;
  }
}
registerProcessor("mic", MicProcessor);
