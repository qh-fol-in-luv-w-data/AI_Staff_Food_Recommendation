/**
 * Âm thanh:
 *  - Speaker: phát lần lượt các câu TTS server gửi về, đo độ lớn để quả cầu của Mai "nói" theo.
 *  - Mic: thu micro (trình duyệt tự khử vọng/ồn), đổi sang PCM16 16 kHz gửi qua WebSocket, đo độ lớn.
 */

function rms(an: AnalyserNode, buf: Uint8Array<ArrayBuffer>) {
  an.getByteTimeDomainData(buf);
  let s = 0;
  for (let i = 0; i < buf.length; i++) {
    const v = (buf[i] - 128) / 128;
    s += v * v;
  }
  return Math.min(1, Math.sqrt(s / buf.length) * 3.2);
}

export interface ClipMeta {
  turn?: number;
  seq?: number;
}

export class Speaker {
  private el = new Audio();
  private queue: { url: string; meta: ClipMeta }[] = [];
  private replyId = "";
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private buf = new Uint8Array(new ArrayBuffer(512));
  playing = false;
  onChange: (playing: boolean) => void = () => {};
  onClip: (meta: ClipMeta) => void = () => {};

  constructor() {
    this.el.preload = "auto";
    this.el.onended = () => this.next();
    this.el.onerror = () => this.next();
  }

  /** Gọi trong sự kiện chạm đầu tiên để trình duyệt cho phép phát âm thanh. */
  unlock() {
    if (this.ctx) {
      void this.ctx.resume();
      return;
    }
    try {
      this.ctx = new AudioContext();
      const src = this.ctx.createMediaElementSource(this.el);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 512;
      src.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);
    } catch {
      this.ctx = null; // vẫn phát được qua thẻ audio, chỉ mất hiệu ứng theo âm lượng
    }
  }

  enqueue(url: string, replyId: string, meta: ClipMeta = {}) {
    if (replyId !== this.replyId) {
      // câu trả lời mới -> bỏ phần còn lại của câu cũ
      this.replyId = replyId;
      this.queue = [];
      if (this.playing) this.el.pause();
      this.playing = false;
    }
    this.queue.push({ url, meta });
    if (!this.playing) this.next();
  }

  stop() {
    this.queue = [];
    this.el.pause();
    this.set(false);
  }

  private next() {
    const clip = this.queue.shift();
    if (!clip) {
      this.set(false);
      return;
    }
    this.set(true);
    this.el.src = clip.url;
    this.el
      .play()
      .then(() => this.onClip(clip.meta))
      .catch(() => this.next());
  }

  private set(p: boolean) {
    if (this.playing !== p) {
      this.playing = p;
      this.onChange(p);
    }
  }

  level() {
    return this.analyser && this.playing ? rms(this.analyser, this.buf) : 0;
  }
}

const WORKLET = `class P extends AudioWorkletProcessor{constructor(){super();this.b=[];this.r=sampleRate/16000;this.p=0}
process(i){const c=i[0]&&i[0][0];if(!c)return true;
for(;this.p<c.length;this.p+=this.r)this.b.push(c[Math.floor(this.p)]);this.p-=c.length;
if(this.b.length>=1600){const o=new Int16Array(this.b.length);for(let k=0;k<this.b.length;k++){const s=Math.max(-1,Math.min(1,this.b[k]));o[k]=s<0?s*32768:s*32767}
this.port.postMessage(o.buffer,[o.buffer]);this.b=[]}return true}}registerProcessor('pcm16',P)`;

export class Mic {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private analyser: AnalyserNode | null = null;
  private buf = new Uint8Array(new ArrayBuffer(512));
  on = false;
  paused = false;

  constructor(private send: (pcm: ArrayBuffer) => void) {}

  async start(): Promise<string | null> {
    if (this.on) return null;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (e) {
      return e instanceof Error ? e.message : "không mở được micro";
    }
    this.ctx = new AudioContext({ sampleRate: 16000 });
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await this.ctx.audioWorklet.addModule(url);
    const src = this.ctx.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(this.ctx, "pcm16");
    node.port.onmessage = (e) => {
      if (this.on && !this.paused) this.send(e.data as ArrayBuffer);
    };
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;
    src.connect(node);
    src.connect(this.analyser);
    this.on = true;
    return null;
  }

  stop() {
    this.on = false;
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.ctx = null;
    this.analyser = null;
  }

  level() {
    return this.analyser && this.on && !this.paused ? rms(this.analyser, this.buf) : 0;
  }
}
