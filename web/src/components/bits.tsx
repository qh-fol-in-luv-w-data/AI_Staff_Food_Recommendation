import { animate } from "motion/react";
import { useEffect, useRef } from "react";
import { money } from "../lib/format";

export const Icon = {
  mic: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M12 15a3.2 3.2 0 0 0 3.2-3.2V5.4a3.2 3.2 0 1 0-6.4 0v6.4A3.2 3.2 0 0 0 12 15Zm5.6-3.2a5.6 5.6 0 0 1-11.2 0H4.6a7.4 7.4 0 0 0 6.5 7.3V22h1.8v-2.9a7.4 7.4 0 0 0 6.5-7.3h-1.8Z" />
    </svg>
  ),
  send: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M3.4 20.4 21 12 3.4 3.6 3.3 10l12.6 2-12.6 2z" />
    </svg>
  ),
  plus: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" fill="none" />
    </svg>
  ),
  minus: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" fill="none" />
    </svg>
  ),
  close: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" fill="none" />
    </svg>
  ),
  chili: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M17.6 4.2c-.7.6-1 1.5-.8 2.4-2.8.2-4.6 2.3-5.6 5-1.2 3.3-3.4 5.4-7.6 6.6.9 1.6 3 2.6 5.6 2.2 5.2-.8 9.4-5.6 9.6-11 .7-.4 1.2-1.1 1.2-2l-1.7-.1c0 .4-.2.7-.5.9a2.6 2.6 0 0 0-1.5-1.6c.1-.5.4-.9.8-1.1z" />
    </svg>
  ),
  leaf: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M20 4c-9 0-15 4.5-15 11 0 1.6.4 3 1 4.1L4.3 21l1.3 1.3 1.8-1.8c1.1.7 2.5 1 4 1C17.6 21.5 20 14 20 4zm-8.6 15.4c-1 0-2-.2-2.8-.6l6-6-1.3-1.3-6 6c-.4-.8-.6-1.7-.6-2.7 0-4.8 4.5-8.4 11.4-8.7-.4 7.7-2.6 13.3-6.7 13.3z" />
    </svg>
  ),
  star: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="m12 3 2.5 5.6 6.1.6-4.6 4.1 1.3 6L12 16.2 6.7 19.3l1.3-6L3.4 9.2l6.1-.6z" />
    </svg>
  ),
  gift: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M20 7h-2.2A3 3 0 0 0 12 4.4 3 3 0 0 0 6.2 7H4a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1Zm-5-1.2a1.2 1.2 0 1 1 0 2.4h-2v-1a1.4 1.4 0 0 1 2-1.4ZM9 5.8a1.2 1.2 0 0 1 2 1.4v1H9a1.2 1.2 0 0 1 0-2.4ZM5 9h6v1.4H5Zm1 3h5v6H6Zm12 6h-5v-6h5Zm1-7.6h-6V9h6Z" />
    </svg>
  ),
  qr: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M3 3h8v8H3zm2 2v4h4V5zm8-2h8v8h-8zm2 2v4h4V5zM3 13h8v8H3zm2 2v4h4v-4zm9-2h2v2h-2zm2 2h2v2h-2zm2-2h3v2h-3zm-4 4h2v4h-2zm4 0h3v4h-2v-2h-1zm-2 2h2v2h-2z" />
    </svg>
  ),
  cash: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="currentColor" d="M2 6h20v12H2zm2 2v8h16V8zm8 1.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM5 9h2v2H5zm12 4h2v2h-2z" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12.5 10 17l9-10" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  ),
};

/** Số tiền chạy lên/xuống mượt khi tổng đơn thay đổi. */
export function AnimatedMoney({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(value);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const from = prev.current;
    prev.current = value;
    if (from === value) {
      el.textContent = money(value);
      return;
    }
    const c = animate(from, value, {
      duration: 0.7,
      ease: [0.2, 0.8, 0.2, 1],
      onUpdate: (v) => {
        el.textContent = money(Math.round(v / 100) * 100);
      },
    });
    return () => c.stop();
  }, [value]);
  return (
    <span ref={ref} className={className}>
      {money(value)}
    </span>
  );
}

/** Ghi mức âm lượng vào biến CSS --lvl (không re-render React 60 lần/giây). */
export function useLevelVar(ref: React.RefObject<HTMLElement | null>, get: () => number, active: boolean) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!active) {
      el.style.setProperty("--lvl", "0");
      return;
    }
    let raf = 0;
    let smooth = 0;
    const tick = () => {
      smooth = smooth * 0.7 + get() * 0.3;
      el.style.setProperty("--lvl", smooth.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ref, get, active]);
}
