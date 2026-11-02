/* Kiosk UI - JS thuần, không thư viện, chạy offline. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const money = (n) => (n || 0).toLocaleString("vi-VN").replace(/,/g, ".") + "đ";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* chế độ ẩn danh */ } },
  };

  let ws = null, cfg = null, sessionId = store.get("aistaff.session"), state = "idle";
  let currentTab = null, lastRecs = [], expiresAt = null, doneTimer = null;

  // ------------------------------------------------------------------ cấu hình + thực đơn
  async function loadConfig() {
    cfg = await (await fetch("/api/config")).json();
    $("storeName").textContent = cfg.store.name;
    $("assistantName").textContent = `Nhân viên AI: ${cfg.store.assistant}`;
    $("welcomeTitle").textContent = `Chào mừng đến ${cfg.store.short_name}!`;
    $("promoTicker").textContent = cfg.promotions.map((p) => "🎁 " + p.name).join("   •   ");
    $("welcomePromos").innerHTML = cfg.promotions.slice(0, 3).map((p) => `<div>🎁 ${esc(p.name)}</div>`).join("");
    $("btnCash").classList.toggle("hidden", !cfg.store.allow_cash);
    if (!cfg.speech) { $("btnMic").classList.add("hidden"); }
    renderTabs();
  }

  function renderTabs() {
    const cats = cfg.categories.filter((c) => cfg.entries.some((e) => (c.id === "combo" ? e.kind === "combo" : e.category === c.id && e.kind === "item")));
    currentTab = currentTab || (cats[0] && cats[0].id);
    $("tabs").innerHTML = cats.map((c) => `<button data-tab="${c.id}" class="${c.id === currentTab ? "active" : ""}">${esc(c.name)}</button>`).join("");
    renderGrid();
  }

  function renderGrid() {
    const list = cfg.entries.filter((e) => (currentTab === "combo" ? e.kind === "combo" : e.category === currentTab && e.kind === "item"));
    $("grid").innerHTML = list.map((e) => {
      const tags = [];
      if (e.best_seller) tags.push('<span class="tag">Bán chạy</span>');
      if (e.vegetarian) tags.push('<span class="tag">Chay</span>');
      if (e.spicy >= 2) tags.push('<span class="tag hot">Cay</span>');
      if (e.serves) tags.push(`<span class="tag">${e.serves} người</span>`);
      (e.promos || []).forEach((p) => tags.push(`<span class="tag promo">${esc(p)}</span>`));
      return `<div class="card ${lastRecs.includes(e.id) ? "hl" : ""}" data-id="${e.id}">
        <h3>${esc(e.name)}</h3><div class="tags">${tags.join("")}</div>
        <p>${esc(e.description || "")}</p>
        <div class="price">${money(e.price)}</div>
        <button data-add="${e.id}">+ Thêm</button></div>`;
    }).join("");
  }

  // ------------------------------------------------------------------ WebSocket
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws${sessionId ? "?session=" + sessionId : ""}`);
    ws.binaryType = "arraybuffer";
    ws.onmessage = (ev) => onMessage(JSON.parse(ev.data));
    ws.onclose = () => { $("status").textContent = "Mất kết nối, đang thử lại…"; setTimeout(connect, 1500); };
    ws.onopen = () => { $("status").textContent = ""; };
  }
  const send = (obj) => ws && ws.readyState === 1 && ws.send(JSON.stringify(obj));

  function onMessage(m) {
    if (m.type === "session") {
      sessionId = m.session_id; store.set("aistaff.session", sessionId);
      if (m.state !== "idle") hideWelcome();
    } else if (m.type === "reply") renderReply(m);
    else if (m.type === "tts") Audio_.enqueue(m.url);
    else if (m.type === "asr") { if (m.text) addMsg("me", m.text); $("status").textContent = `Nhận dạng ${m.latency_ms} ms`; }
    else if (m.type === "vad") $("btnMic").classList.toggle("hear", m.speaking);
    else if (m.type === "listening") Mic.setUi(m.on);
  }

  // ------------------------------------------------------------------ hiển thị
  function addMsg(who, text, extra = "") {
    if (!text && !extra) return;
    const d = document.createElement("div");
    d.className = `msg ${who}`;
    d.innerHTML = esc(text) + extra;
    $("chat").appendChild(d);
    $("chat").scrollTop = $("chat").scrollHeight;
  }

  function renderReply(r) {
    state = r.state;
    if (r.intent !== "reset" && r.intent !== "noop") hideWelcome();
    let extra = "";
    lastRecs = (r.recommendations || []).map((x) => x.entry_id);
    if (r.recommendations && r.recommendations.length) {
      extra = '<div class="recs">' + r.recommendations.map((x, i) => `<div class="rec"><div><b>${i + 1}. ${esc(x.name)}</b> ${money(x.price)}<small>${esc((x.reasons || []).join(" · "))}</small></div><button data-add="${x.entry_id}">Chọn</button></div>`).join("") + "</div>";
    }
    if (r.text) addMsg("ai", r.text, extra);
    $("options").innerHTML = (r.options || []).map((o) => `<button data-add="${o.entry_id}">${esc(o.name)} · ${money(o.price)}</button>`).join("");
    $("chips").innerHTML = (r.suggestions || []).map((s) => `<button data-say="${esc(s)}">${esc(s)}</button>`).join("");
    if (r.cart) renderCart(r.cart);
    if (cfg && lastRecs.length) {
      const first = cfg.entries.find((e) => e.id === lastRecs[0]);
      if (first) { currentTab = first.kind === "combo" ? "combo" : first.category; renderTabs(); }
    } else if (cfg) renderGrid();
    if (r.qr) showPay(r.qr); else if (state !== "awaiting_payment") $("payModal").classList.add("hidden");
    if (r.intent === "paid") showDone(r);
    if (r.intent === "timeout") { resetUi(); showWelcome(); }
  }

  function renderCart(c) {
    $("cartCount").textContent = c.count || 0;
    const lines = (c.lines || []).map((l) => `<li><div><div class="name">${esc(l.name)}${l.option_name ? " (" + esc(l.option_name) + ")" : ""}</div>
      ${l.note ? `<div class="note">${esc(l.note)}</div>` : ""}<div class="note">${money(l.unit_price)}</div></div>
      <div class="qty"><button data-dec="${l.entry_id}" aria-label="Bớt">−</button><b>${l.qty}</b><button data-inc="${l.entry_id}" aria-label="Thêm">+</button></div></li>`);
    (c.free_items || []).forEach((f) => lines.push(`<li class="gift"><div class="name">🎁 ${esc(f.name)} (tặng)</div><div>x${f.qty}</div></li>`));
    $("cartLines").innerHTML = lines.join("") || '<li class="note">Chưa có món nào</li>';
    const t = [`<div class="row"><span>Tạm tính</span><span>${money(c.subtotal)}</span></div>`];
    (c.applied || []).filter((a) => a.discount).forEach((a) => t.push(`<div class="row disc"><span>${esc(a.name)}</span><span>-${money(a.discount)}</span></div>`));
    if (c.vat) t.push(`<div class="row"><span>VAT</span><span>${money(c.vat)}</span></div>`);
    t.push(`<div class="row grand"><span>Tổng cộng</span><span>${money(c.total)}</span></div>`);
    (c.hints || []).forEach((h) => t.push(`<div class="hint">💡 ${esc(h.message)}</div>`));
    $("totals").innerHTML = t.join("");
    $("btnCheckout").disabled = !(c.lines && c.lines.length);
  }

  function showPay(qr) {
    $("qrBox").innerHTML = qr.svg;
    $("payAmount").textContent = money(qr.amount);
    $("payBank").textContent = qr.bank_name || qr.bank_bin;
    $("payName").textContent = qr.account_name;
    $("payAcc").textContent = qr.account_number;
    $("payCode").textContent = qr.code;
    expiresAt = qr.expires_at ? new Date(qr.expires_at) : null;
    $("payModal").classList.remove("hidden");
  }

  function showDone(r) {
    $("payModal").classList.add("hidden");
    $("doneText").textContent = r.text;
    $("doneNo").textContent = r.order && r.order.code ? "#" + parseInt(r.order.code.slice(-6), 10) : "";
    $("doneModal").classList.remove("hidden");
    clearTimeout(doneTimer);
    doneTimer = setTimeout(() => { $("doneModal").classList.add("hidden"); resetUi(); showWelcome(); }, 9000);
  }

  function resetUi() { $("chat").innerHTML = ""; $("options").innerHTML = ""; $("chips").innerHTML = ""; lastRecs = []; renderCart({ lines: [] }); }
  function hideWelcome() { $("welcome").classList.add("hidden"); }
  function showWelcome() { $("welcome").classList.remove("hidden"); Mic.stop(); }

  setInterval(() => {
    if (!expiresAt || $("payModal").classList.contains("hidden")) return;
    const s = Math.max(0, Math.round((expiresAt - new Date()) / 1000));
    $("payCountdown").textContent = `Mã còn hiệu lực ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);

  // ------------------------------------------------------------------ âm thanh ra (TTS)
  const Audio_ = {
    q: [], playing: false, el: new Audio(),
    enqueue(url) { this.q.push(url); if (!this.playing) this.next(); },
    next() {
      const url = this.q.shift();
      if (!url) { this.playing = false; Mic.resumeAfterTts(); return; }
      this.playing = true; Mic.pauseForTts();
      this.el.src = url;
      this.el.play().catch(() => this.next());
    },
  };
  Audio_.el.onended = () => Audio_.next();

  // ------------------------------------------------------------------ micro (PCM16 16 kHz -> WebSocket)
  const Mic = {
    ctx: null, node: null, stream: null, on: false, paused: false,
    async start() {
      if (this.on) return;
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
      } catch (e) { $("status").textContent = "Không mở được micro: " + e.message; return; }
      this.ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const code = `class P extends AudioWorkletProcessor{constructor(){super();this.b=[];this.n=0;this.ratio=sampleRate/16000}
        process(i){const c=i[0][0];if(!c)return true;for(let k=0;k<c.length;k+=this.ratio){this.b.push(c[Math.floor(k)])}
        if(this.b.length>=1600){const o=new Int16Array(this.b.length);for(let k=0;k<this.b.length;k++){const s=Math.max(-1,Math.min(1,this.b[k]));o[k]=s<0?s*32768:s*32767}
        this.port.postMessage(o.buffer,[o.buffer]);this.b=[]}return true}}registerProcessor('pcm16',P)`;
      await this.ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([code], { type: "application/javascript" })));
      const src = this.ctx.createMediaStreamSource(this.stream);
      this.node = new AudioWorkletNode(this.ctx, "pcm16");
      this.node.port.onmessage = (e) => { if (this.on && !this.paused && ws && ws.readyState === 1) ws.send(e.data); };
      src.connect(this.node);
      this.on = true; send({ type: "listen", on: true });
    },
    stop() {
      if (!this.on) return;
      this.on = false; send({ type: "listen", on: false });
      try { this.stream.getTracks().forEach((t) => t.stop()); this.ctx.close(); } catch { /* bỏ qua */ }
      this.setUi(false);
    },
    toggle() { this.on ? this.stop() : this.start(); },
    pauseForTts() { this.paused = true; },          // bán song công: không thu khi AI đang nói
    resumeAfterTts() { setTimeout(() => { this.paused = false; }, 250); },
    setUi(on) { $("btnMic").classList.toggle("on", !!on); $("status").textContent = on ? "Đang nghe… (bấm lại để dừng)" : ""; },
  };

  // ------------------------------------------------------------------ sự kiện
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.tab) { currentTab = b.dataset.tab; renderTabs(); }
    else if (b.dataset.add) send({ type: "action", action: { type: "add", entry_id: b.dataset.add, qty: 1 } });
    else if (b.dataset.inc) send({ type: "action", action: { type: "add", entry_id: b.dataset.inc, qty: 1 } });
    else if (b.dataset.dec) send({ type: "action", action: { type: "remove", entry_id: b.dataset.dec, qty: 1 } });
    else if (b.dataset.say) { addMsg("me", b.dataset.say); send({ type: "text", text: b.dataset.say }); }
  });
  $("form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const t = $("text").value.trim();
    if (!t) return;
    addMsg("me", t); send({ type: "text", text: t }); $("text").value = "";
  });
  $("btnMic").addEventListener("click", () => Mic.toggle());
  $("btnCheckout").addEventListener("click", () => send({ type: "action", action: { type: "checkout" } }));
  $("btnCash").addEventListener("click", () => send({ type: "text", text: "trả tiền mặt" }));
  $("btnCancelPay").addEventListener("click", () => send({ type: "action", action: { type: "cancel" } }));
  $("btnStart").addEventListener("click", () => { resetUi(); hideWelcome(); send({ type: "start" }); if (cfg && cfg.speech) Mic.start(); });
  $("btnRestart").addEventListener("click", () => { resetUi(); send({ type: "action", action: { type: "reset" } }); showWelcome(); });

  loadConfig().then(connect);
})();
