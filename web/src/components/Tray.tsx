import { AnimatePresence, m } from "motion/react";
import { useState } from "react";
import { DishArt } from "../art/DishArt";
import { cap, money } from "../lib/format";
import { useKiosk } from "../store";
import { AnimatedMoney, Icon } from "./bits";

/** Mâm của khách (giỏ hàng). Màn hình dọc / điện thoại: thu gọn thành thanh dưới đáy, chạm để mở. */
export function Tray() {
  const { cart, act, entry, trayBump, trayRef, server } = useKiosk();
  const [open, setOpen] = useState(false);
  const hint = cart.hints.find((h) => h.missing_amount > 0) ?? cart.hints[0];
  const pct = hint && hint.missing_amount > 0 ? Math.min(1, cart.subtotal / (cart.subtotal + hint.missing_amount)) : 0;
  const empty = cart.lines.length === 0;
  const busy = server === "awaiting_payment" || server === "awaiting_cash";
  return (
    <aside className={`tray ${open ? "open" : ""}`} aria-label="Mâm của bạn">
      <header className="tray-head" onClick={() => setOpen((o) => !o)}>
        <h2>Mâm của bạn</h2>
        <m.span
          key={trayBump}
          ref={trayRef}
          className="count-seal"
          initial={{ scale: 1 }}
          animate={{ scale: trayBump ? [1, 1.45, 0.92, 1] : 1, rotate: trayBump ? [0, -8, 4, 0] : 0 }}
          transition={{ duration: 0.55 }}
        >
          {cart.count}
        </m.span>
        <span className="tray-mini-total">{money(cart.total)}</span>
      </header>

      <div className="tray-body">
        {empty ? (
          <div className="tray-empty">
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle cx="60" cy="60" r="52" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 7" />
              <circle cx="60" cy="60" r="38" fill="none" stroke="currentColor" strokeWidth="1" opacity=".5" />
            </svg>
            <p>Mâm còn trống. Chạm vào một món để xem kỹ, hoặc nói với Mai món quý khách thích.</p>
          </div>
        ) : (
          <ul className="lines">
            <AnimatePresence initial={false}>
              {cart.lines.map((l) => {
                const e = entry(l.entry_id);
                return (
                  <m.li
                    key={`${l.entry_id}|${l.option_id}|${l.note}`}
                    layout
                    initial={{ opacity: 0, x: 28 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -28, transition: { duration: 0.2 } }}
                  >
                    <div className="line-art">{e && <DishArt entry={e} lookup={entry} />}</div>
                    <div className="line-text">
                      <strong>{l.name}</strong>
                      {(l.option_name || l.note) && <small>{[l.option_name, l.note].filter(Boolean).join(", ")}</small>}
                      <span className="line-unit">{money(l.unit_price)}</span>
                    </div>
                    <div className="stepper">
                      <button onClick={() => act({ type: "remove", entry_id: l.entry_id, qty: 1 })} aria-label={`Bớt ${l.name}`} disabled={busy}>
                        {Icon.minus}
                      </button>
                      <m.b key={l.qty} initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
                        {l.qty}
                      </m.b>
                      <button onClick={() => act({ type: "add", entry_id: l.entry_id, qty: 1, option_id: l.option_id, note: l.note })} aria-label={`Thêm ${l.name}`} disabled={busy}>
                        {Icon.plus}
                      </button>
                    </div>
                  </m.li>
                );
              })}
              {cart.free_items.map((f) => (
                <m.li key={`gift-${f.entry_id}`} className="gift" layout initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
                  <div className="line-art">{entry(f.entry_id) && <DishArt entry={entry(f.entry_id)!} />}</div>
                  <div className="line-text">
                    <strong>{f.name}</strong>
                    <small>Quà tặng từ ưu đãi</small>
                  </div>
                  <span className="gift-badge">
                    {Icon.gift}×{f.qty}
                  </span>
                </m.li>
              ))}
            </AnimatePresence>
          </ul>
        )}

        {hint && hint.missing_amount > 0 && (
          <div className="meter" role="status">
            <p>{cap(hint.message)}</p>
            <div className="meter-bar">
              <m.i animate={{ width: `${pct * 100}%` }} transition={{ type: "spring", stiffness: 120, damping: 20 }} />
            </div>
          </div>
        )}

        <dl className="sums">
          <div>
            <dt>Tạm tính</dt>
            <dd>
              <AnimatedMoney value={cart.subtotal} />
            </dd>
          </div>
          {cart.applied
            .filter((a) => a.discount > 0)
            .map((a) => (
              <div key={a.id} className="disc">
                <dt>{a.name}</dt>
                <dd>−{money(a.discount)}</dd>
              </div>
            ))}
          {cart.vat > 0 && (
            <div>
              <dt>VAT</dt>
              <dd>{money(cart.vat)}</dd>
            </div>
          )}
          <div className="grand">
            <dt>Tổng cộng</dt>
            <dd>
              <AnimatedMoney value={cart.total} className="gold-text" />
            </dd>
          </div>
        </dl>
      </div>

      <button className="cta" disabled={empty || busy} onClick={() => act({ type: "checkout" })}>
        <span>Thanh toán</span>
        <AnimatedMoney value={cart.total} />
      </button>
    </aside>
  );
}
