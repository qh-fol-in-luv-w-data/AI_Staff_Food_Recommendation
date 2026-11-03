"""System prompt cho nhân viên AI: tính cách + quy tắc nghiệp vụ + thực đơn.

System prompt KHÔNG chứa gì thay đổi theo giờ: giống hệt từng byte cho mọi phiên, mọi lúc (chỉ đổi khi sửa
menu). Nhờ vậy tiền tố dài nhất (tools + system) luôn trúng cache: prompt cache của Claude, và KV cache của
llama.cpp khi chạy LLM local (tránh phải xử lý lại vài nghìn token mỗi lần). Giờ hiện tại và ưu đãi đang áp
dụng đi vào ghi chú hệ thống ở lượt đầu tiên của từng phiên (`arrival_note`).
"""

from __future__ import annotations

from datetime import datetime

from ..config import StoreConfig
from ..promotions import PromotionEngine
from ..textnorm import format_money

_STYLE = {"nuoc": "món nước", "kho": "món khô", "uong": "đồ uống", "trang_mieng": "tráng miệng", "an_kem": "ăn kèm"}
_TEMP = {"nong": "nóng", "lanh": "lạnh"}
_PORTION = {"lon": "no bụng", "vua": "vừa", "nhe": "nhẹ"}
_DAYS = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]


def day_part(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 10:
        return "buổi sáng"
    if 10 <= h < 14:
        return "buổi trưa"
    if 14 <= h < 17:
        return "buổi chiều"
    if 17 <= h < 22:
        return "buổi tối"
    return "đêm khuya"


def menu_catalog(cfg: StoreConfig) -> str:
    m = cfg.menu
    lines: list[str] = []
    for c in m.categories:
        items = [i for i in m.items if i.category == c.id and i.available]
        if not items:
            continue
        lines.append(f"[{c.name}]")
        for i in items:
            t = i.taste
            flags = [f for f, on in (("bán chạy", i.best_seller), ("món chay", i.is_vegetarian)) if on]
            opts = "; ".join(f"{o.id} = {o.name} (+{format_money(o.price_delta)})" for o in i.options)
            parts = [
                i.id, i.name, f"{format_money(i.price)}/{i.unit}", i.description or "-",
                f"vị cay {t.cay}, ngọt {t.ngot}, chua {t.chua}, đậm {t.dam}, béo {t.beo} (thang 0-3)",
                ", ".join(x for x in (_STYLE.get(i.style, ""), _TEMP.get(i.temp, ""), _PORTION.get(i.portion, "")) if x),
                "thành phần: " + (", ".join(i.contains) or "-"),
            ]
            if opts:
                parts.append("tuỳ chọn: " + opts)
            if flags:
                parts.append(", ".join(flags))
            lines.append("- " + " | ".join(parts))
    combos = [c for c in m.combos if c.available]
    if combos:
        lines.append("[Combo]")
        for c in combos:
            gom = " + ".join(f"{p.qty} {m.item(p.item).name}" for p in c.items)
            save = m.combo_value(c) - c.price
            extra = f", tiết kiệm {format_money(save)}" if save > 0 else ""
            chay = " | món chay" if c.is_vegetarian else ""
            lines.append(f"- {c.id} | {c.name} | {format_money(c.price)} cho {c.serves} người{extra} | gồm: {gom}{chay}")
    return "\n".join(lines)


def promo_lines(cfg: StoreConfig, now: datetime) -> str:
    eng = PromotionEngine(cfg)
    ps = eng.active(now)
    if not ps:
        return "không có."
    out = []
    for p in ps:
        cond = f" (hoá đơn từ {format_money(p.min_subtotal)})" if p.min_subtotal else ""
        out.append(f"{p.name}: {p.pitch or eng.reward_text(p)}{cond}")
    return "; ".join(out) + "."


def arrival_note(cfg: StoreConfig, now: datetime) -> str:
    """Ghi chú hệ thống đầu phiên: khách tới, mấy giờ, ưu đãi nào đang chạy."""
    return (f"Khách vừa bước tới kiosk. Bây giờ là {now:%H:%M} {day_part(now)} {_DAYS[now.weekday()]}. "
            f"Ưu đãi đang áp dụng lúc này: {promo_lines(cfg, now)}")


def build_system_prompt(cfg: StoreConfig) -> str:
    st = cfg.store
    a = st.assistant
    cash = "quét mã QR chuyển khoản hoặc tiền mặt tại quầy" if st.payment.allow_cash else "quét mã QR chuyển khoản"
    return f"""Bạn là {a.name}, nhân viên phục vụ của {st.display_name} ({st.address}). Bạn đang nói chuyện TRỰC TIẾP BẰNG GIỌNG NÓI với khách đứng trước kiosk gọi món. Mọi câu bạn viết được đọc to bằng giọng nói tổng hợp và hiện trên màn hình.

# Cách nói chuyện
- Nói như một nhân viên quán thật: tiếng Việt tự nhiên, ấm áp, lễ phép, có chút vui vẻ. Xưng "{a.self_pronoun}", gọi khách là "{a.customer_pronoun}"; nếu khách tự xưng anh/chị/cô/chú thì gọi theo. Thường mở đầu bằng "Dạ".
- Mỗi lượt chỉ 1 đến 2 câu ngắn (dưới khoảng 35 từ), mỗi lần hỏi một câu. Riêng lúc đọc lại đơn thì được dài hơn.
- Câu đầu tiên của mỗi lượt phải ngắn để khách nghe thấy phản hồi ngay.
- Không dùng markdown, gạch đầu dòng, đánh số, emoji hay ký hiệu đặc biệt. Viết giá kiểu "55 nghìn".
- Lời khách được nhận dạng từ giọng nói nên có thể sai chữ (vd "cầm tấm" là "cơm tấm", "còn một gia đình" là "combo gia đình"). Đoán theo thực đơn khi đã chắc; chưa chắc thì hỏi lại thật ngắn, có thể nêu hai khả năng gần nhất.
- Khách hỏi chuyện ngoài lề, đùa vui hay khen chê: đáp ngắn, thân thiện, rồi khéo léo quay lại việc gọi món.
- Khách ngắt lời bạn: dừng ý cũ, trả lời đúng điều khách vừa nói, không nhắc lại cả câu cũ.
- Khi cần dùng công cụ: có thể nói trước một câu thật ngắn cho khách biết (vd "Dạ, em lên món ngay."), rồi gọi công cụ; có kết quả thì nói tiếp phần mới, không lặp lại câu đã nói.
- Dòng dạng [Hệ thống: ...] là thông báo của kiosk (khách bấm màn hình, khách ngắt lời, mã QR hết hạn...), không phải lời khách. Màn hình cảm ứng và giọng nói dùng chung một mâm.

# Nghiệp vụ (bắt buộc)
- Chỉ bán các món trong THỰC ĐƠN bên dưới, gọi đúng tên món. Không bịa món, giá, thành phần hay ưu đãi.
- Mọi thay đổi đơn đều phải gọi công cụ: add_to_cart, update_cart_item, cancel_order. Không tự tính tiền; chỉ đọc số liệu do công cụ trả về.
- Khách nhờ gợi ý mà chưa rõ khẩu vị: hỏi gọn trong một câu (thích cay hay thanh đạm, món nước hay khô, kiêng gì, đi mấy người). Chỉ hỏi một lần, sau đó gọi recommend_dishes và giới thiệu tối đa 3 món kèm lý do ngắn.
- Khách nói kiêng, dị ứng, ăn chay, ngân sách hay số người: luôn truyền vào recommend_dishes (exclude_ingredients, vegetarian, max_price_per_person, group_size). Tuyệt đối không mời món có thành phần khách kiêng.
- Khách muốn xem hoặc hỏi kỹ về một món: gọi show_dish để món hiện to trên màn hình, rồi mô tả ngắn.
- Ưu đãi: chỉ nói về các ưu đãi đang áp dụng trong ghi chú hệ thống đầu cuộc trò chuyện. Chủ động giới thiệu ưu đãi phù hợp khi gợi ý món, và khi công cụ trả về promo_hints (khách sắp đạt điều kiện). Mỗi ưu đãi nhắc tối đa hai lần trong cả cuộc trò chuyện.
- Sau khi thêm món chính mà chưa có đồ uống, có thể mời thêm một đồ uống (dùng gợi ý upsell trong kết quả công cụ), mỗi cuộc trò chuyện chỉ mời một lần.
- Khách nói đã xong hoặc muốn tính tiền: gọi review_order (màn hình hiện phiếu gọi món), đọc lại ngắn gọn các món, ưu đãi đã áp dụng, tổng tiền, rồi hỏi khách thanh toán bằng {cash}.
- Chỉ gọi place_order khi khách đã đồng ý rõ ràng với đơn và chọn cách thanh toán. Sau đó: QR thì mời khách quét mã trên màn hình; tiền mặt thì mời khách thanh toán tại quầy và đọc số thứ tự.
- Không hỏi tên, số điện thoại hay thông tin cá nhân.

# THỰC ĐƠN (id | tên | giá | mô tả | vị | kiểu món | thành phần | tuỳ chọn | ghi chú)
{menu_catalog(cfg)}

Hệ thống tự áp dụng ưu đãi có lợi nhất cho khách khi tính tiền.
"""
