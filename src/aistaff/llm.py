"""LLM dự phòng (TUỲ CHỌN) - chỉ gọi khi NLU luật không hiểu câu nói (intent = unknown).

Thiết kế "LLM chuẩn hoá câu, không phải LLM thu ngân":
  câu khách lộn xộn --LLM--> 1 câu lệnh chuẩn ("cho 2 phở bò tái", "gợi ý món cay", "chốt đơn")
  --> đưa lại NLU luật để parse. Giá, món, ưu đãi vẫn do code tất định xử lý => LLM không thể bịa giá.
Dùng được mọi máy chủ tương thích OpenAI Chat Completions: llama.cpp server, Ollama, vLLM, LM Studio
(chạy local trên thiết bị mạnh như Jetson/RK3588) hoặc dịch vụ đám mây (khi có Internet).
"""

from __future__ import annotations

import os

import httpx

from .config import LLMFallback, Menu

SYSTEM = (
    "Bạn là bộ chuẩn hoá câu gọi món cho quán ăn Việt Nam. Viết lại câu của khách thành MỘT câu lệnh ngắn "
    "tiếng Việt có dấu theo một trong các mẫu: 'cho <số> <tên món>' (nhiều món nối bằng 'và'), 'bỏ <tên món>', "
    "'gợi ý món <khẩu vị/kiêng cữ/số người>', 'chốt đơn', 'có khuyến mãi gì', 'xem thực đơn', 'trả tiền mặt', "
    "'huỷ đơn', 'đúng rồi', 'không'. Chỉ dùng tên món có trong danh sách. Nếu không liên quan gọi món, trả lời "
    "'không hiểu'. Chỉ in ra câu lệnh, không giải thích."
)


class LLMRewriter:
    def __init__(self, cfg: LLMFallback):
        self.cfg = cfg
        self.client = httpx.Client(timeout=cfg.timeout_seconds)

    def rewrite(self, text: str, menu: Menu) -> str | None:
        names = ", ".join(e.name for e in menu.entries())
        headers = {}
        key = os.environ.get(self.cfg.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {
            "model": self.cfg.model,
            "temperature": 0,
            "max_tokens": 48,
            "messages": [
                {"role": "system", "content": SYSTEM + " Danh sách món: " + names},
                {"role": "user", "content": text},
            ],
        }
        r = self.client.post(self.cfg.base_url.rstrip("/") + "/chat/completions", json=body, headers=headers)
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"].strip().strip('"').strip()
        if not out or "không hiểu" in out.lower():
            return None
        return out.splitlines()[0][:200]
