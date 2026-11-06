# djnext: quick start

djnext builds a DJ set for you from your own music in rekordbox. It puts the tracks in a good order (keys that match, tempos that work, an energy curve that builds and drops), tells you how and when to mix each transition, and can put the finished set straight into rekordbox with hot cues on your pads.

Everything runs on **your own computer**. Your music and library never leave it.

## What you need
- **rekordbox** (6 or 7) on a Mac or Windows PC, with some tracks already in it. Streamed SoundCloud tracks work too.
- **Python 3**:
  - **Mac:** usually already there. If not, the first start offers to install it; accept and start again.
  - **Windows:** install it from [python.org/downloads](https://www.python.org/downloads/) and **tick "Add python.exe to PATH"** in the installer.

## Install (once)
1. On the GitHub page you were invited to, click the green **Code** button, then **Download ZIP**, and unzip it somewhere, for example into Documents.
2. Open the folder and double-click:
   - **Mac:** `Start djnext.command`. If the Mac says it can't be opened, **right-click it → Open → Open**. You only need to do that the first time.
   - **Windows:** `Start djnext.bat`. If Windows shows a blue "protected your PC" box, click **More info → Run anyway**.
3. The first start installs everything, which takes a few minutes. Then your browser opens **djnext**.

From then on, just double-click the same file. **Keep the black window open while you use djnext**, and close it when you're done.

## Using it
1. **My music:** paste your SoundCloud profile link (for example `https://soundcloud.com/your-name`) and press **Sync**. Your likes and playlists show up, along with how many tracks rekordbox has already analysed.
   - Tracks rekordbox hasn't analysed yet can't be used. In rekordbox, open them from the SoundCloud section and add them to your collection, or load each one on a deck once. Then press **Reload library**.
2. **Settings:** set **your** BPM range, favourite artists and genres to leave out. The defaults are tech house and groovy techno with the sharer's favourite artists, so change them to your own. Pick **Beginner** or **Advanced** mixing level.
3. **Make a set:** click a **mood** (warm-up, pregame, drunk asf, banging, afters, groovy techno), choose a length, and press **Make a set**. You'll see the order, an energy chart, and for every track **when** and **how** to mix into it.
4. **Send to rekordbox:** **quit rekordbox first**, then press the button. Wait a few seconds, then open rekordbox and look under **Playlists → djnext** (rekordbox's own Playlists at the top of the sidebar, *not* the SoundCloud section).
   - The hot cue pads are set up for you: **E** = where to start the track, **F** = swap the basses here, **G** = start the next track here.
   - **My music → Create mood playlists** adds one playlist per mood under **Playlists → djnext moods**.
5. **Discover:** finds new tracks on SoundCloud that fit your style. Like the ones you want on SoundCloud, sync again, and add them to your rekordbox collection.
6. **Rate:** after mixing, give each transition 👍 or 👎. Pairs you didn't like won't be put together again.

## If something goes wrong
- **Undo:** **Settings → Undo last change** puts your rekordbox library back exactly as it was before djnext's last change. Quit rekordbox first. Every change is backed up beforehand, in the `data/backups` folder.
- **rekordbox hangs when starting:** force-quit it (Mac: ⌥⌘Esc; Windows: Ctrl+Shift+Esc), wait a few seconds and open it again. If it still hangs, use **Undo last change**.
- **Anything else:** send a screenshot of the black djnext window and the browser page to whoever shared djnext with you.

## Tips
- **Energy:** star-rate your tracks in rekordbox (1★ chill … 5★ peak-time). Without ratings, energy is guessed from BPM.
- **Getting an update:** download the ZIP again and replace the old folder, but **keep your old `data` folder**, because it holds your settings and ratings.

## Disclaimer
djnext is an independent hobby project. It is **not affiliated with or endorsed by** Pioneer DJ, AlphaTheta, rekordbox or SoundCloud.
- It reads your rekordbox library and analysis files directly, and when you ask it to, it writes playlists and hot cues into rekordbox's library. rekordbox must be closed for that, and every change is backed up first (**Settings → Undo last change** or `djnext restore`). Still, use it **at your own risk**, and keep your own rekordbox backups too (rekordbox: File → Library → Backup Library).
- SoundCloud is read through public pages with [yt-dlp](https://github.com/yt-dlp/yt-dlp): track lists and metadata only. **No audio is downloaded.**
- Licence: MIT (see [LICENSE](LICENSE)).
