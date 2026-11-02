/**
 * Minh hoạ món ăn bằng SVG, nhìn từ trên xuống: bát/đĩa sứ viền lam kiểu Bát Tràng đặt trên mâm sơn mài.
 * - Món có `image` (ảnh chụp thật của quán) -> hiển thị ảnh.
 * - Món trong menu mẫu có "công thức" vẽ riêng (RECIPES).
 * - Món mới chưa có công thức -> tự suy ra từ thuộc tính (món nước/khô/đồ uống, thành phần, độ cay...).
 * Toàn bộ là vector (nhẹ, nét trên mọi màn hình), vị trí topping cố định theo id món (seeded random).
 */
import { memo, useId, type ReactNode } from "react";
import type { Entry } from "../types";

type Vessel = "bowl" | "plate" | "glass" | "can" | "small";
type Shape =
  | "beefRare" | "beefCooked" | "beefBall" | "tendon" | "chicken" | "shrimp" | "squid" | "herb" | "basil"
  | "scallion" | "onion" | "chili" | "lime" | "tomato" | "tofu" | "mushroom" | "crab" | "chiliOil"
  | "lemongrass" | "knuckle" | "crabCake" | "cucumber" | "pickle" | "sesame" | "peanut" | "bean" | "mung"
  | "jelly" | "kumquat" | "mint" | "ice" | "noodle" | "noodleY" | "egg" | "carrot" | "broccoli" | "chiliFlake"
  | "patty" | "porkBelly" | "bi" | "scallionOil";
type Big =
  | ["rice", number, number, number, "white" | "yellow"]
  | ["porkChop", number, number, number]
  | ["eggCake", number, number, number]
  | ["sauce", number, number, number, string, Shape?]
  | ["rollFresh", number, number, number, "shrimp" | "tofu"]
  | ["rollFried", number, number, number]
  | ["quay", number, number, number]
  | ["chickenLeg", number, number, number]
  | ["nest", number, number, number]
  | ["lettuce", number, number, number, number]
  | ["orange", number, number, number]
  | ["milk"]
  | ["swirl"]
  | ["cream"];
/** [hình, số lượng, góc từ, góc đến, bán kính từ, bán kính đến, tỉ lệ] */
type Layer = [Shape, number, number, number, number, number, number?];

interface Recipe {
  vessel: Vessel;
  liquid?: [string, string, number?];
  big?: Big[];
  layers?: Layer[];
  top?: Big[];
  steam?: boolean;
  ice?: number;
  straw?: string;
}

const C = {
  porcelain: ["#ffffff", "#f1ece1", "#d6cdbb"],
  cobalt: "#2d4f8e",
};

// ------------------------------------------------------------------ seeded random
function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function mulberry(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ------------------------------------------------------------------ hình nhỏ (toạ độ quanh 0,0)
function shape(kind: Shape, r: () => number): ReactNode {
  switch (kind) {
    case "beefRare":
      return (
        <>
          <path d="M-22,-9C-12,-17 12,-16 23,-7C30,0 21,13 5,14C-11,16-27,6-22,-9Z" fill="#c4585c" />
          <path d="M-15,-4C-5,-8 7,-7 16,-2M-12,4C-2,1 8,2 15,6" stroke="#f3bcb8" strokeWidth="1.7" fill="none" opacity=".8" strokeLinecap="round" />
          <path d="M-22,-9C-12,-17 12,-16 23,-7" stroke="#8a2c36" strokeWidth="1.3" fill="none" opacity=".55" />
        </>
      );
    case "beefCooked":
      return (
        <>
          <path d="M-22,-9C-12,-17 12,-16 23,-7C30,0 21,13 5,14C-11,16-27,6-22,-9Z" fill="#8b5c48" />
          <path d="M-15,-4C-5,-8 7,-7 16,-2M-13,5C-3,2 8,3 14,6" stroke="#cfa98f" strokeWidth="1.6" fill="none" opacity=".75" strokeLinecap="round" />
        </>
      );
    case "beefBall":
      return (
        <>
          <circle r="8.5" fill="#674434" />
          <circle cx="-3" cy="-3" r="2.8" fill="#b98c72" opacity=".7" />
        </>
      );
    case "tendon":
      return <ellipse rx="9" ry="5.5" fill="#efe2c4" stroke="#c9b28a" strokeWidth="1.2" opacity=".9" />;
    case "chicken":
      return <rect x="-15" y="-4" width="30" height="8" rx="4" fill="#f2ddb4" stroke="#d3ad78" strokeWidth="1.1" />;
    case "shrimp":
      return (
        <>
          <path d="M-12,4C-15,-8-2,-15 8,-11C15,-8 15,0 10,2C5,4 3,-3-2,-1C-7,1-6,8-12,4Z" fill="#f2955f" />
          <path d="M-6,-9L-3,-2M1,-11L2,-4M7,-9L5,-3" stroke="#fcd6bb" strokeWidth="1.5" strokeLinecap="round" />
        </>
      );
    case "squid":
      return (
        <>
          <circle r="7" fill="none" stroke="#f7efe7" strokeWidth="4.2" />
          <circle r="7" fill="none" stroke="#d9a8c3" strokeWidth="1" opacity=".75" />
        </>
      );
    case "herb":
      return (
        <>
          <path d="M0,-11C7,-6 7,6 0,11C-7,6-7,-6 0,-11Z" fill="#5f9d47" />
          <path d="M0,-9L0,9" stroke="#93d26e" strokeWidth="1.1" />
        </>
      );
    case "basil":
      return (
        <>
          <path d="M0,-15C10,-8 10,8 0,15C-10,8-10,-8 0,-15Z" fill="#3e7a39" />
          <path d="M0,-12L0,12" stroke="#6eb35b" strokeWidth="1.2" />
        </>
      );
    case "mint":
      return <path d="M0,-8C6,-4 6,4 0,8C-6,4-6,-4 0,-8Z" fill="#3fae64" />;
    case "scallion":
      return <circle r="4.3" fill="#d2ee9e" stroke="#5a9c3a" strokeWidth="2" />;
    case "onion":
      return <path d="M-10,2A10,10 0 0 1 10,2" stroke="#f8f3ea" strokeWidth="3.2" fill="none" strokeLinecap="round" />;
    case "chili":
      return (
        <>
          <circle r="4.4" fill="#d8352a" />
          <circle r="1.6" fill="#f7d3a3" />
        </>
      );
    case "chiliFlake":
      return <rect x="-1.6" y="-1" width="3.2" height="2" rx="1" fill="#c62a1a" />;
    case "lime":
      return (
        <>
          <path d="M-15,0A15,15 0 0 1 15,0Z" fill="#7fae3e" />
          <path d="M-12,0A12,12 0 0 1 12,0Z" fill="#c9e58f" />
          <path d="M0,0L0,-11M0,0L-8,-8M0,0L8,-8" stroke="#eaf6cf" strokeWidth="1.2" />
        </>
      );
    case "tomato":
      return (
        <>
          <path d="M-13,0A13,13 0 0 1 13,0C8,4-8,4-13,0Z" fill="#df4a2f" />
          <circle cx="-4" cy="-4" r="1.3" fill="#f6c86a" />
          <circle cx="3" cy="-5" r="1.3" fill="#f6c86a" />
        </>
      );
    case "tofu":
      return <rect x="-8" y="-8" width="16" height="16" rx="3.6" fill="#e6ae53" stroke="#bf7f2a" strokeWidth="1.3" />;
    case "mushroom":
      return (
        <>
          <circle r="9" fill="#6e4628" />
          <path d="M-5,-5L5,5M5,-5L-5,5" stroke="#a7825f" strokeWidth="1.7" strokeLinecap="round" />
        </>
      );
    case "crab": {
      const blobs = Array.from({ length: 6 }, (_, i) => {
        const a = (i / 6) * Math.PI * 2 + r();
        const d = 3 + r() * 5;
        return <circle key={i} cx={Math.cos(a) * d} cy={Math.sin(a) * d} r={4 + r() * 3.5} fill={i % 2 ? "#c46f2c" : "#b25f22"} />;
      });
      return (
        <>
          {blobs}
          <circle cx="-2" cy="-2" r="1.4" fill="#f1b67a" />
          <circle cx="3" cy="2" r="1.2" fill="#f1b67a" />
        </>
      );
    }
    case "chiliOil": {
      const rr = 2.4 + r() * 3.2;
      return (
        <>
          <circle r={rr} fill="#ea6a2b" opacity=".88" />
          <circle cx={-rr / 3} cy={-rr / 3} r={rr / 3} fill="#ffd2a6" opacity=".75" />
        </>
      );
    }
    case "lemongrass":
      return <circle r="3.6" fill="#e5efb8" stroke="#a5bf63" strokeWidth="1.3" />;
    case "knuckle":
      return (
        <>
          <circle r="13" fill="#e8d0ad" stroke="#b78c58" strokeWidth="3" />
          <circle r="4.5" fill="#f6eddc" stroke="#cdb08a" strokeWidth="1.2" />
        </>
      );
    case "crabCake":
      return (
        <>
          <rect x="-10" y="-7" width="20" height="14" rx="3" fill="#d8b089" />
          <circle cx="-4" cy="-2" r="1.3" fill="#a97948" />
          <circle cx="4" cy="2" r="1.3" fill="#a97948" />
        </>
      );
    case "cucumber":
      return (
        <>
          <circle r="8.5" fill="#d8edbb" stroke="#4b8838" strokeWidth="2.6" />
          <circle cx="-2" cy="0" r="1" fill="#9cc77a" />
          <circle cx="2" cy="1" r="1" fill="#9cc77a" />
        </>
      );
    case "pickle":
      return <rect x="-11" y="-2" width="22" height="4" rx="2" fill={r() > 0.5 ? "#f0a050" : "#f6eedc"} />;
    case "sesame":
      return <ellipse rx="1.7" ry="0.9" fill="#f6e7c0" />;
    case "peanut":
      return <ellipse rx="2.6" ry="1.9" fill="#c9955a" />;
    case "bean":
      return <ellipse rx="3.2" ry="2.3" fill="#7c2330" />;
    case "mung":
      return <circle r={3 + r() * 2.5} fill="#f2c24c" />;
    case "jelly":
      return <path d="M-11,0C-5,-5 5,5 11,0" stroke="#69b85f" strokeWidth="3.6" fill="none" strokeLinecap="round" />;
    case "kumquat":
      return (
        <>
          <circle r="8.5" fill="#f4a321" />
          <circle r="6.4" fill="#fbcb6c" />
          <path d="M0,-6L0,6M-6,0L6,0M-4,-4L4,4M4,-4L-4,4" stroke="#f1a432" strokeWidth=".9" />
        </>
      );
    case "ice":
      return (
        <>
          <rect x="-10" y="-10" width="20" height="20" rx="5" fill="rgba(255,255,255,.4)" stroke="rgba(255,255,255,.78)" strokeWidth="1.3" />
          <path d="M-6,-6L2,-6" stroke="#fff" strokeWidth="2.2" opacity=".75" strokeLinecap="round" />
        </>
      );
    case "noodle":
      return <path d="M-30,0C-20,-6-10,6 0,0S20,-6 30,0" stroke="#f8f2e2" strokeWidth="3.3" fill="none" strokeLinecap="round" opacity=".95" />;
    case "noodleY":
      return <path d="M-30,0C-20,-6-10,6 0,0S20,-6 30,0" stroke="#f1d27b" strokeWidth="3.6" fill="none" strokeLinecap="round" />;
    case "egg":
      return (
        <>
          <ellipse rx="14" ry="11" fill="#fbf6ea" />
          <circle cx="1" r="6.2" fill="#f2a01b" />
        </>
      );
    case "carrot":
      return (
        <>
          <circle r="5.4" fill="#f08a2b" />
          <circle r="2.2" fill="#f7b46a" />
        </>
      );
    case "broccoli":
      return (
        <>
          <circle cx="-4" cy="-2" r="5" fill="#4d8c3a" />
          <circle cx="3" cy="-4" r="5" fill="#5a9c45" />
          <circle cx="1" cy="3" r="5" fill="#457f33" />
        </>
      );
    case "patty":
      return (
        <>
          <ellipse rx="14" ry="10" fill="#7a4426" />
          <circle cx="-5" cy="-2" r="2" fill="#3d1f10" opacity=".7" />
          <circle cx="4" cy="3" r="1.6" fill="#3d1f10" opacity=".7" />
          <ellipse cx="-3" cy="-4" rx="5" ry="2" fill="#b0703f" opacity=".6" />
        </>
      );
    case "porkBelly":
      return (
        <>
          <rect x="-15" y="-7" width="30" height="14" rx="3" fill="#8a4a26" />
          <rect x="-15" y="-2" width="30" height="3.4" fill="#e7bb8f" />
          <path d="M-9,-7L-3,7M2,-7L8,7" stroke="#4a230f" strokeWidth="2" opacity=".55" />
        </>
      );
    case "bi":
      return (
        <path d="M-12,-4C-4,-8 4,0 12,-4M-12,0C-4,-4 4,4 12,0M-12,4C-4,0 4,8 12,4" stroke="#f3e3c3" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      );
    case "scallionOil":
      return <circle r={1.6 + r() * 1.4} fill="#6fae3a" />;
  }
}

function place(r: () => number, n: number, a0: number, a1: number, r0: number, r1: number) {
  const out: [number, number, number][] = [];
  for (let i = 0; i < n; i++) {
    const t = n === 1 ? 0.5 : i / (n - 1);
    const a = ((a0 + (a1 - a0) * t + (r() - 0.5) * ((a1 - a0) / Math.max(n, 2)) * 0.8) * Math.PI) / 180;
    const d = r0 + (r1 - r0) * r();
    out.push([120 + Math.cos(a) * d, 120 + Math.sin(a) * d, r() * 360]);
  }
  return out;
}

// ------------------------------------------------------------------ thành phần lớn
function big(b: Big, r: () => number, id: string): ReactNode {
  switch (b[0]) {
    case "rice": {
      const [, x, y, rad, tone] = b;
      const base = tone === "yellow" ? ["#f6dc7c", "#e4b94a"] : ["#fffdf6", "#e9e1cf"];
      const grains = Array.from({ length: 58 }, (_, i) => {
        const a = r() * Math.PI * 2;
        const d = Math.sqrt(r()) * (rad - 5);
        return (
          <ellipse key={i} cx={x + Math.cos(a) * d} cy={y + Math.sin(a) * d} rx="3" ry="1.4"
            transform={`rotate(${r() * 180} ${x + Math.cos(a) * d} ${y + Math.sin(a) * d})`}
            fill={tone === "yellow" ? "#fbe9a6" : "#ffffff"} opacity=".9" />
        );
      });
      return (
        <g>
          <circle cx={x} cy={y} r={rad} fill={`url(#${id}-rice-${tone})`} />
          <defs>
            <radialGradient id={`${id}-rice-${tone}`} cx="40%" cy="35%" r="70%">
              <stop offset="0" stopColor={base[0]} />
              <stop offset="1" stopColor={base[1]} />
            </radialGradient>
          </defs>
          {grains}
        </g>
      );
    }
    case "porkChop": {
      const [, x, y, rot] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot})`}>
          <path d="M-38,-14C-30,-30 18,-32 36,-18C46,-8 40,16 18,22C-4,28-34,22-40,6C-42,-2-41,-8-38,-14Z" fill="#a85f2b" />
          <path d="M-38,-14C-30,-30 18,-32 36,-18C46,-8 40,16 18,22" fill="none" stroke="#6c3313" strokeWidth="3" opacity=".6" />
          <path d="M-24,-20L-8,18M-8,-24L8,16M8,-24L24,12M24,-18L34,4" stroke="#4a210b" strokeWidth="4" strokeLinecap="round" opacity=".55" />
          <path d="M-30,-10C-16,-20 14,-22 28,-12" stroke="#e7a668" strokeWidth="3" fill="none" opacity=".45" strokeLinecap="round" />
          <ellipse cx="-30" cy="4" rx="7" ry="5" fill="#f2dcc0" opacity=".9" />
        </g>
      );
    }
    case "eggCake": {
      const [, x, y, rot] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot})`}>
          <rect x="-24" y="-15" width="48" height="30" rx="5" fill="#f4c34f" />
          <rect x="-24" y="-15" width="48" height="8" rx="4" fill="#c27b1d" />
          <circle cx="-8" cy="4" r="1.6" fill="#d58f2a" />
          <circle cx="8" cy="7" r="1.4" fill="#d58f2a" />
          <circle cx="12" cy="-1" r="1.2" fill="#7c4a1c" />
        </g>
      );
    }
    case "sauce": {
      const [, x, y, rad, color, bit] = b;
      const bits = bit
        ? place(r, 6, 0, 360, 0, rad * 0.55).map(([bx, by, br], i) => (
            <g key={i} transform={`translate(${x + (bx - 120)} ${y + (by - 120)}) rotate(${br}) scale(.55)`}>{shape(bit, r)}</g>
          ))
        : null;
      return (
        <g>
          <circle cx={x + 2} cy={y + 4} r={rad + 4} fill="#000" opacity=".18" />
          <circle cx={x} cy={y} r={rad + 4} fill="#f3eee4" stroke={C.cobalt} strokeWidth="1.6" />
          <circle cx={x} cy={y} r={rad} fill={color} />
          {bits}
          <ellipse cx={x - rad * 0.35} cy={y - rad * 0.4} rx={rad * 0.45} ry={rad * 0.2} fill="#fff" opacity=".22" />
        </g>
      );
    }
    case "rollFresh": {
      const [, x, y, rot, fill] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot})`}>
          <rect x="-38" y="-15" width="76" height="30" rx="15" fill="#f2f6ee" opacity=".92" />
          <rect x="-34" y="-9" width="68" height="18" rx="9" fill="#bfe09a" opacity=".55" />
          {fill === "shrimp" ? (
            <>
              <g transform="translate(-16 0) scale(.75)">{shape("shrimp", r)}</g>
              <g transform="translate(4 1) scale(.75) rotate(20)">{shape("shrimp", r)}</g>
              <g transform="translate(22 -1) scale(.7)">{shape("shrimp", r)}</g>
            </>
          ) : (
            <>
              <rect x="-24" y="-5" width="14" height="10" rx="2.5" fill="#e6ae53" />
              <rect x="-4" y="-5" width="14" height="10" rx="2.5" fill="#e6ae53" />
              <rect x="16" y="-5" width="12" height="10" rx="2.5" fill="#e6ae53" />
            </>
          )}
          <rect x="-38" y="-15" width="76" height="30" rx="15" fill="none" stroke="#fff" strokeWidth="1.5" opacity=".9" />
          <path d="M-30,-10L30,-10" stroke="#fff" strokeWidth="2.4" opacity=".55" strokeLinecap="round" />
        </g>
      );
    }
    case "rollFried": {
      const [, x, y, rot] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot})`}>
          <rect x="-30" y="-10" width="60" height="20" rx="10" fill="#cf8a33" />
          <rect x="-28" y="-8" width="56" height="7" rx="3.5" fill="#e9b05a" opacity=".8" />
          {Array.from({ length: 9 }, (_, i) => (
            <circle key={i} cx={-24 + i * 6} cy={(i % 2 ? 3 : -2) + r()} r="1.3" fill="#f6cf86" opacity=".9" />
          ))}
        </g>
      );
    }
    case "quay": {
      const [, x, y, rot] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot})`}>
          <rect x="-62" y="-11" width="124" height="22" rx="11" fill="#d9993f" />
          <rect x="-58" y="-8" width="116" height="7" rx="3.5" fill="#f0c06c" opacity=".85" />
          <path d="M-40,-10C-36,0-36,0-40,10M-15,-10C-11,0-11,0-15,10M10,-10C14,0 14,0 10,10M35,-10C39,0 39,0 35,10" stroke="#b16f22" strokeWidth="2" fill="none" />
        </g>
      );
    }
    case "chickenLeg": {
      const [, x, y, rot] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot})`}>
          <path d="M-34,-6C-34,-26 0,-30 18,-16C30,-6 30,10 16,18C0,28-34,18-34,-6Z" fill="#c7782b" />
          <path d="M18,-6L44,-4" stroke="#f3e6cf" strokeWidth="7" strokeLinecap="round" />
          <circle cx="46" cy="-4" r="5" fill="#f3e6cf" />
          {Array.from({ length: 14 }, (_, i) => (
            <circle key={i} cx={-26 + r() * 40} cy={-18 + r() * 32} r={1.2 + r() * 1.6} fill="#f0b45e" opacity=".85" />
          ))}
          <path d="M-28,-12C-16,-22 4,-22 14,-14" stroke="#f7c983" strokeWidth="3" fill="none" opacity=".5" strokeLinecap="round" />
        </g>
      );
    }
    case "nest": {
      const [, x, y, rad] = b;
      return (
        <g>
          <circle cx={x} cy={y} r={rad} fill="#f4efe2" />
          {Array.from({ length: 9 }, (_, i) => (
            <circle key={i} cx={x + (r() - 0.5) * 6} cy={y + (r() - 0.5) * 6} r={rad * (0.3 + i * 0.075)} fill="none"
              stroke={i % 2 ? "#fffdf6" : "#e4dccb"} strokeWidth="2.2" strokeDasharray={`${8 + r() * 10} ${4 + r() * 6}`} />
          ))}
        </g>
      );
    }
    case "lettuce": {
      const [, x, y, rot, s] = b;
      return (
        <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`}>
          <path d="M-30,0C-26,-18-8,-24 6,-20C22,-16 34,-6 30,6C26,18 8,22-8,20C-22,18-32,10-30,0Z" fill="#8cc85a" />
          <path d="M-24,2C-10,0 10,-2 26,0" stroke="#c6e89d" strokeWidth="2" fill="none" />
          <path d="M-30,0C-26,-18-8,-24 6,-20C22,-16 34,-6 30,6" stroke="#6aa63f" strokeWidth="2" fill="none" />
        </g>
      );
    }
    case "orange": {
      const [, x, y, rad] = b;
      return (
        <g>
          <circle cx={x} cy={y} r={rad} fill="#f7931e" />
          <circle cx={x} cy={y} r={rad - 3} fill="#ffc46b" />
          {Array.from({ length: 8 }, (_, i) => {
            const a = (i / 8) * Math.PI * 2;
            return <path key={i} d={`M${x},${y}L${x + Math.cos(a) * (rad - 3)},${y + Math.sin(a) * (rad - 3)}`} stroke="#f5a43c" strokeWidth="1.2" />;
          })}
        </g>
      );
    }
    case "milk":
      return (
        <path d="M120,120m-40,0a40,40 0 1,0 80,0a28,28 0 1,0 -56,0a16,16 0 1,0 32,0" fill="none" stroke="#e9d4b6" strokeWidth="7" opacity=".55" strokeLinecap="round" />
      );
    case "swirl":
      return (
        <path d="M120,120m-46,0a46,46 0 1,0 92,0a33,33 0 1,0 -66,0a20,20 0 1,0 40,0" fill="none" stroke="#e6f0bf" strokeWidth="6" opacity=".6" strokeLinecap="round" />
      );
    case "cream":
      return (
        <g>
          <circle cx="120" cy="120" r="64" fill="#fbf8f0" />
          {Array.from({ length: 16 }, (_, i) => {
            const a = r() * Math.PI * 2;
            const d = r() * 52;
            const cx = 120 + Math.cos(a) * d;
            const cy = 120 + Math.sin(a) * d;
            return <path key={i} d={`M${cx - 5},${cy}L${cx},${cy - 6}L${cx + 6},${cy + 1}L${cx},${cy + 5}Z`} fill="#ffffff" stroke="#e7eef3" strokeWidth=".8" />;
          })}
        </g>
      );
  }
}

// ------------------------------------------------------------------ công thức món mẫu
const SOUP_GARNISH: Layer[] = [
  ["onion", 5, 330, 420, 22, 58],
  ["scallion", 10, 0, 360, 10, 64],
  ["herb", 4, 40, 130, 34, 60],
  ["chili", 3, 140, 220, 40, 62],
];
const PHO_NOODLES: Layer = ["noodle", 6, 0, 360, 30, 66];

const RECIPES: Record<string, Recipe> = {
  "pho-bo-tai": { vessel: "bowl", liquid: ["#e3ad5f", "#ad6c2c"], layers: [PHO_NOODLES, ["beefRare", 5, 160, 330, 18, 52], ...SOUP_GARNISH], steam: true },
  "pho-bo-chin": { vessel: "bowl", liquid: ["#e3ad5f", "#ad6c2c"], layers: [PHO_NOODLES, ["beefCooked", 5, 160, 330, 18, 52], ...SOUP_GARNISH], steam: true },
  "pho-dac-biet": {
    vessel: "bowl", liquid: ["#dca055", "#a3632a"],
    layers: [PHO_NOODLES, ["beefRare", 3, 170, 260, 20, 50], ["beefCooked", 3, 270, 350, 20, 50], ["beefBall", 4, 20, 140, 30, 55], ["tendon", 2, 140, 170, 40, 55], ["scallion", 12, 0, 360, 8, 64], ["herb", 3, 60, 120, 20, 40], ["onion", 4, 0, 90, 30, 60]],
    steam: true,
  },
  "pho-ga": { vessel: "bowl", liquid: ["#ecca83", "#c39249"], layers: [PHO_NOODLES, ["chicken", 7, 150, 340, 15, 55], ["onion", 4, 340, 420, 28, 58], ["scallion", 10, 0, 360, 10, 64], ["herb", 5, 40, 140, 30, 60]], steam: true },
  "bun-bo-hue": {
    vessel: "bowl", liquid: ["#d8592c", "#9a2c13"],
    layers: [["noodle", 5, 0, 360, 34, 66], ["chiliOil", 16, 0, 360, 6, 70], ["beefCooked", 3, 180, 280, 22, 50], ["knuckle", 1, 300, 300, 40, 40], ["crabCake", 2, 20, 70, 36, 52], ["lemongrass", 5, 90, 160, 30, 60], ["scallion", 8, 0, 360, 10, 64], ["onion", 3, 120, 170, 40, 60]],
    steam: true,
  },
  "bun-rieu": {
    vessel: "bowl", liquid: ["#e27f3c", "#b04f1e"],
    layers: [["noodle", 5, 0, 360, 34, 66], ["crab", 4, 180, 330, 18, 48], ["tomato", 4, 20, 150, 30, 58], ["tofu", 3, 160, 200, 40, 60], ["scallion", 10, 0, 360, 8, 64], ["chiliOil", 6, 0, 360, 10, 66]],
    steam: true,
  },
  "mi-cay": {
    vessel: "bowl", liquid: ["#d9432a", "#8a1d11"],
    layers: [["noodleY", 6, 0, 360, 28, 66], ["chiliFlake", 26, 0, 360, 4, 72], ["shrimp", 3, 190, 320, 26, 50], ["squid", 4, 20, 150, 30, 58], ["egg", 1, 160, 160, 42, 42], ["sesame", 14, 0, 360, 4, 66], ["scallion", 6, 0, 360, 10, 60]],
    steam: true,
  },
  "bun-cha": {
    vessel: "plate",
    big: [["nest", 86, 92, 46], ["sauce", 158, 150, 42, "#c98a45"], ["lettuce", 92, 168, -20, 0.8]],
    layers: [["patty", 3, 0, 360, 10, 26], ["porkBelly", 2, 0, 360, 14, 24], ["pickle", 5, 0, 360, 6, 30], ["herb", 4, 190, 250, 70, 90], ["chili", 2, 0, 360, 10, 20]],
  },
  "com-tam": {
    vessel: "plate",
    big: [["rice", 92, 104, 50, "white"], ["porkChop", 152, 128, -18], ["eggCake", 102, 172, 8], ["sauce", 172, 64, 20, "#d8963c", "chili"]],
    layers: [["scallionOil", 18, 0, 360, 0, 1], ["bi", 2, 120, 160, 60, 70], ["cucumber", 3, 250, 300, 72, 88], ["tomato", 2, 310, 340, 78, 88]],
  },
  "com-ga": {
    vessel: "plate",
    big: [["rice", 94, 106, 50, "yellow"], ["chickenLeg", 150, 140, -28], ["sauce", 170, 66, 18, "#d23c26"]],
    layers: [["cucumber", 3, 120, 170, 70, 86], ["tomato", 2, 180, 210, 76, 88], ["herb", 3, 90, 120, 76, 88]],
  },
  "com-chay": {
    vessel: "plate",
    big: [["rice", 96, 100, 48, "white"], ["sauce", 168, 66, 18, "#5a3a22"]],
    layers: [["tofu", 4, 20, 110, 52, 78], ["mushroom", 3, 120, 170, 58, 80], ["broccoli", 3, 290, 340, 56, 80], ["carrot", 4, 340, 400, 66, 86]],
  },
  "goi-cuon": {
    vessel: "plate",
    big: [["lettuce", 116, 112, 10, 1.4], ["rollFresh", 104, 96, -24, "shrimp"], ["rollFresh", 122, 140, -24, "shrimp"], ["sauce", 176, 70, 22, "#8a5a32", "peanut"]],
  },
  "goi-cuon-chay": {
    vessel: "plate",
    big: [["lettuce", 116, 112, 10, 1.4], ["rollFresh", 104, 96, -24, "tofu"], ["rollFresh", 122, 140, -24, "tofu"], ["sauce", 176, 70, 22, "#8a5a32", "peanut"]],
  },
  "cha-gio": {
    vessel: "plate",
    big: [["lettuce", 92, 150, -30, 1.2], ["lettuce", 150, 160, 40, 1], ["rollFried", 96, 92, -30], ["rollFried", 118, 112, -30], ["rollFried", 140, 132, -30], ["rollFried", 104, 140, 40], ["rollFried", 150, 90, 40], ["sauce", 178, 176, 20, "#d8963c", "chili"]],
  },
  quay: { vessel: "small", big: [["quay", 120, 108, -18], ["quay", 120, 136, -8]] },
  "tra-da": { vessel: "glass", liquid: ["#d9a86c", "#a8743b", 0.75], ice: 7 },
  "tra-tac": { vessel: "glass", liquid: ["#f0b347", "#c47e1d", 0.85], layers: [["kumquat", 3, 0, 360, 20, 44], ["mint", 3, 0, 360, 10, 40]], ice: 4, straw: "#3f7d3a" },
  "ca-phe-sua-da": { vessel: "glass", liquid: ["#8a5634", "#4a2914"], big: [["milk"]], ice: 4, straw: "#1d1410" },
  "nuoc-cam": { vessel: "glass", liquid: ["#f9a43a", "#e2690c"], big: [["orange", 154, 82, 24]], ice: 3, straw: "#f3e7d4" },
  "sinh-to-bo": { vessel: "glass", liquid: ["#c4d97f", "#8fae45"], big: [["swirl"]], straw: "#5a9c45" },
  "nuoc-ngot": { vessel: "can" },
  "che-ba-mau": { vessel: "glass", liquid: ["#f3efe2", "#d9d1bd"], big: [["cream"]], layers: [["jelly", 6, 0, 360, 20, 60], ["bean", 9, 0, 360, 10, 56], ["mung", 6, 0, 360, 10, 50]] },
};

/** Món mới chưa có công thức: suy từ thuộc tính menu. */
function inferRecipe(e: Entry): Recipe {
  const has = (k: string) => e.contains.some((c) => c.includes(k));
  if (e.style === "uong") {
    const sweet = e.taste.ngot >= 2;
    return { vessel: "glass", liquid: sweet ? ["#f0b347", "#c47e1d"] : ["#d9a86c", "#a8743b", 0.8], ice: 4, straw: "#9e2b1d" };
  }
  if (e.style === "trang_mieng") {
    return { vessel: "glass", liquid: ["#f3efe2", "#d9d1bd"], big: [["cream"]], layers: [["bean", 6, 0, 360, 10, 50], ["jelly", 4, 0, 360, 20, 56]] };
  }
  const tops: Layer[] = [];
  if (has("bò")) tops.push(["beefCooked", 4, 170, 320, 18, 50]);
  if (has("gà")) tops.push(["chicken", 6, 160, 330, 16, 52]);
  if (has("tôm") || has("hải sản")) tops.push(["shrimp", 3, 20, 140, 26, 52]);
  if (has("mực")) tops.push(["squid", 3, 200, 300, 28, 54]);
  if (has("heo")) tops.push(["porkBelly", 3, 200, 320, 20, 48]);
  if (has("cua")) tops.push(["crab", 3, 180, 300, 20, 46]);
  if (has("đậu hũ")) tops.push(["tofu", 4, 20, 160, 30, 56]);
  if (has("nấm")) tops.push(["mushroom", 3, 120, 200, 34, 58]);
  if (has("trứng")) tops.push(["egg", 1, 150, 150, 40, 40]);
  if (e.style === "nuoc") {
    const spicy = e.taste.cay >= 2;
    return {
      vessel: "bowl",
      liquid: spicy ? ["#d8592c", "#9a2c13"] : ["#e3ad5f", "#ad6c2c"],
      layers: [["noodle", 5, 0, 360, 32, 66], ...(spicy ? ([["chiliOil", 12, 0, 360, 6, 70]] as Layer[]) : []), ...tops, ["scallion", 9, 0, 360, 10, 64], ["herb", 3, 40, 120, 30, 60]],
      steam: e.temp === "nong",
    };
  }
  if (e.style === "an_kem") {
    return { vessel: "small", big: [["rollFried", 104, 108, -24], ["rollFried", 136, 132, -24]], layers: [["herb", 3, 0, 360, 50, 70]] };
  }
  const isRice = e.category.includes("com") || e.name.toLowerCase().includes("cơm");
  return {
    vessel: "plate",
    big: isRice ? [["rice", 94, 104, 50, "white"]] : [["nest", 94, 100, 46]],
    layers: [...tops.map((l) => [l[0], l[1], -40, 80, 40, 80, l[6]] as Layer), ["cucumber", 2, 120, 170, 70, 86], ["herb", 3, 180, 240, 70, 86]],
  };
}

export function recipeFor(e: Entry): Recipe {
  return RECIPES[e.id] ?? inferRecipe(e);
}

// ------------------------------------------------------------------ vẽ 1 món
function Vessel({ v, id, children, liquid }: { v: Vessel; id: string; children: ReactNode; liquid?: [string, string, number?] }) {
  const shadow = <circle cx="126" cy="134" r="112" fill={`url(#${id}-sh)`} />;
  const defs = (
    <defs>
      <radialGradient id={`${id}-sh`} cx="50%" cy="50%" r="50%">
        <stop offset=".72" stopColor="#000" stopOpacity=".55" />
        <stop offset="1" stopColor="#000" stopOpacity="0" />
      </radialGradient>
      <radialGradient id={`${id}-pc`} cx="38%" cy="32%" r="72%">
        <stop offset="0" stopColor={C.porcelain[0]} />
        <stop offset=".6" stopColor={C.porcelain[1]} />
        <stop offset="1" stopColor={C.porcelain[2]} />
      </radialGradient>
      {liquid && (
        <radialGradient id={`${id}-lq`} cx="38%" cy="34%" r="70%">
          <stop offset="0" stopColor={liquid[0]} />
          <stop offset="1" stopColor={liquid[1]} />
        </radialGradient>
      )}
      <linearGradient id={`${id}-gl`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#fff" stopOpacity=".55" />
        <stop offset=".5" stopColor="#fff" stopOpacity=".05" />
        <stop offset="1" stopColor="#fff" stopOpacity="0" />
      </linearGradient>
      <radialGradient id={`${id}-can`} cx="35%" cy="30%" r="80%">
        <stop offset="0" stopColor="#f6f6f4" />
        <stop offset=".55" stopColor="#b9b9b6" />
        <stop offset="1" stopColor="#7d7d7a" />
      </radialGradient>
    </defs>
  );
  if (v === "bowl") {
    return (
      <>
        {defs}
        {shadow}
        <circle cx="120" cy="120" r="106" fill={`url(#${id}-pc)`} />
        <circle cx="120" cy="120" r="104" fill="none" stroke={C.cobalt} strokeWidth="2.6" />
        <circle cx="120" cy="120" r="97" fill="none" stroke={C.cobalt} strokeWidth="1.4" strokeDasharray="1.5 7" strokeLinecap="round" />
        <circle cx="120" cy="120" r="91" fill="#e7e0d1" />
        <circle cx="120" cy="120" r="86" fill={`url(#${id}-lq)`} />
        <g clipPath={`url(#${id}-clip)`}>{children}</g>
        <clipPath id={`${id}-clip`}>
          <circle cx="120" cy="120" r="86" />
        </clipPath>
        <ellipse cx="92" cy="80" rx="46" ry="17" transform="rotate(-28 92 80)" fill="#fff" opacity=".13" />
        <path d="M44,90A80,80 0 0 1 104,38" stroke="#fff" strokeWidth="4" fill="none" opacity=".55" strokeLinecap="round" />
      </>
    );
  }
  if (v === "plate" || v === "small") {
    const R = v === "plate" ? 112 : 94;
    return (
      <>
        {defs}
        <circle cx="126" cy="134" r={R} fill={`url(#${id}-sh)`} />
        <circle cx="120" cy="120" r={R} fill={`url(#${id}-pc)`} />
        <circle cx="120" cy="120" r={R - 4} fill="none" stroke={C.cobalt} strokeWidth="2.2" />
        <circle cx="120" cy="120" r={R - 13} fill="none" stroke={C.cobalt} strokeWidth="1" opacity=".6" />
        <circle cx="120" cy="120" r={R - 16} fill="#faf7f0" />
        {children}
        <path d={`M${120 - R + 14},104A${R - 14},${R - 14} 0 0 1 104,${120 - R + 14}`} stroke="#fff" strokeWidth="4" fill="none" opacity=".6" strokeLinecap="round" />
      </>
    );
  }
  if (v === "can") {
    return (
      <>
        {defs}
        {shadow}
        <circle cx="120" cy="120" r="84" fill={`url(#${id}-can)`} />
        <circle cx="120" cy="120" r="84" fill="none" stroke="#9e2b1d" strokeWidth="7" />
        <circle cx="120" cy="120" r="70" fill="none" stroke="#e9e9e6" strokeWidth="3" />
        <circle cx="120" cy="120" r="64" fill="none" stroke="#8e8e8a" strokeWidth="1.2" />
        <path d="M98,82C98,70 142,70 142,82L138,104C136,110 104,110 102,104Z" fill="#5f5f5c" />
        <rect x="104" y="118" width="32" height="40" rx="14" fill="#cfcfcc" stroke="#8e8e8a" strokeWidth="1.5" />
        <rect x="113" y="128" width="14" height="18" rx="6" fill="#8e8e8a" />
        <path d="M70,98A56,56 0 0 1 104,66" stroke="#fff" strokeWidth="4" fill="none" opacity=".7" strokeLinecap="round" />
      </>
    );
  }
  // glass: ly đặt trên đĩa lót sứ
  const op = liquid?.[2] ?? 1;
  return (
    <>
      {defs}
      <circle cx="126" cy="134" r="108" fill={`url(#${id}-sh)`} />
      <circle cx="120" cy="120" r="106" fill={`url(#${id}-pc)`} />
      <circle cx="120" cy="120" r="102" fill="none" stroke={C.cobalt} strokeWidth="2" />
      <circle cx="120" cy="120" r="95" fill="none" stroke={C.cobalt} strokeWidth="1" strokeDasharray="1.5 7" strokeLinecap="round" />
      <circle cx="123" cy="126" r="88" fill="#000" opacity=".22" />
      <circle cx="120" cy="120" r="86" fill="rgba(255,255,255,.18)" stroke="rgba(255,255,255,.65)" strokeWidth="2" />
      <circle cx="120" cy="120" r="78" fill={`url(#${id}-lq)`} opacity={op} />
      <g clipPath={`url(#${id}-clip)`}>{children}</g>
      <clipPath id={`${id}-clip`}>
        <circle cx="120" cy="120" r="78" />
      </clipPath>
      <circle cx="120" cy="120" r="82" fill="none" stroke={`url(#${id}-gl)`} strokeWidth="6" />
    </>
  );
}

function Steam() {
  return (
    <g className="steam" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <path key={i} className={`wisp w${i}`} d="M0,0C-9,-14 9,-26 0,-42C-9,-56 7,-66 0,-82"
          transform={`translate(${96 + i * 24} ${118 - (i % 2) * 10})`} />
      ))}
    </g>
  );
}

export interface DishArtProps {
  entry: Entry;
  steam?: boolean;
  className?: string;
  /** combo: id món con -> Entry để ghép hình */
  lookup?: (id: string) => Entry | undefined;
}

function Single({ entry, steam, uid }: { entry: Entry; steam: boolean; uid: string }) {
  const rec = recipeFor(entry);
  const r = mulberry(hash(entry.id));
  const layers = (rec.layers ?? []).flatMap(([k, n, a0, a1, r0, r1, sc], li) =>
    place(r, n, a0, a1, r0, r1).map(([x, y, rot], i) => {
      let px = x, py = y;
      if (k === "scallionOil") {
        const a = r() * Math.PI * 2, d = Math.sqrt(r()) * 40;
        px = 92 + Math.cos(a) * d; py = 104 + Math.sin(a) * d;
      }
      if (k === "patty" || k === "porkBelly" || k === "pickle" || (k === "chili" && rec.vessel === "plate" && entry.id === "bun-cha")) {
        px = 158 + (x - 120); py = 150 + (y - 120);
      }
      return (
        <g key={`${li}-${i}`} transform={`translate(${px.toFixed(1)} ${py.toFixed(1)}) rotate(${rot.toFixed(0)}) scale(${sc ?? 1})`}>
          {shape(k, r)}
        </g>
      );
    }),
  );
  const ice = Array.from({ length: rec.ice ?? 0 }, (_, i) => {
    const [x, y, rot] = place(r, 1, i * (360 / (rec.ice || 1)), i * (360 / (rec.ice || 1)) + 20, 14, 52)[0];
    return (
      <g key={`ice${i}`} className="ice" style={{ animationDelay: `${(i * 0.37) % 2}s` }} transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${rot.toFixed(0)})`}>
        {shape("ice", r)}
      </g>
    );
  });
  const bigs = (rec.big ?? []).map((b, i) => <g key={`b${i}`}>{big(b, r, uid)}</g>);
  return (
    <>
      <Vessel v={rec.vessel} id={uid} liquid={rec.liquid}>
        {bigs}
        {layers}
        {ice}
        {rec.straw && (
          <g>
            <circle cx="150" cy="86" r="8" fill={rec.straw} />
            <circle cx="150" cy="86" r="4.5" fill="#1b120d" opacity=".75" />
          </g>
        )}
      </Vessel>
      {steam && rec.steam && <Steam />}
    </>
  );
}

function DishArtImpl({ entry, steam = false, className, lookup }: DishArtProps) {
  const uid = "d" + useId().replace(/[^a-zA-Z0-9]/g, "");
  if (entry.image) {
    return (
      <div className={`dish-photo ${className ?? ""}`}>
        <img src={entry.image} alt={entry.name} loading="lazy" draggable={false} />
      </div>
    );
  }
  if (entry.kind === "combo" && entry.items && lookup) {
    const parts = entry.items.map((p) => lookup(p.id)).filter(Boolean) as Entry[];
    const mains = parts.filter((p) => p.style !== "uong");
    const drinks = parts.filter((p) => p.style === "uong");
    const pick = [...mains.slice(0, 2), ...drinks.slice(0, 1)];
    const pos = pick.length === 1 ? [[0, 0, 1]] : pick.length === 2 ? [[-8, -8, 0.8], [62, 62, 0.46]] : [[-14, -14, 0.7], [70, 18, 0.5], [40, 84, 0.44]];
    return (
      <svg className={`dish-art ${className ?? ""}`} viewBox="0 0 240 240" role="img" aria-label={entry.name}>
        {pick.map((p, i) => (
          <g key={p.id} transform={`translate(${pos[i][0] + (240 - 240 * pos[i][2]) / 2} ${pos[i][1] + (240 - 240 * pos[i][2]) / 2}) scale(${pos[i][2]})`}>
            <Single entry={p} steam={steam && i === 0} uid={`${uid}c${i}`} />
          </g>
        ))}
      </svg>
    );
  }
  return (
    <svg className={`dish-art ${className ?? ""}`} viewBox="0 0 240 240" role="img" aria-label={entry.name}>
      <Single entry={entry} steam={steam} uid={uid} />
    </svg>
  );
}

export const DishArt = memo(DishArtImpl);
