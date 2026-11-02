export const money = (n: number) => `${Math.round(n || 0).toLocaleString("vi-VN").replace(/,/g, ".")}đ`;

export const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export function orderNumber(code?: string | null) {
  if (!code) return "";
  return String(parseInt(code.slice(-6), 10));
}

/** Gợi ý ghi chú nhanh theo kiểu món (khách chạm thay vì nói). */
export function noteChips(style: string): string[] {
  if (style === "uong") return ["Ít đá", "Không đá", "Ít đường"];
  if (style === "trang_mieng") return ["Ít ngọt", "Thêm đá"];
  if (style === "nuoc") return ["Không hành", "Ít bánh", "Nhiều rau", "Thêm ớt"];
  return ["Không hành", "Ít cay", "Thêm nước mắm"];
}

export const TASTE_LABEL: Record<string, string> = {
  cay: "Cay",
  ngot: "Ngọt",
  chua: "Chua",
  dam: "Đậm đà",
  beo: "Béo",
};

export const reduceMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export const liteMode = () => typeof location !== "undefined" && new URLSearchParams(location.search).has("lite");
