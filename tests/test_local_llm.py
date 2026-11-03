"""Engine LLM local (API tương thích OpenAI: llama.cpp / Ollama / vLLM).

Đây là test giao thức (định dạng request, đọc stream, gọi công cụ) trên HTTP giả lập - KHÔNG phải kết quả
chạy model thật. Chất lượng hội thoại với model thật cần đo trên máy có model (xem scripts/run_local_llm.sh).
"""

import asyncio
import json

import httpx
import pytest

from aistaff.agent import ConversationAgent, ProviderError
from aistaff.agent.local import LocalProvider, ThinkFilter, openai_messages, openai_tools
from aistaff.config import Conversation, LocalLLM

from .conftest import TUE_HAPPY


def sse(chunks):
    return ("".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()


def chunk(delta=None, finish=None, usage=None):
    c = {"id": "x", "object": "chat.completion.chunk", "model": "qwen-test", "choices": []}
    if delta is not None or finish:
        c["choices"] = [{"index": 0, "delta": delta or {}, "finish_reason": finish}]
    if usage:
        c["usage"] = usage
    return c


def tool_turn():
    return sse([
        chunk({"role": "assistant", "content": "Dạ, em lên "}),
        chunk({"content": "món ngay."}),
        chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                "function": {"name": "add_to_cart", "arguments": ""}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": "{\"item_id\": \"pho-ga\","}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": " \"quantity\": 2}"}}]}),
        chunk(finish="tool_calls"),
        chunk(usage={"prompt_tokens": 4200, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 4100}}),
    ])


def text_turn(text):
    return sse([chunk({"content": text[:5]}), chunk({"content": text[5:]}), chunk(finish="stop")])


def provider(handler, **local):
    conv = Conversation(provider="local", local=LocalLLM(**local))
    return LocalProvider(conv, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_message_and_tool_conversion():
    tools = [{"name": "show_dish", "description": "d", "input_schema": {"type": "object", "properties": {}}, "eager_input_streaming": True}]
    assert openai_tools(tools) == [{"type": "function", "function": {"name": "show_dish", "description": "d",
                                                                     "parameters": {"type": "object", "properties": {}}}}]
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "[Hệ thống: Khách vừa tới.]"}, {"type": "text", "text": "phở gà"}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                          {"type": "text", "text": "Dạ."},
                                          {"type": "tool_use", "id": "c1", "name": "show_dish", "input": {"item_id": "pho-ga"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{\"ok\": 1}"},
                                     {"type": "text", "text": "thôi lấy bún"}]},
    ]
    out = openai_messages("SYS", msgs)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool", "user"]
    assert out[1]["content"] == "[Hệ thống: Khách vừa tới.]\nphở gà"
    assert out[2]["content"] == "Dạ." and out[2]["tool_calls"][0]["function"] == {
        "name": "show_dish", "arguments": "{\"item_id\": \"pho-ga\"}"}
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"ok\": 1}"}


@pytest.mark.parametrize("pieces,expected", [
    (["Dạ <think>khách muốn phở</think>em lên món."], "Dạ em lên món."),
    (["<thi", "nk>abc</th", "ink>Dạ vâng"], "Dạ vâng"),
    (["Giá 5 < 6 nghìn", " ạ"], "Giá 5 < 6 nghìn ạ"),
    (["<think>chưa đóng thẻ"], ""),
])
def test_think_filter(pieces, expected):
    f = ThinkFilter()
    assert "".join(f.feed(p) for p in pieces) + f.flush() == expected


def test_stream_with_tool_calls():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=tool_turn())

    p = provider(handler, base_url="http://127.0.0.1:8080/v1/", model="qwen3-4b",
                 extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    deltas = []

    async def on_text(d):
        deltas.append(d)

    res = asyncio.run(p.step("SYS", [{"name": "add_to_cart", "description": "", "input_schema": {"type": "object"}}],
                             [{"role": "user", "content": [{"type": "text", "text": "2 phở gà"}]}], on_text,
                             tool_choice={"type": "none"}))
    b = seen["body"]
    assert seen["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert b["model"] == "qwen3-4b" and b["stream"] is True and b["tool_choice"] == "none"
    assert b["chat_template_kwargs"] == {"enable_thinking": False} and b["messages"][0] == {"role": "system", "content": "SYS"}
    assert "".join(deltas) == "Dạ, em lên món ngay."
    assert res.stop_reason == "tool_use" and res.usage["cache_read_input_tokens"] == 4100
    assert res.content == [{"type": "text", "text": "Dạ, em lên món ngay."},
                           {"type": "tool_use", "id": "call_1", "name": "add_to_cart",
                            "input": {"item_id": "pho-ga", "quantity": 2}}]


def test_agent_full_turn_over_local_protocol(make_dm):
    """Agent + công cụ thật + định dạng OpenAI: lượt 1 gọi add_to_cart, lượt 2 nói kết quả."""
    bodies = []
    replies = [tool_turn(), text_turn("Dạ, em thêm 2 tô phở gà rồi ạ.")]

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=replies.pop(0))

    dm = make_dm(TUE_HAPPY)
    ag = ConversationAgent(dm.cfg, dm, dm.new_session(), provider(handler))
    out = []

    async def on_text(d):
        out.append(d)

    async def on_event(e):
        pass

    res = asyncio.run(ag.turn("cho 2 phở gà", on_text, on_event))
    assert ag.s.cart.qty_of("pho-ga") == 2 and res.tools == ["add_to_cart"]
    second = bodies[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assert json.loads(second[3]["content"])["cart"]["items"] == ["2 tô Phở gà: 100.000đ"]
    assert bodies[0]["messages"][0] == bodies[1]["messages"][0] and bodies[0]["tools"] == bodies[1]["tools"]


def test_bad_tool_json_becomes_tool_error(make_dm):
    body = sse([chunk({"tool_calls": [{"index": 0, "id": "c9", "function": {"name": "add_to_cart",
                                                                              "arguments": "{\"item_id\": \"pho"}}]}),
                chunk(finish="tool_calls")])
    replies = [body, text_turn("Dạ, anh muốn món nào ạ?")]

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=replies.pop(0))

    dm = make_dm(TUE_HAPPY)
    ag = ConversationAgent(dm.cfg, dm, dm.new_session(), provider(handler))

    async def noop(_):
        pass

    asyncio.run(ag.turn("phở", noop, noop))
    tr = ag.messages[-2]["content"][0]
    assert tr["is_error"] and "INVALID_JSON" in tr["content"] and ag.s.cart.is_empty


@pytest.mark.parametrize("status,kind", [(503, "overloaded"), (400, "bad_request"), (500, "server"), (401, "auth")])
def test_status_errors(status, kind):
    p = provider(lambda r: httpx.Response(status, text="model loading"))

    async def noop(_):
        pass

    with pytest.raises(ProviderError) as ei:
        asyncio.run(p.step("S", [], [{"role": "user", "content": "hi"}], noop))
    assert ei.value.kind == kind


def test_server_not_running():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    async def noop(_):
        pass

    with pytest.raises(ProviderError) as ei:
        asyncio.run(provider(handler).step("S", [], [{"role": "user", "content": "hi"}], noop))
    assert ei.value.kind == "network"
    with pytest.raises(ProviderError):
        asyncio.run(provider(handler).prewarm("S", []))


def test_make_provider_auto(monkeypatch, cfg):
    from aistaff.kiosk.server import make_provider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert type(make_provider(cfg)).__name__ == "LocalProvider"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert type(make_provider(cfg)).__name__ == "AnthropicProvider"
    rules = cfg.model_copy(deep=True)
    rules.store.conversation.engine = "rules"
    assert make_provider(rules) is None
