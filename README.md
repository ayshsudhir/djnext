# 🎧 djnext

**Your DJ sidekick for rekordbox.** djnext looks at the tracks in your rekordbox library and tells you **what to play next**, and **how to mix it**.

- 🎚️ **Live mode:** a small window next to rekordbox. Turn the crowd knob (💤 dead … 🔥 going off) and it suggests the next track that fits the room *and* mixes well with what's playing.
- 📈 **It learns:** after each set you see how the crowd moved. Tracks that lifted the room get suggested more often.
- ✨ **Set builder:** pick a mood (warm-up, banging, afters…) and get a whole set in the right order, sent straight to rekordbox with hot cues on your pads.

Free, and it runs only on your own computer. Made for the Pioneer DDJ-FLX4; the suggestions work with any controller you use with rekordbox.

---

## ✅ What you need first

1. **rekordbox 6 or 7** on your computer ([free download](https://rekordbox.com/en/download/)). Open it at least once.
2. **Your music inside rekordbox.** djnext can only suggest tracks that are in rekordbox's **Collection** and that rekordbox has **analysed** (that's where the tempo and key come from). Two kinds work:
   - **Downloaded files** (MP3, WAV, AIFF, FLAC…): drag them onto **Collection** in rekordbox's left sidebar. rekordbox analyses them by itself.
   - **Streamed tracks** from a service built into rekordbox, such as **SoundCloud** (needs a paid SoundCloud Go+ or DJ plan to play them in rekordbox), Apple Music, Beatport or TIDAL: add them to your **Collection** too ([how](#how-to-add-streamed-tracks-to-your-rekordbox-collection)).
   - ❌ **Spotify and YouTube don't work:** rekordbox can't play them, so djnext can't use them.
3. **A few dozen tracks in your style**, at least. More tracks = better suggestions.
4. **Optional: a SoundCloud account** with public likes or playlists. If you link it during setup, djnext picks **only from your SoundCloud likes and playlists that are also in rekordbox**. If you skip it, djnext picks from your **whole rekordbox Collection**.

#### How to add streamed tracks to your rekordbox Collection
In rekordbox, click the streaming service in the left sidebar (for example **SoundCloud → Likes**), select the tracks (⌘A selects all), and **drag them onto Collection** at the top of the sidebar. Or load each track onto a deck once. rekordbox then analyses them, and djnext can use them.

---

## ⬇️ Download

### 🍎 Mac with an Apple chip (M1, M2, M3, M4…)
### 👉 [**Download djnext for Mac**](https://github.com/ayshsudhir/djnext/releases/latest/download/djnext.dmg)

Not sure which chip you have? Click the  Apple menu (top-left of your screen) → **About This Mac**. If it says **Chip: Apple M…**, this is the one for you. If it says **Processor: Intel**, use the Windows / Intel link below.

### 🪟 Windows, or a Mac with an Intel processor
### 👉 [**Download djnext (ZIP)**](https://github.com/ayshsudhir/djnext/archive/refs/heads/main.zip)
Then follow [the Windows / Intel steps](#install-on-windows-or-an-intel-mac) below.

---

## 🛠️ Install on a Mac in 4 steps

1. **Download** with the link above. It goes to your **Downloads** folder (click the ⬇️ arrow at the top-right of Safari or Chrome to see it).
2. **Double-click `djnext.dmg`.** A window opens with the djnext icon and an Applications folder. **Drag djnext onto the Applications folder.**
3. **Open djnext:** press **⌘ Space**, type **djnext**, press Enter.
4. **The first time only**, your Mac blocks it because djnext isn't registered with Apple (that costs money; djnext is a free hobby app). To allow it:
   - Click **Done** on the warning.
   - Open  Apple menu → **System Settings** → **Privacy & Security**.
   - Scroll down to *"djnext" was blocked…* and click **Open Anyway**, then **Open Anyway** again (you may need your Mac password).

That's it. djnext opens with a [1-minute setup](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#first-time-setup): your SoundCloud link (optional), the kind of music you play, and whether you're a beginner or advanced DJ.

## Install on Windows or an Intel Mac

These need **Python 3** too: on Windows, install it from [python.org/downloads](https://www.python.org/downloads/) and **tick "Add python.exe to PATH"** in the installer.

1. **Download** the ZIP with the link above and double-click it in your Downloads folder to unzip it. Move the unzipped folder somewhere handy, for example Documents.
2. Open the folder and double-click **`Start djnext.bat`** (Windows) or **`Start djnext.command`** (Intel Mac).
   - Windows shows a blue "protected your PC" box? Click **More info → Run anyway**.
   - The Mac says it can't be opened? Right-click it → **Open → Open**.
3. The first start installs everything (a few minutes), then your browser opens djnext. **Keep the black window open** while you use it.

---

## 📖 How to use it

The full guide, in plain words: **[How to use djnext](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md)**

Quick links:
- [The first-time setup](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#first-time-setup)
- [🎚️ Live mode: the crowd knob](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#live-mode-while-you-play)
- [✨ Making a set](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#make-a-set-before-you-play)
- [Something went wrong?](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#if-something-goes-wrong)
- [Getting a newer version](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#updating-and-removing)
- [Disclaimer (please read)](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#disclaimer)

Stuck? [**Ask a question here**](https://github.com/ayshsudhir/djnext/issues/new) (you need a free GitHub account), or message whoever sent you this link.

---

## 👩‍💻 For developers

Everything below is for people who want to run djnext from the code or change it. You don't need any of it to use the app.

Orders your tracks into a DJ set that mixes harmonically (Camelot), stays within tempo-slider range, and follows the **DJ set energy curve** (warm-up → build → first peak → breather → final peak). See [PLAN.md](PLAN.md) for the full roadmap.

### Building the Mac app
`packaging/mac/build_app.sh` builds **djnext.app** (its own window, Python included) and a drag-to-Applications
**.dmg** in `dist/`. It needs Python 3.10+ (`brew install python@3.12`). The app opens the small **Live** window
(next to rekordbox, kept on top) and keeps its data in `~/Library/Application Support/djnext`, its log in
`~/Library/Logs/djnext.log`. It's signed ad hoc (free), so friends click **Open Anyway** once in
System Settings → Privacy & Security. Publish it with `gh release create v0.2.0 dist/djnext.dmg`. Keep the file name `djnext.dmg`: the download link at the top of this page always fetches the newest release's `djnext.dmg`.

### Run from the code
```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,plot]'   # add ,mac for the own-window version
source .venv/bin/activate
djnext app                 # the app in your browser
python -m djnext.desktop   # the app in its own window (needs the mac extra)
```

### Use it with your library
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
Then drag `set.m3u8` into rekordbox's Playlists panel, load it on the FLX4 and play.
`set_notes.txt` is your cheat sheet: how to do every transition.

### How it tells you to mix
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

### Moods: "what do you want to hear?"
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

### Discover new tracks on SoundCloud
```bash
djnext discover            # ~30 new tracks that fit your style, with links (--deep looks further)
```
It starts from your best tracks (spread over your moods and artists), follows SoundCloud's "related tracks" and searches your favourite artists, then keeps only 2–9 minute tracks (no DJ sets or re-uploads) whose genre fits yours and that you don't have yet. Results are ranked by how many of your tracks led there, likes and plays, and favourite artists, and each gets a likely mood. Nothing is downloaded. The list is also on the web page's **Discover** tab.

Outside tools can't like tracks or create playlists on your SoundCloud account, so the last step is yours:
1. Open the links and ♥ like the ones you want.
2. Run `djnext soundcloud sync` (it remembers your username).
3. In rekordbox, open SoundCloud → Likes, select the new tracks and add them to your collection so they get analysed.

After that they're part of your moods and sets.

### Put the set straight into rekordbox
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

### Your style
`config.yaml` → `style:` holds the BPM range (122–134 for tech house / groovy techno), genres to leave out, and favourite artists who get a bonus. Add artists you love there. Use `--any-style` to ignore the style for one run. Recorded DJ sets (>15 min) and clips (<2 min) are always left out.

### Is the set any good? (the feedback loop)
1. **Scorecard**: printed after every `order` (or run `djnext report set.m3u8`). It shows the harmonic %, key clashes, tempo jumps, how closely the energy follows the curve, and how much better than a random shuffle the set is. This tells you the set is *technically clean*, not that it sounds good.
2. **Mix it on the FLX4**, using `set_notes.txt` as your cheat sheet.
3. **`djnext rate set.m3u8`**: for each transition, `g` (good) / `b` (didn't work) / `s` (skip), plus an optional note ("vocals clashed", "energy dip"). Ratings are saved in `data/feedback.sqlite`.
4. **`djnext feedback`**: shows which techniques, key moves and tempo changes work for your ears, and lists the transitions that failed. Use it to adjust the weights in `config.yaml`.

### Give your tracks an energy value (important!)
Energy is read in this order:
1. **rekordbox comment** containing `Energy 7` (or `E7`). Mixed In Key writes this automatically.
2. **Star rating**: 1★ = 2 … 5★ = 10.
3. A guess from BPM (weak; the CLI tells you how many tracks fell back to this).

### Tuning
Everything is in [config.yaml](config.yaml): scoring weights, BPM tolerance, play time per track, and the energy curves. If a generated set has a transition that felt wrong on the decks, raise that factor's weight.

### Try it without your library
```bash
djnext order --xml tests/fixtures/sample_rekordbox.xml -p Friday --plot
pytest
```

### Disclaimer and licence
See the [disclaimer](https://github.com/ayshsudhir/djnext/blob/main/FRIENDS.md#disclaimer). MIT licence: see [LICENSE](LICENSE).
