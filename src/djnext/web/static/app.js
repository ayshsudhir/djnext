// djnext web page: talks to the local server (only on this computer).
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let STATUS = null, SET = null, MOOD = null, LENGTH = 60, RB_OPEN = null, OVERALL = 0;
const RATINGS = {};

// Mood colours (gradient per mood card).
const HUES = {
  "": ["#8b6cff", "#3ec8ff"], warmup: ["#ffb347", "#ff6a88"], pregame: ["#ffd86b", "#ff7a45"],
  drunk: ["#ff3d8b", "#b44bff"], banging: ["#ff5a36", "#ff1f5a"], afters: ["#5b6cff", "#9b4bff"],
  groovy_techno: ["#3ec8ff", "#3ee0a0"],
};
const PALETTE = [["#ff7a45", "#ff3d8b"], ["#3ec8ff", "#8b6cff"], ["#3ee0a0", "#3ec8ff"], ["#ffd86b", "#ff7a45"]];

// Style presets for the setup and Settings: BPM range + genres to leave out.
const COMMON_OUT = ["rock", "hip-hop", "hip hop", "rap", "pop", "r&b", "classical", "country", "metal", "jazz", "folk", "soundtrack", "reggae", "indie"];
const PRESETS = [
  { name: "Tech house", bpm: [122, 130], out: [...COMMON_OUT, "ambient"] },
  { name: "Tech house + groovy techno", bpm: [122, 134], out: [...COMMON_OUT, "ambient"] },
  { name: "House / deep house", bpm: [118, 126], out: COMMON_OUT },
  { name: "Melodic techno", bpm: [118, 128], out: COMMON_OUT },
  { name: "Techno", bpm: [126, 140], out: [...COMMON_OUT, "ambient"] },
  { name: "Drum & bass", bpm: [165, 178], out: COMMON_OUT },
  { name: "A bit of everything", bpm: [70, 180], out: [] },
];

// ---------- helpers ----------
async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (${res.status})`);
  return data;
}

function toast(text, kind = "ok", ms = 4500) {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.innerHTML = text;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function banner(html, kind = "") {
  const b = $("#banner");
  if (!html) return b.classList.add("hidden");
  b.className = `banner ${kind}`;
  b.innerHTML = html;
}

// Runs an action with a spinner on the button; errors become a red toast.
async function busy(btn, fn) {
  btn.classList.add("loading");
  btn.disabled = true;
  document.body.classList.add("busy");
  try { return await fn(); }
  catch (e) { toast(esc(e.message), "err", 7000); }
  finally { btn.classList.remove("loading"); btn.disabled = false; document.body.classList.remove("busy"); }
}

function when(s) { return s ? s.replace("T", " at ").slice(0, 19) : ""; }

// ---------- tabs ----------
$$("#nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${name}`));
  if (name === "rate") { renderRate(); loadFeedback(); }
  if (name === "discover") loadDiscover();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
window.showTab = showTab;

// ---------- rekordbox open/closed (polled) ----------
async function pollRekordbox() {
  try {
    const r = await api("/api/rekordbox");
    RB_OPEN = r.running;
  } catch { RB_OPEN = null; }
  const pill = $("#rb-pill");
  pill.className = `pill ${RB_OPEN === null ? "" : RB_OPEN ? "open" : "closed"}`;
  pill.querySelector(".txt").textContent = RB_OPEN === null ? "rekordbox ?" : RB_OPEN ? "rekordbox is open" : "rekordbox closed";
  const quit = $("#step-quit");
  quit.classList.toggle("done", RB_OPEN === false);
  quit.classList.toggle("todo", RB_OPEN === true);
  quit.lastChild.textContent = RB_OPEN ? "Quit rekordbox (it's open now)" : "Quit rekordbox";
}
setInterval(pollRekordbox, 4000);

// ---------- status ----------
async function loadStatus() {
  try {
    STATUS = await api("/api/status");
  } catch (e) {
    banner(`<b>Couldn't open your rekordbox library.</b> ${esc(e.message)} Make sure rekordbox is installed and has been opened at least once, then reload this page.`, "err");
    return false;
  }
  renderLists();
  renderMusic();
  renderSettings();
  $("#curve").innerHTML = STATUS.curves.map((c) => `<option ${c === STATUS.default_curve ? "selected" : ""}>${esc(c)}</option>`).join("");
  $("#style-hint").textContent = `(${STATUS.style.bpm_min}–${STATUS.style.bpm_max} BPM)`;
  if (STATUS.soundcloud && STATUS.not_analysed > 0) {
    const ready = STATUS.soundcloud_lists.filter((l) => l.used).reduce((a, l) => a + l.ready, 0);
    banner(`<span>💡 <b>${STATUS.not_analysed}</b> tracks from your SoundCloud lists aren't in your rekordbox Collection yet, so djnext can't suggest them (it can use ${ready} now). Adding a whole list takes one drag.</span>
            <button onclick="showTab('music')">Show me how</button>`);
  } else banner("");
  return true;
}

function renderLists() {
  const items = [...STATUS.soundcloud_lists, ...STATUS.rekordbox_lists];
  if (!items.length) {
    $("#lists").innerHTML = `<p class="muted small">No lists yet, so your whole rekordbox collection is used.</p>`;
    return;
  }
  $("#lists").innerHTML = items.map((l) => `
    <label class="list-item ${l.ready ? "" : "disabled"}" title="${l.ready} of ${l.total} tracks are analysed in rekordbox">
      <input type="checkbox" value="${esc(l.key)}" ${l.ready ? "checked" : "disabled"}>
      ${l.key.startsWith("sc:") ? "☁︎ " : "📁 "}${esc(l.name)} <small>${l.ready}/${l.total}</small>
    </label>`).join("");
}

// ---------- moods ----------
async function loadMoods() {
  try {
    const r = await api("/api/moods");
    const cards = [{ key: null, emoji: "🎛️", name: "My style", ask: "Your whole range, with your favourite artists first.", count: null }, ...r.moods];
    $("#moods").innerHTML = cards.map((m, i) => {
      const [h1, h2] = HUES[m.key ?? ""] || PALETTE[i % PALETTE.length];
      const thin = m.count !== null && m.count < 8;
      return `<button class="mood ${(m.key ?? null) === MOOD ? "on" : ""} ${thin ? "thin" : ""}" data-key="${esc(m.key ?? "")}"
                style="--h1:${h1};--h2:${h2}" title="${esc((m.examples || []).length ? "e.g. " + m.examples.join(", ") : "")}">
        <span class="em">${m.emoji}</span><b>${esc(m.name)}</b><span class="ask">${esc(m.ask)}</span>
        <span class="count">${m.count === null ? "Choose lists in More options" : thin ? `Only ${m.count} tracks, too few` : `${m.count} tracks`}</span>
      </button>`;
    }).join("");
    $$(".mood").forEach((b) => b.addEventListener("click", () => {
      MOOD = b.dataset.key || null;
      $$(".mood").forEach((x) => x.classList.toggle("on", x === b));
      $("#lists-wrap").classList.toggle("hidden", !!MOOD);
      $("#curve-row").classList.toggle("hidden", !!MOOD);
      $("#mood-hint").textContent = MOOD ? "Moods pick from all your analysed tracks and have their own energy shape, so there's nothing to choose here." : "";
    }));
  } catch (e) { $("#moods").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

$$("#length button").forEach((b) => b.addEventListener("click", () => {
  LENGTH = +b.dataset.v;
  $$("#length button").forEach((x) => x.classList.toggle("on", x === b));
}));

// ---------- make a set ----------
$("#make").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  spinning(true);
  const minShow = new Promise((r) => setTimeout(r, 1200));  // long enough to see, never a flicker
  try { await Promise.all([makeSet(), minShow]); } finally { spinning(false); }
}));

async function makeSet() {
  const lists = $$("#lists input:checked").map((i) => i.value);
  const onlySc = lists.length > 0 && lists.every((l) => l.startsWith("sc:"));
  SET = await api("/api/set", {
    mood: MOOD, lists, source: onlySc ? "soundcloud" : null, length: LENGTH,
    curve: $("#curve").value, use_style: $("#use-style").checked,
  });
  Object.keys(RATINGS).forEach((k) => delete RATINGS[k]);
  OVERALL = 0;
  renderSet();
  $("#result").classList.remove("hidden");
  $("#result .section-title").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSet() {
  const n = SET.tracks.length;
  const harmonic = SET.report[0].match(/(\d+)\/(\d+)/);
  $("#stats").innerHTML = [
    `<div class="stat hl"><b>${n}</b><span>tracks</span></div>`,
    `<div class="stat"><b>${Math.round(SET.length_min)} min</b><span>${esc(SET.curve)}</span></div>`,
    harmonic ? `<div class="stat"><b>${harmonic[1]}/${harmonic[2]}</b><span>mixes in key</span></div>` : "",
    `<div class="stat"><b>${SET.vs_random_pct}%</b><span>smoother than a random order</span></div>`,
    SET.bpm_guessed ? `<div class="stat warn"><b>Energy is guessed</b><span>for ${SET.bpm_guessed} of ${n} tracks. Star-rate them in rekordbox for better results.</span></div>` : "",
  ].join("");
  $("#set-notes").innerHTML = [...SET.notes, ...SET.report.slice(1)].map((t) => `<li>${esc(t)}</li>`).join("");
  drawChart();
  $("#tracks").innerHTML = SET.tracks.map((t) => `
    <details class="track" id="trk-${t.n}">
      <summary>
        <span class="n">${t.n}</span>
        <span class="name"><b>${esc(t.title)}</b><span>${esc(t.artist)} · ${t.time}</span></span>
        <span class="meta">
          <span class="tag">${t.bpm} BPM</span><span class="tag">${esc(t.key)}</span>
          <span class="ebar" title="energy ${Math.round(t.energy)}/10"><i style="width:${Math.min(100, t.energy * 10)}%"></i></span>
          ${t.technique ? `<span class="tech ${esc(t.technique_id)}">${esc(t.technique)}</span>` : `<span class="tech">▶ Opener</span>`}
        </span>
      </summary>
      <div class="how">${t.n === 1 ? `<p class="muted">Start the set with this track. Load it on deck 1 and press play.</p>` : howHtml(t)}</div>
    </details>`).join("");
  renderRate();
}

function howHtml(t) {
  let h = `<p class="muted">${esc(t.transition)}</p>`;
  if (t.timing.length) h += `<h4>⏱ When</h4><ul>${t.timing.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  h += `<h4>🎚 How</h4><ol>${t.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>`;
  if (t.advice_notes.length) h += `<ul class="muted">${t.advice_notes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  if (t.alternative) h += `<p class="muted">Or instead: ${esc(t.alternative)}</p>`;
  if (t.bridge) h += `<div class="bridge">💡 Smoother route: play <b>${esc(t.bridge)}</b> in between.</div>`;
  return h;
}

// Energy chart, drawn as SVG (no internet needed).
function drawChart() {
  const W = 820, H = 250, L = 34, R = 12, T = 12, B = 30;
  const len = SET.length_min || 1;
  const x = (m) => L + (m / len) * (W - L - R);
  const y = (e) => T + (1 - e / 10) * (H - T - B);
  let grid = "";
  for (const e of [0, 2.5, 5, 7.5, 10]) grid += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(e)}" y2="${y(e)}"/>`;
  grid += `<text class="axis" x="${L - 8}" y="${y(10) + 4}" text-anchor="end">peak</text><text class="axis" x="${L - 8}" y="${y(0) + 4}" text-anchor="end">chill</text>`;
  const step = len > 90 ? 20 : len > 45 ? 10 : 5;
  for (let m = 0; m <= len + 0.01; m += step) grid += `<text class="axis" x="${x(m)}" y="${H - 8}" text-anchor="middle">${Math.round(m)} min</text>`;
  const target = SET.curve_points.map((p, i) => `${i ? "L" : "M"}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join("");
  let line = "";
  SET.tracks.forEach((t, i) => {
    const x0 = x(t.start_min), x1 = x(i + 1 < SET.tracks.length ? SET.tracks[i + 1].start_min : len);
    line += `${i ? "L" : "M"}${x0.toFixed(1)},${y(t.energy).toFixed(1)}L${x1.toFixed(1)},${y(t.energy).toFixed(1)}`;
  });
  const area = `${line}L${x(len)},${y(0)}L${x(0)},${y(0)}Z`;
  const dots = SET.tracks.map((t) => `<circle class="dotpt" data-n="${t.n}" cx="${x(t.start_min)}" cy="${y(t.energy)}" r="4.5" fill="#fff" stroke="#ff3d8b" stroke-width="2">
      <title>${t.n}. ${esc(t.title)} (energy ${Math.round(t.energy)}) at ${t.time}</title></circle>`).join("");
  $("#chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Energy chart">
    <defs>
      <linearGradient id="ln" x1="0" x2="1"><stop offset="0" stop-color="#ff7a45"/><stop offset="1" stop-color="#ff3d8b"/></linearGradient>
      <linearGradient id="ar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff3d8b" stop-opacity=".35"/><stop offset="1" stop-color="#ff3d8b" stop-opacity="0"/></linearGradient>
    </defs>
    ${grid}
    <path d="${area}" fill="url(#ar)"/>
    <path d="${target}" fill="none" stroke="rgba(255,255,255,.6)" stroke-width="2" stroke-dasharray="6 5"/>
    <path d="${line}" fill="none" stroke="url(#ln)" stroke-width="3" stroke-linejoin="round"/>
    ${dots}
  </svg>`;
  $$("#chart .dotpt").forEach((d) => d.addEventListener("click", () => {
    const el = $(`#trk-${d.dataset.n}`);
    el.open = true;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
  }));
}

// ---------- push to rekordbox ----------
$("#push").addEventListener("click", (ev) => {
  if (RB_OPEN) return toast("rekordbox is still open. Quit it first (Cmd+Q on a Mac), then press Send again.", "err", 7000);
  busy(ev.currentTarget, async () => {
    const r = await api("/api/push", { name: $("#set-name").value.trim() || null, cues: $("#with-cues").checked });
    $("#push-status").innerHTML = `<div class="banner ok"><div>🎉 <b>It's in rekordbox!</b> Open rekordbox → left sidebar → <b>Playlists</b>
      (rekordbox's own, at the top, not SoundCloud) → <b>${esc(r.folder)}</b> → <b>${esc(r.name)}</b> (${r.tracks} tracks).
      ${r.cues ? `<br>Added ${r.cues} hot cues.` : ""}${r.cues_skipped ? ` ${r.cues_skipped} skipped because the pad was already used.` : ""}
      <br><span class="small muted">If anything looks wrong: Settings → Undo last change.</span></div></div>`;
  });
});

// ---------- my music ----------
function renderMusic() {
  const sc = STATUS.soundcloud;
  if (sc) $("#sc-user").value = `https://soundcloud.com/${sc.user}`;
  $("#sc-status").textContent = sc ? `Last synced ${when(sc.synced_at)}` : "Not connected yet.";
  $("#sc-lists").innerHTML = STATUS.soundcloud_lists.length ? `<table class="sc-table">
      <tr><th>List</th><th>Use for DJing</th><th>Ready to use</th><th></th></tr>
      ${STATUS.soundcloud_lists.map((l) => `<tr class="${l.used ? "" : "off"}"><td>${esc(l.name)}</td>
        <td><label class="switch" title="Off = djnext ignores this list when counting tracks to add"><input type="checkbox" data-list="${esc(l.name)}" ${l.used ? "checked" : ""}><span></span></label></td>
        <td><div class="progress"><i style="width:${l.total ? (100 * l.ready) / l.total : 0}%"></i></div></td>
        <td class="num">${l.ready} of ${l.total}</td></tr>`).join("")}
    </table>` : "";
  $$("#sc-lists input[data-list]").forEach((cb) => cb.addEventListener("change", async () => {
    const skip = $$("#sc-lists input[data-list]").filter((x) => !x.checked).map((x) => x.dataset.list);
    try { STATUS = await api("/api/soundcloud/lists", { skip }); await loadStatus(); }
    catch (e) { toast(esc(e.message), "err"); }
  }));
  $("#sc-help").open = !sc;
  $("#missing-count").textContent = STATUS.not_analysed ? `(${STATUS.not_analysed} tracks waiting)` : "";
  $("#missing-card").classList.toggle("hidden", !sc || !STATUS.not_analysed);
  const bs = STATUS.library.by_source;
  $("#library").innerHTML = `<div class="stat"><b>${STATUS.library.total}</b><span>tracks in total</span></div>` +
    Object.entries(bs).map(([k, v]) => `<div class="stat"><b>${v}</b><span>${esc(k === "local" ? "files" : k)}</span></div>`).join("");
}

async function syncSoundCloud(user) {
  STATUS = await api("/api/soundcloud/sync", { user });
  renderLists(); renderMusic();
  loadMoods();
  return STATUS;
}

$("#sc-sync").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  $("#sc-status").textContent = "Syncing… this can take a minute.";
  await syncSoundCloud($("#sc-user").value);
  await loadStatus();
  toast("SoundCloud synced 🎉");
}));

$("#reload").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  STATUS = await api("/api/reload", {});
  await loadStatus(); loadMoods();
  toast("Library reloaded.");
}));

$("#show-missing").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  const r = await api("/api/soundcloud/missing");
  if (!r.tracks.length) { $("#missing").innerHTML = "<p>None: everything in the lists you use is ready.</p>"; return; }
  const groups = {};
  r.tracks.forEach((t) => (groups[t.list || "other"] ||= []).push(t));
  $("#missing").innerHTML = Object.entries(groups).map(([name, ts]) => `
    <details><summary><b>${esc(name)}</b> <span class="muted">${ts.length} track${ts.length === 1 ? "" : "s"} to add</span></summary>
      <ol>${ts.map((t) => `<li>${t.url ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.label)}</a>` : esc(t.label)}</li>`).join("")}</ol>
    </details>`).join("");
}));

$("#moods-push").addEventListener("click", (ev) => {
  if (RB_OPEN) return toast("Quit rekordbox first, then press the button again.", "err");
  busy(ev.currentTarget, async () => {
    const r = await api("/api/moods/push", {});
    $("#moods-push-status").innerHTML = `<div class="banner ok" style="margin-top:14px">Done! In rekordbox: <b>Playlists → ${esc(r.folder)}</b>.<br>` +
      Object.entries(r.playlists).map(([k, v]) => `${esc(k)} (${v})`).join(" · ") + "</div>";
  });
});

// ---------- discover ----------
function renderDiscover(d) {
  if (!d.tracks || !d.tracks.length) {
    $("#discover-list").innerHTML = `<div class="card empty" style="grid-column:1/-1">🔭<p>Nothing yet. Press <b>Find new tracks</b>. It takes about a minute.</p></div>`;
    return;
  }
  $("#discover-status").textContent = d.made_at ? `Last search ${when(d.made_at)}` : "";
  $("#discover-list").innerHTML = d.tracks.map((c) => `
    <div class="disc">
      <b>${esc(c.title)}</b><span class="who">${esc(c.uploader)}</span><span class="why">${esc(c.why)}</span>
      <div class="foot">
        ${c.mood_guess ? `<span class="tag">${esc(c.mood_guess)}</span>` : ""}
        <span class="tag">${(c.likes || 0).toLocaleString()} ♥</span>
        <a class="open" href="${esc(c.url)}" target="_blank" rel="noopener">Open on SoundCloud ↗</a>
      </div>
    </div>`).join("");
}

async function loadDiscover() {
  try { renderDiscover(await api("/api/discover")); } catch (e) { $("#discover-status").textContent = e.message; }
}

$("#discover-run").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  $("#discover-status").textContent = "Searching SoundCloud… about a minute.";
  renderDiscover(await api("/api/discover", {}));
}));

// ---------- rate ----------
function renderRate() {
  if (!SET || SET.tracks.length < 2) return;
  $("#rate-overall").classList.remove("hidden");
  $("#rate-list").innerHTML = SET.tracks.slice(1).map((t) => {
    const prev = SET.tracks[t.n - 2];
    const r = RATINGS[t.n] || {};
    return `<div class="rate-row" data-pos="${t.n}">
      <div class="pair"><span class="muted small">${t.n - 1} → ${t.n} · ${esc(t.technique || "")}</span><br>
        <b>${esc(prev.title)}</b><span class="arrow">→</span><b>${esc(t.title)}</b></div>
      <div class="thumbs"><button data-v="good" class="${r.good === true ? "on-good" : ""}" title="Sounded good">👍</button><button data-v="bad" class="${r.good === false ? "on-bad" : ""}" title="Didn't work">👎</button></div>
      <input placeholder="Note, e.g. vocals clashed" value="${esc(r.note || "")}">
    </div>`;
  }).join("");
  $$(".rate-row").forEach((row) => {
    const pos = +row.dataset.pos;
    row.querySelectorAll(".thumbs button").forEach((b) => b.addEventListener("click", () => {
      RATINGS[pos] = { ...(RATINGS[pos] || {}), good: b.dataset.v === "good" };
      row.querySelectorAll(".thumbs button").forEach((x) => x.className = x === b ? (b.dataset.v === "good" ? "on-good" : "on-bad") : "");
    }));
    row.querySelector("input").addEventListener("input", (e) => { RATINGS[pos] = { ...(RATINGS[pos] || {}), note: e.target.value }; });
  });
  renderStars();
}

function renderStars() {
  $("#stars").innerHTML = [1, 2, 3, 4, 5].map((i) => `<button data-v="${i}" class="${i <= OVERALL ? "on" : ""}" title="${i} star${i > 1 ? "s" : ""}">★</button>`).join("");
  $$("#stars button").forEach((b) => b.addEventListener("click", () => { OVERALL = +b.dataset.v; renderStars(); }));
}

$("#rate-save").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  const ratings = Object.entries(RATINGS).filter(([, r]) => r.good !== undefined)
    .map(([pos, r]) => ({ position: +pos, good: r.good, note: r.note || "" }));
  const r = await api("/api/rate", { ratings, overall: OVERALL, overall_note: $("#overall-note").value });
  toast(`Saved ${r.saved} rating${r.saved === 1 ? "" : "s"}. Thanks, djnext learns from this!`);
  loadFeedback();
}));

async function loadFeedback() {
  const f = await api("/api/feedback");
  if (!f.rated) return ($("#feedback").textContent = "No ratings yet.");
  const titles = { technique: "By mixing technique", key: "By key move", tempo: "By tempo change" };
  let h = `<div class="stats"><div class="stat hl"><b>${Math.round((100 * f.good) / f.rated)}%</b><span>of ${f.rated} transitions sounded good</span></div></div>`;
  for (const [g, buckets] of Object.entries(f.groups)) {
    h += `<b>${titles[g] || esc(g)}</b><table class="fb">` + Object.entries(buckets).map(([name, [good, n]]) =>
      `<tr><td>${esc(name.replace("_", " "))}</td><td>${good}/${n}</td><td class="${good / n >= 0.75 ? "e-good" : good / n >= 0.5 ? "e-warn" : "e-bad"}">${Math.round((100 * good) / n)}%</td></tr>`).join("") + "</table>";
  }
  if (f.bad.length) h += `<b>Didn't work</b><ul>${f.bad.map(([p, n]) => `<li>${esc(p)}${n ? ` <span class="muted">(${esc(n)})</span>` : ""}</li>`).join("")}</ul>`;
  $("#feedback").innerHTML = h;
}

// ---------- tag inputs (artists, genres) ----------
function tagInput(el, placeholder) {
  let items = [];
  const render = () => {
    el.innerHTML = items.map((t, i) => `<span class="t">${esc(t)}<button data-i="${i}" title="Remove">×</button></span>`).join("") +
      `<input placeholder="${esc(placeholder)}">`;
    el.querySelectorAll(".t button").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); items.splice(+b.dataset.i, 1); render(); }));
    const inp = el.querySelector("input");
    const add = () => { const v = inp.value.replace(/,$/, "").trim(); if (v && !items.includes(v)) items.push(v); inp.value = ""; render(); el.querySelector("input").focus(); };
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
      else if (e.key === "Backspace" && !inp.value && items.length) { items.pop(); render(); el.querySelector("input").focus(); }
    });
    inp.addEventListener("blur", () => { if (inp.value.trim()) add(); });
  };
  el.addEventListener("click", () => el.querySelector("input").focus());
  render();
  return { get: () => { const v = el.querySelector("input").value.trim(); return v && !items.includes(v) ? [...items, v] : [...items]; },
           set: (arr) => { items = [...arr]; render(); } };
}
const FAVS = tagInput($("#favs"), "Type an artist, press Enter");
const EXCL = tagInput($("#excl"), "Type a genre, press Enter");
const WIZ_FAVS = tagInput($("#wiz-favs"), "e.g. Fisher, press Enter");

function presetButtons(el, onPick) {
  el.innerHTML = PRESETS.map((p, i) => `<button data-i="${i}">${esc(p.name)} <small>${p.bpm[0]}–${p.bpm[1]}</small></button>`).join("");
  el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    el.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    onPick(PRESETS[+b.dataset.i]);
  }));
}
function markPreset(el, st) {
  el.querySelectorAll("button").forEach((b) => {
    const p = PRESETS[+b.dataset.i];
    b.classList.toggle("on", p.bpm[0] === st.bpm_min && p.bpm[1] === st.bpm_max);
  });
}

function choice(el, value) {
  el.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.v === value));
}
function choiceValue(el) { return (el.querySelector("button.on") || {}).dataset?.v || "beginner"; }
$$(".choice").forEach((el) => el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => choice(el, b.dataset.v))));

// ---------- settings ----------
presetButtons($("#presets"), (p) => { $("#bpm-min").value = p.bpm[0]; $("#bpm-max").value = p.bpm[1]; EXCL.set(p.out); });

function renderSettings() {
  const st = STATUS.style;
  $("#bpm-min").value = st.bpm_min; $("#bpm-max").value = st.bpm_max;
  choice($("#skill"), STATUS.skill || "beginner");
  FAVS.set(st.favourite_artists); EXCL.set(st.exclude_genres);
  markPreset($("#presets"), st);
}

async function saveSettings(extra = {}) {
  STATUS = await api("/api/settings", {
    skill: choiceValue($("#skill")), bpm_min: +$("#bpm-min").value, bpm_max: +$("#bpm-max").value,
    favourite_artists: FAVS.get(), exclude_genres: EXCL.get(), ...extra,
  });
  $("#style-hint").textContent = `(${STATUS.style.bpm_min}–${STATUS.style.bpm_max} BPM)`;
  renderSettings();
  loadMoods();
}

$("#save-style").addEventListener("click", (ev) => busy(ev.currentTarget, async () => { await saveSettings(); toast("Saved. Your moods are updated."); }));

$("#undo").addEventListener("click", async (ev) => {
  const b = await api("/api/backups");
  if (!b.backups.length) return toast("Nothing to undo yet: djnext hasn't changed rekordbox.", "ok");
  if (RB_OPEN) return toast("Quit rekordbox first, then press Undo again.", "err");
  if (!confirm(`Put rekordbox back to how it was before djnext's last change (${b.backups[0]})?`)) return;
  busy(ev.currentTarget, async () => {
    await api("/api/undo", {});
    toast("Done! rekordbox is back to how it was. You can open it now.");
    loadStatus();
  });
});

$("#remove-cues").addEventListener("click", (ev) => {
  if (RB_OPEN) return toast("Quit rekordbox first.", "err");
  if (!confirm("Remove every hot cue djnext added? Your own cues stay.")) return;
  busy(ev.currentTarget, async () => { const r = await api("/api/cues/remove", {}); toast(`Removed ${r.removed} cues.`); });
});

$("#rerun-setup").addEventListener("click", () => openWizard());

// ---------- first-run setup ----------
let WIZ_STEP = 0, WIZ_PRESET = null;
function wizGo(i) {
  WIZ_STEP = i;
  $$(".wiz-step").forEach((s) => s.classList.toggle("on", +s.dataset.step === i));
  $$(".wiz-dots span").forEach((d, j) => d.classList.toggle("on", j <= i));
}
function openWizard() {
  $("#wizard").classList.remove("hidden");
  const lib = STATUS && STATUS.library;
  const note = $("#wiz-lib");
  if (lib) { note.className = "wiz-note ok"; note.textContent = `✓ Found your rekordbox library: ${lib.total} tracks.`; }
  else { note.className = "wiz-note err"; note.textContent = "Couldn't find your rekordbox library. Is rekordbox installed and opened at least once?"; }
  if (STATUS && STATUS.soundcloud) $("#wiz-sc").value = `https://soundcloud.com/${STATUS.soundcloud.user}`;
  if (STATUS) { WIZ_FAVS.set(STATUS.onboarded ? STATUS.style.favourite_artists : []); choice($("#wiz-skill"), STATUS.skill || "beginner"); }
  wizGo(0);
}
$$("#wizard [data-next]").forEach((b) => b.addEventListener("click", () => wizGo(WIZ_STEP + 1)));
$$("#wizard [data-back]").forEach((b) => b.addEventListener("click", () => wizGo(WIZ_STEP - 1)));
$$("#wizard [data-skip]").forEach((b) => b.addEventListener("click", () => wizGo(WIZ_STEP + 1)));
presetButtons($("#wiz-presets"), (p) => { WIZ_PRESET = p; });

$("#wiz-sc-go").addEventListener("click", async (ev) => {
  const v = $("#wiz-sc").value.trim();
  const st = $("#wiz-sc-status");
  if (!v) { st.className = "wiz-note err"; st.textContent = "Paste your profile link first (or press I don't use SoundCloud)."; return; }
  st.className = "wiz-note"; st.textContent = "Reading your likes and playlists… this can take a minute.";
  const btn = ev.currentTarget;
  btn.classList.add("loading");
  try {
    const s = await syncSoundCloud(v);
    const total = s.soundcloud_lists.reduce((a, l) => a + l.total, 0);
    st.className = "wiz-note ok"; st.textContent = `✓ Found ${total} tracks in ${s.soundcloud_lists.length} lists.`;
    setTimeout(() => wizGo(2), 900);
  } catch (e) {
    st.className = "wiz-note err"; st.textContent = e.message;
  } finally { btn.classList.remove("loading"); }
});

$("#wiz-done").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  const p = WIZ_PRESET;
  STATUS = await api("/api/settings", {
    skill: choiceValue($("#wiz-skill")),
    bpm_min: p ? p.bpm[0] : STATUS.style.bpm_min, bpm_max: p ? p.bpm[1] : STATUS.style.bpm_max,
    favourite_artists: WIZ_FAVS.get(), exclude_genres: p ? p.out : STATUS.style.exclude_genres, onboarded: true,
  });
  $("#wizard").classList.add("hidden");
  if (window.pywebview) { window.pywebview.api.open_main(); return; }  // Mac app: grow from setup size to the set builder
  await loadStatus();
  loadMoods();
  toast("All set! Pick a mood and press <b>Make my set</b>.", "ok", 6000);
}));

// ---------- DJ touches ----------
function drawWave() {  // a rekordbox-style waveform strip behind the heading
  let h = "";
  for (let i = 0; i < 140; i++) {
    const v = 0.25 + 0.75 * Math.abs(Math.sin(i * 0.37) * Math.cos(i * 0.11) + 0.35 * Math.sin(i * 1.7));
    h += `<i class="${i < 46 ? "played" : ""}" style="height:${Math.min(100, v * 85)}%"></i>`;
  }
  $("#wave").innerHTML = h;
}
const SPIN_MSGS = ["Digging through your crates…", "Matching keys…", "Lining up the drops…", "Shaping the energy curve…"];
function spinning(on) {
  $("#spinning").classList.toggle("hidden", !on);
  clearInterval(spinning.t);
  if (on) {
    let i = 0;
    $("#spin-msg").textContent = SPIN_MSGS[0];
    spinning.t = setInterval(() => { $("#spin-msg").textContent = SPIN_MSGS[++i % SPIN_MSGS.length]; }, 900);
  }
}

// ---------- live window ----------
$("#open-live").addEventListener("click", () => {
  if (window.pywebview) window.pywebview.api.open_live();  // the Mac app: a small window next to rekordbox
  else window.open("/live", "djnext-live", "width=420,height=900");
});

// ---------- start ----------
(async () => {
  drawWave();
  pollRekordbox();
  const ok = await loadStatus();
  if (!ok) return;
  loadMoods();
  if (!STATUS.onboarded) openWizard();
})();
