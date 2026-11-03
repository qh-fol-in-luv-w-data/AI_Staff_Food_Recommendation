export type Taste = { cay: number; ngot: number; chua: number; dam: number; beo: number };

export interface Option {
  id: string;
  name: string;
  price_delta: number;
  aliases?: string[];
}

export interface Entry {
  id: string;
  name: string;
  price: number;
  kind: "item" | "combo";
  category: string;
  description: string;
  unit: string;
  best_seller: boolean;
  vegetarian: boolean;
  spicy: number;
  taste: Taste;
  style: string;
  temp: string;
  portion: string;
  contains: string[];
  pairs_with: string[];
  image: string;
  options: Option[];
  promos: string[];
  serves?: number;
  value?: number;
  items?: { id: string; name: string; qty: number }[];
}

export interface Promo {
  id: string;
  name: string;
  pitch: string;
  type: string;
  reward: string;
  min_subtotal: number;
}

export interface Config {
  store: {
    id: string;
    name: string;
    short_name: string;
    address: string;
    phone: string;
    assistant: string;
    allow_cash: boolean;
    customer_pronoun: string;
    qr_expire_minutes: number;
  };
  categories: { id: string; name: string }[];
  entries: Entry[];
  promotions: Promo[];
  speech: boolean;
  conversation?: { engine: "llm" | "rules"; brain: string; barge_in: boolean; partial_asr: boolean };
}

export interface CartLine {
  entry_id: string;
  name: string;
  display_name: string;
  kind: string;
  unit_price: number;
  qty: number;
  unit: string;
  option_id: string | null;
  option_name: string | null;
  note: string;
  total: number;
}

export interface Cart {
  lines: CartLine[];
  count: number;
  subtotal: number;
  discount: number;
  vat: number;
  total: number;
  applied: { id: string; name: string; discount: number; free_items: FreeItem[] }[];
  free_items: FreeItem[];
  hints: { id: string; name: string; message: string; missing_amount: number }[];
}

export interface FreeItem {
  entry_id: string;
  name: string;
  qty: number;
  value: number;
}

export interface Rec {
  entry_id: string;
  name: string;
  kind: string;
  price: number;
  score: number;
  reasons: string[];
  promos: string[];
  description: string;
}

export interface QR {
  payload: string;
  svg: string;
  amount: number;
  code: string;
  bank_name: string;
  bank_bin: string;
  account_number: string;
  account_name: string;
  expires_at: string | null;
}

export interface Reply {
  type: "reply";
  id: string;
  text: string;
  speech: string;
  state: string;
  intent: string;
  cart: Cart | null;
  recommendations: Rec[];
  options: { entry_id: string; name: string; price: number }[];
  suggestions: string[];
  qr: QR | null;
  order: { code: string; total: number; method?: string; status?: string; expires_at?: string | null } | null;
  end: boolean;
  latency_ms: number;
}

export type ServerMsg =
  | Reply
  | { type: "session"; session_id: string; state: string; speech: boolean }
  | { type: "tts"; reply_id: string; seq: number; url: string; synth_ms: number; turn?: number; filler?: boolean }
  | { type: "asr"; text: string; latency_ms: number }
  | { type: "asr_partial"; text: string }
  | { type: "vad"; speaking: boolean }
  | { type: "listening"; on: boolean }
  // ---- hội thoại thời gian thực (LLM): chữ chảy ra theo từng mẩu, công cụ cập nhật màn hình
  | { type: "assistant_start"; turn: number; replace?: boolean }
  | { type: "assistant_delta"; turn: number; text: string }
  | { type: "assistant_end"; turn: number; text: string; state: string; cart: Cart; tools?: string[]; error?: string }
  | { type: "cart"; cart: Cart; state?: string }
  | { type: "recs"; items: Rec[] }
  | { type: "show_dish"; id: string }
  | { type: "state"; state: string; qr?: QR | null; order?: Reply["order"] }
  | { type: "stop_audio"; turn: number | null }
  | { type: "pong" };

export type Action =
  | { type: "add"; entry_id: string; qty?: number; option_id?: string | null; note?: string }
  | { type: "remove"; entry_id: string; qty?: number }
  | { type: "set_qty"; entry_id: string; qty: number }
  | { type: "checkout" }
  | { type: "confirm"; method: "vietqr" | "cash" }
  | { type: "cancel" }
  | { type: "edit" }
  | { type: "recommend" }
  | { type: "reset" };

export const EMPTY_CART: Cart = {
  lines: [],
  count: 0,
  subtotal: 0,
  discount: 0,
  vat: 0,
  total: 0,
  applied: [],
  free_items: [],
  hints: [],
};
