// djnext Live: what's playing + crowd knob -> what to play next. Talks to the local server only.
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const LEVELS = { 1: ["💤", "Dead"], 2: ["😐", "Meh"], 3: ["🙂", "Vibing"], 4: ["🙌", "Into it"], 5: ["🔥", "Going off"] };
let STATE = null, CROWD = 3, SESSION_START = null;

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (${res.status})`);
  return data;
}
function toast(text, kind = "ok", ms = 4000) {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.innerHTML = text;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// ---------- knob ----------
const ANG = (lvl) => -135 + (lvl - 1) * 67.5;  // 5 positions over 270 degrees, like a real rotary knob
const pt = (a, r) => [100 + r * Math.sin((a * Math.PI) / 180), 100 - r * Math.cos((a * Math.PI) / 180)];
function arc(a0, a1, r = 80) {
  const [x0, y0] = pt(a0, r), [x1, y1] = pt(a1, r);
  return `M${x0.toFixed(2)},${y0.toFixed(2)} A${r},${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)},${y1.toFixed(2)}`;
}
$(".knob .arc-bg").setAttribute("d", arc(-135, 135));
$("#ticks").innerHTML = [1, 2, 3, 4, 5].map((l) => {
  const [x, y] = pt(ANG(l), 97);
  return `<text class="tick" x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="middle">${l}</text>`;
}).join("");
$("#crowd-steps").innerHTML = [1, 2, 3, 4, 5].map((l) => `<button data-l="${l}" title="${LEVELS[l][1]} (key ${l})">${LEVELS[l][0]}</button>`).join("");

function drawKnob(lvl) {
  $(".knob .arc-on").setAttribute("d", arc(-135, Math.max(ANG(lvl), -134)));
  $("#pointer").style.transform = `rotate(${ANG(lvl)}deg)`;
  $("#knob-emoji").textContent = LEVELS[lvl][0];
  $("#crowd-name").textContent = LEVELS[lvl][1];
  $("#knob").setAttribute("aria-valuenow", lvl);
  $$("#crowd-steps button").forEach((b) => b.classList.toggle("on", +b.dataset.l === lvl));
}

let sendTimer = null;
function setCrowd(lvl) {
  lvl = Math.max(1, Math.min(5, lvl));
  if (lvl === CROWD) return;
  CROWD = lvl;
  drawKnob(lvl);
  clearTimeout(sendTimer);  // one reading per settled knob position, not one per pixel of dragging
  sendTimer = setTimeout(async () => {
    try { STATE = await api("/api/live/crowd", { level: CROWD }); startClock(); loadPicks(); }
    catch (e) { toast(esc(e.message), "err"); }
  }, 350);
}

(() => {
  const k = $("#knob");
  let start = null;
  k.addEventListener("pointerdown", (e) => { start = { x: e.clientX, y: e.clientY, lvl: CROWD }; k.setPointerCapture(e.pointerId); });
  k.addEventListener("pointermove", (e) => {
    if (!start) return;
    const d = (start.y - e.clientY) + (e.clientX - start.x);  // up or right = turn it up
    setCrowd(start.lvl + Math.round(d / 32));
  });
  const end = () => { start = null; };
  k.addEventListener("pointerup", end);
  k.addEventListener("pointercancel", end);
  let wheelAcc = 0;
  k.addEventListener("wheel", (e) => {
    e.preventDefault();
    wheelAcc += e.deltaY;
    if (Math.abs(wheelAcc) > 40) { setCrowd(CROWD + (wheelAcc < 0 ? 1 : -1)); wheelAcc = 0; }
  }, { passive: false });
  k.addEventListener("keydown", (e) => {
    if (e.key === "ArrowUp" || e.key === "ArrowRight") { setCrowd(CROWD + 1); e.preventDefault(); }
    if (e.key === "ArrowDown" || e.key === "ArrowLeft") { setCrowd(CROWD - 1); e.preventDefault(); }
  });
  $$("#crowd-steps button").forEach((b) => b.addEventListener("click", () => setCrowd(+b.dataset.l)));
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.metaKey || e.ctrlKey) return;
    if (/^[1-5]$/.test(e.key)) setCrowd(+e.key);
  });
})();

// ---------- now playing ----------
function renderNow() {
  const t = STATE && STATE.current;
  $("#np-track").classList.toggle("hidden", !t);
  $("#q").placeholder = t ? "Playing something else? Search here" : "What's playing? Type a track or artist";
  if (!t) return;
  $("#np-title").textContent = t.title;
  $("#np-artist").textContent = t.artist;
  $("#np-meta").innerHTML = `<span class="tag">${t.bpm} BPM</span><span class="tag">${esc(t.key)}</span>
    <span class="ebar" title="energy ${Math.round(t.energy)}/10"><i style="width:${t.energy * 10}%"></i></span>
    <span class="tag">track ${STATE.played + 1} of your set</span>`;
}

async function playNow(id) {
  try {
    STATE = await api("/api/live/now", { track_id: id });
    $("#q").value = ""; hideHits();
    renderNow(); startClock(); loadPicks();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { toast(esc(e.message), "err"); }
}

let searchTimer = null, HITS = [], SEL = 0;
$("#q").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const q = $("#q").value.trim();
    if (!q) return hideHits();
    HITS = (await api(`/api/live/search?q=${encodeURIComponent(q)}`)).tracks;
    SEL = 0;
    renderHits();
  }, 150);
});
$("#q").addEventListener("keydown", (e) => {
  if (!HITS.length) return;
  if (e.key === "ArrowDown") { SEL = Math.min(SEL + 1, HITS.length - 1); renderHits(); e.preventDefault(); }
  if (e.key === "ArrowUp") { SEL = Math.max(SEL - 1, 0); renderHits(); e.preventDefault(); }
  if (e.key === "Enter") playNow(HITS[SEL].id);
  if (e.key === "Escape") hideHits();
});
function renderHits() {
  const h = $("#hits");
  h.classList.toggle("hidden", !HITS.length && !$("#q").value.trim());
  h.innerHTML = HITS.length ? HITS.map((t, i) => `<button data-id="${esc(t.id)}" class="${i === SEL ? "sel" : ""}">
      <b>${esc(t.title)}</b><span>${esc(t.artist)} · ${t.bpm} BPM · ${esc(t.key)}</span></button>`).join("")
    : `<button disabled><span>No match in your tracks.</span></button>`;
  h.querySelectorAll("button[data-id]").forEach((b) => b.addEventListener("click", () => playNow(b.dataset.id)));
}
function hideHits() { HITS = []; $("#hits").classList.add("hidden"); }
document.addEventListener("click", (e) => { if (!e.target.closest(".search")) hideHits(); });

// ---------- picks ----------
function keyTag(why) {
  const m = why.match(/(\S+->\S+) (perfect|harmonic|ok|clash)/);
  return m ? `<span class="tag key-${m[2]}">${esc(m[1].replace("->", "→"))} ${m[2]}</span>` : "";
}
function deltaBox(d) {
  const cls = d > 0.4 ? "up" : d < -0.4 ? "down" : "flat";
  const arrow = cls === "up" ? "↑" : cls === "down" ? "↓" : "→";
  return `<span class="delta ${cls}" title="energy change">${arrow}<small>${d > 0 ? "+" : ""}${d.toFixed(1)}</small></span>`;
}

async function loadPicks() {
  let s;
  try { s = await api("/api/live/suggest"); } catch (e) { return toast(esc(e.message), "err"); }
  if (STATE && STATE.current) {
    $("#need-head").textContent = `${s.emoji} ${s.need}`;
    $("#need-tip").textContent = s.tip;
  }
  if (!s.picks.length) {
    $("#picks").innerHTML = `<div class="empty-picks">${STATE && STATE.current ? "Nothing fits. Try another crowd setting." : "🎧 Search for the track that's playing, above."}</div>`;
    return;
  }
  $("#picks").innerHTML = s.picks.map((p, i) => `
    <details class="pick">
      <summary>${deltaBox(p.delta)}
        <span class="t"><b>${esc(p.title)}</b><span class="a">${esc(p.artist)}</span>
          <span class="chips"><span class="tag">${p.bpm} BPM</span>${keyTag(p.why)}
            ${p.pleaser ? `<span class="tag star">★ crowd-pleaser</span>` : ""}
            ${p.learned ? `<span class="tag ${/dipped/.test(p.learned) ? "learn-bad" : "learn"}">${/dipped/.test(p.learned) ? "📉" : "🚀"} ${esc(p.learned)}</span>` : ""}
            <span class="tech ${esc(p.technique_id)}">${esc(p.technique)}</span></span></span>
      </summary>
      <div class="body">
        ${p.timing.length ? `<h4>WHEN</h4><ul>${p.timing.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        <h4>HOW</h4><ol>${p.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>
        <button class="primary play" data-id="${esc(p.id)}">▶ I'm playing this now</button>
      </div>
    </details>`).join("");
  $$(".pick .play").forEach((b) => b.addEventListener("click", () => playNow(b.dataset.id)));
}

// ---------- clock ----------
function startClock() {
  if (STATE && STATE.session) SESSION_START = new Date(STATE.session);
  $("#rec").classList.toggle("on", !!SESSION_START);
}
setInterval(() => {
  if (!SESSION_START) return;
  const s = Math.max(0, Math.floor((Date.now() - SESSION_START) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, "0");
  $("#clock").textContent = h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}, 1000);

// ---------- review ----------
function reviewChart(r) {
  const W = 520, H = 150, L = 26, R = 8, T = 8, B = 22;
  const len = Math.max(r.length_min, 1);
  const x = (m) => L + (m / len) * (W - L - R), y = (c) => T + (1 - (c - 1) / 4) * (H - T - B);
  let g = "";
  for (let c = 1; c <= 5; c++) g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(c)}" y2="${y(c)}"/><text class="axis" x="2" y="${y(c) + 4}">${LEVELS[c][0]}</text>`;
  const step = len > 90 ? 30 : len > 30 ? 15 : 5;
  for (let m = 0; m <= len; m += step) g += `<text class="axis" x="${x(m)}" y="${H - 6}" text-anchor="middle">${m}m</text>`;
  let d = "";
  r.timeline.forEach((p, i) => {
    const nx = i + 1 < r.timeline.length ? r.timeline[i + 1].min : len;
    d += `${i ? "L" : "M"}${x(p.min).toFixed(1)},${y(p.crowd).toFixed(1)}L${x(nx).toFixed(1)},${y(p.crowd).toFixed(1)}`;
  });
  const marks = r.tracks.map((t) => `<line x1="${x(t.min)}" x2="${x(t.min)}" y1="${T}" y2="${H - B}" stroke="rgba(255,255,255,.12)" stroke-dasharray="2 3"><title>${esc(t.label)}</title></line>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}">
    <defs><linearGradient id="rvl" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#5b6cff"/><stop offset=".5" stop-color="#3ee0a0"/><stop offset="1" stop-color="#ff3d5a"/></linearGradient></defs>
    ${g}${marks}<path d="${d}" fill="none" stroke="url(#rvl)" stroke-width="3" stroke-linejoin="round"/></svg>`;
}

function renderReview(r) {
  if (!r.timeline.length && !r.tracks.length) {
    $("#rv-body").innerHTML = `<p class="muted">Nothing logged yet. Pick what's playing and turn the crowd knob as the night goes.</p>`;
    return;
  }
  const avg = r.avg_crowd ? LEVELS[Math.round(r.avg_crowd)] : null;
  const li = (t, cls) => `<li>${esc(t.label)} <span class="${cls}">${t.lift > 0 ? "+" : ""}${t.lift}</span></li>`;
  $("#rv-body").innerHTML = `
    <div class="stats">
      <div class="stat hl"><b>${r.tracks.length}</b><span>tracks</span></div>
      <div class="stat"><b>${avg ? avg[0] : "–"}</b><span>${avg ? `on average: ${avg[1].toLowerCase()}` : "no readings"}</span></div>
      <div class="stat"><b>${r.peak_share}%</b><span>of the time they were into it</span></div>
    </div>
    <h3>Crowd through the set</h3>
    <div class="rvchart">${r.timeline.length ? reviewChart(r) : `<p class="muted small">Turn the knob during the set to see this.</p>`}</div>
    ${r.lifted.length ? `<h3>🚀 Tracks that lifted the room</h3><ol>${r.lifted.map((t) => li(t, "up")).join("")}</ol>` : ""}
    ${r.dipped.length ? `<h3>📉 Where it dipped</h3><ol>${r.dipped.map((t) => li(t, "dn")).join("")}</ol>` : ""}
    <div id="learned"></div>
    <p class="tiny muted">${r.length_min} min · started ${esc(r.started.replace("T", " ").slice(0, 16))}</p>`;
}

async function loadLearned() {
  try {
    const m = await api("/api/live/learned");
    const el = $("#learned");
    if (!el) return;
    if (!m.sets) {
      el.innerHTML = `<h3>🧠 What djnext is learning</h3><p class="muted small">Turn the knob during your sets. After each set, djnext learns which tracks lift your crowd and puts them higher in the picks.</p>`;
      return;
    }
    const list = (xs) => `<ol>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>`;
    el.innerHTML = `<h3>🧠 What djnext has learned</h3>
      <p class="muted small">From ${m.sets} set${m.sets === 1 ? "" : "s"}: ${m.tracks} tracks and ${m.transitions} transitions. These now shape your picks.</p>
      ${m.best.length ? `<p class="small"><b>Your crowd lifters</b></p>${list(m.best)}` : ""}
      ${m.rescue.length ? `<p class="small"><b>Rescue tracks</b> <span class="muted">(brought a dead room back)</span></p>${list(m.rescue)}` : ""}
      ${m.worst.length ? `<p class="small"><b>Picked less often now</b></p>${list(m.worst)}` : ""}`;
  } catch { /* the review still works without it */ }
}

async function openReview(session) {
  $("#review").classList.remove("hidden");
  try {
    const [r, list] = await Promise.all([api(`/api/live/review${session ? `?session=${encodeURIComponent(session)}` : ""}`), api("/api/live/sessions")]);
    renderReview(r);
    loadLearned();
    $("#rv-sessions").innerHTML = `<option value="">This set</option>` + list.sessions.map((s) =>
      `<option value="${esc(s)}" ${s === session ? "selected" : ""}>Set of ${esc(s.replace("T", " ").replace(/-(\d\d)-(\d\d)$/, ":$1"))}</option>`).join("");
  } catch (e) { $("#rv-body").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}
$("#open-review").addEventListener("click", () => openReview());
$("#rv-close").addEventListener("click", () => $("#review").classList.add("hidden"));
$("#rv-sessions").addEventListener("change", (e) => openReview(e.target.value || undefined));
$("#end-set").addEventListener("click", async () => {
  if (!confirm("End this set? It's saved, and you can look at its review any time.")) return;
  try {
    renderReview(await api("/api/live/end", {}));
    loadLearned();
    STATE = await api("/api/live/state");
    SESSION_START = null; $("#clock").textContent = "0:00"; $("#rec").classList.remove("on");
    CROWD = STATE.crowd; drawKnob(CROWD); renderNow(); loadPicks();
    $("#need-head").textContent = "Pick what's playing to get started";
    toast("Set saved. Have a good one! 🎉");
  } catch (e) { toast(esc(e.message), "err"); }
});

// ---------- Mac app: keep the window on top of rekordbox ----------
window.addEventListener("pywebviewready", async () => {
  const pin = $("#pin");
  pin.classList.remove("hidden");
  pin.classList.toggle("on", await window.pywebview.api.is_on_top());
  pin.addEventListener("click", async () => pin.classList.toggle("on", await window.pywebview.api.toggle_on_top()));
});

// ---------- other window ----------
$("#open-main").addEventListener("click", () => {
  if (window.pywebview) window.pywebview.api.open_main();
  else window.open("/", "djnext-main");
});

// ---------- start ----------
(async () => {
  try { STATE = await api("/api/live/state"); }
  catch (e) { $("#need-head").textContent = "Couldn't open your library"; $("#need-tip").textContent = e.message; return; }
  CROWD = STATE.crowd;
  drawKnob(CROWD);
  renderNow(); startClock(); loadPicks();
  if (!STATE.current) $("#q").focus();
})();
