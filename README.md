# djnext: next-song recommender for rekordbox + DDJ-FLX4

Orders your tracks into a DJ set that mixes harmonically (Camelot), stays within tempo-slider range, and follows the **DJ set energy curve** (warm-up → build → first peak → breather → final peak). See [PLAN.md](PLAN.md) for the full roadmap.

## Easiest: the web page
Double-click **`Start djnext.command`** (Mac) or **`Start djnext.bat`** (Windows), or run `djnext app`. It opens a page in your browser where you sync SoundCloud, make a set, send it to rekordbox and rate transitions. It runs only on your computer. To share it with friends, see [FRIENDS.md](FRIENDS.md).

## Setup (once)
```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,plot]'
source .venv/bin/activate
```

## Use it with your library
The tool reads your rekordbox library directly (from a temporary **copy** of rekordbox's database, so the real one is never touched, and it works while rekordbox is open). Streamed SoundCloud tracks are included with the BPM and key that rekordbox analysed.

**Your SoundCloud likes and playlists:**
```bash
djnext soundcloud sync <your-soundcloud-username>   # fetch likes + your playlists (track lists only)
djnext soundcloud status                            # which are ready, which rekordbox hasn't analysed yet
djnext order -A --source soundcloud --plot          # a set picked from ALL your SoundCloud lists
djnext order -p "sc:likes" -p "sc:<playlist name>"  # or only specific SoundCloud lists
```
SoundCloud tracks rekordbox has never seen have no BPM or key yet. `status` lists them: add them to your rekordbox collection once (or load them on a deck) and they're picked up next time. Only public likes and playlists are visible.

Since streamed tracks aren't files, rekordbox can't import the `.m3u8` for them. Load them from the SoundCloud tab in the order shown (the file is still used by `report` and `rate`).

Optional: use an XML export instead (**File → Export Collection in xml format** → `data/rekordbox.xml`, or `--xml path`).

**Commands:**
```bash
djnext playlists                                   # what's in the export
djnext order -p "Friday" --length 60 --plot        # ordered set → set.m3u8 (+ set.png energy chart)
djnext order -p "Friday" --start "Opening Track"   # force the opener
djnext next "Artist - Title" --at 25               # top 5 picks, 25 min into the set + how to mix #1
djnext mix "Track A" "Track B"                     # step-by-step: how to mix A into B
djnext curves                                      # classic-1h (default), warmup, peak-time
```
3. Drag `set.m3u8` into rekordbox's Playlists panel, then load it on the FLX4 and play.
   `set_notes.txt` is your cheat sheet: how to do every transition.

## How it tells you to mix
Every transition gets a technique, chosen from the key, BPM, genre and energy of the two tracks:

| Technique | When | On the FLX4 |
|---|---|---|
| **Long blend with a bass swap** | harmonic keys, tempo within 3%, same vibe | 16–32 bar blend, swap the LOW knobs on the phrase |
| **Filter fade** | keys only "ok", genre change, or a bigger tempo jump | CFX knob: high-pass out on A, low-pass in on B |
| **Build and drop swap** | energy jumps up into a high-energy section | Beat FX ROLL or a loop on A's build, swap basses on B's drop |
| **Reverb wash-out** | big energy drop (the breather) | Beat FX REVERB/ECHO on A, B comes in on a soft intro |
| **Echo out** | key clash or tempo out of range | Beat FX ECHO 1/2 beat on A, cut, start B clean |

Each one also gives you the tempo-slider move (or BEAT SYNC), an alternative technique, and, when two tracks clash, a **bridge track** that would sit nicely between them.

### Exact mix points (from rekordbox's phrase analysis)
rekordbox already analysed each track's structure (Intro, Build, Drop, Breakdown, Outro) and beat grid. The tool reads it (read-only) and adds a **When** section to every transition:
```
When:
  - Cue B at 0:00 (start of its Intro, 16 bars before its Drop).
  - Press PLAY on B on the 1 when A reaches 2:27 (start of A's Outro).
  - Swap the basses at A 2:57 = B 0:29, where B's Drop starts (16-bar blend).
  - A's music ends at 2:57, so pull A's fader down as B takes over.
```
- B's drop is lined up to land on a phrase change in A, ideally A's outro, its end or a breakdown, and B is started on a phrase change too.
- If B's run-up is longer than A's outro, B starts earlier (during A's last drop) so the two still line up.
- Build/drop swaps cue B up to 16 bars before its drop, and echo outs say exactly which beat to echo on.
- Set times also use each track's real outro, so the minute marks in the set are realistic.
- `djnext mix "A" "B"` also prints both tracks' structure ("Intro 0:00 (4 bars) > Build 0:07 …").
- Times for A are on A's clock (A is the master deck). B's positions are B's own track time, which is what you see when you cue it.

## Moods: "what do you want to hear?"
```bash
djnext set                        # asks: what mood? how long? into rekordbox? ... and builds it
djnext moods                      # your tracks sorted into moods, with examples
djnext moods --to-rekordbox       # one rekordbox playlist per mood (Playlists > djnext moods)
djnext order --mood drunk         # a set for one mood
```
Moods stay inside **your style** (your BPM range and genres from `config.yaml`, e.g. tech house + groovy techno). Tempo is relative to that range, so the same moods work for friends with a different style.

| Mood | Picks |
|---|---|
| 🌅 warmup | slower end of your range, deeper/melodic, low intensity |
| 🍻 pregame | groovy, vocal tracks, medium intensity |
| 🥴 drunk | edits/bootlegs/mashups of songs everyone knows, lots of drops |
| 🔥 banging | peak-time: high intensity, lots of drops, your favourite artists |
| 🌙 afters | hypnotic/minimal/groovy, steady (fewer big drops), longer tracks |
| ⚡ groovy_techno | the faster, techno end of your range |

Each mood has its own energy shape (warm-up stays low, drunk bounces between peaks, afters rolls steadily). Each track goes to the mood it fits best (or two, if it fits both almost equally). Moods pick from all your analysed SoundCloud tracks that match your style. The rules are in `src/djnext/core/moods.py`, and you can override them in `config.yaml`.

## Discover new tracks on SoundCloud
```bash
djnext discover            # ~30 new tracks that fit your style, with links (--deep looks further)
```
It starts from your best tracks (spread over your moods and artists), follows SoundCloud's "related tracks" and searches your favourite artists, then keeps only 2–9 minute tracks (no DJ sets or re-uploads) whose genre fits yours and that you don't have yet. Results are ranked by how many of your tracks led there, likes and plays, and favourite artists, and each gets a likely mood. Nothing is downloaded. The list is also on the web page's **Discover** tab.

Outside tools can't like tracks or create playlists on your SoundCloud account, so the last step is yours:
1. Open the links and ♥ like the ones you want.
2. Run `djnext soundcloud sync` (it remembers your username).
3. In rekordbox, open SoundCloud → Likes, select the new tracks and add them to your collection so they get analysed.

After that they're part of your moods and sets.

## Put the set straight into rekordbox
```bash
djnext order -A --source soundcloud --to-rekordbox     # build + create it as a rekordbox playlist
djnext push set.m3u8 --name "Friday warmup"            # or push a set you made earlier
djnext restore data/backups/<date-time>                # undo: library back exactly as before
```
- It also adds **hot cues** for the mix points, which show on the waveform and on the FLX4 pads (HOT CUE mode):
  - **E** "djnext IN": where to cue the incoming track
  - **F** "djnext SWAP": its drop, the moment to swap the basses
  - **G** "djnext NEXT > …": on the outgoing track, press play on the next track here
  Your own cues are never changed (a taken pad means another free pad is used). Rebuilding replaces only the djnext cues, `djnext cues --remove` takes them all off, and `--no-cues` skips them.
- rekordbox must be **closed** while writing. If it's open, nothing is written and you're told the command to run after closing it.
- Every write first makes a **full backup** of your rekordbox library in `data/backups/`.
- Sets go into a **djnext** folder under Playlists. Your own playlists are never touched, and an existing name gets "(2)" instead of being overwritten.

## Your style
`config.yaml` → `style:` holds the BPM range (122–134 for tech house / groovy techno), genres to leave out, and favourite artists who get a bonus. Add artists you love there. Use `--any-style` to ignore the style for one run. Recorded DJ sets (>15 min) and clips (<2 min) are always left out.

## Is the set any good? (the feedback loop)
1. **Scorecard**: printed after every `order` (or run `djnext report set.m3u8`). It shows the harmonic %, key clashes, tempo jumps, how closely the energy follows the curve, and how much better than a random shuffle the set is. This tells you the set is *technically clean*, not that it sounds good.
2. **Mix it on the FLX4**, using `set_notes.txt` as your cheat sheet.
3. **`djnext rate set.m3u8`**: for each transition, `g` (good) / `b` (didn't work) / `s` (skip), plus an optional note ("vocals clashed", "energy dip"). Ratings are saved in `data/feedback.sqlite`.
4. **`djnext feedback`**: shows which techniques, key moves and tempo changes work for your ears, and lists the transitions that failed. Use it to adjust the weights in `config.yaml`.

## Give your tracks an energy value (important!)
Energy is read in this order:
1. **rekordbox comment** containing `Energy 7` (or `E7`). Mixed In Key writes this automatically.
2. **Star rating**: 1★ = 2 … 5★ = 10.
3. A guess from BPM (weak; the CLI tells you how many tracks fell back to this).

## Tuning
Everything is in [config.yaml](config.yaml): scoring weights, BPM tolerance, play time per track, and the energy curves. If a generated set has a transition that felt wrong on the decks, raise that factor's weight.

## Try it without your library
```bash
djnext order --xml tests/fixtures/sample_rekordbox.xml -p Friday --plot
pytest
```

## Disclaimer
djnext is an independent hobby project. It is **not affiliated with or endorsed by** Pioneer DJ, AlphaTheta, rekordbox or SoundCloud.
- It reads your rekordbox library and analysis files directly, and when you ask it to, it writes playlists and hot cues into rekordbox's library. rekordbox must be closed for that, and every change is backed up first (**Settings → Undo last change** or `djnext restore`). Still, use it **at your own risk**, and keep your own rekordbox backups too (rekordbox: File → Library → Backup Library).
- SoundCloud is read through public pages with [yt-dlp](https://github.com/yt-dlp/yt-dlp): track lists and metadata only. **No audio is downloaded.**
- Licence: MIT (see [LICENSE](LICENSE)).
