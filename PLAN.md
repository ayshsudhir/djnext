# Next Song Recommender for DJing (DDJ-FLX4 + rekordbox)

## Context
You want a personal tool that looks at your songs (your SoundCloud likes and your rekordbox library) and tells you **what to play next**, or gives you a **whole set in playing order** for the DDJ-FLX4. It's a pet project, so it should cost nothing.

**My take on your idea:** start with the "simple" version you described: *give it a list of songs, get back an ordered set.* That's the right POC. The hard parts of the "big" version (reading what's playing live in rekordbox, pulling SoundCloud likes through the API) are hard **access** problems, not hard **logic** problems. The ordering logic is the core either way, so build it first and plug in the live inputs later.

On approval, the first step is to copy this plan into the project as `PLAN.md`.

---

## 1. How it decides the order (the core logic)
DJs order tracks with a few rules. We turn each rule into a "transition cost" between two tracks and look for the cheapest path through the list.

| Factor | Rule | Where the data comes from |
|---|---|---|
| **Key (harmonic mixing)** | Camelot wheel: same key, ±1 step (8A→9A), or switching A↔B (8A→8B) mixes cleanly | rekordbox analysis (already in your library) |
| **BPM** | Keep the jump within about ±6% (the FLX4 tempo slider range); half or double time is allowed | rekordbox analysis |
| **Energy** | Follow the **"DJ Set Energy" curve** (see 1a): warm-up → build → first peak → breather → final peak | estimated from audio (POC: BPM + genre tag + your own 1–10 rating) |
| **Vibe/genre** | Avoid jarring genre jumps | tags/genre from rekordbox, SoundCloud, Last.fm |
| **Freshness** | No repeats; spread out tracks by the same artist | the set itself |

### 1a. Target energy trajectory (the default set shape)
The whole set should follow this curve. It comes from your cheat sheet and is drawn for a 1-hour set:

```
energy
 10 |                        ★ first peak                  ★ final peak
  9 |                      .-'-.                         .-'
  8 |                    .'     '.                     .'
  7 |                 .-'         '.          .--.-.-'
  6 |              .-'              '.     .-'  rebuild
  5 |           .-'                   '-.-'   breather
  4 |       .●'  build tension
  3 |    .-'
  2 | .-'  warm-up
  0 +----+----+----+----+----+----+----> minutes
    0   10   20   30   40   50   60
```

| Phase | Time (1 h set) | Target energy (0–10) | What happens |
|---|---|---|---|
| Warm up | 0–10 min | 1.5 → 4 | lower energy, groove, get people in the mood |
| Build | 10–25 min | 4 → ~7.5 | gradually increase energy, add layers |
| First peak | 25–35 min | ~9 at ~28 min | big tracks and drops |
| Breather / reset | 35–45 min | down to ~5.3 at ~40 min | lower energy, keep people dancing |
| Final build & peak | 45–60 min | 6.6 at 50 min → ~9 at 60 min | build anticipation, finish strong |

**How it's used:**
- Stored in `config.yaml` as control points `(time_fraction, energy)`: `(0, 1.5) (0.17, 4) (0.33, 6.5) (0.47, 8.8) (0.65, 5.3) (0.83, 6.6) (1.0, 8.8)`, joined with smooth interpolation (monotone cubic, via `numpy`/`scipy`, or plain linear in the POC).
- **Time-based, not track-count-based:** each track's slot sits at the cumulative play time (track length minus about 30–60 s of mix overlap), divided by the total set length. Because the curve uses fractions of the set, the same shape stretches to a 30-, 60- or 90-minute set.
- Cost term: `w_energy × (track_energy − target_energy(t))²`. Energy *moves* also count: the cost also penalises going **down** during build phases and going **up** during the breather, so the shape holds even when the right energy levels aren't available.
- **Peak placement:** your highest-energy tracks (your "bangers") are held back for the ~28-min and ~60-min slots, so the sequencer doesn't spend them early.
- Track energy needs to be on the same 0–10 scale: POC = your rekordbox star rating / a manual tag, or an estimate from BPM + genre; Phase 3 = Essentia energy/danceability, rescaled to 0–10 across your library.
- Other curves (e.g. "warmup only", "peak-time") are just different point lists in `config.yaml`; this one is the default (`--curve classic-1h`).

**Algorithm:**
- Cost(A→B) = weighted sum of key distance + BPM gap + energy deviation from the target curve at B's time slot + genre distance.
- POC: **greedy** (start track → always pick the cheapest next track), then improve the order with **2-opt** swaps. This is a TSP-style problem, but at 20–200 tracks greedy plus 2-opt runs in milliseconds.
- "Next song" mode is the same cost function: given the current track, return the top 5 cheapest next tracks, with a reason for each ("8A→9A, +2 BPM, energy up").

---

## 2. Data sources: what's realistic

### rekordbox (best data source, use it first)
- rekordbox has already analyzed **BPM, key, and genre** for every track you imported. Reuse that instead of re-analyzing.
- **Easy path:** in rekordbox, *File → Export Collection in xml format* → parse `rekordbox.xml` (plain XML, fully documented).
- **Direct path:** the `pyrekordbox` Python library reads rekordbox 6/7's `master.db` (encrypted SQLite) directly, with no export step.
- **Getting the set back into rekordbox:** write an **M3U8 playlist** or a rekordbox XML playlist, import it in rekordbox, and play it on the FLX4. Simple and reliable.

### SoundCloud likes
- The official SoundCloud API has had **app registration closed or limited for years**, so don't plan around it. If you get access, it's a bonus.
- **Free workaround:** `yt-dlp --flat-playlist -J https://soundcloud.com/<you>/likes` lists your likes' metadata (title, artist, duration, genre tag) **without downloading audio**.
- Catch: SoundCloud tracks only play inside rekordbox with a **SoundCloud Go+/DJ subscription** (paid). Without one, the likes are useful as a **"taste signal" and wishlist** ("you liked these; buy or download the ones that fit your set"), not as playable tracks. The POC therefore orders **local rekordbox tracks** and uses likes to boost or suggest.

### "What's playing right now" in rekordbox (hard, later phase)
- rekordbox has **no official now-playing API**.
- Options, from easiest to hardest:
  1. **History polling:** rekordbox writes play history to `master.db`; read it with `pyrekordbox` every few seconds. It may lag (it can update only after a track is loaded or saved). Test this first.
  2. **MIDI sniffing:** the FLX4 is a USB MIDI device. With `mido`/`python-rtmidi` you can see play, load, and crossfader events, which tell you *which deck is live*. The MIDI doesn't say *which track*, so combine it with option 1.
  3. **Memory reading** (like the open-source `rkbx_link` project): exact and real-time, but fragile and breaks on rekordbox updates. Avoid it unless the other two fail.

---

## 3. Phased plan

### Phase 0: Setup ✅ done (Python 3.9 venv, since this Mac has no newer Python)
- Python 3.11+, `uv` or `venv`, git repo.
- Export `rekordbox.xml`, put a sample in `data/`.

### Phase 1: POC "list in → ordered set out" (CLI): ✅ done (2026-11-05), including `djnext next` from Phase 2
- `ingest/rekordbox_xml.py` – parse the XML into `Track(id, title, artist, bpm, key, genre, rating, duration, path)`.
- `core/camelot.py` – convert rekordbox key → Camelot, plus a key-distance function.
- `core/scoring.py` – the transition cost function (weights in `config.yaml`).
- `core/energy_curve.py` – load curve points from config, `target_energy(t_fraction)`, map tracks to time slots.
- `core/sequencer.py` – greedy + 2-opt ordering against the energy curve (with bangers held back for the peaks).
- `export/m3u.py` – write `set.m3u8` for rekordbox import.
- `cli.py` (Typer): `djnext order --playlist "Friday" --start "Track X" --length 60 --curve classic-1h` → prints the ordered table (with time, target energy and actual energy per track) and writes the playlist.
- `--plot` flag: saves a PNG chart (matplotlib) of the target curve against the set's actual energy, so you can see how well the set matches.

### Phase 1b: Mixing advice ✅ done (2026-11-05)
- `core/mix_advice.py`: for every transition, pick bass swap / filter fade / build and drop / reverb wash-out / echo out from key, BPM, genre and energy, with FLX4 knob-level steps, the tempo move, an alternative, and a bridge track when the keys clash.
- Shown in `djnext order` (Mix column + `set_notes.txt`), `djnext next` and `djnext mix A B`.

### Phase 1c: Evaluation + your SoundCloud lists ✅ done (2026-11-05)
- `djnext report` (scorecard vs random/BPM-sorted baselines), `djnext rate` + `djnext feedback` (your 👍/👎 per transition, stored in `data/feedback.sqlite`).
- Reads rekordbox's `master.db` directly via pyrekordbox (from a temp copy). Streamed SoundCloud tracks come with the BPM and key rekordbox already analysed.
- `djnext soundcloud sync <user>` (yt-dlp, likes + own playlists) → linked to rekordbox by exact SoundCloud track id (`soundcloud:tracks:<id>`), so no fuzzy matching is needed for streamed tracks.
- Next: backtest against rekordbox's play history; optionally write the set straight into a rekordbox playlist (needs rekordbox closed + a backup).

### Phase 1d: Style + write to rekordbox ✅ done (2026-11-05)
- `style:` in config (tech house + groovy techno: 122–134 BPM, genre exclusions, favourite artists Omar+, Cloonee, Beltran, Vintage Culture, Max Styler get a bonus).
- `--to-rekordbox` / `djnext push` create the set as a playlist in a "djnext" folder in rekordbox (rekordbox closed, automatic backup, `djnext restore` to undo). Tested on a copy of the library: order kept, duplicate names get "(2)", restore gives back the original state.

### Phase 1e: Exact mix points ✅ done (2026-11-05)
- Reads rekordbox phrase analysis (PSSI) + beat grid (PQTZ) from the ANLZ files in `~/Library/Pioneer/rekordbox/share` (read-only; only the two needed blocks are parsed, ~2 s for 336 tracks). 333/336 SoundCloud tracks have phrases.
- Every transition gets "When": cue point for B, when to press play (A's time), bass-swap moment in both tracks, blend length in bars, when A must be out. Set timing uses real outros.
- Next ideas (parked by the user for later): history backtest, live now-playing via FLX4 MIDI, continue-from-what-you-played.

### Phase 2: "Next song" + SoundCloud likes
- `djnext next "Current Track"` → top 5 next tracks with reasons.
- `ingest/soundcloud_likes.py` via yt-dlp → fuzzy-match against the local library (`rapidfuzz`); matched tracks get a "you like this" boost, and unmatched tracks that fit go to a wishlist.
- Optional: Last.fm API (free key) for similar-artist and tag data to improve genre and vibe matching.

### Phase 3: Smarter "vibe" (still free)
- Audio analysis with **Essentia** (free; includes pretrained models for genre, mood, danceability, energy) or **librosa** for an energy estimate.
- Audio embeddings with **CLAP** (LAION, runs locally) so that "sounds similar" becomes a cosine distance in the cost function.
- Store vectors in SQLite with `sqlite-vec` (or Chroma).

### Phase 4: Live assist while you DJ
- Now-playing watcher (history polling + MIDI) → auto-refreshing "next up" suggestions.
- Small UI on a laptop side-window or your phone: **FastAPI + simple HTML** (chosen).
  - `web/app.py` (FastAPI): `GET /now` (current track), `GET /next` (top 5 with reasons), `POST /order` (build a set from a playlist), `GET /curve` (target vs. actual energy data).
  - `web/static/index.html` + a small vanilla JS file. No framework and no build step. It polls `/next` every few seconds, and the energy curve is drawn with Chart.js from a CDN.
  - Run with `uvicorn djnext.web.app:app --host 0.0.0.0` and open `http://<mac-ip>:8000` on your phone over the same Wi-Fi.
  - The web app calls the same `core/` functions as the CLI, so there is no duplicate logic.

### Phase 5 (optional): LLM layer
- Use an LLM to **explain** picks, take free-text requests ("darker, rolling, no vocals"), and re-rank the top 10 candidates. **The LLM never chooses the order alone**: the math picks the candidates and the LLM only re-ranks them.
- Free option: **Ollama** with a local model (Llama/Qwen). Paid option: the OpenAI API if you have it.

### Phase 6 (later): Discovery beyond your likes
- Find candidates through SoundCloud "related tracks" for your liked songs (`yt-dlp` on `/recommended`) and Last.fm `track.getSimilar` (free API).
- Analyse a short preview of each candidate for BPM, key and energy, then score it with the same cost function.
- Output is a **wishlist** ("would fit after track 7, download or buy it"), not playable tracks.

---

## 4. Tech stacks

### Manageable, 100% free (recommended)
| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Library data | rekordbox XML export (later `pyrekordbox`) |
| SoundCloud likes | `yt-dlp` (metadata only) |
| Matching | `rapidfuzz`: fuzzy text matching, used to work out that a SoundCloud like and a rekordbox file are the same song even when the names differ slightly |
| Ordering | your own greedy + 2-opt (no dependency); `networkx` optional |
| CLI / config | `typer`, `pyyaml`, `rich` for nice tables |
| Storage | SQLite (built into Python) |
| Output | M3U8 / rekordbox XML playlist |
| UI (later) | FastAPI + uvicorn + plain HTML/JS (Chart.js from a CDN) |
| Tests | `pytest` |
| Cost | **$0**, all local on your Mac |

### Best version (still mostly free)
| Layer | Choice |
|---|---|
| Library | `pyrekordbox` reading `master.db` live |
| Now playing | history polling + FLX4 MIDI via `mido`/`python-rtmidi` |
| Audio intelligence | Essentia models (energy, mood, genre, danceability) + CLAP embeddings |
| Vector search | `sqlite-vec` or Chroma (local) |
| Ordering | Google **OR-Tools** (free) for TSP with energy-curve constraints |
| Taste model | learn from your history (which transitions you actually played) → adjust the weights over time |
| LLM | OpenAI API (if available) or Ollama locally for explanations and natural-language requests |
| UI | Same FastAPI + plain HTML/JS app, served to your phone over local Wi-Fi (live energy chart, WebSocket push instead of polling) |
| Paid extras (optional) | SoundCloud Go+/DJ subscription to stream likes in rekordbox |

**Azure:** not needed. Everything runs locally on your Mac; a cloud server adds cost and lag for a single-user DJ tool. If you ever want it on your phone away from home, a free tier (Fly.io, Render) is enough.

**Don't rely on:** the Spotify "audio features" API (closed to new apps since Nov 2024) or AcousticBrainz (shut down in 2022).

---

## 5. Proposed project layout
```
next_song_recommender/
  PLAN.md
  pyproject.toml
  config.yaml            # scoring weights, BPM tolerance, energy curves
  data/                  # rekordbox.xml, cache.sqlite (gitignored)
  src/djnext/
    ingest/rekordbox_xml.py
    ingest/soundcloud_likes.py
    core/models.py       # Track dataclass
    core/camelot.py
    core/scoring.py
    core/sequencer.py
    core/energy_curve.py
    export/m3u.py
    cli.py
    web/app.py           # FastAPI (Phase 4)
    web/static/index.html, app.js
  tests/
```

---

## 6. Verification
- **Unit tests:** Camelot conversion (all 24 keys), key distance (8A→9A = 1, 8A→3B = far), BPM tolerance including half and double time, and a check that the sequencer never repeats a track.
- **Energy curve tests:** `target_energy` returns ≈1.5 at 0, ≈8.8 at 0.47, ≈5.3 at 0.65 and ≈8.8 at 1.0. In a generated set, the highest-energy track lands in the 25–35 min window, and the 35–45 min window has lower average energy than the peak.
- **Golden test:** 10 hand-picked tracks with a known "good" order; the sequencer's total cost should be ≤ the hand-made order's cost.
- **Real-world test:** run on one of your rekordbox playlists → import `set.m3u8` into rekordbox → mix it on the FLX4 and note which transitions felt wrong → adjust the weights in `config.yaml`.

## 7. Open questions (answer whenever)
- Are most of your tracks **local files in rekordbox**, or mostly streamed from SoundCloud? This decides whether the likes are playable or only a taste signal.
- Which genres or BPM range do you usually play? This sets the defaults for the energy curve.
