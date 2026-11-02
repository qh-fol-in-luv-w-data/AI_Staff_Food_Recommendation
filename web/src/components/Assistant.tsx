import { AnimatePresence, m } from "motion/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { DishArt } from "../art/DishArt";
import { liteMode, money, reduceMotion } from "../lib/format";
import { useKiosk, type Msg } from "../store";
import { Icon, useLevelVar } from "./bits";
import { Orb, useOrbState } from "./Orb";

const STATUS: Record<string, string> = {
  idle: "Sẵn sàng giúp quý khách",
  listening: "Đang lắng nghe…",
  thinking: "Đang suy nghĩ…",
  speaking: "Đang trả lời",
};

/** Chữ hiện dần như đang nói (tắt khi người dùng bật giảm chuyển động). */
function useTypewriter(text: string, enabled: boolean) {
  const [n, setN] = useState(enabled ? 0 : text.length);
  useEffect(() => {
    if (!enabled || reduceMotion()) {
      setN(text.length);
      return;
    }
    setN(0);
    let i = 0;
    const id = setInterval(() => {
      i += 5;
      setN(i);
      if (i >= text.length) clearInterval(id);
    }, 40);
    return () => clearInterval(id);
  }, [text, enabled]);
  return text.slice(0, n);
}

function RecCard({ msgId, id, reasons }: { msgId: string; id: string; reasons: string[] }) {
  const { entry, openDetail, detail, act, cart } = useKiosk();
  const e = entry(id);
  const artRef = useRef<HTMLDivElement>(null);
  if (!e) return null;
  const source = `rec-${msgId}-${id}`;
  const inTray = cart.lines.filter((l) => l.entry_id === id).reduce((a, l) => a + l.qty, 0);
  return (
    <li className="rec">
      <button className="rec-art" onClick={() => openDetail({ id, source })} aria-label={`Xem ${e.name}`}>
        {detail?.source === source ? (
          <div className="art-wrap ghost" />
        ) : (
          <m.div layoutId={source} className="art-wrap" ref={artRef}>
            <DishArt entry={e} lookup={entry} />
          </m.div>
        )}
      </button>
      <div className="rec-text">
        <strong>{e.name}</strong>
        <span className="rec-price">{money(e.price)}</span>
        {reasons.length > 0 && (
          <span className="rec-why">
            {reasons.slice(0, 3).map((r) => (
              <em key={r}>{r}</em>
            ))}
          </span>
        )}
      </div>
      <button className="rec-add" onClick={() => act({ type: "add", entry_id: id, qty: 1 }, artRef.current)}>
        {inTray ? `Thêm nữa (${inTray})` : "Chọn món"}
      </button>
    </li>
  );
}

/** Màn hình đã có thẻ món / phiếu tính tiền -> bỏ phần liệt kê trùng lặp trong lời thoại. */
function displayText(msg: Msg) {
  let lines = msg.text.split("\n");
  if (msg.recs?.length) lines = lines.filter((l) => !/^\d+\.\s/.test(l) && !/Có thể nói/.test(l));
  if (msg.intent === "checkout" || msg.intent === "view_cart")
    lines = lines.filter((l) => !/^(Tạm tính|Ưu đãi|Tặng kèm|VAT|TỔNG CỘNG)/.test(l));
  return lines.join("\n").trim();
}

function AiMessage({ m: msg, live }: { m: Msg; live: boolean }) {
  const full = displayText(msg);
  const text = useTypewriter(full, live);
  const done = text.length >= full.length;
  return (
    <m.div className="msg ai" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <p className={done ? "" : "typing-text"}>{text}</p>
      {msg.recs && msg.recs.length > 0 && (
        <m.ul className="recs" initial="hide" animate="show" variants={{ show: { transition: { staggerChildren: 0.08 } } }}>
          {msg.recs.map((r) => (
            <m.div key={r.entry_id} variants={{ hide: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } }}>
              <RecCard msgId={msg.id} id={r.entry_id} reasons={r.reasons} />
            </m.div>
          ))}
        </m.ul>
      )}
    </m.div>
  );
}

export function Assistant() {
  const k = useKiosk();
  const state = useOrbState();
  const scroller = useRef<HTMLDivElement>(null);
  const micRef = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState("");
  useLevelVar(micRef, k.level, k.listening);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: reduceMotion() ? "auto" : "smooth" });
  }, [k.msgs.length, k.thinking]);
  const lastAi = [...k.msgs].reverse().find((x) => x.role === "ai")?.id;
  const submit = (ev: FormEvent) => {
    ev.preventDefault();
    const t = draft.trim();
    if (!t) return;
    k.say(t);
    setDraft("");
  };
  const name = k.cfg?.store.assistant ?? "Mai";
  return (
    <section className="assistant" aria-label={`Trò chuyện với ${name}`}>
      <header className="mai">
        <div ref={k.orbRef} className="mai-orb">
          <Orb state={state} size={92} />
        </div>
        <div>
          <h2 className="mai-name">{name}</h2>
          <p className="mai-status" aria-live="polite">
            {k.micError ? "Chưa mở được micro, quý khách chạm để chọn món" : STATUS[state]}
          </p>
        </div>
      </header>

      <div className="convo" ref={scroller} role="log" aria-live="polite">
        {k.msgs.map((msg) =>
          msg.role === "ai" ? (
            <AiMessage key={msg.id} m={msg} live={msg.id === lastAi && !liteMode()} />
          ) : (
            <m.div key={msg.id} className="msg me" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }}>
              <p>{msg.text}</p>
            </m.div>
          ),
        )}
        {k.thinking && (
          <div className="msg ai typing" aria-label="Mai đang trả lời">
            <i />
            <i />
            <i />
          </div>
        )}
      </div>

      <AnimatePresence>
        {k.options.length > 0 && (
          <m.div className="choices" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {k.options.map((o) => {
              const e = k.entry(o.entry_id);
              return (
                <button key={o.entry_id} onClick={(ev) => k.act({ type: "add", entry_id: o.entry_id, qty: 1 }, ev.currentTarget.querySelector("svg"))}>
                  {e && <DishArt entry={e} lookup={k.entry} />}
                  <span>{o.name}</span>
                  <b>{money(o.price)}</b>
                </button>
              );
            })}
          </m.div>
        )}
      </AnimatePresence>

      <div className="chips">
        {k.suggestions.map((s) => (
          <button key={s} onClick={() => k.say(s)}>
            {s}
          </button>
        ))}
      </div>

      <form className="composer" onSubmit={submit}>
        {k.cfg?.speech && (
          <button
            type="button"
            ref={micRef}
            className={`mic ${k.listening ? "on" : ""}`}
            onClick={k.toggleMic}
            aria-pressed={k.listening}
            aria-label={k.listening ? "Tắt micro" : "Bật micro để nói"}
          >
            {Icon.mic}
          </button>
        )}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={k.cfg?.speech ? "Nói với Mai, hoặc gõ: cho tôi 2 phở bò tái" : "Gõ: cho tôi 2 phở bò tái, gợi ý món cay…"}
          aria-label="Nhập câu gọi món"
        />
        <button type="submit" className="send" aria-label="Gửi">
          {Icon.send}
        </button>
      </form>
    </section>
  );
}
