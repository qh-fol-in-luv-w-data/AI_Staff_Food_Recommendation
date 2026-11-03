import { AnimatePresence, m } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { DishArt } from "../art/DishArt";
import { liteMode, money } from "../lib/format";
import { useKiosk } from "../store";
import type { Entry } from "../types";
import { Icon } from "./bits";

function Tile({ e, index, rec }: { e: Entry; index: number; rec: boolean }) {
  const { entry, act, openDetail, detail, cart } = useKiosk();
  const artRef = useRef<HTMLDivElement>(null);
  const source = `grid-${e.id}`;
  const qty = cart.lines.filter((l) => l.entry_id === e.id).reduce((a, l) => a + l.qty, 0);
  return (
    <m.article
      className={`tile ${rec ? "is-rec" : ""}`}
      initial={{ opacity: 0, y: 18, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1, transition: { delay: index * 0.045, type: "spring", stiffness: 260, damping: 24 } }}
      exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.15 } }}
    >
      <button className="tile-art" onClick={() => openDetail({ id: e.id, source })} aria-label={`Xem chi tiết ${e.name}`}>
        {detail?.source === source ? (
          <div className="art-wrap ghost" />
        ) : (
          <m.div layoutId={source} className="art-wrap" ref={artRef}>
            <DishArt entry={e} steam={!liteMode()} lookup={entry} />
          </m.div>
        )}
        {rec && <span className="rec-flag">Mai gợi ý</span>}
        <AnimatePresence>
          {qty > 0 && (
            <m.span key={qty} className="in-tray" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.4, opacity: 0 }}>
              {qty}
            </m.span>
          )}
        </AnimatePresence>
      </button>
      <div className="tile-text">
        <h3>{e.name}</h3>
        <div className="tile-tags">
          {e.best_seller && <span className="tag">{Icon.star}Bán chạy</span>}
          {e.spicy >= 2 && <span className="tag hot">{Icon.chili}Cay</span>}
          {e.vegetarian && <span className="tag veg">{Icon.leaf}Chay</span>}
          {e.serves && e.serves > 1 && <span className="tag">{e.serves} người</span>}
          {e.promos.length > 0 && <span className="tag promo">{Icon.gift}Ưu đãi</span>}
        </div>
      </div>
      <div className="tile-foot">
        <span className="price">{money(e.price)}</span>
        <button className="add" onClick={() => act({ type: "add", entry_id: e.id, qty: 1 }, artRef.current)} aria-label={`Thêm ${e.name}`}>
          {Icon.plus}
        </button>
      </div>
    </m.article>
  );
}

export function Menu() {
  const { cfg, recs, detail } = useKiosk();
  const cats = useMemo(() => {
    if (!cfg) return [];
    return cfg.categories.filter((c) =>
      cfg.entries.some((e) => (c.id === "combo" ? e.kind === "combo" : e.kind === "item" && e.category === c.id)),
    );
  }, [cfg]);
  const [cat, setCat] = useState<string | null>(null);
  const current = cat ?? cats[1]?.id ?? cats[0]?.id;
  const recIds = useMemo(() => new Set(recs.map((r) => r.entry_id)), [recs]);

  // Mai vừa gợi ý -> mở đúng nhóm món chứa món gợi ý đầu tiên
  useEffect(() => {
    if (!cfg || !recs.length) return;
    const first = cfg.entries.find((e) => e.id === recs[0].entry_id);
    if (first) setCat(first.kind === "combo" ? "combo" : first.category);
  }, [recs, cfg]);
  // Mai mở một món theo lời khách -> thực đơn chuyển tới nhóm của món đó (đóng lại thì bát bay về đúng chỗ)
  const shown = detail?.source.startsWith("grid-") ? detail.id : null;
  useEffect(() => {
    if (!cfg || !shown) return;
    const e = cfg.entries.find((x) => x.id === shown);
    if (e) setCat(e.kind === "combo" ? "combo" : e.category);
  }, [shown, cfg]);

  if (!cfg) return <section className="menu" />;
  const list = cfg.entries.filter((e) => (current === "combo" ? e.kind === "combo" : e.kind === "item" && e.category === current));
  return (
    <section className="menu" aria-label="Thực đơn">
      <nav className="cats" aria-label="Nhóm món">
        {cats.map((c) => (
          <button key={c.id} className={c.id === current ? "on" : ""} onClick={() => setCat(c.id)} aria-current={c.id === current}>
            {c.name}
            {c.id === current && <m.span layoutId="cat-ind" className="cat-ind" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
          </button>
        ))}
      </nav>
      <div className="table" key={current}>
        <AnimatePresence mode="popLayout">
          {list.map((e, i) => (
            <Tile key={e.id} e={e} index={i} rec={recIds.has(e.id)} />
          ))}
        </AnimatePresence>
      </div>
    </section>
  );
}
