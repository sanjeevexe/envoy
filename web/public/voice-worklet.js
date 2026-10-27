// Microphone → 24 kHz 16-bit PCM for Muse Voice Transcribe (Phase 5, push to talk).
// Runs on the audio thread. Each output sample is the mean of the input samples it covers (a box filter, enough to keep
// speech clean when going from 48 or 44.1 kHz down to 24 kHz). Posts 80 ms chunks (1,920 samples), the size Meta's
// sample client uses; on {flush: true} it posts what is left.
class EnvoyPcm extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const target = (options.processorOptions && options.processorOptions.targetRate) || 24000;
    this.ratio = sampleRate / target;
    this.pos = 0;
    this.sum = 0;
    this.count = 0;
    this.buf = new Int16Array(1920);
    this.n = 0;
    this.port.onmessage = (e) => {
      if (e.data && e.data.flush && this.n > 0) {
        const rest = this.buf.slice(0, this.n);
        this.port.postMessage(rest.buffer, [rest.buffer]);
        this.n = 0;
      }
    };
  }

  process(inputs) {
    const x = inputs[0] && inputs[0][0];
    if (!x) return true;
    for (let i = 0; i < x.length; i++) {
      this.sum += x[i];
      this.count += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.sum / this.count));
        this.buf[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        this.sum = 0;
        this.count = 0;
        if (this.n === this.buf.length) {
          this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
          this.buf = new Int16Array(1920);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("envoy-pcm", EnvoyPcm);
