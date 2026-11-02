import { useRef } from "react";
import { useKiosk } from "../store";
import { useLevelVar } from "./bits";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

/** Quả cầu sơn mài của Mai: lá vàng trôi bên trong, phản ứng theo trạng thái và âm lượng. */
export function Orb({ state, size = 104 }: { state: OrbState; size?: number }) {
  const { level } = useKiosk();
  const ref = useRef<HTMLDivElement>(null);
  useLevelVar(ref, level, state === "listening" || state === "speaking");
  const flakes = [
    [30, 6, 0], [24, 9, 40], [36, 7, 95], [18, 6, 150], [34, 8, 200], [26, 7, 250], [14, 5, 300], [38, 6, 330],
  ];
  return (
    <div ref={ref} className="orb" data-state={state} style={{ width: size, height: size }} aria-hidden="true">
      <svg viewBox="0 0 120 120">
        <defs>
          <radialGradient id="orb-glow" cx="50%" cy="50%" r="50%">
            <stop offset=".55" stopColor="#d9ad55" stopOpacity=".55" />
            <stop offset="1" stopColor="#d9ad55" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="orb-body" cx="38%" cy="30%" r="75%">
            <stop offset="0" stopColor="#4a2414" />
            <stop offset=".55" stopColor="#24130b" />
            <stop offset="1" stopColor="#0f0805" />
          </radialGradient>
          <linearGradient id="orb-rim" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#f3d58f" />
            <stop offset=".5" stopColor="#9c7428" />
            <stop offset="1" stopColor="#e2bb6a" />
          </linearGradient>
          <linearGradient id="orb-leaf" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#f6dc9a" />
            <stop offset="1" stopColor="#b98a35" />
          </linearGradient>
        </defs>
        <circle className="orb-glow" cx="60" cy="60" r="60" fill="url(#orb-glow)" />
        <circle className="orb-ring r1" cx="60" cy="60" r="50" />
        <circle className="orb-ring r2" cx="60" cy="60" r="50" />
        <circle cx="60" cy="60" r="44" fill="url(#orb-body)" />
        <g className="orb-flakes">
          {flakes.map(([d, s, a], i) => (
            <g key={i} className={`flake f${i % 4}`} style={{ transform: `rotate(${a}deg)` }}>
              <path d={`M${60 + d},${60 - s / 2}l${s},${s * 0.3}l-${s * 0.4},${s * 0.8}l-${s * 0.7},-${s * 0.3}z`} fill="url(#orb-leaf)" />
            </g>
          ))}
        </g>
        <path d="M30,44A34,34 0 0 1 58,24" stroke="#fff" strokeOpacity=".28" strokeWidth="3" fill="none" strokeLinecap="round" />
        <circle cx="60" cy="60" r="44" fill="none" stroke="url(#orb-rim)" strokeWidth="2.2" />
      </svg>
    </div>
  );
}

export function useOrbState(): OrbState {
  const { speaking, listening, thinking } = useKiosk();
  if (speaking) return "speaking";
  if (thinking) return "thinking";
  if (listening) return "listening";
  return "idle";
}
