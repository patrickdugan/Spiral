// In-and-Out-Burger demo page. Static: reads data/demo.json (scripts/build_site_data.py) and asks
// mempool.space for live testnet4 confirmations. The payout key check at the bottom recomputes
// P' = P + t*G and its address with the code in this file only (secp256k1, SHA-256 via WebCrypto,
// RIPEMD-160, Base58Check).
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
};
const short = (x, n = 8) => (x && x.length > 2 * n + 1 ? `${x.slice(0, n)}…${x.slice(-n)}` : x || "");
const fmt = (n) => (n === null || n === undefined ? "–" : Number(n).toLocaleString("en-US"));
const pill = (text, kind = "") => h("span", { class: `pill ${kind}` }, text);

let D = null;
const live = { tip: null, tx: {}, addr: {} };

// ---------------------------------------------------------------------------------------------
// data and live chain

async function loadData() {
  const r = await fetch("data/demo.json", { cache: "no-cache" });
  D = await r.json();
}

const API = () => `${D.explorer}/api`;
const txUrl = (txid) => `${D.explorer}/tx/${txid}`;
const addrUrl = (a) => `${D.explorer}/address/${a}`;

async function getJSON(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

function knownTxids() {
  const ids = new Set(D.transactions.map((t) => t.txid));
  for (const i of D.instances) {
    for (const v of Object.values(i.txids)) if (v) ids.add(v);
    if (i.graph) { ids.add(i.graph.claim_txid); ids.add(i.graph.payout_txid); }
  }
  return [...ids];
}

async function pollChain() {
  const tip = await fetch(`${API()}/blocks/tip/height`).then((r) => (r.ok ? r.text() : null)).catch(() => null);
  live.tip = tip && Number.isInteger(Number(tip)) ? Number(tip) : null;
  live.tx = {};
  await Promise.all(knownTxids().map(async (txid) => {
    const s = await getJSON(`${API()}/tx/${txid}/status`);
    if (s) live.tx[txid] = s;
  }));
  if (D.addresses.payout) live.addr.payout = await getJSON(`${API()}/address/${D.addresses.payout}`);
  renderLive();
}

function confs(txid) {
  const s = live.tx[txid];
  if (s && !s.confirmed) return 0;
  if (s && live.tip !== null && live.tip >= s.block_height) return live.tip - s.block_height + 1;
  return D.transactions.find((t) => t.txid === txid)?.recorded_confirmations ?? null;
}

function hasLiveStatus(txid) {
  const s = live.tx[txid];
  return !!s && (!s.confirmed || (live.tip !== null && live.tip >= s.block_height));
}

function confPill(txid) {
  const el = h("span", { class: "pill quiet", "data-conf": txid }, "…");
  return el;
}

function renderLive() {
  $("#tip-pill").textContent = live.tip ? `live tip ${fmt(live.tip)}` : D.recording?.tip ? `recorded tip ${fmt(D.recording.tip)}` : "live data unavailable";
  const recordedAt = D.recording?.at?.replace("T", " ").replace("Z", " UTC");
  $("#chain-note").textContent = live.tip
    ? "Live confirmations from mempool.space. Individual lookups fall back to the labelled recorded count when unavailable."
    : recordedAt ? `Recorded confirmations as of ${recordedAt}. Live explorer data is unavailable.` : "Live explorer data is unavailable; no recorded confirmations are available.";
  document.querySelectorAll("[data-conf]").forEach((el) => {
    const txid = el.getAttribute("data-conf");
    const c = confs(txid);
    const source = hasLiveStatus(txid) ? "live" : "recorded";
    el.title = source === "live" ? "Current explorer status" : `Snapshot from ${recordedAt || "the run record"}`;
    if (c === null) { el.textContent = "status unavailable"; el.className = "pill quiet"; }
    else if (c === 0) { el.textContent = source === "live" ? "in mempool" : "unconfirmed · recorded"; el.className = "pill wait"; }
    else { el.textContent = `${fmt(c)} conf${source === "recorded" ? " · recorded" : ""}`; el.className = "pill ok"; }
  });
  const a = live.addr.payout;
  const bal = $("#payout-balance");
  if (bal) {
    if (!a) {
      const honest = D.instances.find((i) => i.name === "honest");
      bal.textContent = honest?.txids.payout ? `${fmt(honest.graph.payout_sats)} sats in the recorded payout` : "–";
    }
    else {
      const got = a.chain_stats.funded_txo_sum + a.mempool_stats.funded_txo_sum;
      bal.textContent = got ? `${fmt(got)} sats received (${a.chain_stats.tx_count + a.mempool_stats.tx_count} tx)` : "nothing yet";
    }
  }
  renderFlow();
}

// ---------------------------------------------------------------------------------------------
// the flow strip

function stages() {
  const honest = D.instances.find((i) => i.name === "honest");
  const payTx = D.payment.txid;
  const paid = confs(payTx);
  const payoutTx = honest && honest.txids.payout;
  const payoutConf = payoutTx ? confs(payoutTx) : null;
  return [
    { t: "Pay in", s: `${fmt(D.payment.sats)} sats to the burger`, st: paid === null ? "done" : paid > 0 ? "done" : "run" },
    { t: "Confirm", s: `block ${fmt(D.payment.block)} + ${D.payment.confirmations_proven - 1}`, st: "done" },
    { t: "Nova fold", s: `${fmt(D.pipeline.nova.steps)} headers`, st: "done" },
    { t: "SP1 guest", s: `${(D.pipeline.m16.instructions / 1e9).toFixed(1)}B instructions`, st: "done" },
    { t: "GPU proof", s: D.pipeline.gpu.done ? "proved and wrapped" : "proving", st: D.pipeline.gpu.done ? "done" : "run" },
    { t: "Garbled M14", s: `${(D.pipeline.m14.gates / 1e6).toFixed(0)}M gates`, st: honest && honest.evaluation ? (honest.evaluation.verdict === "accept" ? "done" : "bad") : (D.pipeline.gpu.done ? "run" : "wait") },
    { t: "BitVM payout", s: "to P′", st: payoutTx ? (payoutConf > 0 ? "done" : "run") : honest && honest.txids.claim ? "run" : "wait" },
    { t: "Derived-key spend", s: "payer uses p + t", st: honest?.txids.sweep ? (confs(honest.txids.sweep) > 0 ? "done" : "run") : "wait" },
  ];
}

const NOTES = [
  "The payer spends from a P2PKH key P to the burger's pre-programmed address.",
  "Six blocks bury the payment; the statement pins the tip and its chainwork.",
  "Nova folds every header from checkpoint 160,000 to the tip, one header per step.",
  "The M16 SP1 guest verifies the Nova proof and the payment's Merkle path, then commits the statement.",
  "SP1 proves that run on the GPU; M13 wraps it under BLAKE3 for the garbled verifier.",
  "M14 is that final verifier as one garbled circuit; the statement is a constant, the proof bits are the input.",
  "If no reject label turns up within 6 blocks of the claim, the presigned payout pays the bond to P′.",
  "The payer spends the P′ output with p′ = p + t, demonstrating control of the derived key on chain.",
];

let flowTimer = null;
function renderFlow() {
  const el = $("#flow");
  const ss = stages();
  el.replaceChildren(h("div", { class: "rail" }));
  const coin = h("div", { class: "coin", title: "tBTC" }, "₿");
  el.append(coin);
  ss.forEach((s, i) => el.append(h("div", { class: `station ${s.st}`, "data-i": i, onmouseenter: () => showNote(i) },
    h("i", { class: "dot" }), h("b", {}, s.t), h("span", {}, s.s))));
  const reached = ss.reduce((acc, s, i) => (s.st === "done" ? i : acc), 0);
  clearInterval(flowTimer);
  let i = 0;
  const step = () => {
    const st = el.querySelectorAll(".station");
    st.forEach((n) => n.classList.remove("active"));
    if (st[i]) {
      st[i].classList.add("active");
      const r = st[i].getBoundingClientRect(), p = el.getBoundingClientRect();
      coin.style.left = `${r.left - p.left + r.width / 2 - 14}px`;
      showNote(i);
    }
    i = i >= Math.min(reached + 1, ss.length - 1) ? 0 : i + 1;
  };
  step();
  flowTimer = setInterval(step, 2600);
}
function showNote(i) { $("#flow-note").textContent = `${i + 1}. ${NOTES[i]}`; }

// ---------------------------------------------------------------------------------------------
// timeline

function txLine(label, txid) {
  return [h("dt", {}, label), h("dd", {}, h("a", { href: txUrl(txid), target: "_blank", rel: "noopener", class: "mono" }, short(txid, 10)), " ", confPill(txid))];
}

function renderResults() {
  const r = D.recording || {};
  const honest = D.instances.find((i) => i.name === "honest");
  $("#results-title").textContent = r.complete ? "Completed on testnet4" : "The testnet4 run";
  $("#run-summary").replaceChildren(
    h("p", { class: "result-total" }, honest?.txids.payout ? `${fmt(honest.graph.payout_sats)} sats paid to P′` : "The three-claim demonstration"),
    h("p", {}, r.complete ? "Both invalid claims were disproved. The honest payout and the payer’s derived-key sweep were confirmed." : "Follow the honest claim and its two counterexamples through the same verifier and claim graph."),
    h("div", { class: "result-checks" }, pill(r.native_verified ? "Native proof verified" : "Proof pending", r.native_verified ? "ok" : "wait"),
      ...(r.checks ? [pill(`${r.checks_passed}/${r.checks} final checks`, r.checks_passed === r.checks ? "ok" : "bad")] : []),
      ...(r.guest_mutations_refused ? [pill(`${r.guest_mutations_refused} guest mutations refused`, "ok")] : []),
      ...(D.regtest.checks.length ? [pill(`${D.regtest.checks.filter((c) => c.ok).length}/${D.regtest.checks.length} regtest checks`, D.regtest.all_pass ? "ok" : "bad")] : [])),
    h("p", { class: "record-anchor" }, `Proof anchored at checkpoint ${fmt(D.statement.anchor.height)} → ${fmt(D.statement.tip.height)}. The committee-of-one trust assumptions below still apply.`));
  const names = Object.fromEntries(D.instances.map((i) => [i.name, i.title]));
  const labels = { claim: "claim", disprove: "disprove", payout: "Payout to P′", payer_sweep: "Derived-key sweep" };
  const receipts = D.transactions.filter((t) => Object.hasOwn(labels, t.kind));
  $("#receipts").replaceChildren(...receipts.map((t) => {
    const label = ["claim", "disprove"].includes(t.kind) ? `${names[t.instance]} · ${labels[t.kind]}` : labels[t.kind];
    return h("tr", { "data-kind": t.kind, "data-instance": t.instance },
      h("th", { scope: "row" }, label),
      h("td", {}, h("a", { href: txUrl(t.txid), target: "_blank", rel: "noopener", class: "mono", title: t.txid, "aria-label": `View ${label} on the testnet4 explorer` }, short(t.txid, 10))),
      h("td", {}, confPill(t.txid)));
  }));
  const recordUrl = `${D.source}/results/testnet4-bitvm3`;
  $("#evidence").replaceChildren(h("a", { href: recordUrl, target: "_blank", rel: "noopener" }, "Public proof and transaction record"),
    ...(r.checks ? [" · ", h("a", { href: `${recordUrl}/checks.json`, target: "_blank", rel: "noopener" }, "Final verification checks")] : []));
}

function renderTimeline() {
  const st = D.statement;
  const v = D.transactions.find((t) => t.kind === "vault_funding");
  const honest = D.instances.find((i) => i.name === "honest");
  const items = [
    {
      done: true, title: "The payer pays the burger",
      body: [h("p", {}, `${fmt(D.payment.sats)} sats from the payer's P2PKH key to the menu address. The input reveals the key P.`),
        h("dl", { class: "facts" }, ...txLine("payment", D.payment.txid),
          h("dt", {}, "to"), h("dd", {}, h("a", { href: addrUrl(D.addresses.burger), target: "_blank", rel: "noopener", class: "mono" }, D.addresses.burger)),
          h("dt", {}, "payer key P"), h("dd", { class: "mono" }, short(D.payment.payer_pubkey, 12)))],
    },
    {
      done: true, title: "The desk bonds three vaults",
      body: [h("p", {}, "One vault per claim: 25,000 sats for the honest claim and 10,000 each for the two counterexamples, all to one Taproot vault script."),
        h("dl", { class: "facts" }, ...(v ? txLine("vault funding", v.txid) : []),
          h("dt", {}, "vault"), h("dd", { class: "mono" }, short(D.addresses.vault, 14)))],
    },
    {
      done: true, title: "Nova folds the header chain",
      body: [h("p", {}, `One Nova segment, ${fmt(D.pipeline.nova.steps)} steps at one header per step, from checkpoint ${fmt(D.pipeline.nova.anchor)} to tip ${fmt(D.pipeline.nova.tip)}, folded in ${fmt(D.pipeline.nova.fold_seconds)} s. Every header's proof of work, link and testnet4 difficulty rule is a constraint.`),
        h("dl", { class: "facts" }, h("dt", {}, "Nova key"), h("dd", { class: "mono" }, short(D.pipeline.nova.nova_vk, 10)))],
    },
    {
      done: !!st, title: "The SP1 guest states what was paid",
      body: st ? [h("p", {}, `M16's guest verifies the Nova proof inside SP1, checks the payment's Merkle path under the proven tip, and commits the statement. The desk checks it against its own node: ${st.checks_passed} of ${st.checks} checks pass.`),
        h("dl", { class: "facts" },
          h("dt", {}, "statement"), h("dd", { class: "mono" }, short(st.sha256, 12)),
          h("dt", {}, "anchor"), h("dd", {}, `block ${fmt(st.anchor.height)} `, h("span", { class: "mono" }, short(st.anchor.hash, 8))),
          h("dt", {}, "tip"), h("dd", {}, `block ${fmt(st.tip.height)} `, h("span", { class: "mono" }, short(st.tip.hash, 8))),
          h("dt", {}, "guest"), h("dd", {}, `${fmt(D.pipeline.m16.instructions)} instructions, program key `, h("span", { class: "mono" }, short(D.pipeline.m16.program_vk_digest, 8))))] : [],
    },
    {
      done: D.pipeline.gpu.done, run: !D.pipeline.gpu.done, title: "The GPU proves it",
      body: [h("p", {}, D.pipeline.gpu.done ? "SP1 proved the guest run on the laptop's GPU; M13 wrapped it under BLAKE3." :
        `SP1 is proving the guest run on the laptop's GPU${D.pipeline.gpu.tasks_recorded ? ` (${fmt(D.pipeline.gpu.tasks_recorded)} tasks recorded at the last data refresh)` : ""}. The honest claim waits for this proof.`)],
    },
    {
      done: !!(honest && honest.txids.claim), run: !(honest && honest.txids.claim), title: "Claims go on chain, the garbled verifier rules",
      body: [h("p", {}, `M14 is the complete final verifier as one garbled circuit of ${fmt(D.pipeline.m14.gates)} gates over ${fmt(D.pipeline.m14.input_bits)} proof bits. Self-test on the M16 mainnet proof: ${D.pipeline.m14.selftest.verdict || "–"}, ${fmt(D.pipeline.m14.selftest.ciphertexts)} ciphertexts.`),
        h("p", {}, h("a", { href: "#claims" }, "See the three claims ↓"))],
    },
    {
      done: !!(honest && honest.txids.payout), title: "The vault pays P′",
      body: [h("p", {}, "The presigned payout spends the claim output to P2PKH(P′) once the claim has 6 confirmations and no reject label has turned up."),
        h("dl", { class: "facts" },
          h("dt", {}, "P′ address"), h("dd", {}, h("a", { href: addrUrl(D.addresses.payout), target: "_blank", rel: "noopener", class: "mono" }, D.addresses.payout)),
          h("dt", {}, "received"), h("dd", { id: "payout-balance" }, "…"),
          ...(honest && honest.txids.payout ? txLine("payout", honest.txids.payout) : []),
          ...(honest && honest.txids.sweep ? txLine("payer sweep", honest.txids.sweep) : []))],
    },
  ];
  $("#timeline").replaceChildren(...items.map((it, i) => h("li", { class: it.done ? "done" : it.run ? "run" : "" },
    h("span", { class: "num" }, String(i + 1)),
    h("div", { class: "tcard" }, h("h3", {}, it.title, it.done ? pill("done", "ok") : it.run ? pill("in progress", "wait") : pill("waiting", "wait")), ...it.body))));
}

// ---------------------------------------------------------------------------------------------
// the three claims

const EXPECT = { honest: "accept", "tampered-proof": "reject", "wrong-statement": "reject" };
let current = "honest";

function renderTabs() {
  $("#tabs").replaceChildren(...D.instances.map((i) => h("button", {
    class: "tab", role: "tab", "aria-selected": String(i.name === current),
    onclick: () => { current = i.name; renderTabs(); renderClaim(); },
  }, i.title)));
}

function renderClaim() {
  const i = D.instances.find((x) => x.name === current);
  const expect = EXPECT[i.name];
  const verdict = i.evaluation ? i.evaluation.verdict : null;
  const settledBy = i.txids.payout ? "payout" : i.txids.disprove ? "disprove" : null;
  const vault = h("div", { class: "gnode", id: "g-vault" }, h("b", {}, "Vault"), `${fmt(i.vault.sats)} sats`, h("div", { class: "mono" }, short(i.vault.outpoint, 8)));
  const claim = h("div", { class: "gnode", id: "g-claim" }, h("b", {}, "Claim"), "OP_RETURN IOB3 ‖ claim id",
    i.graph ? h("div", { class: "mono" }, short(i.graph.claim_id, 8)) : h("div", { class: "pill wait" }, "graph not signed yet"));
  const pay = h("div", { class: "gnode", id: "g-pay" }, h("b", {}, "Payout leaf → P′"),
    h("div", { class: "script mono" }, "6 OP_CSV OP_DROP <desk> OP_CHECKSIG"), "presigned to P2PKH(P′)");
  const dis = h("div", { class: "gnode", id: "g-dis" }, h("b", {}, "Disprove leaf → desk"),
    h("div", { class: "script mono" }, `OP_SHA256 <${i.graph ? short(i.graph.reject_label_sha256, 6) : "H(reject label)"}> OP_EQUALVERIFY <watchtower> OP_CHECKSIG`));
  const graph = h("div", { class: "graph" }, vault, h("div", {}, h("div", { class: "arrow" }, "→"), claim), h("div", { class: "leaves" }, pay, dis));

  const step = (label, status, ...detail) => h("li", {}, status, h("span", {}, h("b", {}, label), " ", ...detail));
  const txa = (txid) => (txid ? [h("a", { href: txUrl(txid), target: "_blank", rel: "noopener", class: "mono" }, short(txid, 8)), " ", confPill(txid)] : []);
  const steps = h("ul", { class: "steps" },
    step("Graph signed", i.graph ? pill("done", "ok") : pill("pending", "wait"),
      i.graph ? `claim ${short(i.graph.claim_txid, 6)}, payout ${short(i.graph.payout_txid, 6)} fixed before broadcast` : "after the claimant garbles M14 for this statement"),
    step("Claim on chain", i.txids.claim ? pill("done", "ok") : pill("pending", "wait"), ...txa(i.txids.claim)),
    step("Garbled verdict", verdict ? pill(verdict, verdict === "accept" ? "ok" : "bad") : pill(`expect ${expect}`, "wait"),
      i.evaluation ? `${fmt(i.evaluation.ciphertexts)} ciphertexts${i.evaluation.flipped_input_bit != null ? `, input bit ${fmt(i.evaluation.flipped_input_bit)} flipped` : ""}` : ""),
    step(expect === "accept" ? "Payout to P′" : "Disprove", settledBy ? pill("done", "ok") : pill("pending", "wait"),
      ...txa(i.txids.payout || i.txids.disprove)));

  const play = h("button", { class: "btn ghost", onclick: () => animateClaim(expect) }, settledBy ? "Replay what happened" : "Play the expected outcome");
  $("#claim").replaceChildren(h("p", {}, i.story), graph, steps, play);
  renderLive();
}

function animateClaim(expect) {
  const ids = ["g-vault", "g-claim", expect === "accept" ? "g-pay" : "g-dis"];
  ["g-vault", "g-claim", "g-pay", "g-dis"].forEach((id) => $(`#${id}`).classList.remove("lit", "win", "lose"));
  ids.forEach((id, k) => setTimeout(() => {
    const el = $(`#${id}`);
    el.classList.add(k < 2 ? "lit" : expect === "accept" ? "win" : "lose");
  }, 700 * (k + 1)));
}

// ---------------------------------------------------------------------------------------------
// the payout key, recomputed here

const Pm = 2n ** 256n - 2n ** 32n - 977n;
const Nn = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
const Gp = [0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798n, 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8n];
const mod = (a, m = Pm) => ((a % m) + m) % m;
function inv(a, m = Pm) { let [r0, r1, s0, s1] = [mod(a, m), m, 1n, 0n]; while (r1) { const q = r0 / r1; [r0, r1] = [r1, r0 - q * r1]; [s0, s1] = [s1, s0 - q * s1]; } return mod(s0, m); }
function padd(a, b) {
  if (!a) return b; if (!b) return a;
  let l;
  if (a[0] === b[0]) { if (mod(a[1] + b[1]) === 0n) return null; l = mod(3n * a[0] * a[0] * inv(2n * a[1])); }
  else l = mod((b[1] - a[1]) * inv(b[0] - a[0]));
  const x = mod(l * l - a[0] - b[0]);
  return [x, mod(l * (a[0] - x) - a[1])];
}
function pmul(k, p = Gp) { let r = null; for (k = mod(k, Nn); k; k >>= 1n) { if (k & 1n) r = padd(r, p); p = padd(p, p); } return r; }
function powmod(b, e, m) { let r = 1n; b = mod(b, m); for (; e; e >>= 1n) { if (e & 1n) r = r * b % m; b = b * b % m; } return r; }
const hex2b = (x) => Uint8Array.from(x.match(/../g).map((b) => parseInt(b, 16)));
const b2hex = (b) => [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
const big = (b) => BigInt(`0x${b2hex(b) || "0"}`);
const be32 = (n) => hex2b(n.toString(16).padStart(64, "0"));
function decompress(b) {
  const x = big(b.slice(1)), y2 = mod(x ** 3n + 7n);
  let y = powmod(y2, (Pm + 1n) / 4n, Pm);
  if (mod(y * y) !== y2) throw new Error("not on the curve");
  if ((y & 1n) !== BigInt(b[0] & 1)) y = Pm - y;
  return [x, y];
}
const compress = (p) => Uint8Array.from([2 + Number(p[1] & 1n), ...be32(p[0])]);
const cat = (...as) => { const o = new Uint8Array(as.reduce((n, a) => n + a.length, 0)); let i = 0; for (const a of as) { o.set(a, i); i += a.length; } return o; };
const sha256 = async (b) => new Uint8Array(await crypto.subtle.digest("SHA-256", b));
async function taggedHash(tag, msg) { const t = await sha256(new TextEncoder().encode(tag)); return sha256(cat(t, t, msg)); }

function ripemd160(msg) {
  const r1 = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13];
  const r2 = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11];
  const s1 = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6];
  const s2 = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11];
  const K1 = [0, 0x5a827999, 0x6ed9eba1, 0x8f1bbcdc, 0xa953fd4e], K2 = [0x50a28be6, 0x5c4dd124, 0x6d703ef3, 0x7a6d76e9, 0];
  const f = (j, x, y, z) => (j < 16 ? x ^ y ^ z : j < 32 ? (x & y) | (~x & z) : j < 48 ? (x | ~y) ^ z : j < 64 ? (x & z) | (y & ~z) : x ^ (y | ~z));
  const rol = (x, n) => (x << n) | (x >>> (32 - n));
  const len = msg.length, padLen = ((len + 8) >> 6) * 64 + 64;
  const m = new Uint8Array(padLen); m.set(msg); m[len] = 0x80;
  const bits = len * 8; for (let i = 0; i < 8; i++) m[padLen - 8 + i] = Math.floor(bits / 2 ** (8 * i)) & 0xff;
  let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
  for (let o = 0; o < padLen; o += 64) {
    const X = []; for (let i = 0; i < 16; i++) X.push(m[o + 4 * i] | (m[o + 4 * i + 1] << 8) | (m[o + 4 * i + 2] << 16) | (m[o + 4 * i + 3] << 24));
    let [a, b, c, d, e] = [h0, h1, h2, h3, h4], [A, B, C, Dd, E] = [h0, h1, h2, h3, h4];
    for (let j = 0; j < 80; j++) {
      let t = (rol((a + f(j, b, c, d) + X[r1[j]] + K1[j >> 4]) | 0, s1[j]) + e) | 0;
      [a, e, d, c, b] = [e, d, rol(c, 10), b, t];
      t = (rol((A + f(79 - j, B, C, Dd) + X[r2[j]] + K2[j >> 4]) | 0, s2[j]) + E) | 0;
      [A, E, Dd, C, B] = [E, Dd, rol(C, 10), B, t];
    }
    const t = (h1 + c + Dd) | 0; h1 = (h2 + d + E) | 0; h2 = (h3 + e + A) | 0; h3 = (h4 + a + B) | 0; h4 = (h0 + b + C) | 0; h0 = t;
  }
  const out = new Uint8Array(20);
  [h0, h1, h2, h3, h4].forEach((w, i) => { for (let k = 0; k < 4; k++) out[4 * i + k] = (w >>> (8 * k)) & 0xff; });
  return out;
}
async function base58check(payload) {
  const ck = (await sha256(await sha256(payload))).slice(0, 4);
  const b = cat(payload, ck), A = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  let n = big(b), s = "";
  while (n > 0n) { s = A[Number(n % 58n)] + s; n /= 58n; }
  for (const x of b) { if (x) break; s = `1${s}`; }
  return s;
}

function renderKey() {
  const k = D.payout_key;
  $("#keybox").replaceChildren(h("dl", { class: "facts" },
    h("dt", {}, "payment"), h("dd", { class: "mono" }, `${short(k.txid, 10)}:${k.vout}`),
    h("dt", {}, "P (revealed by the payment)"), h("dd", { class: "mono" }, k.P),
    h("dt", {}, "t = tagged_hash(\"IOB/payout-key\", txid ‖ vout ‖ P)"), h("dd", { class: "mono" }, k.t),
    h("dt", {}, "P′ = P + t·G"), h("dd", { class: "mono" }, k.P_prime),
    h("dt", {}, "payout address, P2PKH(P′)"), h("dd", {}, h("a", { href: addrUrl(k.address), target: "_blank", rel: "noopener", class: "mono" }, k.address)),
    h("dt", {}, "who can spend it"), h("dd", {}, "whoever knows p, at p + t mod n (", h("code", {}, "python -m iob payout-key --wif-stdin"), ")")));
}

async function recompute() {
  const k = D.payout_key, out = $("#verify");
  const row = (ok, label, val) => h("div", {}, pill(ok ? "match" : "differs", ok ? "ok" : "bad"), h("span", {}, label, " ", h("span", { class: "mono" }, short(val, 12))));
  try {
    const t0 = performance.now();
    const P = hex2b(k.P);
    const msg = cat(hex2b(k.txid).reverse(), Uint8Array.from([k.vout & 255, (k.vout >> 8) & 255, (k.vout >> 16) & 255, (k.vout >>> 24) & 255]), P);
    const t = big(await taggedHash(k.tag, msg)) % Nn;
    const Pp = compress(padd(decompress(P), pmul(t)));
    const addr = await base58check(cat(Uint8Array.of(0x6f), ripemd160(await sha256(Pp))));
    out.replaceChildren(
      row(t.toString(16).padStart(64, "0") === k.t, "t", t.toString(16).padStart(64, "0")),
      row(b2hex(Pp) === k.P_prime, "P′", b2hex(Pp)),
      row(addr === k.address, "address", addr),
      h("div", { class: "pill quiet" }, `computed in ${Math.round(performance.now() - t0)} ms with this page's own secp256k1, SHA-256 and RIPEMD-160`));
  } catch (e) {
    out.replaceChildren(h("div", {}, pill("error", "bad"), String(e)));
  }
}

// ---------------------------------------------------------------------------------------------
// refusals

function renderRefusals() {
  const rows = [];
  for (const p of D.probes) {
    rows.push({ where: "testnet4", ok: !p.allowed, what: `${p.instance}: ${(p.case || "disprove with the accept label").replaceAll("_", " ")}`, why: p.reject_reason || "accepted" });
  }
  for (const c of D.regtest.checks || []) {
    rows.push({ where: "regtest rehearsal", ok: c.ok, what: c.check, why: c.detail || (c.ok ? "as expected" : "unexpected") });
  }
  rows.push({ where: "SP1 guest", ok: true, what: "the compressed Nova key in place of the pinned raw key", why: "guest exits 1: refused before any statement" });
  $("#refusals").replaceChildren(...rows.map((r) => h("div", { class: "ref" },
    h("div", {}, pill(r.ok ? "as expected" : "unexpected", r.ok ? "ok" : "bad"), h("div", { class: "where" }, r.where)),
    h("div", {}, h("div", {}, r.what), h("div", { class: "why mono" }, r.why)))));
}

// ---------------------------------------------------------------------------------------------

async function main() {
  await loadData();
  $("#explorer-link").href = D.explorer;
  $("#source-link").href = D.source;
  $("#generated").textContent = `refreshed ${D.generated_at.replace("T", " ").replace("Z", " UTC")}`;
  renderResults();
  renderTimeline();
  renderTabs();
  renderClaim();
  renderKey();
  renderRefusals();
  renderFlow();
  $("#recompute").addEventListener("click", recompute);
  pollChain();
  setInterval(pollChain, 60_000);
  window.addEventListener("resize", renderFlow);
}
main();
