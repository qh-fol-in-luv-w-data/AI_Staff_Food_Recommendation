import { AnimatePresence, m } from "motion/react";
import { useEffect, useState } from "react";
import { DishArt } from "../art/DishArt";
import { liteMode } from "../lib/format";
import { useKiosk } from "../store";
import { Orb } from "./Orb";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

/** Thanh trên: con dấu tên quán + dải ưu đãi chạy luân phiên. */
export function TopBar() {
  const { cfg, reset, started } = useKiosk();
  const promos = cfg?.promotions ?? [];
  const [i, setI] = useState(0);
  useEffect(() => {
    if (promos.length < 2) return;
    const id = setInterval(() => setI((x) => (x + 1) % promos.length), 5200);
    return () => clearInterval(id);
  }, [promos.length]);
  const p = promos[i % Math.max(1, promos.length)];
  return (
    <header className="topbar">
      <div className="brand">
        <span className="seal-logo" aria-hidden="true">
          {initials(cfg?.store.short_name ?? "")}
        </span>
        <div>
          <h1>{cfg?.store.short_name ?? ""}</h1>
          <p>{cfg?.store.address}</p>
        </div>
      </div>
      <div className="ribbon" aria-live="polite">
        <AnimatePresence mode="wait">
          {p && (
            <m.p key={p.id} initial={{ y: 16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -16, opacity: 0 }} transition={{ duration: 0.4 }}>
              <b className="gold-text">{p.name}</b>
              <span>{p.pitch ? p.pitch[0].toUpperCase() + p.pitch.slice(1) : p.reward}</span>
            </m.p>
          )}
        </AnimatePresence>
      </div>
      {started && (
        <button className="ghost-btn" onClick={reset}>
          Khách mới
        </button>
      )}
    </header>
  );
}

/** Màn hình chờ: mâm sơn mài xoay chậm với các món đặt vòng quanh, Mai ở giữa. */
export function Attract() {
  const { cfg, start, started, entry } = useKiosk();
  const ring = (cfg?.entries ?? []).filter((e) => e.kind === "item" && e.style !== "an_kem").slice(0, 10);
  const name = cfg?.store.assistant ?? "Mai";
  return (
    <AnimatePresence>
      {!started && cfg && (
        <m.section
          className="attract"
          onClick={start}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, scale: 1.04, transition: { duration: 0.45 } }}
          aria-label="Màn hình chào"
        >
          <div className={`tray-ring ${liteMode() ? "" : "spin"}`} aria-hidden="true">
            {ring.map((e, i) => {
              const a = (i / ring.length) * 360;
              return (
                <div key={e.id} className="ring-dish" style={{ transform: `rotate(${a}deg) translate(var(--ring-r)) rotate(${-a}deg)` }}>
                  <m.div
                    className="ring-pop"
                    initial={{ opacity: 0, scale: 0.6 }}
                    animate={{ opacity: 1, scale: 1, transition: { delay: 0.25 + i * 0.09, type: "spring", stiffness: 180, damping: 16 } }}
                  >
                    <div className="ring-dish-inner">
                      <DishArt entry={e} steam={!liteMode()} lookup={entry} />
                    </div>
                  </m.div>
                </div>
              );
            })}
          </div>

          <div className="attract-center">
            <Orb state="idle" size={120} />
            <m.h1 initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.5 } }}>
              Xin chào
            </m.h1>
            <m.p initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { delay: 0.8 } }}>
              Em là {name}, sẽ giúp quý khách chọn món ngon hôm nay.
            </m.p>
            <m.button
              className="cta start"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0, transition: { delay: 1.05 } }}
              onClick={(ev) => {
                ev.stopPropagation();
                start();
              }}
            >
              Chạm để gọi món
            </m.button>
            {cfg.speech && <p className="attract-hint">hoặc nói "Xin chào {name}"</p>}
          </div>

          {cfg.promotions.length > 0 && (
            <div className="tickets">
              {cfg.promotions.slice(0, 3).map((p, i) => (
                <m.div key={p.id} className="ticket" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0, transition: { delay: 1.2 + i * 0.12 } }}>
                  <b>{p.name}</b>
                  <span>{p.reward}</span>
                </m.div>
              ))}
            </div>
          )}
        </m.section>
      )}
    </AnimatePresence>
  );
}

/** Món "bay" vào mâm khi được thêm (từ màn hình chạm hoặc từ quả cầu của Mai khi gọi bằng giọng nói). */
export function FlyLayer() {
  const { flyers, dropFlyer, trayRef, entry } = useKiosk();
  return (
    <div className="fly-layer" aria-hidden="true">
      {flyers.map((f) => {
        const e = entry(f.entryId);
        const target = trayRef.current?.getBoundingClientRect();
        if (!e || !target) {
          setTimeout(() => dropFlyer(f.key), 0);
          return null;
        }
        const size = Math.min(150, Math.max(70, f.from.width));
        const sx = f.from.left + f.from.width / 2 - size / 2;
        const sy = f.from.top + f.from.height / 2 - size / 2;
        const dx = target.left + target.width / 2 - (sx + size / 2);
        const dy = target.top + target.height / 2 - (sy + size / 2);
        return (
          <m.div
            key={f.key}
            className="flyer"
            style={{ left: sx, top: sy, width: size, height: size }}
            initial={{ x: 0, y: 0, scale: 1, opacity: 1, rotate: 0 }}
            animate={{ x: [0, dx * 0.45, dx], y: [0, dy * 0.45 - 150, dy], scale: [1, 0.72, 0.16], rotate: [0, 120, 260], opacity: [1, 1, 0.3] }}
            transition={{ duration: 0.9, ease: "easeInOut", times: [0, 0.48, 1] }}
            onAnimationComplete={() => dropFlyer(f.key)}
          >
            <DishArt entry={e} lookup={entry} />
          </m.div>
        );
      })}
    </div>
  );
}

export function Offline() {
  const { connected, cfg } = useKiosk();
  return (
    <AnimatePresence>
      {cfg && !connected && (
        <m.div className="offline" initial={{ y: -40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -40, opacity: 0 }} role="status">
          Mất kết nối với máy chủ của quán, đang kết nối lại…
        </m.div>
      )}
    </AnimatePresence>
  );
}
