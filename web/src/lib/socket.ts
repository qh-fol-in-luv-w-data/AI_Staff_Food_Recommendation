import type { Action, ServerMsg } from "../types";

const KEY = "aistaff.session";

function load(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function save(v: string) {
  try {
    localStorage.setItem(KEY, v);
  } catch {
    /* trình duyệt chặn lưu trữ: vẫn chạy bình thường */
  }
}

/** WebSocket tới kiosk server, tự kết nối lại khi rớt mạng LAN / server khởi động lại. */
export class KioskSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<(m: ServerMsg) => void>();
  private statusListeners = new Set<(ok: boolean) => void>();
  private retry = 0;
  private stopped = false;
  session: string | null = load();

  connect() {
    if (this.stopped) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const q = this.session ? `?session=${encodeURIComponent(this.session)}` : "";
    const ws = new WebSocket(`${proto}://${location.host}/ws${q}`);
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.statusListeners.forEach((f) => f(true));
    };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data as string) as ServerMsg;
      if (m.type === "session") {
        this.session = m.session_id;
        save(m.session_id);
      }
      this.listeners.forEach((f) => f(m));
    };
    ws.onclose = () => {
      this.statusListeners.forEach((f) => f(false));
      const wait = Math.min(8000, 600 * 2 ** this.retry++);
      setTimeout(() => this.connect(), wait);
    };
  }

  on(f: (m: ServerMsg) => void) {
    this.listeners.add(f);
    return () => this.listeners.delete(f);
  }

  onStatus(f: (ok: boolean) => void) {
    this.statusListeners.add(f);
    return () => this.statusListeners.delete(f);
  }

  private raw(obj: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  text(text: string) {
    this.raw({ type: "text", text });
  }

  action(action: Action) {
    this.raw({ type: "action", action });
  }

  start() {
    this.raw({ type: "start" });
  }

  listen(on: boolean) {
    this.raw({ type: "listen", on });
  }

  /** Báo server câu nào đang phát (để biết khách đã nghe tới đâu khi ngắt lời) / đã phát xong. */
  playback(state: "start" | "idle", turn?: number, seq?: number) {
    this.raw({ type: "playback", state, turn, seq });
  }

  audio(buf: ArrayBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(buf);
  }
}

export const socket = new KioskSocket();
