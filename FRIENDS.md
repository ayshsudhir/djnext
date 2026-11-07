# djnext: quick start

djnext builds a DJ set for you from your own music in rekordbox. It puts the tracks in a good order (keys that match, tempos that work, an energy curve that builds and drops), tells you how and when to mix each transition, and can put the finished set straight into rekordbox with hot cues on your pads.

Everything runs on **your own computer**. Your music and library never leave it.

**Jump to:** [Install on a Mac](#install-on-a-mac-apple-silicon-m1-or-newer) · [Windows / Intel Mac](#install-on-windows-or-an-intel-mac) · [Using it](#using-it) · [Something went wrong](#if-something-goes-wrong) · [Tips](#tips) · [Disclaimer](#disclaimer) · [⬅ Back to the start page](https://github.com/ayshsudhir/djnext)

## Install on a Mac (Apple Silicon: M1 or newer)
1. **[Click here to download djnext for Mac](https://github.com/ayshsudhir/djnext/releases/latest/download/djnext.dmg).** It goes to your **Downloads** folder.
2. Double-click the downloaded `.dmg`. A window opens: **drag the djnext icon onto the Applications folder**.
3. Open djnext from **Launchpad**, **Spotlight** (⌘ Space, type *djnext*) or your Applications folder. Drag it to your Dock to keep it there.
4. **The first time**, the Mac says djnext can't be checked for malware (it's a free hobby app, not registered with Apple). Click **Done**, then open
   **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to *"djnext" was blocked*, then **Open Anyway** again.
   You only do this once.

Nothing else to install: Python and everything djnext needs are inside the app. You can eject the djnext disk and delete the `.dmg` afterwards.
- Your settings, SoundCloud lists and ratings live in `~/Library/Application Support/djnext`. Updating = drag the new version into Applications and replace; your data stays.
- To remove djnext completely: drag it from Applications to the Bin, and delete that `djnext` folder.

## Install on Windows, or an Intel Mac
- You need **rekordbox** (6 or 7) and **Python 3**: install it from [python.org/downloads](https://www.python.org/downloads/) and **tick "Add python.exe to PATH"** (Windows).
1. **[Click here to download the ZIP](https://github.com/ayshsudhir/djnext/archive/refs/heads/main.zip)** and double-click it in your Downloads folder to unzip it. Move the unzipped folder somewhere handy, for example Documents.
2. Double-click **`Start djnext.bat`** (Windows; if a blue "protected your PC" box shows, click **More info → Run anyway**) or **`Start djnext.command`** (Intel Mac; if it can't be opened, right-click → **Open → Open**).
3. The first start installs everything, which takes a few minutes. Then your browser opens **djnext**. Keep the black window open while you use it.

## Using it
The first time djnext opens, a **short setup** (about a minute) asks three things:
1. **Your SoundCloud link**, for example `https://soundcloud.com/your-name`. Don't use SoundCloud? Press **I don't use SoundCloud** and djnext uses your rekordbox collection instead.
2. **What you play**: tech house, techno, house, drum & bass… plus your favourite artists if you like.
3. **Beginner or advanced**: beginners get simpler mixes with BEAT SYNC.

Then:
- **🎚️ Live (while you play):** a small window that sits next to rekordbox and stays on top (📌 to switch that off). The Mac app opens straight into it.
  1. Type the track that's playing and press Enter.
  2. Watch the crowd and turn the **knob**: 💤 dead · 😐 meh · 🙂 vibing · 🙌 into it · 🔥 going off (or press keys **1–5**).
  3. djnext says what the room needs ("Change it up: something they know", "Ride it, don't break it"…) and lists tracks that mix well with what's playing. ↑ means more energy. Tap one to see when and how to mix it, and press **I'm playing this now** when it's on.
  4. **📈** shows how the set is going: the crowd through the night, which tracks lifted the room and where it dipped. **End set** saves it.
  5. **djnext learns from this.** Tracks that lifted your crowd move up in future picks (🚀), ones that made it dip move down (📉), and tracks that rescued a dead room come first when you set the knob to 💤 or 😐. The more sets you play with the knob, the better the picks get.
- **Make a set:** tap a mood (warm-up, pregame, drunk asf, banging, afters…), pick how long, and press **Make my set**. You get the order, an energy chart, and for every track **when** and **how** to mix into it. Tap a track to open its tips.
- **Send to rekordbox:** the dot at the top right shows whether rekordbox is open. **Quit rekordbox** until it says *rekordbox closed*, then press **Send to rekordbox**. In rekordbox, look under **Playlists → djnext** (rekordbox's own Playlists at the top of the sidebar, *not* the SoundCloud section).
  - Your hot cue pads are set up for you: **E** = start the track here, **F** = swap the basses here, **G** = start the next track here.
- **My music:** shows which of your SoundCloud tracks rekordbox has analysed. Tracks it hasn't analysed yet can't be used: in rekordbox, open them from the SoundCloud section and add them to your collection, then press **Reload library**.
- **Discover:** finds new tracks on SoundCloud that fit your style. Like the ones you want on SoundCloud, sync again, and add them to your rekordbox collection.
- **Rate:** after mixing, give each transition 👍 or 👎. Pairs you didn't like won't be put together again.
- **Settings:** change your style or level any time, or **Run the setup again**.

## If something goes wrong
- **Undo:** **Settings → Undo last change** puts your rekordbox library back exactly as it was before djnext's last change. Quit rekordbox first. Every change is backed up beforehand, in the `data/backups` folder.
- **rekordbox hangs when starting:** force-quit it (Mac: ⌥⌘Esc; Windows: Ctrl+Shift+Esc), wait a few seconds and open it again. If it still hangs, use **Undo last change**.
- **Anything else:** [ask a question here](https://github.com/ayshsudhir/djnext/issues/new) (free GitHub account needed), or send a screenshot to whoever shared djnext with you. Mac app: the file `~/Library/Logs/djnext.log` helps; in Finder press ⇧⌘G and paste that path to find it.

## Tips
- **Energy:** star-rate your tracks in rekordbox (1★ chill … 5★ peak-time). Without ratings, energy is guessed from BPM.
- **Getting an update:** Mac app: [download the newest version](https://github.com/ayshsudhir/djnext/releases/latest/download/djnext.dmg) and drag djnext into Applications again (choose **Replace**). ZIP version: [download the ZIP again](https://github.com/ayshsudhir/djnext/archive/refs/heads/main.zip) and replace the old folder, but **keep your old `data` folder**, because it holds your settings and ratings.

## Disclaimer
djnext is an independent hobby project. It is **not affiliated with or endorsed by** Pioneer DJ, AlphaTheta, rekordbox or SoundCloud.
- It reads your rekordbox library and analysis files directly, and when you ask it to, it writes playlists and hot cues into rekordbox's library. rekordbox must be closed for that, and every change is backed up first (**Settings → Undo last change** or `djnext restore`). Still, use it **at your own risk**, and keep your own rekordbox backups too (rekordbox: File → Library → Backup Library).
- SoundCloud is read through public pages with [yt-dlp](https://github.com/yt-dlp/yt-dlp): track lists and metadata only. **No audio is downloaded.**
- Licence: MIT (see [LICENSE](LICENSE)).
