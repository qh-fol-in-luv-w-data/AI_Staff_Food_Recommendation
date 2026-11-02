import { AnimatePresence, m } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { DishArt } from "../art/DishArt";
import { liteMode, money, orderNumber, reduceMotion } from "../lib/format";
import { useKiosk } from "../store";
import { AnimatedMoney, Icon } from "./bits";

/** Phiếu gọi món giấy vỏ trứng trượt lên khi khách bấm Thanh toán / nói "chốt đơn". */
export function ConfirmSheet() {
  const { server, cart, act, cfg } = useKiosk();
  const open = server === "confirm_order";
  return (
    <AnimatePresence>
      {open && (
        <m.div className="sheet-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <m.section
            className="receipt"
            role="dialog"
            aria-modal="true"
            aria-label="Phiếu gọi món"
            initial={{ y: "100%", rotate: -1.5 }}
            animate={{ y: 0, rotate: 0, transition: { type: "spring", stiffness: 170, damping: 22 } }}
            exit={{ y: "100%", transition: { duration: 0.25 } }}
          >
            <h2>Phiếu gọi món</h2>
            <p className="receipt-store">{cfg?.store.name}</p>
            <ul>
              {cart.lines.map((l) => (
                <li key={`${l.entry_id}|${l.option_id}|${l.note}`}>
                  <span>
                    {l.qty} × {l.name}
                    {(l.option_name || l.note) && <small>{[l.option_name, l.note].filter(Boolean).join(", ")}</small>}
                  </span>
                  <i />
                  <b>{money(l.total)}</b>
                </li>
              ))}
              {cart.free_items.map((f) => (
                <li key={`g${f.entry_id}`} className="gift">
                  <span>
                    {f.qty} × {f.name} <small>quà tặng</small>
                  </span>
                  <i />
                  <b>0đ</b>
                </li>
              ))}
              {cart.applied
                .filter((a) => a.discount > 0)
                .map((a) => (
                  <li key={a.id} className="disc">
                    <span>{a.name}</span>
                    <i />
                    <b>−{money(a.discount)}</b>
                  </li>
                ))}
            </ul>
            <div className="receipt-total">
              <span>Tổng cộng</span>
              <AnimatedMoney value={cart.total} />
            </div>
            <div className="pay-choices">
              <button className="cta" onClick={() => act({ type: "confirm", method: "vietqr" })}>
                {Icon.qr}
                <span>Quét mã QR</span>
              </button>
              {cfg?.store.allow_cash && (
                <button className="cta ghost" onClick={() => act({ type: "confirm", method: "cash" })}>
                  {Icon.cash}
                  <span>Tiền mặt tại quầy</span>
                </button>
              )}
            </div>
            <button className="text-btn" onClick={() => act({ type: "edit" })}>
              Sửa món
            </button>
          </m.section>
        </m.div>
      )}
    </AnimatePresence>
  );
}

function useCountdown(iso: string | null | undefined) {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!iso) return;
    const end = new Date(iso).getTime();
    const tick = () => setLeft(Math.max(0, Math.round((end - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [iso]);
  return left;
}

/** Thẻ thanh toán: mã VietQR trong khung vàng lá, tia quét, đếm ngược. */
export function PaymentSheet() {
  const { server, qr, order, act, cfg, say } = useKiosk();
  const left = useCountdown(qr?.expires_at);
  const total = Math.max(1, (cfg?.store.qr_expire_minutes ?? 10) * 60);
  const isQr = server === "awaiting_payment" && qr;
  const isCash = server === "awaiting_cash";
  return (
    <AnimatePresence>
      {(isQr || isCash) && (
        <m.div className="sheet-backdrop center" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <m.section
            className="paycard"
            role="dialog"
            aria-modal="true"
            aria-label="Thanh toán"
            initial={{ scale: 0.86, opacity: 0, y: 30 }}
            animate={{ scale: 1, opacity: 1, y: 0, transition: { type: "spring", stiffness: 200, damping: 22 } }}
            exit={{ scale: 0.9, opacity: 0 }}
          >
            {isQr && qr ? (
              <>
                <h2>Quét mã để thanh toán</h2>
                <p className="paycard-sub">Mở ứng dụng ngân hàng bất kỳ và quét mã. Số tiền và nội dung đã điền sẵn.</p>
                <div className="qr-frame">
                  <div className="qr-img" dangerouslySetInnerHTML={{ __html: qr.svg }} />
                  {!liteMode() && <div className="qr-beam" aria-hidden="true" />}
                  <span className="corner tl" />
                  <span className="corner tr" />
                  <span className="corner bl" />
                  <span className="corner br" />
                </div>
                <p className="pay-amount gold-text">{money(qr.amount)}</p>
                <dl className="bank">
                  <div>
                    <dt>Ngân hàng</dt>
                    <dd>{qr.bank_name || qr.bank_bin}</dd>
                  </div>
                  <div>
                    <dt>Chủ tài khoản</dt>
                    <dd>{qr.account_name}</dd>
                  </div>
                  <div>
                    <dt>Số tài khoản</dt>
                    <dd>{qr.account_number}</dd>
                  </div>
                  <div>
                    <dt>Nội dung</dt>
                    <dd className="mono">{qr.code}</dd>
                  </div>
                </dl>
                <div className="countdown" aria-label={`Mã còn hiệu lực ${Math.floor(left / 60)} phút ${left % 60} giây`}>
                  <div className="countdown-bar">
                    <i style={{ transform: `scaleX(${left / total})` }} />
                  </div>
                  <span>
                    Mã còn hiệu lực {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
                  </span>
                </div>
                <p className="waiting">
                  <span className="pulse" /> Đang chờ ngân hàng xác nhận
                </p>
                <div className="paycard-actions">
                  {cfg?.store.allow_cash && (
                    <button className="cta ghost" onClick={() => say("trả tiền mặt")}>
                      {Icon.cash}
                      <span>Trả tiền mặt</span>
                    </button>
                  )}
                  <button className="text-btn" onClick={() => act({ type: "cancel" })}>
                    Huỷ đơn
                  </button>
                </div>
              </>
            ) : (
              <>
                <h2>Mời quý khách thanh toán tại quầy</h2>
                <p className="ticket-no">
                  <small>Số thứ tự</small>
                  {orderNumber(order?.code)}
                </p>
                <p className="pay-amount gold-text">{money(order?.total ?? 0)}</p>
                <p className="paycard-sub">Nhân viên sẽ xác nhận khi nhận tiền. Mã đơn {order?.code}.</p>
                <div className="paycard-actions">
                  <button className="text-btn" onClick={() => act({ type: "cancel" })}>
                    Huỷ đơn
                  </button>
                </div>
              </>
            )}
          </m.section>
        </m.div>
      )}
    </AnimatePresence>
  );
}

/** Lá vàng bung ra khi thanh toán xong (canvas nhẹ, tự dừng sau ~3 giây). */
function GoldBurst() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (reduceMotion() || liteMode()) return;
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = innerWidth * dpr;
    c.height = innerHeight * dpr;
    ctx.scale(dpr, dpr);
    const colors = ["#f3d58f", "#d9ad55", "#b98a35", "#f6e2ae", "#c2412a"];
    const ps = Array.from({ length: 110 }, () => ({
      x: innerWidth / 2,
      y: innerHeight * 0.42,
      vx: (Math.random() - 0.5) * 16,
      vy: -Math.random() * 15 - 4,
      r: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.3,
      w: 6 + Math.random() * 9,
      h: 4 + Math.random() * 6,
      c: colors[(Math.random() * colors.length) | 0],
    }));
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      const k = Math.min(1, (t - t0) / 3200);
      for (const p of ps) {
        p.vy += 0.32;
        p.vx *= 0.985;
        p.x += p.vx;
        p.y += p.vy;
        p.r += p.vr;
        ctx.save();
        ctx.globalAlpha = 1 - k;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.r);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.r * 2)));
        ctx.restore();
      }
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={ref} className="burst" aria-hidden="true" />;
}

/** Thanh toán xong: con dấu son "đóng" xuống + số thứ tự, rồi tự trở về màn hình chờ. */
export function Success() {
  const { server, order, reset, cart, entry } = useKiosk();
  const done = server === "done";
  const [left, setLeft] = useState(12);
  useEffect(() => {
    if (!done) return;
    setLeft(12);
    const id = setInterval(() => setLeft((x) => x - 1), 1000);
    return () => clearInterval(id);
  }, [done]);
  useEffect(() => {
    if (done && left <= 0) reset();
  }, [done, left, reset]);
  const firsts = cart.lines.slice(0, 4);
  return (
    <AnimatePresence>
      {done && (
        <m.div className="success" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={reset}>
          <GoldBurst />
          <m.div
            className="seal"
            initial={{ scale: 2.6, rotate: -22, opacity: 0 }}
            animate={{ scale: 1, rotate: -8, opacity: 1, transition: { type: "spring", stiffness: 260, damping: 15, delay: 0.15 } }}
          >
            <span>Đã nhận tiền</span>
            <b>{orderNumber(order?.code)}</b>
          </m.div>
          <m.h2 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.55 } }}>
            Cảm ơn quý khách
          </m.h2>
          <m.p initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay: 0.75 } }}>
            Món đang được chuẩn bị. Quý khách giữ số thứ tự <b>{orderNumber(order?.code)}</b> để nhận món nhé.
          </m.p>
          <m.div className="success-dishes" initial="h" animate="s" variants={{ s: { transition: { staggerChildren: 0.1, delayChildren: 0.9 } } }}>
            {firsts.map((l) => {
              const e = entry(l.entry_id);
              return e ? (
                <m.div key={l.entry_id} variants={{ h: { opacity: 0, y: 20, scale: 0.8 }, s: { opacity: 1, y: 0, scale: 1 } }}>
                  <DishArt entry={e} lookup={entry} />
                </m.div>
              ) : null;
            })}
          </m.div>
          <p className="success-foot">Màn hình sẽ trở về sau {Math.max(0, left)} giây, chạm để về ngay</p>
        </m.div>
      )}
    </AnimatePresence>
  );
}
