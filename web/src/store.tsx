import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { Mic, Speaker } from "./lib/audio";
import { socket } from "./lib/socket";
import { EMPTY_CART, type Action, type Cart, type Config, type Entry, type QR, type Rec, type Reply } from "./types";

export interface Msg {
  id: string;
  role: "ai" | "user";
  text: string;
  recs?: Rec[];
  options?: Reply["options"];
  intent?: string;
}

export interface Detail {
  id: string;
  source: string; // layoutId nguồn để bát "bay" ra đúng chỗ
}

export interface Flyer {
  key: number;
  entryId: string;
  from: DOMRect;
}

interface State {
  cfg: Config | null;
  connected: boolean;
  server: string;
  started: boolean;
  msgs: Msg[];
  cart: Cart;
  recs: Rec[];
  options: Reply["options"];
  suggestions: string[];
  qr: QR | null;
  order: Reply["order"];
  thinking: boolean;
  intent: string;
  detail: Detail | null;
}

type Ev =
  | { t: "cfg"; cfg: Config }
  | { t: "conn"; ok: boolean }
  | { t: "session"; state: string }
  | { t: "reply"; r: Reply }
  | { t: "user"; text: string }
  | { t: "thinking"; on: boolean }
  | { t: "start" }
  | { t: "reset" }
  | { t: "detail"; d: Detail | null };

const init: State = {
  cfg: null,
  connected: false,
  server: "idle",
  started: false,
  msgs: [],
  cart: EMPTY_CART,
  recs: [],
  options: [],
  suggestions: [],
  qr: null,
  order: null,
  thinking: false,
  intent: "",
  detail: null,
};

let seq = 0;
const nid = () => `m${++seq}`;

function reducer(s: State, e: Ev): State {
  switch (e.t) {
    case "cfg":
      return { ...s, cfg: e.cfg };
    case "conn":
      return { ...s, connected: e.ok };
    case "session":
      return { ...s, server: e.state, started: s.started || (e.state !== "idle" && e.state !== "done") };
    case "user":
      return { ...s, msgs: [...s.msgs, { id: nid(), role: "user" as const, text: e.text }].slice(-30), thinking: true };
    case "thinking":
      return { ...s, thinking: e.on };
    case "start":
      return { ...init, cfg: s.cfg, connected: s.connected, started: true, thinking: true };
    case "reset":
      return { ...init, cfg: s.cfg, connected: s.connected };
    case "detail":
      return { ...s, detail: e.d };
    case "reply": {
      const r = e.r;
      if (r.intent === "reset") return { ...init, cfg: s.cfg, connected: s.connected };
      const msgs = r.text
        ? [...s.msgs, { id: nid(), role: "ai" as const, text: r.text, recs: r.recommendations, options: r.options, intent: r.intent }].slice(-30)
        : s.msgs;
      return {
        ...s,
        msgs,
        server: r.state,
        started: r.intent === "timeout" ? false : true,
        cart: r.cart ?? s.cart,
        recs: r.recommendations?.length ? r.recommendations : s.recs,
        options: r.options ?? [],
        suggestions: r.suggestions ?? [],
        qr: r.qr ?? (r.state === "awaiting_payment" ? s.qr : null),
        order: r.order ?? (r.state === "ordering" ? null : s.order),
        thinking: false,
        intent: r.intent,
      };
    }
  }
}

interface Ctx extends State {
  entry: (id: string) => Entry | undefined;
  say: (text: string) => void;
  act: (a: Action, fromEl?: Element | null) => void;
  start: () => void;
  reset: () => void;
  openDetail: (d: Detail | null) => void;
  speaking: boolean;
  listening: boolean;
  micError: string | null;
  toggleMic: () => void;
  level: () => number;
  flyers: Flyer[];
  dropFlyer: (key: number) => void;
  trayBump: number;
  orbRef: React.RefObject<HTMLDivElement | null>;
  trayRef: React.RefObject<HTMLDivElement | null>;
}

const KioskCtx = createContext<Ctx | null>(null);

export const speaker = new Speaker();
const mic = new Mic((pcm) => socket.audio(pcm));

export function KioskProvider({ children }: { children: ReactNode }) {
  const [s, dispatch] = useReducer(reducer, init);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);
  const [flyers, setFlyers] = useState<Flyer[]>([]);
  const [trayBump, setTrayBump] = useState(0);
  const orbRef = useRef<HTMLDivElement | null>(null);
  const trayRef = useRef<HTMLDivElement | null>(null);
  const localAdd = useRef(0);
  const prevQty = useRef<Record<string, number>>({});
  const flyKey = useRef(0);

  const entries = useMemo(() => new Map((s.cfg?.entries ?? []).map((e) => [e.id, e])), [s.cfg]);
  const entry = useCallback((id: string) => entries.get(id), [entries]);

  const fly = useCallback((entryId: string, from: DOMRect) => {
    setFlyers((f) => [...f, { key: ++flyKey.current, entryId, from }]);
  }, []);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg: Config) => dispatch({ t: "cfg", cfg }))
      .catch(() => undefined);
    speaker.onChange = (p) => {
      setSpeaking(p);
      mic.paused = p; // bán song công: không thu khi Mai đang nói
    };
    const offS = socket.onStatus((ok) => dispatch({ t: "conn", ok }));
    const off = socket.on((m) => {
      if (m.type === "session") dispatch({ t: "session", state: m.state });
      else if (m.type === "reply") {
        // món mới vào mâm do giọng nói -> bay từ quả cầu của Mai sang mâm
        const now: Record<string, number> = {};
        (m.cart?.lines ?? []).forEach((l) => (now[l.entry_id] = (now[l.entry_id] ?? 0) + l.qty));
        const grew = Object.keys(now).filter((k) => now[k] > (prevQty.current[k] ?? 0));
        if (grew.length && Date.now() - localAdd.current > 1500 && orbRef.current) {
          const rect = orbRef.current.getBoundingClientRect();
          grew.slice(0, 3).forEach((id, i) => setTimeout(() => fly(id, rect), i * 160));
        }
        if (grew.length) setTimeout(() => setTrayBump((b) => b + 1), 700);
        prevQty.current = now;
        dispatch({ t: "reply", r: m });
      } else if (m.type === "tts") speaker.enqueue(m.url, m.reply_id);
      else if (m.type === "asr") {
        if (m.text) dispatch({ t: "user", text: m.text });
      } else if (m.type === "listening") setListening(m.on);
    });
    socket.connect();
    return () => {
      off();
      offS();
    };
  }, [fly]);

  const say = useCallback((text: string) => {
    dispatch({ t: "user", text });
    socket.text(text);
  }, []);

  const act = useCallback(
    (a: Action, fromEl?: Element | null) => {
      if (a.type === "add") {
        localAdd.current = Date.now();
        if (fromEl) fly(a.entry_id, fromEl.getBoundingClientRect());
      }
      socket.action(a);
    },
    [fly],
  );

  const startMic = useCallback(async () => {
    const err = await mic.start();
    setMicError(err);
    if (!err) socket.listen(true);
  }, []);

  const start = useCallback(() => {
    speaker.unlock();
    dispatch({ t: "start" });
    socket.start();
    if (s.cfg?.speech) void startMic();
  }, [s.cfg, startMic]);

  const reset = useCallback(() => {
    speaker.stop();
    mic.stop();
    socket.listen(false);
    setListening(false);
    prevQty.current = {};
    socket.action({ type: "reset" });
    dispatch({ t: "reset" });
  }, []);

  const toggleMic = useCallback(() => {
    speaker.unlock();
    if (mic.on) {
      mic.stop();
      socket.listen(false);
    } else void startMic();
  }, [startMic]);

  const level = useCallback(() => Math.max(speaker.level(), mic.level()), []);

  const value: Ctx = {
    ...s,
    entry,
    say,
    act,
    start,
    reset,
    openDetail: (d) => dispatch({ t: "detail", d }),
    speaking,
    listening,
    micError,
    toggleMic,
    level,
    flyers,
    dropFlyer: (key) => setFlyers((f) => f.filter((x) => x.key !== key)),
    trayBump,
    orbRef,
    trayRef,
  };
  return <KioskCtx.Provider value={value}>{children}</KioskCtx.Provider>;
}

export function useKiosk() {
  const c = useContext(KioskCtx);
  if (!c) throw new Error("KioskProvider missing");
  return c;
}
