import { useEffect, useState } from "react";
import { DishArt } from "./art/DishArt";
import type { Config, Entry } from "./types";

/** /?gallery : xem nhanh minh hoạ toàn bộ món (cho chủ quán kiểm tra menu). */
export default function Gallery() {
  const [cfg, setCfg] = useState<Config | null>(null);
  useEffect(() => {
    fetch("/api/config").then((r) => r.json()).then(setCfg);
  }, []);
  if (!cfg) return null;
  const lookup = (id: string) => cfg.entries.find((e) => e.id === id) as Entry | undefined;
  return (
    <div className="gallery">
      {cfg.entries.map((e) => (
        <figure key={e.id}>
          <DishArt entry={e} steam lookup={lookup} />
          <figcaption>{e.name}</figcaption>
        </figure>
      ))}
    </div>
  );
}
