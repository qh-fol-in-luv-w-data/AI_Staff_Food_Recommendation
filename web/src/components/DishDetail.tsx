import { AnimatePresence, m } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { DishArt } from "../art/DishArt";
import { liteMode, money, noteChips, TASTE_LABEL } from "../lib/format";
import { useKiosk } from "../store";
import { Icon } from "./bits";

const TASTES = ["cay", "ngot", "chua", "dam", "beo"] as const;

/** Chạm vào món -> bát "nhấc" khỏi mâm, phóng to ra giữa, xoay chầm chậm, kèm thông tin + tuỳ chọn. */
export function DishDetail() {
  const { detail, entry, openDetail, act } = useKiosk();
  const e = detail ? entry(detail.id) : undefined;
  const [qty, setQty] = useState(1);
  const [opt, setOpt] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const artRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQty(1);
    setOpt(null);
    setNotes([]);
  }, [detail?.id]);

  useEffect(() => {
    if (!detail) return;
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && openDetail(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [detail, openDetail]);

  const option = e?.options.find((o) => o.id === opt);
  const unit = (e?.price ?? 0) + (option?.price_delta ?? 0);
  const add = () => {
    if (!e) return;
    act({ type: "add", entry_id: e.id, qty, option_id: opt, note: notes.join(", ").toLowerCase() }, artRef.current);
    openDetail(null);
  };

  return (
    <AnimatePresence>
      {e && detail && (
        <m.div className="detail-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => openDetail(null)}>
          <div className="detail" role="dialog" aria-modal="true" aria-label={e.name} onClick={(ev) => ev.stopPropagation()}>
            <m.div layoutId={detail.source} className="detail-art" ref={artRef} transition={{ type: "spring", stiffness: 210, damping: 26 }}>
              <div className={liteMode() ? "" : "slow-spin"}>
                <DishArt entry={e} steam={!liteMode()} lookup={entry} />
              </div>
            </m.div>

            <m.div
              className="detail-body"
              initial={{ opacity: 0, x: 28 }}
              animate={{ opacity: 1, x: 0, transition: { delay: 0.12, duration: 0.35 } }}
              exit={{ opacity: 0, transition: { duration: 0.12 } }}
            >
              <h2 className="detail-name">{e.name}</h2>
              <p className="detail-price gold-text">{money(unit)}</p>
              {e.description && <p className="detail-desc">{e.description}</p>}

              <div className="tile-tags">
                {e.best_seller && <span className="tag">{Icon.star}Món bán chạy</span>}
                {e.vegetarian && <span className="tag veg">{Icon.leaf}Món chay</span>}
                {e.promos.map((p) => (
                  <span key={p} className="tag promo">
                    {Icon.gift}
                    {p}
                  </span>
                ))}
              </div>

              {e.kind === "combo" && e.items ? (
                <div className="combo-parts">
                  <ul>
                    {e.items.map((p) => {
                      const pe = entry(p.id);
                      return (
                        <li key={p.id}>
                          {pe && <DishArt entry={pe} />}
                          <span>
                            {p.qty} × {p.name}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  {e.value && e.value > e.price && (
                    <p className="saving">
                      Gọi lẻ <s>{money(e.value)}</s>, combo tiết kiệm <b>{money(e.value - e.price)}</b>
                    </p>
                  )}
                </div>
              ) : (
                <div className="taste" aria-label="Hương vị">
                  {TASTES.map((t) => (
                    <div key={t} className="taste-row">
                      <span>{TASTE_LABEL[t]}</span>
                      <span className="pips" aria-label={`${e.taste[t]} trên 3`}>
                        {[1, 2, 3].map((i) => (
                          <m.i
                            key={i}
                            className={i <= e.taste[t] ? `on ${t === "cay" ? "hot" : ""}` : ""}
                            initial={{ scaleX: 0 }}
                            animate={{ scaleX: 1, transition: { delay: 0.25 + i * 0.06 } }}
                          />
                        ))}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {e.options.length > 0 && (
                <div className="opts" role="radiogroup" aria-label="Kích cỡ">
                  <button role="radio" aria-checked={opt === null} className={opt === null ? "on" : ""} onClick={() => setOpt(null)}>
                    Tiêu chuẩn
                  </button>
                  {e.options.map((o) => (
                    <button key={o.id} role="radio" aria-checked={opt === o.id} className={opt === o.id ? "on" : ""} onClick={() => setOpt(o.id)}>
                      {o.name[0].toUpperCase() + o.name.slice(1)} <small>+{money(o.price_delta)}</small>
                    </button>
                  ))}
                </div>
              )}

              {e.kind === "item" && (
                <div className="notes" aria-label="Ghi chú cho bếp">
                  {noteChips(e.style).map((n) => {
                    const on = notes.includes(n);
                    return (
                      <button key={n} className={on ? "on" : ""} aria-pressed={on} onClick={() => setNotes((xs) => (on ? xs.filter((x) => x !== n) : [...xs, n]))}>
                        {on && Icon.check}
                        {n}
                      </button>
                    );
                  })}
                </div>
              )}

              <div className="detail-actions">
                <div className="stepper big">
                  <button onClick={() => setQty((q) => Math.max(1, q - 1))} aria-label="Bớt một phần">
                    {Icon.minus}
                  </button>
                  <m.b key={qty} initial={{ y: -10, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
                    {qty}
                  </m.b>
                  <button onClick={() => setQty((q) => Math.min(20, q + 1))} aria-label="Thêm một phần">
                    {Icon.plus}
                  </button>
                </div>
                <button className="cta" onClick={add}>
                  <span>Thêm vào mâm</span>
                  <b>{money(unit * qty)}</b>
                </button>
              </div>
            </m.div>

            <button className="detail-close" onClick={() => openDetail(null)} aria-label="Đóng">
              {Icon.close}
            </button>
          </div>
        </m.div>
      )}
    </AnimatePresence>
  );
}
