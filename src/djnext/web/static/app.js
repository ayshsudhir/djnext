// djnext web page: talks to the local server (only on this computer).
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let STATUS = null, SET = null, CHART = null, MOOD = null;
const RATINGS = {};

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (${res.status})`);
  return data;
}

function banner(text, kind = "") {
  const b = $("#banner");
  if (!text) return b.classList.add("hidden");
  b.className = `banner ${kind}`;
  b.innerHTML = text;
}

// ---------- tabs ----------
document.querySelectorAll("nav button").forEach((btn) => btn.addEventListener("click", () => showTab(btn.dataset.tab)));
function showTab(name) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${name}`));
  if (name === "rate") { renderRate(); loadFeedback(); }
  if (name === "discover") loadDiscover();
}

// ---------- status ----------
async function loadStatus() {
  try {
    STATUS = await api("/api/status");
  } catch (e) {
    banner(esc(e.message), "err");
    return;
  }
  renderLists();
  renderMusic();
  renderSettings();
  $("#curve").innerHTML = STATUS.curves.map((c) => `<option ${c === STATUS.default_curve ? "selected" : ""}>${esc(c)}</option>`).join("");
  const st = STATUS.style;
  $("#style-hint").textContent = `(${st.bpm_min}–${st.bpm_max} BPM)`;
  if (!STATUS.soundcloud) {
    banner(`Welcome! Start in <b>My music</b>: paste your SoundCloud profile link so the tool knows your likes and playlists.
            <button onclick="showTab('music')">Go to My music</button>`);
  } else banner("");
}

function renderLists() {
  const items = [...STATUS.soundcloud_lists, ...STATUS.rekordbox_lists];
  if (!items.length) {
    $("#lists").innerHTML = `<p class="muted">No lists yet. Sync SoundCloud in <b>My music</b>, or the whole rekordbox collection will be used.</p>`;
    return;
  }
  $("#lists").innerHTML = items.map((l) => `
    <label class="list-item ${l.ready ? "" : "disabled"}" title="${l.ready} of ${l.total} tracks are analysed in rekordbox">
      <input type="checkbox" value="${esc(l.key)}" ${l.ready ? "checked" : "disabled"}>
      ${l.key.startsWith("sc:") ? "☁︎ " : ""}${esc(l.name)} <small>${l.ready}/${l.total} ready</small>
    </label>`).join("");
}

// ---------- moods ----------
async function loadMoods() {
  try {
    const r = await api("/api/moods");
    const cards = [{ key: null, emoji: "🎛️", name: "My style", ask: "Your BPM range + favourite artists, from the lists below.", count: null }, ...r.moods];
    $("#moods").innerHTML = cards.map((m) => `
      <button class="mood ${m.key === MOOD ? "on" : ""} ${m.count !== null && m.count < 8 ? "thin" : ""}" data-key="${m.key ?? ""}"
              title="${esc((m.examples || []).join(", "))}">
        <span class="em">${m.emoji}</span><b>${esc(m.name)}</b><span>${esc(m.ask)}</span>
        ${m.count !== null ? `<span>${m.count} tracks${m.count < 8 ? " (too few for a set)" : ""}</span>` : ""}
      </button>`).join("");
    document.querySelectorAll(".mood").forEach((b) => b.addEventListener("click", () => {
      MOOD = b.dataset.key || null;
      loadMoods();
      $("#lists").classList.toggle("hidden", !!MOOD);
      $("#use-style").closest("label").classList.toggle("hidden", !!MOOD);
      $("#curve").closest("label").classList.toggle("hidden", !!MOOD);
      $("#mood-hint").textContent = MOOD ? "Moods pick from all your analysed SoundCloud tracks and use their own energy shape." : "";
    }));
  } catch (e) { $("#moods").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

$("#moods-push").addEventListener("click", async () => {
  $("#moods-push").disabled = true;
  try {
    const r = await api("/api/moods/push", {});
    $("#moods-push-status").innerHTML = `<div class="banner ok">Created under <b>Playlists → ${esc(r.folder)}</b>: ` +
      Object.entries(r.playlists).map(([k, v]) => `${esc(k)} (${v})`).join(", ") + "</div>";
  } catch (e) { $("#moods-push-status").innerHTML = `<div class="banner err">${esc(e.message)}</div>`; }
  $("#moods-push").disabled = false;
});

// ---------- make a set ----------
$("#make").addEventListener("click", async () => {
  const lists = [...document.querySelectorAll("#lists input:checked")].map((i) => i.value);
  const onlySc = lists.length > 0 && lists.every((l) => l.startsWith("sc:"));
  $("#make").disabled = true;
  $("#make-status").textContent = "Building your set…";
  try {
    SET = await api("/api/set", {
      mood: MOOD, lists, source: onlySc ? "soundcloud" : null, length: +$("#length").value,
      curve: $("#curve").value, use_style: $("#use-style").checked,
    });
    Object.keys(RATINGS).forEach((k) => delete RATINGS[k]);
    renderSet();
    $("#make-status").textContent = "";
  } catch (e) {
    $("#make-status").textContent = e.message;
  } finally {
    $("#make").disabled = false;
  }
});

function energyClass(e, t) { const d = Math.abs(e - t); return d <= 1.5 ? "e-good" : d <= 3 ? "e-warn" : "e-bad"; }

function renderSet() {
  $("#result").classList.remove("hidden");
  const n = SET.tracks.length;
  const harmonic = SET.report[0].match(/(\d+)\/(\d+)/);
  $("#chips").innerHTML = [
    `<span class="chip">${n} tracks · ${Math.round(SET.length_min)} min · ${esc(SET.curve)}</span>`,
    harmonic ? `<span class="chip">harmonic mixes <b>${harmonic[1]}/${harmonic[2]}</b></span>` : "",
    `<span class="chip"><b>${SET.vs_random_pct}%</b> smoother than random</span>`,
    SET.bpm_guessed ? `<span class="chip">energy guessed from BPM for ${SET.bpm_guessed}/${n} (star-rate tracks to improve)</span>` : "",
  ].join("");
  $("#set-notes").innerHTML = [...SET.notes, ...SET.report.slice(1)].map((t) => `<li>${esc(t)}</li>`).join("");
  drawChart();
  $("#tracks").innerHTML = SET.tracks.map((t) => `
    <details class="track">
      <summary>
        <span class="n">${t.n}</span><span class="t">${t.time}</span>
        <span class="name"><b>${esc(t.title)}</b><span>${esc(t.artist)}</span></span>
        <span class="bpm">${t.bpm} BPM</span><span class="key">${esc(t.key)}</span>
        <span class="en ${energyClass(t.energy, t.target)}">E ${Math.round(t.energy)}</span>
        ${t.technique ? `<span class="tech ${t.technique_id}">${esc(t.technique)}</span>` : `<span class="tech">opener</span>`}
      </summary>
      <div class="how">${t.n === 1 ? `<p class="muted">Start the set with this track.</p>` : howHtml(t)}</div>
    </details>`).join("");
  renderRate();
}

function howHtml(t) {
  let h = `<p class="muted">${esc(t.transition)}</p>`;
  if (t.timing.length) h += `<h4>When</h4><ul>${t.timing.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  h += `<h4>How</h4><ol>${t.steps.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>`;
  if (t.advice_notes.length) h += `<ul class="muted">${t.advice_notes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  if (t.alternative) h += `<p class="muted">Alternative: ${esc(t.alternative)}</p>`;
  if (t.bridge) h += `<p>Smoother route: play <b>${esc(t.bridge)}</b> in between.</p>`;
  return h;
}

function drawChart() {
  if (!window.Chart) return;
  const steps = SET.tracks.map((t) => ({ x: t.start_min, y: t.energy }));
  if (steps.length) steps.push({ x: SET.length_min, y: steps[steps.length - 1].y });
  if (CHART) CHART.destroy();
  CHART = new Chart($("#chart"), {
    type: "line",
    data: { datasets: [
      { label: "target energy", data: SET.curve_points, borderColor: "#ff6a3d", pointRadius: 0, tension: 0.3 },
      { label: "your set", data: steps, borderColor: "#3d9bff", stepped: true, pointRadius: 2 },
    ] },
    options: {
      maintainAspectRatio: false, parsing: false,
      scales: {
        x: { type: "linear", min: 0, max: SET.length_min, title: { display: true, text: "minutes", color: "#9aa3b2" }, ticks: { color: "#9aa3b2" }, grid: { color: "#2a2f3a" } },
        y: { min: 0, max: 10.5, title: { display: true, text: "energy", color: "#9aa3b2" }, ticks: { color: "#9aa3b2" }, grid: { color: "#2a2f3a" } },
      },
      plugins: { legend: { labels: { color: "#e8eaf0" } } },
    },
  });
}

// ---------- push to rekordbox ----------
$("#push").addEventListener("click", async () => {
  $("#push").disabled = true;
  $("#push-status").innerHTML = `<p class="muted">Writing to rekordbox…</p>`;
  try {
    const r = await api("/api/push", { name: $("#set-name").value.trim() || null, cues: $("#with-cues").checked });
    $("#push-status").innerHTML = `<div class="banner ok">Done! Open rekordbox → left sidebar → <b>Playlists</b> (rekordbox's own, at the top, not the SoundCloud section) → <b>${esc(r.folder)}</b> → <b>${esc(r.name)}</b> (${r.tracks} tracks).
      ${r.cues ? `<br>Added ${r.cues} hot cues (E = cue here, F = drop / swap basses, G = start next track).` : ""}
      ${r.cues_skipped ? `<br>${r.cues_skipped} cues skipped (no free pad).` : ""}
      <br><span class="small">Backup of your library from just before: ${esc(r.backup)}</span></div>`;
  } catch (e) {
    $("#push-status").innerHTML = `<div class="banner err">${esc(e.message)}</div>`;
  } finally {
    $("#push").disabled = false;
  }
});

// ---------- my music ----------
function renderMusic() {
  const sc = STATUS.soundcloud;
  if (sc) $("#sc-user").value = `https://soundcloud.com/${sc.user}`;
  $("#sc-status").textContent = sc ? `Last synced ${sc.synced_at.replace("T", " ").slice(0, 16)}` : "";
  $("#sc-lists").innerHTML = STATUS.soundcloud_lists.length ? `<table class="fb"><tr><th>List</th><th>On SoundCloud</th><th>Ready in rekordbox</th></tr>
    ${STATUS.soundcloud_lists.map((l) => `<tr><td>${esc(l.name)}</td><td>${l.total}</td><td>${l.ready}</td></tr>`).join("")}</table>
    <p class="muted">${STATUS.not_analysed} tracks still need analysing in rekordbox (see below).</p>` : "";
  const bs = STATUS.library.by_source;
  $("#library").textContent = `${STATUS.library.total} tracks: ` + Object.entries(bs).map(([k, v]) => `${v} ${k}`).join(", ") +
    (STATUS.rekordbox_running ? " · rekordbox is open" : " · rekordbox is closed");
}

$("#sc-sync").addEventListener("click", async () => {
  $("#sc-sync").disabled = true;
  $("#sc-status").textContent = "Syncing… this can take a minute.";
  try {
    STATUS = await api("/api/soundcloud/sync", { user: $("#sc-user").value });
    renderLists(); renderMusic(); banner("SoundCloud synced. Now go to <b>Make a set</b>.", "ok");
  } catch (e) {
    $("#sc-status").textContent = e.message;
  } finally {
    $("#sc-sync").disabled = false;
  }
});

$("#reload").addEventListener("click", async () => {
  $("#reload").disabled = true;
  try { STATUS = await api("/api/reload", {}); renderLists(); renderMusic(); } catch (e) { banner(esc(e.message), "err"); }
  $("#reload").disabled = false;
});

$("#show-missing").addEventListener("click", async () => {
  const r = await api("/api/soundcloud/missing");
  $("#missing").innerHTML = r.tracks.map((t) => `<li>${t.url ? `<a href="${esc(t.url)}" target="_blank" style="color:#9fd0ff">${esc(t.label)}</a>` : esc(t.label)}</li>`).join("") || "<li>None, everything is analysed.</li>";
});

// ---------- discover ----------
function renderDiscover(d) {
  if (!d.tracks || !d.tracks.length) {
    $("#discover-list").innerHTML = `<p class="muted">Nothing yet. Press <b>Find new tracks</b> (takes about a minute).</p>`;
    return;
  }
  $("#discover-status").textContent = d.made_at ? `Last search ${d.made_at.replace("T", " ").slice(0, 16)}` : "";
  $("#discover-list").innerHTML = d.tracks.map((c) => `
    <div class="disc">
      <div><b>${esc(c.title)}</b><span class="why">${esc(c.uploader)} · ${esc(c.why)}</span></div>
      <span class="mood-g small">${esc(c.mood_guess || "")}</span>
      <span class="likes small muted">${(c.likes || 0).toLocaleString()} ♥</span>
      <a class="open" href="${esc(c.url)}" target="_blank" rel="noopener">Open ↗</a>
    </div>`).join("");
}

async function loadDiscover() {
  try { renderDiscover(await api("/api/discover")); } catch (e) { $("#discover-status").textContent = e.message; }
}

$("#discover-run").addEventListener("click", async () => {
  $("#discover-run").disabled = true;
  $("#discover-status").textContent = "Searching SoundCloud… about a minute.";
  try { renderDiscover(await api("/api/discover", {})); }
  catch (e) { $("#discover-status").textContent = e.message; }
  $("#discover-run").disabled = false;
});

// ---------- rate ----------
function renderRate() {
  if (!SET || SET.tracks.length < 2) return;
  $("#rate-list").innerHTML = SET.tracks.slice(1).map((t) => {
    const prev = SET.tracks[t.n - 2];
    const r = RATINGS[t.n] || {};
    return `<div class="rate-row" data-pos="${t.n}">
      <div><b>${t.n - 1} → ${t.n}</b> ${esc(prev.title)} → ${esc(t.title)} <span class="muted small">(${esc(t.technique || "")})</span></div>
      <div class="thumbs"><button data-v="good" class="${r.good === true ? "on-good" : ""}">👍</button><button data-v="bad" class="${r.good === false ? "on-bad" : ""}">👎</button></div>
      <input placeholder="note, e.g. vocals clashed" value="${esc(r.note || "")}">
    </div>`;
  }).join("");
  document.querySelectorAll(".rate-row").forEach((row) => {
    const pos = +row.dataset.pos;
    row.querySelectorAll(".thumbs button").forEach((b) => b.addEventListener("click", () => {
      RATINGS[pos] = { ...(RATINGS[pos] || {}), good: b.dataset.v === "good" };
      renderRate();
    }));
    row.querySelector("input").addEventListener("input", (e) => { RATINGS[pos] = { ...(RATINGS[pos] || {}), note: e.target.value }; });
  });
}

$("#rate-save").addEventListener("click", async () => {
  const ratings = Object.entries(RATINGS).filter(([, r]) => r.good !== undefined)
    .map(([pos, r]) => ({ position: +pos, good: r.good, note: r.note || "" }));
  try {
    const r = await api("/api/rate", { ratings, overall: +$("#overall").value, overall_note: $("#overall-note").value });
    $("#rate-status").textContent = `Saved ${r.saved} ratings. Thanks!`;
    loadFeedback();
  } catch (e) { $("#rate-status").textContent = e.message; }
});

async function loadFeedback() {
  const f = await api("/api/feedback");
  if (!f.rated) return ($("#feedback").textContent = "No ratings yet.");
  const titles = { technique: "By mixing technique", key: "By key move", tempo: "By tempo change" };
  let h = `<p><b>${f.good}/${f.rated}</b> transitions rated good (${Math.round((100 * f.good) / f.rated)}%)</p>`;
  for (const [g, buckets] of Object.entries(f.groups)) {
    h += `<b>${titles[g]}</b><table class="fb">` + Object.entries(buckets).map(([name, [good, n]]) =>
      `<tr><td>${esc(name.replace("_", " "))}</td><td>${good}/${n}</td><td class="${good / n >= 0.75 ? "e-good" : good / n >= 0.5 ? "e-warn" : "e-bad"}">${Math.round((100 * good) / n)}%</td></tr>`).join("") + "</table>";
  }
  if (f.bad.length) h += `<b>Didn't work</b><ul>${f.bad.map(([p, n]) => `<li>${esc(p)}${n ? ` <span class="muted">(${esc(n)})</span>` : ""}</li>`).join("")}</ul>`;
  $("#feedback").innerHTML = h;
}

// ---------- settings ----------
function renderSettings() {
  const st = STATUS.style;
  $("#bpm-min").value = st.bpm_min; $("#bpm-max").value = st.bpm_max;
  $("#skill").value = STATUS.skill || "beginner";
  $("#favs").value = st.favourite_artists.join("\n"); $("#excl").value = st.exclude_genres.join("\n");
}

$("#save-style").addEventListener("click", async () => {
  const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
  try {
    STATUS = await api("/api/settings", {
      skill: $("#skill").value, bpm_min: +$("#bpm-min").value, bpm_max: +$("#bpm-max").value,
      favourite_artists: lines($("#favs").value), exclude_genres: lines($("#excl").value),
    });
    $("#style-status").textContent = "Saved.";
    $("#style-hint").textContent = `(${STATUS.style.bpm_min}–${STATUS.style.bpm_max} BPM)`;
  } catch (e) { $("#style-status").textContent = e.message; }
});

$("#undo").addEventListener("click", async () => {
  const b = await api("/api/backups");
  if (!b.backups.length) return ($("#undo-status").textContent = "Nothing to undo yet.");
  if (!confirm(`Put rekordbox back to how it was at ${b.backups[0]}? (rekordbox must be closed)`)) return;
  try { const r = await api("/api/undo", {}); $("#undo-status").textContent = `Done: back to ${r.restored}. You can open rekordbox now.`; loadStatus(); }
  catch (e) { $("#undo-status").textContent = e.message; }
});

$("#remove-cues").addEventListener("click", async () => {
  if (!confirm("Remove all hot cues made by djnext from every track? Your own cues stay.")) return;
  try { const r = await api("/api/cues/remove", {}); $("#cues-status").textContent = `Removed ${r.removed} cues.`; }
  catch (e) { $("#cues-status").textContent = e.message; }
});

loadStatus().then(loadMoods);
