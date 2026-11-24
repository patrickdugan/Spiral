"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const usd = (n) => "$" + fmt(n);
  const short = (h) => h.slice(0, 8) + "…" + h.slice(-4);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };
  const txid = (h) => `<button class="txid" type="button" data-copy="${h}" title="Copy ${h}">${short(h)}</button>`;

  // theme toggle (stamps data-theme; OS setting is the default)
  try { const t = localStorage.getItem("shz-theme"); if (t) document.documentElement.dataset.theme = t; } catch (_) {}
  $("#theme").addEventListener("click", () => {
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("shz-theme", next); } catch (_) {}
  });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    navigator.clipboard?.writeText(b.dataset.copy).then(() => {
      const t = b.textContent; b.textContent = "copied"; setTimeout(() => (b.textContent = t), 900);
    }).catch(() => {});
  });

  const tip = $("#tip");
  const showTip = (html, x, y) => {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > innerHeight - 8) top = y - r.height - 14;
    tip.style.left = Math.max(8, left) + "px"; tip.style.top = Math.max(8, top) + "px";
  };
  const hideTip = () => { tip.hidden = true; };
  addEventListener("scroll", hideTip, { passive: true });
  addEventListener("hashchange", hideTip);

  const pill = (ok, text) => `<span class="pill ${ok ? "good" : "bad"}"><span class="ic" aria-hidden="true">${ok ? "✓" : "✕"}</span>${esc(text)}</span>`;
  const verdict = (node, result) => {
    const ok = result === "accepted";
    return pill(ok, `${node}: ${ok ? "accepted" : result.replace("block-script-verify-flag-failed ", "")}`);
  };
  const tipStatus = (node, status) => {
    if (status === "active") return pill(true, `${node}: active${node === "legacy" ? " (forked)" : ""}`);
    return pill(false, `${node}: ${status || "not seen"}`);
  };

  fetch("data/showcase.json").then((r) => r.json()).then(render).catch((err) => {
    $("#stats").innerHTML = `<p>Could not load data/showcase.json: ${esc(err)}</p>`;
  });

  function render(D) {
    stats(D); proto(D); k1(D); k2(D); book(D); sizes(D); trials(D); links(D);
  }

  function stats(D) {
    const bad = D.trials.filter((t) => !t.ok).length;
    const k2 = D.k2.signet;
    const items = [
      [`${D.trials.length}`, `regtest trials, ${bad} mismatches`],
      [`${fmt(D.trade1.cets_total)}`, "script leaves for one trade"],
      [`${k2.transfer.vsize} vB`, "exclusive on-chain transfer, one signature"],
      [D.book.parties.map((p) => fmt(D.book.at_125k[p])).join(" · "), "netted book at $125k (alice · bob · carol)"],
      [D.k2.oracle.threshold, "FROST oracle quorum"],
    ];
    $("#stats").innerHTML = items.map(([b, s]) => `<div class="stat"><b>${esc(b)}</b><span>${esc(s)}</span></div>`).join("");
  }

  // ---------------------------------------------------------------- 01
  function proto(D) {
    const P = D.prototype, W = 900, H = 300;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Three DLC fundings feed one clearing transaction with four outputs" });
    const names = ["Alice long · Bob short @ $80k", "Bob long · Carol short @ $100k", "Carol long · Alice short @ $125k"];
    const outNames = ["Bob (freed margin)", "Alice (margin + PnL)", "CPFP anchor", "Carol (freed margin)"];
    P.fundings.forEach((f, i) => {
      const y = 30 + i * 85;
      el("rect", { x: 10, y, width: 250, height: 64, rx: 10, class: "box" }, svg);
      el("text", { x: 24, y: y + 26, "font-size": 13, "font-weight": 600 }, svg).textContent = `DLC ${i + 1} · ${fmt(f.sats)} sats`;
      el("text", { x: 24, y: y + 46, "font-size": 12, class: "muted" }, svg).textContent = names[i];
      el("path", { d: `M260 ${y + 32} C 320 ${y + 32}, 330 150, 370 150`, class: "edge" }, svg);
    });
    el("rect", { x: 370, y: 90, width: 170, height: 120, rx: 12, class: "tx" }, svg);
    el("text", { x: 455, y: 128, "text-anchor": "middle", "font-size": 14, "font-weight": 600 }, svg).textContent = "Clearing tx";
    el("text", { x: 455, y: 150, "text-anchor": "middle", "font-size": 12, class: "muted" }, svg).textContent = `${P.clearing_vsize} vB · 3 in · 4 out`;
    el("text", { x: 455, y: 170, "text-anchor": "middle", "font-size": 12, class: "muted" }, svg).textContent = "mark $125,000";
    el("text", { x: 455, y: 190, "text-anchor": "middle", "font-size": 12, class: "muted" }, svg).textContent = "all parties pre-sign";
    P.outputs.forEach((o, i) => {
      const y = 22 + i * 68;
      el("path", { d: `M540 150 C 580 150, 590 ${y + 26}, 640 ${y + 26}`, class: "edge" }, svg);
      el("rect", { x: 640, y, width: 250, height: 52, rx: 10, class: "box" }, svg);
      el("text", { x: 654, y: y + 22, "font-size": 13, "font-weight": 600 }, svg).textContent = `${fmt(o.sats)} sats`;
      el("text", { x: 654, y: y + 40, "font-size": 12, class: "muted" }, svg).textContent = `${outNames[i]} · unspent on ${o.unspent_on.length} nodes`;
    });
    $("#proto-flow").appendChild(svg);
    $("#proto-cap").innerHTML = `Funding ${txid(P.funding_txid)} and clearing ${txid(P.clearing_txid)} confirmed in signed block
      ${txid(P.block)} on the miner and the observer (${esc(Object.values(P.versions)[0])}).
      SHZ's own attack probes were refused by the mempool, as they should be:
      <span class="verdicts" style="margin-top:8px">${P.probes.map((p) => pill(false, p.probe_id.replace("testnet4-", "") + ": refused")).join("")}</span>`;
  }

  // ---------------------------------------------------------------- 02
  function k1(D) {
    const T = D.trade1, cets = T.cets;
    $("#cet-n").textContent = fmt(T.cets_total);
    $("#k1-legend").innerHTML = `<span><i style="background:var(--series-1)"></i>Long (Alice)</span><span><i style="background:var(--series-2)"></i>Short (Bob)</span>`;
    const W = 900, H = 340, m = { l: 56, r: 16, t: 16, b: 34 };
    const xs = T.curve.map((d) => d[0]), x0 = xs[0], x1 = xs[xs.length - 1];
    const X = (p) => m.l + (p - x0) / (x1 - x0) * (W - m.l - m.r);
    const Y = (s) => H - m.b - s / T.total * (H - m.t - m.b);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}` });
    const ga = el("g", { class: "axis" }, svg);
    for (let s = 0; s <= T.total; s += 250) {
      el("line", { x1: m.l, x2: W - m.r, y1: Y(s), y2: Y(s), class: "gridline" }, ga);
      el("text", { x: m.l - 8, y: Y(s) + 4, "text-anchor": "end" }, ga).textContent = fmt(s);
    }
    for (let p = 50000; p <= x1; p += 50000) el("text", { x: X(p), y: H - 12, "text-anchor": "middle" }, ga).textContent = "$" + p / 1000 + "k";
    const longPath = "M" + T.curve.map((d) => `${X(d[0])},${Y(d[1])}`).join("L");
    el("path", { d: `${longPath}L${X(x1)},${Y(0)}L${X(x0)},${Y(0)}Z`, fill: "var(--series-1)", opacity: .85 }, svg);
    el("path", { d: `${longPath}L${X(x1)},${Y(T.total)}L${X(x0)},${Y(T.total)}Z`, fill: "var(--series-2)", opacity: .85 }, svg);
    el("path", { d: longPath, stroke: "var(--surface-1)", "stroke-width": 2, fill: "none" }, svg);
    el("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), class: "baseline" }, svg);
    // Liquidation and entry markers: ticks on the top edge, labels inside the plot.
    for (const [p, t, anchor, row] of [[T.spec.long_liq, "long liquidated", "start", 0], [T.spec.entry, "entry", "start", 1],
                                       [T.spec.short_liq, "short liquidated", "end", 0]]) {
      if (p < x0 || p > x1) continue;
      el("line", { x1: X(p), x2: X(p), y1: m.t, y2: H - m.b, stroke: "var(--surface-1)", "stroke-width": 1, "stroke-dasharray": "2 4", opacity: .9 }, svg);
      const tx = el("text", { x: X(p) + (anchor === "end" ? -6 : 6), y: m.t + 14 + row * 16, "text-anchor": anchor, class: "lbl on-fill" }, svg);
      tx.textContent = `${t} ${usd(p)}`;
    }
    const band = el("rect", { y: m.t, height: H - m.t - m.b, class: "band" }, svg);
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "cross" }, svg);
    const dot = el("circle", { r: 5, fill: "var(--series-1)", stroke: "var(--surface-1)", "stroke-width": 2 }, svg);
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    $("#k1-chart").appendChild(svg);

    const find = (p) => cets.find((c) => p >= c[0] && p <= c[1]);
    const exact = (p) => { const i = Math.round((p - x0) / 1000); return T.curve[Math.max(0, Math.min(T.curve.length - 1, i))][1]; };
    function select(p) {
      const c = find(p); if (!c) return;
      const bx = X(Math.max(c[0], x0)), bw = Math.max(4, X(Math.min(c[1], x1)) - bx);
      band.setAttribute("x", bw === 4 ? bx - 2 : bx); band.setAttribute("width", bw);
      cross.setAttribute("x1", X(p)); cross.setAttribute("x2", X(p));
      dot.setAttribute("cx", X(p)); dot.setAttribute("cy", Y(exact(p)));
      const bits = c[4].padEnd(20, "·").split("").map((b, i) => `<span class="bit ${i < c[3] ? "on" : ""}" title="digit ${i}">${b}</span>`).join("");
      $("#k1-leaf").innerHTML = `
        <dt>Price</dt><dd>${usd(p)}</dd>
        <dt>Leaf range</dt><dd>${usd(c[0])} – ${usd(c[1])}</dd>
        <dt>Oracle digits</dt><dd><div class="bits">${bits}</div></dd>
        <dt>Checked in script</dt><dd>${c[3]} digit signatures (OP_CHECKSIGFROMSTACK, nonce pinned)</dd>
        <dt>Leaf pays</dt><dd>long ${fmt(c[2])} · short ${fmt(T.total - c[2])} sats (exact at this price: ${fmt(exact(p))} / ${fmt(T.total - exact(p))})</dd>`;
      return c;
    }
    select(125000);
    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const p = Math.round((x0 + ((ev.clientX - r.left) / r.width * W - m.l) / (W - m.l - m.r) * (x1 - x0)) / 100) * 100;
      if (p < x0 || p > x1) return;
      const c = select(p);
      const l = exact(p);
      showTip(`<b>${usd(p)}</b><div class="row"><span><i style="background:var(--series-1)"></i>Long</span><span>${fmt(l)}</span></div>
        <div class="row"><span><i style="background:var(--series-2)"></i>Short</span><span>${fmt(T.total - l)}</span></div>
        <div class="row"><span>Leaf digits</span><span>${c ? c[3] : "-"}</span></div>`, ev.clientX, ev.clientY);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerleave", () => { hideTip(); select(125000); });
    $("#k1-table").innerHTML = `<div class="scroll"><table><tr><th>Price</th><th>Long</th><th>Short</th></tr>${
      T.curve.filter((d, i) => i % 10 === 0).map((d) => `<tr><td>${usd(d[0])}</td><td>${fmt(d[1])}</td><td>${fmt(T.total - d[1])}</td></tr>`).join("")}</table></div>`;
  }

  // ---------------------------------------------------------------- 03
  function k2(D) {
    const S = D.k2.single, sig = D.k2.signet;
    const W = 520, H = 250;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "P2MR tree: contract subtree C beside a state leaf holding the owner keys" });
    const node = (x, y, w, h, cls, lines) => {
      el("rect", { x: x - w / 2, y, width: w, height: h, rx: 9, class: cls }, svg);
      lines.forEach((t, i) => el("text", { x, y: y + 20 + i * 16, "text-anchor": "middle", class: i ? "mono" : "" }, svg).textContent = t);
    };
    const edge = (xa, ya, xb, yb) => el("path", { d: `M${xa} ${ya} C ${xa} ${(ya + yb) / 2}, ${xb} ${(ya + yb) / 2}, ${xb} ${yb}`, class: "edge" }, svg);
    node(260, 8, 230, 44, "node", ["P2MR output (witness v2)", "root = TapBranch(C, state)"]);
    edge(260, 52, 130, 92); edge(260, 52, 390, 92);
    node(130, 92, 220, 44, "node", ["C · contract leaves", `${fmt(S.leaves)} leaves, no keys`]);
    node(390, 92, 220, 44, "state", ["state leaf (never runs)", "OP_RETURN <K_long> <K_short>"]);
    const kids = [["CET ranges", `${fmt(S.cet_leaves)}`], ["refund", `CSV ${S.refund_csv}`], ["transfer", "× 2 parties"]];
    kids.forEach((k, i) => { const x = 40 + i * 90; edge(130, 136, x + 5, 176); node(x + 5, 176, 84, 44, "node", k); });
    el("text", { x: 390, y: 170, "text-anchor": "middle", class: "mono" }, svg).textContent = "transfer: same C,";
    el("text", { x: 390, y: 186, "text-anchor": "middle", class: "mono" }, svg).textContent = "one key replaced";
    el("text", { x: 390, y: 214, "text-anchor": "middle" }, svg).textContent = `${S.transfer_leaf_bytes}-byte transfer leaf`;
    $("#k2-tree").appendChild(svg);

    $("#k2-rules").innerHTML = [
      ["The current owner signs", "an ordinary BIP342 signature by the key in the state, over the transfer transaction."],
      ["Only that key changes", "the single output must be this same contract with the owner's key replaced."],
      ["A fixed fee", `the output keeps the input amount minus ${S.transfer_fee} sats (4-byte script arithmetic).`],
      ["A floor", `the output may not fall below ${fmt(S.settle_floor)} sats, so settlement stays funded.`],
      ["No counterparty", "nothing in the leaf asks for, or lets, the other side block the sale."],
    ].map(([b, t]) => `<li><b>${b}:</b> ${t}</li>`).join("");

    const order = ["miner", "observer", "legacy"];
    const nodes = order.filter((n) => n in sig.versions);
    const ordered = (obj) => order.filter((n) => n in obj).map((n) => [n, obj[n]]);
    const all = (ok) => nodes.map((n) => pill(ok, `${n}: ${ok ? "accepted" : "rejected"}`)).join("");
    const steps = [
      [true, "Alice sells her long position to Carol", `On-chain transfer ${txid(sig.transfer.txid)} (${sig.transfer.vsize} vB), signed by Alice alone. The mempool refuses it as non-standard (${esc(sig.mempool.miner)}), so the block signer includes it.`, all(sig.transfer.accepted_by_all)],
      [false, "Attack blocked: Alice sells the same position again",`Her transfer of the same coin to Mallory, ${txid(sig.double_sale.txid)}, in a correctly signed block.`, ordered(sig.double_sale.verdicts).map(([n, v]) => verdict(n, v)).join("")],
      [false, "Attack blocked: Alice settles the coin she sold",`Settlement naming her as owner, ${txid(sig.split.txid)}, in signed block ${txid(sig.split.block)}. The patched nodes reject it. The stock node accepts and forks, and is rolled back afterwards.`, ordered(sig.split.status).map(([n, s]) => tipStatus(n, s)).join("")],
      [true, "The oracle attests $125,000; the new coin settles", `FROST quorum 2, 4, 5 signs the digits. ${txid(sig.settle.txid)} pays Carol ${fmt(sig.settle.outputs[0])} and Bob ${fmt(sig.settle.outputs[1])} sats.`, all(sig.settle.accepted_by_all)],
      [true, "Keyless refund after the CSV delay", `Refused before the delay (${esc(sig.refund_early)}). After 144 blocks, ${txid(sig.refund.txid)} returns the margins ${sig.refund.outputs.map(fmt).join(" / ")}.`, all(sig.refund.accepted_by_all)],
    ];
    $("#k2-timeline").innerHTML = steps.map(([ok, h, p, v]) =>
      `<li><span class="dot ${ok ? "good" : "bad"}" aria-hidden="true"></span><h4>${h}</h4><p>${p}</p><div class="verdicts">${v}</div></li>`).join("");
  }

  // ---------------------------------------------------------------- 04
  function book(D) {
    const B = D.book, cols = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
    $("#book-ranges").textContent = fmt(B.ranges_total);
    $("#book-legend").innerHTML = B.parties.map((p, i) => `<span><i style="background:${cols[i]}"></i>${p}</span>`).join("");
    const W = 900, H = 320, m = { l: 56, r: 70, t: 16, b: 34 };
    const xs = B.curve.map((d) => d[0]), x0 = xs[0], x1 = xs[xs.length - 1];
    const ymax = Math.ceil(Math.max(...B.curve.flatMap((d) => d.slice(1))) / 500) * 500;
    const X = (p) => m.l + (p - x0) / (x1 - x0) * (W - m.l - m.r);
    const Y = (s) => H - m.b - s / ymax * (H - m.t - m.b);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}` });
    const ga = el("g", { class: "axis" }, svg);
    for (let s = 0; s <= ymax; s += 500) {
      el("line", { x1: m.l, x2: W - m.r, y1: Y(s), y2: Y(s), class: "gridline" }, ga);
      el("text", { x: m.l - 8, y: Y(s) + 4, "text-anchor": "end" }, ga).textContent = fmt(s);
    }
    for (let p = 50000; p <= x1; p += 50000) el("text", { x: X(p), y: H - 12, "text-anchor": "middle" }, ga).textContent = "$" + p / 1000 + "k";
    el("line", { x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0), class: "baseline" }, svg);
    B.parties.forEach((p, i) => {
      el("path", { d: "M" + B.curve.map((d) => `${X(d[0])},${Y(d[i + 1])}`).join("L"), stroke: cols[i], "stroke-width": 2, fill: "none" }, svg);
      const last = B.curve[B.curve.length - 1];
      el("text", { x: W - m.r + 8, y: Y(last[i + 1]) + 4, class: "lbl" }, svg).textContent = p;
    });
    const mk = 125000;
    el("line", { x1: X(mk), x2: X(mk), y1: m.t, y2: H - m.b, class: "cross", opacity: .6 }, svg);
    el("text", { x: X(mk) + 6, y: m.t + 12, class: "lbl" }, svg).textContent = "$125k = SHZ clearing";
    B.parties.forEach((p, i) => el("circle", { cx: X(mk), cy: Y(B.at_125k[p]), r: 5, fill: cols[i], stroke: "var(--surface-1)", "stroke-width": 2 }, svg));
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    $("#book-chart").appendChild(svg);
    hit.addEventListener("pointermove", (ev) => {
      const r = svg.getBoundingClientRect();
      const i = Math.max(0, Math.min(B.curve.length - 1, Math.round(((ev.clientX - r.left) / r.width * W - m.l) / (W - m.l - m.r) * (B.curve.length - 1))));
      const d = B.curve[i];
      cross.setAttribute("x1", X(d[0])); cross.setAttribute("x2", X(d[0])); cross.setAttribute("visibility", "visible");
      showTip(`<b>${usd(d[0])}</b>` + B.parties.map((p, j) => `<div class="row"><span><i style="background:${cols[j]}"></i>${p}</span><span>${fmt(d[j + 1])}</span></div>`).join(""), ev.clientX, ev.clientY);
    });
    hit.addEventListener("pointerleave", () => { hideTip(); cross.setAttribute("visibility", "hidden"); });
    $("#book-trades").innerHTML = B.trades.map((t, i) => `<div class="trade"><b>Trade ${i + 1}</b> · entry ${usd(t.entry)}<br>${t.long} long (${fmt(t.long_margin)}) vs ${t.short} short (${fmt(t.short_margin)})</div>`).join("")
      + `<div class="trade"><b>On the Signet</b><br>${txid(D.k2.signet.book.txid)} · ${D.k2.signet.book.vsize} vB<br>${D.k2.signet.book.outputs.map(fmt).join(" / ")} · ${D.k2.signet.book.accepted_by_all ? "accepted by all nodes" : "not accepted by all"}</div>`;
    $("#book-table").innerHTML = `<div class="scroll"><table><tr><th>Price</th>${B.parties.map((p) => `<th>${p}</th>`).join("")}</tr>${
      B.curve.filter((d, i) => i % 10 === 0).map((d) => `<tr><td>${usd(d[0])}</td>${d.slice(1).map((v) => `<td>${fmt(v)}</td>`).join("")}</tr>`).join("")}</table></div>`;
  }

  function sizes(D) {
    const max = Math.max(...D.sizes.map((s) => s.vsize));
    $("#sizes").innerHTML = D.sizes.map((s) => `<div class="bar-row"><span class="name">${esc(s.label)}</span>
      <div class="bar-track"><div class="bar ${s.kind === "shz" ? "shz" : ""}" style="width:${s.vsize / max * 85}%"></div>
      <span class="bar-val" style="left:${s.vsize / max * 85}%">${fmt(s.vsize)}</span></div></div>`).join("");
  }

  function trials(D) {
    const suites = ["All", ...new Set(D.trials.map((t) => t.suite))];
    let active = "All";
    const draw = () => {
      const rows = D.trials.filter((t) => active === "All" || t.suite === active);
      $("#trial-table").innerHTML = `<thead><tr><th>Suite</th><th>Case</th><th>new</th><th>old-flag</th><th>old-stock</th><th>Expected</th></tr></thead><tbody>${
        rows.map((t) => `<tr><td class="suite">${esc(t.suite)} · ${esc(t.arm)}</td><td>${esc(t.case)}${t.note ? `<div class="note">${esc(t.note)}</div>` : ""}</td>${
          ["new", "old-flag", "old-stock"].map((n) => `<td class="v" title="${esc(t.reasons[n])}">${t.accepted[n] ? pill(true, "accepted") : pill(false, "rejected")}</td>`).join("")
        }<td class="v">${t.ok ? pill(true, "matches") : pill(false, "mismatch")}</td></tr>`).join("")}</tbody>`;
    };
    $("#filters").innerHTML = suites.map((s) => `<button type="button" aria-pressed="${s === active}" data-s="${esc(s)}">${esc(s)} (${s === "All" ? D.trials.length : D.trials.filter((t) => t.suite === s).length})</button>`).join("");
    $("#filters").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      active = b.dataset.s;
      $("#filters").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      draw();
    });
    draw();
  }

  function links(D) {
    const L = D.links;
    $("#links").innerHTML = [
      [L.results, "RESULTS.md: full write-up and every transaction ID"],
      [L.evidence, "Raw receipts (no private keys)"],
      [L.k2_code, "shz_k2.py: ownership-in-output covenant"],
      [L.frost_code, "shz_frost.py: t-of-n FROST digit oracle"],
      [L.margin_code, "shz_margin.py: contract maths ported from Rust"],
      [L.ci.k2, "CI run: SHZ-K2 on patched Core, all jobs green"],
      [L.ci.prototype_k1, "CI run: SHZ prototype on stock Signet and SHZ-K1"],
      [L.shz_repo, "SatsHedgeZero"],
    ].map(([h, t]) => `<li><a href="${h}">${esc(t)}</a></li>`).join("");
  }
})();
