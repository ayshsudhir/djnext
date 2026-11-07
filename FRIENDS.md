# How to use djnext

Not installed yet? Start on the **[djnext start page](https://github.com/ayshsudhir/djnext)**: it has what you need, the download and the install steps.

**Jump to:** [First-time setup](#first-time-setup) · [🎚️ Live mode](#live-mode-while-you-play) · [✨ Make a set](#make-a-set-before-you-play) · [Something went wrong](#if-something-goes-wrong) · [Tips](#tips) · [Updating](#updating-and-removing) · [Disclaimer](#disclaimer)

## First-time setup
The first time djnext opens, a **short setup** (about a minute) asks three things:
1. **Your SoundCloud profile link** (optional). Find it on SoundCloud: click your profile picture → **Profile**, then copy the address from the browser's address bar, for example `https://soundcloud.com/your-name`.
   - djnext reads your **public** likes and playlists (just the track lists; nothing is downloaded) and then picks **only from those tracks, and only the ones that are also in your rekordbox Collection**.
   - Don't use SoundCloud? Press **I don't use SoundCloud**. djnext then picks from your **whole rekordbox Collection**.
2. **The kind of music you play**: tech house, techno, house, drum & bass… This sets the tempo range djnext picks from. You can also type your favourite artists; they get suggested a bit more often.
3. **Beginner or advanced**: beginners get simpler mixing instructions that use BEAT SYNC and short blends; advanced gets longer blends and EQ work.

## Live mode (while you play)
A small window that sits next to rekordbox and stays in front of it (press **📌 Keep on top** to switch that off). The Mac app opens straight into it.
1. In the search box at the top of the Live window, type part of the title or artist of the track that's playing on your deck, then pick it from the list (or press Enter).
2. Watch the crowd and turn the **knob**: 💤 dead · 😐 meh · 🙂 vibing · 🙌 into it · 🔥 going off (or press keys **1–5**).
3. djnext says what the room needs ("Change it up: something they know", "Ride it, don't break it"…) and lists tracks that mix well with what's playing. The arrow on the left shows the energy change: **↑** more energy, **→** about the same, **↓** calmer. Click a track to see when and how to mix it in, and press **I'm playing this now** once it's playing, so djnext knows and suggests the next one.
4. **📈 How's it going?** (at the top) shows how the set is going: the crowd through the night, which tracks lifted the room and where it dipped. When you finish, press **End set & start fresh** in that window to save the set.
5. **djnext learns from this.** Tracks that lifted your crowd move up in future picks (🚀), ones that made it dip move down (📉), and tracks that rescued a dead room come first when you set the knob to 💤 or 😐. The more sets you play with the knob, the better the picks get.

## Make a set (before you play)
Press **✨ Make a set** at the top of Live: the same window grows into the set builder. **🎚️ Go live** takes you back. (In the ZIP version the set builder is the main page.)
- **Make a set:** tap a mood (warm-up, pregame, drunk asf, banging, afters…), pick how long, and press **Make my set**. You get the track order, an energy chart, and for every track **when** and **how** to mix into it. Click a track to open its tips.
- **Send to rekordbox:** the dot at the top right shows whether rekordbox is open. **Quit rekordbox** (on a Mac: **rekordbox menu → Quit rekordbox**, or ⌘Q) and wait until the dot says *rekordbox closed*, then press **Send to rekordbox**. Then open rekordbox again. In rekordbox, look under **Playlists → djnext** (rekordbox's own Playlists at the top of the sidebar, *not* the SoundCloud section).
  - Your hot cue pads are set up for you: **E** = start the track here, **F** = swap the basses here, **G** = start the next track here.
- **My music:** shows, for each SoundCloud list, how many tracks are ready to use. A track is ready once it's in your rekordbox Collection and analysed. To make more tracks ready, [add them to your rekordbox Collection](https://github.com/ayshsudhir/djnext#how-to-add-streamed-tracks-to-your-rekordbox-collection), then press **Reload library** in djnext.
- **Discover:** finds new tracks on SoundCloud that fit your style. To use one: click **Open on SoundCloud** and press ♥ like there → in djnext, **My music → Sync** → [add it to your rekordbox Collection](https://github.com/ayshsudhir/djnext#how-to-add-streamed-tracks-to-your-rekordbox-collection) → **Reload library**.
- **Rate:** after you've mixed a set made with **Make a set**, give each change from one track to the next a 👍 or 👎. Pairs you didn't like won't be put together again.
- **Settings:** change your style or level any time, or **Run the setup again**.

## If something goes wrong
- **Undo:** **Settings → Undo last change** puts your rekordbox library back exactly as it was before djnext's last change. Quit rekordbox first. Every change is backed up beforehand (Mac app: in `~/Library/Application Support/djnext/data/backups`; ZIP version: in the `data/backups` folder).
- **rekordbox hangs when starting:** force-quit it (Mac: ⌥⌘Esc; Windows: Ctrl+Shift+Esc), wait a few seconds and open it again. If it still hangs, use **Undo last change**.
- **Anything else:** [ask a question here](https://github.com/ayshsudhir/djnext/issues/new) (free GitHub account needed), or send a screenshot to whoever shared djnext with you. Mac app: the file `~/Library/Logs/djnext.log` helps; in Finder press ⇧⌘G and paste that path to find it.

## Tips
- **Better energy suggestions:** give your tracks stars in rekordbox: in the track list, click the stars in the **Rating** column (1★ = chill … 5★ = peak-time banger). Without stars, djnext guesses energy from the tempo and how much of each track is drops, which is less accurate.

## Updating and removing
- **Getting an update:** Mac app: [download the newest version](https://github.com/ayshsudhir/djnext/releases/latest/download/djnext.dmg) and drag djnext into Applications again (choose **Replace**). ZIP version: [download the ZIP again](https://github.com/ayshsudhir/djnext/archive/refs/heads/main.zip) and replace the old folder, but **keep your old `data` folder**, because it holds your settings and ratings.
- **Where your data is:** Mac app: `~/Library/Application Support/djnext` (settings, SoundCloud lists, ratings, set reviews). ZIP version: the `data` folder. Updating never touches it.
- **Removing djnext:** Mac app: drag it from Applications to the Bin, and delete that `djnext` folder. ZIP version: delete the folder.

## Disclaimer
djnext is an independent hobby project. It is **not affiliated with or endorsed by** Pioneer DJ, AlphaTheta, rekordbox or SoundCloud.
- It reads your rekordbox library and analysis files directly, and when you ask it to, it writes playlists and hot cues into rekordbox's library. rekordbox must be closed for that, and every change is backed up first (**Settings → Undo last change** or `djnext restore`). Still, use it **at your own risk**, and keep your own rekordbox backups too (rekordbox: File → Library → Backup Library).
- SoundCloud is read through public pages with [yt-dlp](https://github.com/yt-dlp/yt-dlp): track lists and metadata only. **No audio is downloaded.**
- Licence: MIT (see [LICENSE](LICENSE)).
