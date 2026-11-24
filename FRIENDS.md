# How to use djnext

Not installed yet? Start on the **[djnext start page](https://github.com/ayshsudhir/djnext)**: it has the download and the install steps.

djnext sorts **your SoundCloud likes** into genre lists, then picks a playlist from the list you choose where every track flows into the next, and puts it in rekordbox with the hot cues already set. It never picks a track you haven't liked.

**Jump to:** [First time](#first-time) · [Genre lists](#genre-lists) · [Make a playlist](#make-a-playlist) · [Change a pick](#change-a-pick) · [Send to rekordbox](#send-to-rekordbox) · [How it picks](#how-it-picks) · [Something went wrong](#if-something-goes-wrong) · [Updating](#updating-and-removing) · [Disclaimer](#disclaimer)

## First time
1. Paste **your SoundCloud profile link** and press **Get my likes**. Find the link on SoundCloud: click your profile picture → **Profile**, then copy the address from the address bar, for example `https://soundcloud.com/your-name`. Your likes must be public.
2. Make sure your liked tracks are **analysed in rekordbox**: in rekordbox, open **SoundCloud → Likes** in the left sidebar, select the tracks (⌘A) and drag them onto **Collection**. djnext needs rekordbox's tempo, key and phrase analysis, so a liked track that isn't in your Collection can't be picked. After adding more, press **Update my likes** in djnext.
3. Open **Your genre lists** at the bottom and press **Find DJ pairs**. djnext looks each of your tracks up in DJ tracklists on [MixesDB](https://www.mixesdb.com) to learn which of them real DJs play together, and which genre those DJ sets are. It takes about 15 seconds per track, only once; you can keep using djnext meanwhile.

## Genre lists
Your likes are sorted into **Groovy techno, Tech house, House, Indie dance & melodic, Hard & fast** and **Other**. djnext decides from three clues: the genres of the DJ sets a track was played in (the strongest), its genre tag, and its tempo. A track with few clues follows your other tracks by the same artist or label.
- Open **Your genre lists** to see every list. A **?** marks a guess: hover over it to see why.
- Wrong list? Pick the right one in the menu next to the track. djnext remembers your choice.
- **Send genre lists to rekordbox** (rekordbox closed) adds each list as a playlist in a **djnext genres** folder. Sending again refreshes them.

## Make a playlist
1. Choose a **genre**. The number shows how many of your tracks are in that list.
2. Choose how many **tracks** (8, 12, 16 or 20).
3. Choose the **shape**: **Warm up, then build** (starts deep and climbs) or **Peak time** (stays up).
4. Optional: **Start with** a track you want to open with. Otherwise djnext chooses.
5. Press **Make playlist**. It only uses tracks from that genre list.

Each track shows its tempo and key, **why it follows the track before** (for example *real DJs played it straight after this twice*, or *you've mixed these before*), and the **hot cues** it will get.

## Change a pick
- **Other options:** shows the next-best tracks for that spot. They mix well after the track before and into the track after. Press **Use this** to swap one in.
- **Doesn't work after #…:** you tried this change and it didn't sound right. djnext remembers that pair, never puts those two together again, and picks the rest of the playlist again from there.
- **Don't use:** keeps a track out of every playlist (all uploads of that song). **Your genre lists → Not used** lists them; press **Use again** to bring one back.

## Send to rekordbox
1. **Quit rekordbox** (⌘Q). The button only works while rekordbox is closed.
2. Give the playlist a name if you like, and press **Send to rekordbox with hot cues**.
3. Open rekordbox. The playlist is under **Playlists → djnext** (rekordbox's own Playlists, not the SoundCloud section).

Your hot cue pads are set up for each change: **E** = cue the incoming track here, **F** = swap the basses here, **G** = start the next track here. Your own hot cues are never changed: if a pad is already used, djnext uses a free one.

## How it picks
For every "this track, then that one" djnext checks, in this order:
1. **Can it be mixed smoothly?** Tempo within 5% and a compatible key (same key, one step on the Camelot wheel, or the relative major/minor). Anything else is never picked.
2. **Has it been tested?** Real DJs played them back to back (MixesDB tracklists), or you did (your rekordbox history).
3. **Same groove?** The two tracks turn up in the same DJ sets, or DJs who play one also play the other's artist.
4. **Clean blend?** A long intro to lay over the outro is preferred (from rekordbox's phrase analysis).
5. **Does it keep the flow?** Small tempo steps that climb rather than jump around, energy following the shape you picked, never the same artist (or remixer) twice in a row, and a mix of tunes the crowd knows and deeper cuts.

## If something goes wrong
- **Undo:** after a Send, press **Undo** next to the result. rekordbox goes back exactly as it was before that Send (quit rekordbox first). Every Send is backed up beforehand (Mac app: `~/Library/Application Support/djnext/data/backups`; ZIP version: `data/backups`).
- **rekordbox hangs when starting:** force-quit it (⌥⌘Esc), wait a few seconds and open it again. If it still hangs, open djnext and use **Undo**.
- **Anything else:** [ask a question here](https://github.com/ayshsudhir/djnext/issues/new), or send a screenshot to whoever shared djnext with you. Mac app: `~/Library/Logs/djnext.log` helps (Finder: ⇧⌘G and paste that path).

## Updating and removing
- **Getting an update:** Mac app: [download the newest version](https://github.com/ayshsudhir/djnext/releases/latest/download/djnext.dmg) and drag djnext into Applications again (choose **Replace**). ZIP version: [download the ZIP again](https://github.com/ayshsudhir/djnext/archive/refs/heads/main.zip) and replace the old folder, but **keep your old `data` folder**.
- **Where your data is:** Mac app: `~/Library/Application Support/djnext`. ZIP version: the `data` folder. It holds your SoundCloud likes list, the DJ-tracklist cache, your genre choices, the tracks you said not to use, and backups. Updating never touches it.
- **Removing djnext:** Mac app: drag it from Applications to the Bin, and delete that `djnext` folder. ZIP version: delete the folder.

## Disclaimer
djnext is an independent hobby project, **not affiliated with or endorsed by** Pioneer DJ, AlphaTheta, rekordbox, SoundCloud or MixesDB.
- It reads your rekordbox library directly, and when you press Send it writes a playlist and hot cues into rekordbox's library. rekordbox must be closed for that, and every change is backed up first. Still, use it **at your own risk**, and keep your own rekordbox backups too (rekordbox: File → Library → Backup Library).
- SoundCloud is read through public pages with [yt-dlp](https://github.com/yt-dlp/yt-dlp): the list of your likes only. **No audio is downloaded.**
- **Find DJ pairs** sends the artist and title of each of your likes to MixesDB's public search, one request per second.
- Licence: MIT (see [LICENSE](LICENSE)).
