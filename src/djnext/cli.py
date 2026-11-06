"""djnext command line.

  djnext playlists                          list playlists in your rekordbox export
  djnext order --playlist "Friday"          build an ordered set following the energy curve
  djnext order -p "Friday" -p "Techno"      ... picking from several playlists combined
  djnext order --all-playlists              ... picking from every playlist you made
  djnext next "Artist - Title" --at 30      top 5 tracks to play next, 30 minutes into the set
  djnext mix "Track A" "Track B"            how to mix A into B (bass swap, filter, echo out ...)
  djnext report set.m3u8                    scorecard for a set (harmonic %, energy fit, vs random)
  djnext rate set.m3u8                      after mixing: thumbs up/down per transition
  djnext feedback                           what your ratings say works
  djnext set                                answer a few questions (mood, length) and get a set
  djnext moods                              your tracks sorted into moods (--to-rekordbox for playlists)
  djnext order --mood drunk                 a set for one mood
  djnext app                                open the click-to-use web page in your browser
  djnext curves                             show the available energy curves
  djnext order ... --to-rekordbox           also create the set as a rekordbox playlist
  djnext push set.m3u8                      create an existing set as a rekordbox playlist
  djnext cues set.m3u8                      add mix-point hot cues (E in / F drop / G next) for a set
  djnext cues --remove                      remove all hot cues this tool made
  djnext restore data/backups/<time>        undo: put the rekordbox library back
  djnext soundcloud sync <user>             fetch your SoundCloud likes + playlists
  djnext discover                           find new tracks on SoundCloud that fit your style
  djnext order -A --source soundcloud       set from all your SoundCloud lists
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import Config, Style, load_config
from .core.energy import spread_guessed
from .core.mix_advice import MixAdvice, advise
from .core.models import Track
from .core.sequencer import SetPlan, build_set, play_seconds, suggest_next
from .core.report import make_report, report_lines
from .export.m3u import read_m3u8, write_m3u8
from . import feedback as fb
from .ingest import soundcloud as sc
from .ingest.rekordbox_xml import Library, load_library

app = typer.Typer(add_completion=False, help="Next-song recommender / set builder for rekordbox + DDJ-FLX4.")
console = Console()

DEFAULT_XML = Path("data/rekordbox.xml")


XML_HELP = "rekordbox XML export (default: read your rekordbox library directly)"


def _load(xml: Optional[Path], quiet: bool = False) -> Library:
    """Library from an XML export if given (or data/rekordbox.xml exists), else rekordbox's own database.
    Your SoundCloud likes/playlists (from `djnext soundcloud sync`) are added as 'sc:...' playlists."""
    if xml is None and DEFAULT_XML.exists():
        xml = DEFAULT_XML
    if xml is not None:
        if not xml.exists():
            console.print(f"[red]Can't find {xml}.[/red]")
            raise typer.Exit(1)
        lib = load_library(xml)
    else:
        from .ingest.rekordbox_db import load_rekordbox_db

        try:
            lib = load_rekordbox_db()
        except (FileNotFoundError, RuntimeError) as e:
            console.print(f"[red]{e}[/red]. Export an XML from rekordbox instead and pass --xml.")
            raise typer.Exit(1)
    data = sc.load()
    if data:
        res = sc.attach(lib, data)
        if not quiet and res.not_analysed:
            console.print(f"[dim]{len(res.not_analysed)} tracks from your SoundCloud lists aren't in rekordbox yet "
                          f"(see `djnext soundcloud status`).[/dim]")
    return lib


def _filter_source(pool: List[Track], source: Optional[str], style: Optional[Style] = None) -> List[Track]:
    from .service import filter_pool

    out, notes = filter_pool(pool, source, style)
    for n in notes:
        console.print(f"[dim]{n}[/dim]")
    if not out:
        console.print(f"[red]No {source + ' ' if source else ''}tracks to pick from.[/red]")
        raise typer.Exit(1)
    return out


def _pool(lib: Library, playlists: Optional[List[str]], all_playlists: bool = False,
          source: Optional[str] = None, style: Optional[Style] = None) -> List[Track]:
    """Tracks to pick from: given playlists, every playlist you made, or (default) the whole collection."""
    if all_playlists:
        names = [n for n in lib.playlists if lib.playlists[n]]
        if source == "soundcloud":
            names = [n for n in names if n.startswith("sc:")] or names
    elif playlists:
        names = playlists
    else:
        return _filter_source(list(lib.tracks.values()), source, style)
    pool: Dict[str, Track] = {}
    for name in names:
        try:
            for t in lib.playlist_tracks(name):
                pool.setdefault(t.id, t)  # a track in several playlists is only counted once
        except KeyError as e:
            console.print(f"[red]{e.args[0]}[/red]")
            raise typer.Exit(1)
    result = _filter_source(list(pool.values()), source, style)
    if len(names) > 1:
        console.print(f"Picking from {len(result)} unique tracks across {len(names)} playlists.")
    return result


def _with_structure(tracks: List[Track]) -> List[Track]:
    """Load rekordbox phrase analysis (intro/drop/outro + beat grid) for these tracks."""
    from .ingest.rekordbox_anlz import attach_structures

    todo = [t for t in tracks if t.analysis_path and t.structure is None]
    if todo:
        attach_structures(todo)
    return tracks


def _find(lib: Library, query: str, pool: List[Track]) -> Track:
    try:
        return lib.find(query, pool)
    except KeyError as e:
        console.print(f"[red]{e.args[0]}[/red]")
        raise typer.Exit(1)


def _energy_warning(tracks: List[Track]) -> None:
    sources = Counter(t.energy_source for t in tracks)
    guessed = sources.get("bpm", 0) + sources.get("spread", 0)
    if guessed:
        console.print(
            f"[yellow]Note:[/yellow] {guessed}/{len(tracks)} tracks have no energy rating, so energy was estimated "
            "from tempo + how much of each track is drops. Star-rate tracks in rekordbox (or add 'Energy 7' to the "
            "comment) for better sets."
        )


def _mmss(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def _set_advice(plan: SetPlan, cfg: Config, pool: List[Track]) -> List[Optional[MixAdvice]]:
    out: List[Optional[MixAdvice]] = [None]
    for prev, cur in zip(plan.slots, plan.slots[1:]):
        out.append(advise(prev.track, cur.track, cfg, pool))
    return out


def _print_advice(adv: MixAdvice, a: Track, b: Track) -> None:
    console.print(f"\n[bold]How to mix[/bold] {a.label} -> {b.label}:  [cyan]{adv.title}[/cyan]")
    if adv.timing:
        console.print("  [bold]When[/bold]")
        for t in adv.timing:
            console.print(f"   - {t}")
        console.print("  [bold]How[/bold]")
    for i, step in enumerate(adv.steps, 1):
        console.print(f"  {i}. {step}")
    for n in adv.notes:
        console.print(f"  [dim]* {n}[/dim]")
    if adv.alternative:
        console.print(f"  [dim]Alternative: {adv.alternative}[/dim]")
    if adv.bridge is not None:
        console.print(f"  [yellow]Smoother route:[/yellow] play '{adv.bridge.label}' in between")


def _write_notes(plan: SetPlan, advice: List[Optional[MixAdvice]], out: Path) -> None:
    from .service import write_notes

    write_notes(plan, advice, out)


def _print_plan(plan: SetPlan, advice: Optional[List[Optional[MixAdvice]]] = None) -> None:
    table = Table(title=f"Set: {plan.curve.name}, {plan.length_s / 60:.0f} min, {len(plan.slots)} tracks")
    table.add_column("#", justify="right")
    table.add_column("Time")
    table.add_column("Track")
    table.add_column("BPM", justify="right")
    table.add_column("Key")
    table.add_column("Energy", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Transition")
    table.add_column("Mix")
    for i, s in enumerate(plan.slots, 1):
        adv = advice[i - 1] if advice else None
        t = s.track
        e = t.energy or 0
        colour = "green" if abs(e - s.target) <= 1.5 else "yellow" if abs(e - s.target) <= 3 else "red"
        table.add_row(
            str(i), _mmss(s.start_s), t.label, f"{t.bpm:.1f}", t.key or "?",
            f"[{colour}]{e:.0f}[/{colour}]", f"{s.target:.1f}", s.reason if i > 1 else "opener",
            adv.title if adv else "",
        )
    console.print(table)
    console.print(f"Total cost: {plan.total_cost:.2f} (lower is smoother)")


def _print_report(tracks: List[Track], curve, cfg: Config, length_s: Optional[float] = None) -> None:
    console.print("\n[bold]Scorecard[/bold]")
    for line in report_lines(make_report(tracks, curve, cfg, length_s)):
        console.print(f"  {line}")


def _tracks_from_set(lib: Library, set_file: Path) -> List[Track]:
    if not set_file.exists():
        console.print(f"[red]Can't find {set_file}[/red]")
        raise typer.Exit(1)
    by_path = {t.path: t for t in lib.tracks.values() if t.path}
    by_label = {t.label.lower(): t for t in lib.tracks.values()}
    tracks, missing = [], []
    for location, label in read_m3u8(set_file):
        t = by_path.get(location) or by_label.get(label.lower())
        if t is None:
            missing.append(label or location)
        else:
            tracks.append(t)
    if missing:
        console.print(f"[yellow]{len(missing)} tracks in {set_file} aren't in the rekordbox export: {missing[:5]}[/yellow]")
    return _with_structure(tracks)


def _rekordbox_write(set_file: Path, retry_cmd: str, **kw) -> Optional[dict]:
    from .export.rekordbox_playlist import RekordboxRunning, write_to_rekordbox

    try:
        return write_to_rekordbox(**kw)
    except RekordboxRunning:
        console.print(f"[yellow]rekordbox is open, so nothing was written.[/yellow] Quit rekordbox (Cmd+Q), then run:\n"
                      f"  {retry_cmd}")
        raise typer.Exit(1)


def _report_cues(res: dict) -> None:
    written, skipped = res.get("cues_written") or [], res.get("cues_skipped") or []
    if written:
        moved = [c for c in written if c.slot not in ("E", "F", "G")]
        console.print(f"[green]Added {len(written)} hot cues[/green]: pad [bold]E[/bold] = where to cue the track, "
                      f"[bold]F[/bold] = its drop (swap basses), [bold]G[/bold] = start the next track here.")
        if moved:
            console.print(f"[dim]{len(moved)} went to another pad because you already use that one.[/dim]")
    if skipped:
        console.print(f"[yellow]{len(skipped)} cues skipped (no free hot cue pad on those tracks).[/yellow]")


def _push(tracks: List[Track], name: str, xml: Optional[Path], set_file: Path, cfg: Config, cues: bool = True) -> None:
    from .export.rekordbox_cues import plan_cues

    if xml is not None or DEFAULT_XML.exists():
        console.print("[red]Writing to rekordbox needs the library read from rekordbox itself (not an XML export).[/red]")
        raise typer.Exit(1)
    cue_plan = plan_cues(tracks, cfg) if cues else None
    res = _rekordbox_write(set_file, f'djnext push {set_file} --name "{name}"',
                           content_ids=[t.id for t in tracks], name=name, cues=cue_plan,
                           remove_own_cues=bool(cue_plan))  # old djnext cues from earlier sets go first
    console.print(f"[green]Created rekordbox playlist[/green] [bold]{res['folder']} / {res['name']}[/bold] "
                  f"({res['tracks']} tracks).")
    console.print(f"In rekordbox: left sidebar > [bold]Playlists[/bold] (rekordbox's own, at the top, not the "
                  f"SoundCloud section) > [bold]{res['folder']}[/bold] > {res['name']}.")
    _report_cues(res)
    console.print(f"[dim]Backup of your library before the change: {res['backup']}  "
                  f"(undo with: djnext restore \"{res['backup']}\")[/dim]")


def _plot(plan: SetPlan, cfg: Config, out: Path) -> None:
    try:
        import warnings

        warnings.filterwarnings("ignore")  # matplotlib's own deprecation chatter
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        console.print("[yellow]--plot needs matplotlib: pip install -e '.[plot]'[/yellow]")
        return
    length_min = plan.length_s / 60
    xs = [i / 100 for i in range(101)]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot([x * length_min for x in xs], [plan.curve.target(x) for x in xs], label="target", color="#e05a2b")
    xs_set = [s.start_s / 60 for s in plan.slots]
    ys_set = [s.track.energy or 0 for s in plan.slots]
    if plan.slots:  # extend the last step to the end of the last track
        last = plan.slots[-1]
        xs_set.append((last.start_s + play_seconds(last.track, cfg)) / 60)
        ys_set.append(ys_set[-1])
    ax.step(xs_set, ys_set, where="post", label="your set", color="#2b7de0")
    ax.set_xlabel("minutes")
    ax.set_ylabel("energy")
    ax.set_ylim(0, 10.5)
    ax.set_title(f"Energy: {plan.curve.name}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    console.print(f"Energy plot saved to {out}")


@app.command()
def playlists(xml: Optional[Path] = typer.Option(None, help=XML_HELP)) -> None:
    """List playlists in the rekordbox export."""
    lib = _load(xml)
    sources = Counter(t.source or "local" for t in lib.tracks.values())
    console.print(f"{len(lib.tracks)} tracks in collection: " + ", ".join(f"{n} {k}" for k, n in sources.most_common()))
    for name, ids in lib.playlists.items():
        console.print(f"  {name}  ({len(ids)} tracks)")


@app.command()
def curves(config: Path = typer.Option(Path("config.yaml"))) -> None:
    """Show the available energy curves."""
    cfg = load_config(config)
    for name, pts in cfg.curves.items():
        mark = " (default)" if name == cfg.default_curve else ""
        console.print(f"{name}{mark}: " + "  ".join(f"{t:.0%}->{e}" for t, e in pts))


@app.command()
def order(
    playlist: Optional[List[str]] = typer.Option(
        None, "--playlist", "-p", help="Playlist to pick from; repeat -p to combine several (default: whole collection)"),
    all_playlists: bool = typer.Option(False, "--all-playlists", "-A", help="Pick from every playlist you made"),
    source: Optional[str] = typer.Option(None, "--source", help="Only these tracks: soundcloud, apple-music or local"),
    any_style: bool = typer.Option(False, "--any-style", help="Ignore the style filter in config.yaml (BPM range, genres)"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Opening track ('Artist - Title' or part of it)"),
    length: float = typer.Option(60.0, "--length", "-l", help="Set length in minutes"),
    curve: Optional[str] = typer.Option(None, "--curve", "-c", help="Energy curve name (see `djnext curves`)"),
    mood: Optional[str] = typer.Option(None, "--mood", "-m", help="warmup, pregame, drunk, banging, afters, groovy_techno (see `djnext moods`)"),
    out: Path = typer.Option(Path("set.m3u8"), "--out", "-o", help="Playlist file to write"),
    plot: bool = typer.Option(False, "--plot", help="Also save an energy chart PNG next to the playlist"),
    notes: bool = typer.Option(True, "--notes/--no-notes", help="Write step-by-step mixing notes (<out>_notes.txt)"),
    to_rekordbox: bool = typer.Option(False, "--to-rekordbox", "-R", help="Also create the set as a rekordbox playlist (rekordbox must be closed)"),
    name: Optional[str] = typer.Option(None, "--name", help="Playlist name in rekordbox"),
    cues: bool = typer.Option(True, "--cues/--no-cues", help="With --to-rekordbox: also add mix-point hot cues (E/F/G)"),
    xml: Optional[Path] = typer.Option(None, help=XML_HELP),
    config: Path = typer.Option(Path("config.yaml")),
) -> None:
    """Order tracks into a set that follows the energy curve and write an .m3u8 for rekordbox."""
    cfg = load_config(config)
    if mood:
        _mood_set(cfg, mood, length, curve, playlist, source or "soundcloud", out, plot, notes, to_rekordbox, name, cues, xml)
        return
    try:
        energy_curve = cfg.curve(curve)
    except KeyError as e:
        console.print(f"[red]{e.args[0]}[/red]")
        raise typer.Exit(1)
    lib = _load(xml)
    pool = _with_structure(_pool(lib, playlist, all_playlists, source, None if any_style else cfg.style))
    spread_guessed(pool)
    if not pool:
        console.print("[red]No tracks to order.[/red]")
        raise typer.Exit(1)
    opener = _find(lib, start, pool) if start else None
    plan = build_set(pool, energy_curve, cfg, length_min=length, start=opener)
    advice = _set_advice(plan, cfg, plan.unused)  # bridges come from tracks not already in the set
    _print_plan(plan, advice)
    _energy_warning(plan.tracks)
    _print_report(plan.tracks, energy_curve, cfg, plan.length_s)
    if plan.unused:
        console.print(f"{len(plan.unused)} tracks didn't fit into {length:.0f} min (or fit the curve worse).")
    elif plan.slots and plan.slots[-1].start_s < length * 60 * 0.8:
        console.print(f"[yellow]Only enough tracks for about {plan.slots[-1].start_s / 60 + 4:.0f} min.[/yellow]")
    write_m3u8(plan.tracks, out)
    streams = sum(t.is_stream for t in plan.tracks)
    if to_rekordbox:
        console.print(f"Set saved to [bold]{out}[/bold] (used by `djnext rate`/`report`).")
    elif streams == len(plan.tracks):
        console.print(f"Set saved to [bold]{out}[/bold] (for `djnext report`/`rate`). These are streamed tracks, so "
                      "rekordbox can't import the file. Add --to-rekordbox to get it as a rekordbox playlist, "
                      "or load them from the SoundCloud tab in this order.")
    elif streams:
        console.print(f"Playlist written to [bold]{out}[/bold]. rekordbox will import the {len(plan.tracks) - streams} local "
                      f"files. Load the {streams} streamed tracks from rekordbox's streaming tab.")
    else:
        console.print(f"Playlist written to [bold]{out}[/bold] -> import it in rekordbox (drag & drop onto Playlists).")
    if notes:
        notes_path = out.with_name(out.stem + "_notes.txt")
        _write_notes(plan, advice, notes_path)
        console.print(f"Mixing notes (how to do each transition) written to [bold]{notes_path}[/bold]")
    if plot:
        _plot(plan, cfg, out.with_suffix(".png"))
    if to_rekordbox:
        _push(plan.tracks, name or f"{datetime.now():%b %d %H.%M} {energy_curve.name}", xml, out, cfg, cues)


@app.command("next")
def next_track(
    current: str = typer.Argument(..., help="Track playing now ('Artist - Title' or part of it)"),
    at: float = typer.Option(0.0, "--at", help="Minutes into the set right now"),
    length: float = typer.Option(60.0, "--length", "-l", help="Set length in minutes"),
    playlist: Optional[List[str]] = typer.Option(
        None, "--playlist", "-p", help="Pick from this playlist; repeat -p to combine several (default: whole collection)"),
    all_playlists: bool = typer.Option(False, "--all-playlists", "-A", help="Pick from every playlist you made"),
    source: Optional[str] = typer.Option(None, "--source", help="Only these tracks: soundcloud, apple-music or local"),
    any_style: bool = typer.Option(False, "--any-style", help="Ignore the style filter in config.yaml (BPM range, genres)"),
    curve: Optional[str] = typer.Option(None, "--curve", "-c"),
    top: int = typer.Option(5, "--top", "-n"),
    xml: Optional[Path] = typer.Option(None, help=XML_HELP),
    config: Path = typer.Option(Path("config.yaml")),
) -> None:
    """Suggest the best tracks to play after the current one."""
    cfg = load_config(config)
    energy_curve = cfg.curve(curve)
    lib = _load(xml)
    pool = _with_structure(_pool(lib, playlist, all_playlists, source, None if any_style else cfg.style))
    spread_guessed(pool)
    cur = _find(lib, current, list(lib.tracks.values()))
    _with_structure([cur])
    frac = min(max(at / length, 0.0), 1.0) if length > 0 else 0.0
    console.print(
        f"Now: [bold]{cur.label}[/bold]  ({cur.bpm:.1f} BPM, {cur.key or '?'}, energy {cur.energy:.0f}); "
        f"target energy at {at:.0f} min: {energy_curve.target(frac):.1f}"
    )
    table = Table()
    table.add_column("#", justify="right")
    table.add_column("Track")
    table.add_column("Score", justify="right")
    table.add_column("Why")
    table.add_column("Mix")
    suggestions = suggest_next(cur, pool, energy_curve, cfg, frac, top=top)
    advices = [advise(cur, s.track, cfg, pool) for s in suggestions]
    for i, (s, adv) in enumerate(zip(suggestions, advices), 1):
        table.add_row(str(i), s.track.label, f"{s.cost:.2f}", s.reason, adv.title)
    console.print(table)
    if suggestions:
        _print_advice(advices[0], cur, suggestions[0].track)


@app.command()
def mix(
    track_a: str = typer.Argument(..., help="Track playing now (outgoing)"),
    track_b: str = typer.Argument(..., help="Track you want to bring in"),
    xml: Optional[Path] = typer.Option(None, help=XML_HELP),
    config: Path = typer.Option(Path("config.yaml")),
) -> None:
    """Explain how to mix track A into track B (bass swap, filter, echo out ...)."""
    cfg = load_config(config)
    lib = _load(xml)
    everything = list(lib.tracks.values())
    a = _find(lib, track_a, everything)
    b = _find(lib, track_b, everything)
    _with_structure([a, b])
    for t in (a, b):
        console.print(f"{t.label}: {t.bpm:.1f} BPM, key {t.key or '?'}, energy {t.energy or 0:.0f}, {t.genre or 'no genre'}")
        if t.structure is not None:
            console.print(f"  [dim]{t.structure.summary()}[/dim]")
    _print_advice(advise(a, b, cfg, everything), a, b)


@app.command()
def report(
    set_file: Path = typer.Argument(Path("set.m3u8"), help="Set to score (.m3u8 written by `order`, or any rekordbox export)"),
    curve: Optional[str] = typer.Option(None, "--curve", "-c"),
    xml: Optional[Path] = typer.Option(None, help=XML_HELP),
    config: Path = typer.Option(Path("config.yaml")),
) -> None:
    """Scorecard for a set: harmonic %, tempo jumps, energy-curve fit, and comparison with a random shuffle."""
    cfg = load_config(config)
    lib = _load(xml)
    tracks = _tracks_from_set(lib, set_file)
    if len(tracks) < 2:
        console.print("[red]Need at least 2 known tracks to score a set.[/red]")
        raise typer.Exit(1)
    _print_report(tracks, cfg.curve(curve), cfg)


@app.command()
def rate(
    set_file: Path = typer.Argument(Path("set.m3u8"), help="The set you just mixed"),
    xml: Optional[Path] = typer.Option(None, help=XML_HELP),
    config: Path = typer.Option(Path("config.yaml")),
    db: Path = typer.Option(fb.DEFAULT_DB, help="Where ratings are stored"),
) -> None:
    """After mixing a set: give each transition a thumbs up or down (and an optional note)."""
    cfg = load_config(config)
    lib = _load(xml)
    tracks = _tracks_from_set(lib, set_file)
    conn = fb.connect(db)
    set_name = f"{set_file.name} ({datetime.fromtimestamp(set_file.stat().st_mtime):%Y-%m-%d %H:%M})"
    console.print("For each transition: [green]g[/green] = sounded good, [red]b[/red] = didn't work, "
                  "s = skip (didn't play it), q = stop.\n")
    rated = 0
    for t in fb.describe(tracks, cfg):
        console.print(f"[bold]{t.position - 1} -> {t.position}[/bold]  {t.a.label}  ->  {t.b.label}   "
                      f"[dim]({t.technique.replace('_', ' ')})[/dim]")
        answer = typer.prompt("  g/b/s/q", default="s").strip().lower()[:1]
        if answer == "q":
            break
        if answer not in ("g", "b"):
            continue
        note = typer.prompt("  note (optional, e.g. 'vocals clashed', 'energy dip')", default="", show_default=False)
        fb.save_transition(conn, set_name, t, good=answer == "g", note=note.strip())
        rated += 1
    overall = typer.prompt("\nWhole set, 1-5 (0 = skip)", default=0, type=int)
    if 1 <= overall <= 5:
        note = typer.prompt("Anything about the set as a whole?", default="", show_default=False)
        fb.save_set(conn, set_name, overall, note.strip())
    console.print(f"Saved {rated} ratings to {db}. Run [bold]djnext feedback[/bold] to see what works.")


@app.command("feedback")
def feedback_summary(db: Path = typer.Option(fb.DEFAULT_DB, help="Where ratings are stored")) -> None:
    """What your ratings say: which techniques, key moves and tempo jumps work for your ears."""
    if not db.exists():
        console.print("No ratings yet. Mix a set, then run [bold]djnext rate set.m3u8[/bold].")
        raise typer.Exit(0)
    summ = fb.summary(fb.connect(db))
    if not summ["rated"]:
        console.print("No ratings yet.")
        raise typer.Exit(0)
    console.print(f"[bold]{summ['good']}/{summ['rated']}[/bold] transitions rated good "
                  f"({summ['good'] / summ['rated']:.0%})\n")
    titles = {"technique": "By mixing technique", "key": "By key move", "tempo": "By tempo change"}
    for group, buckets in summ["groups"].items():
        table = Table(title=titles[group])
        table.add_column(group)
        table.add_column("good", justify="right")
        table.add_column("rated", justify="right")
        table.add_column("%", justify="right")
        for name, (good, n) in sorted(buckets.items(), key=lambda kv: kv[1][0] / kv[1][1]):
            pct = good / n
            colour = "green" if pct >= 0.75 else "yellow" if pct >= 0.5 else "red"
            table.add_row(str(name).replace("_", " "), str(good), str(n), f"[{colour}]{pct:.0%}[/{colour}]")
        console.print(table)
    if summ["bad"]:
        console.print("[bold]Transitions that didn't work[/bold]")
        for pair, note in summ["bad"][-15:]:
            console.print(f"  - {pair}" + (f"  [dim]({note})[/dim]" if note else ""))
    if summ["sets"]:
        console.print("\n[bold]Whole-set ratings[/bold]")
        for name, overall, note, when in summ["sets"]:
            console.print(f"  {when[:10]}  {'*' * overall}{'.' * (5 - overall)}  {name}" + (f"  ({note})" if note else ""))


@app.command()
def push(
    set_file: Path = typer.Argument(Path("set.m3u8"), help="Set made by `djnext order`"),
    name: Optional[str] = typer.Option(None, "--name", help="Playlist name in rekordbox (default: date + time)"),
    cues: bool = typer.Option(True, "--cues/--no-cues", help="Also add mix-point hot cues (E/F/G)"),
    config: Path = typer.Option(Path("config.yaml")),
) -> None:
    """Create a set as a playlist inside rekordbox (in a 'djnext' folder), with mix-point hot cues."""
    cfg = load_config(config)
    lib = _load(None, quiet=True)
    tracks = _tracks_from_set(lib, set_file)
    if not tracks:
        console.print("[red]No known tracks in that set.[/red]")
        raise typer.Exit(1)
    _push(tracks, name or f"{datetime.now():%b %d %H.%M} set", None, set_file, cfg, cues)


@app.command("cues")
def cues_cmd(
    set_file: Path = typer.Argument(Path("set.m3u8"), help="Set made by `djnext order`"),
    remove: bool = typer.Option(False, "--remove", help="Remove ALL hot cues this tool created (from every track)"),
    config: Path = typer.Option(Path("config.yaml")),
) -> None:
    """Add mix-point hot cues for a set (without making a playlist), or remove all djnext cues."""
    if remove:
        res = _rekordbox_write(set_file, "djnext cues --remove", remove_own_cues=True)
        console.print(f"Removed {res['removed_cues']} djnext hot cues. Your own cues were left alone.")
        return
    from .export.rekordbox_cues import plan_cues

    cfg = load_config(config)
    tracks = _tracks_from_set(_load(None, quiet=True), set_file)
    res = _rekordbox_write(set_file, f"djnext cues {set_file}", cues=plan_cues(tracks, cfg))
    _report_cues(res)


@app.command()
def restore(backup: Optional[Path] = typer.Argument(None, help="A folder under data/backups/ (default: undo the last change)")) -> None:
    """Put your rekordbox library back exactly as it was in a backup (rekordbox must be closed)."""
    from .export.rekordbox_playlist import RekordboxRunning, list_backups, restore as do_restore

    if backup is None:
        backups = list_backups()
        if not backups:
            console.print("No backups yet: djnext hasn't changed your rekordbox library.")
            raise typer.Exit(0)
        backup = backups[0]
        console.print(f"Undoing the last change (back to {backup.name}).")

    try:
        do_restore(backup)
    except (RekordboxRunning, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Restored rekordbox library from {backup}.[/green]")


@app.command("app")
def web_app(
    port: int = typer.Option(8765, help="Port for the local web page"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the browser automatically"),
) -> None:
    """Open djnext in your browser (runs only on this computer)."""
    from .web.app import run

    run(port=port, open_browser=not no_browser)


def _mood_set(cfg: Config, mood: str, length: float, curve: Optional[str], playlist: Optional[List[str]],
              source: Optional[str], out: Path, plot: bool, notes: bool, to_rekordbox: bool,
              name: Optional[str], cues: bool, xml: Optional[Path]) -> None:
    from .service import make_set

    lib = _load(xml)
    moods = cfg.moods()
    try:
        res = make_set(lib, cfg, lists=playlist or None, source=source, length_min=length, curve=curve,
                       set_file=out, mood=mood)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    for n in res.notes:
        console.print(f"[dim]{n}[/dim]")
    _print_plan(res.plan, res.advice)
    _print_report(res.plan.tracks, res.plan.curve, cfg, res.plan.length_s)
    console.print(f"Set saved to [bold]{out}[/bold], mixing notes in [bold]{out.with_name(out.stem + '_notes.txt')}[/bold].")
    if not notes:
        out.with_name(out.stem + "_notes.txt").unlink(missing_ok=True)
    if plot:
        _plot(res.plan, cfg, out.with_suffix(".png"))
    if to_rekordbox:
        label = moods[mood].label
        _push(res.plan.tracks, name or f"{datetime.now():%b %d %H.%M} {label}", xml, out, cfg, cues)


def _ask_choice(title: str, options: List[str], default: int = 1) -> int:
    console.print(f"\n[bold]{title}[/bold]")
    for i, o in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan]. {o}")
    while True:
        raw = typer.prompt("Pick a number", default=str(default))
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print("[red]Type one of the numbers above.[/red]")


@app.command("set")
def guided_set() -> None:
    """Answer a few questions (what mood? how long?) and get a set, optionally straight into rekordbox."""
    cfg = load_config()
    lib = _load(None, quiet=True)
    from .service import mood_pools

    pools, _ = mood_pools(lib, cfg)
    moods = cfg.moods()
    keys = list(moods)
    labels = [f"{moods[k].label}  [dim]({len(pools[k])} tracks) {moods[k].ask}[/dim]" for k in keys]
    mood = keys[_ask_choice("What mood of music do you want?", labels) - 1]
    lengths = [30, 45, 60, 90, 120]
    length = lengths[_ask_choice("How long?", [f"{m} min" for m in lengths], default=3) - 1]
    from .export.rekordbox_playlist import rekordbox_running

    push = typer.confirm("Put it straight into rekordbox with hot cues? (rekordbox must be closed)",
                         default=not rekordbox_running())
    _mood_set(cfg, mood, length, None, None, "soundcloud", Path("set.m3u8"), False, True, push, None, True, None)


@app.command("moods")
def moods_cmd(
    to_rekordbox: bool = typer.Option(False, "--to-rekordbox", "-R", help="Create one rekordbox playlist per mood (folder 'djnext moods')"),
    top: int = typer.Option(5, "--top", "-n", help="Example tracks to show per mood"),
    source: Optional[str] = typer.Option("soundcloud", "--source", help="soundcloud, apple-music, local (or 'all')"),
) -> None:
    """Sort your tracks into moods (warm-up, pregame, drunk asf, banging, afters, groovy techno), within your style."""
    from .service import mood_pools

    cfg = load_config()
    lib = _load(None, quiet=True)
    pools, notes = mood_pools(lib, cfg, source=None if source == "all" else source)
    moods = cfg.moods()
    table = Table(title="Your music by mood")
    table.add_column("Mood")
    table.add_column("Tracks", justify="right")
    table.add_column("For example")
    for key, items in pools.items():
        examples = ", ".join(t.title[:30] for t, _ in items[:top])
        table.add_row(f"{moods[key].label}\n[dim]{key}[/dim]", str(len(items)), examples or "[dim]none yet[/dim]")
    console.print(table)
    console.print("Make a set: [bold]djnext order --mood drunk[/bold]   or just [bold]djnext set[/bold] and answer the questions.")
    if to_rekordbox:
        playlists = {moods[k].label: [t.id for t, _ in items] for k, items in pools.items()}
        res = _rekordbox_write(Path("set.m3u8"), "djnext moods --to-rekordbox", mood_playlists=playlists)
        made = res.get("mood_playlists", {})
        console.print(f"[green]Created {len(made)} mood playlists[/green] in rekordbox under "
                      f"[bold]Playlists > {res['moods_folder']}[/bold]: " + ", ".join(f"{k} ({v})" for k, v in made.items()))
        console.print(f"[dim]Backup of your library before the change: {res['backup']}[/dim]")


@app.command()
def discover(
    results: int = typer.Option(40, "--results", "-n", help="How many new tracks to suggest"),
    deep: bool = typer.Option(False, "--deep", help="Look further (more seeds and related tracks; slower)"),
) -> None:
    """Find new tracks on SoundCloud that fit your style and moods (nothing is downloaded)."""
    from .ingest import discover as dc

    data = sc.load()
    if not data:
        console.print("Sync your SoundCloud first: [bold]djnext soundcloud sync <your-username>[/bold]")
        raise typer.Exit(1)
    cfg = load_config()
    lib = _load(None, quiet=True)
    cands = dc.discover(lib, cfg, data, seeds_max=30 if deep else 15, related_per_seed=25 if deep else 15,
                        max_lookups=250 if deep else 120, results=results, log=lambda m: console.print(f"[dim]{m}[/dim]"))
    if not cands:
        console.print("Nothing new found this time. Try --deep.")
        raise typer.Exit(0)
    path = dc.save(cands)
    table = Table(title=f"{len(cands)} new tracks for you on SoundCloud")
    table.add_column("#", justify="right")
    table.add_column("Track")
    table.add_column("Likely mood")
    table.add_column("Likes", justify="right")
    table.add_column("Link")
    for i, c in enumerate(cands, 1):
        table.add_row(str(i), f"{c.title}\n[dim]{c.uploader} · {c.why}[/dim]", c.mood_guess or "-", f"{c.likes:,}", c.url)
    console.print(table)
    console.print(f"Saved to {path} (also shown in the web app's Discover tab).")
    console.print("[bold]To use them:[/bold] open the links and ♥ like the ones you want on SoundCloud, then run "
                  "[bold]djnext soundcloud sync[/bold]. In rekordbox, open SoundCloud > Likes, select the new tracks and "
                  "add them to your collection so they get analysed. After that they show up in your moods and sets.")


sc_app = typer.Typer(help="Your SoundCloud likes and playlists.")
app.add_typer(sc_app, name="soundcloud")


@sc_app.command("sync")
def sc_sync(
    user: Optional[str] = typer.Argument(None, help="Your SoundCloud username (soundcloud.com/<username>); remembered after the first sync"),
    xml: Optional[Path] = typer.Option(None, help=XML_HELP),
) -> None:
    """Fetch your likes and your own playlists (track lists only; nothing is downloaded)."""
    if not user:
        previous = sc.load()
        if not previous:
            console.print("Give your SoundCloud username the first time: djnext soundcloud sync <username>")
            raise typer.Exit(1)
        user = previous["user"]
    user = user.strip().rstrip("/").split("soundcloud.com/")[-1].split("/")[0]
    try:
        data = sc.fetch(user, log=console.print)
    except Exception as e:  # network / yt-dlp errors
        console.print(f"[red]Couldn't read SoundCloud for '{user}': {e}[/red]")
        raise typer.Exit(1)
    path = sc.save(data)
    console.print(f"Saved to {path}")
    _sc_status(_load(xml, quiet=True), data)


@sc_app.command("status")
def sc_status_cmd(xml: Optional[Path] = typer.Option(None, help=XML_HELP)) -> None:
    """Which of your SoundCloud tracks rekordbox has analysed (and which it hasn't)."""
    data = sc.load()
    if not data:
        console.print("Nothing synced yet: run [bold]djnext soundcloud sync <your-username>[/bold].")
        raise typer.Exit(0)
    _sc_status(_load(xml, quiet=True), data)


def _sc_status(lib: Library, data: dict) -> None:
    res = sc.attach(lib, data)
    table = Table(title=f"SoundCloud: {data['user']} (synced {data['synced_at'][:16]})")
    table.add_column("List")
    table.add_column("on SoundCloud", justify="right")
    table.add_column("ready (analysed in rekordbox)", justify="right")
    lists = {"likes": data.get("likes", [])}
    lists.update(data.get("playlists", {}))
    for name, entries in lists.items():
        table.add_row(name, str(len(entries)), str(res.playlists.get(f"sc:{name}", 0)))
    console.print(table)
    ready = {i for k, ids in lib.playlists.items() if k.startswith("sc:") for i in ids}
    console.print(f"[bold]{len(ready)}[/bold] unique tracks ready to use: "
                  "[bold]djnext order -A --source soundcloud[/bold]")
    if res.not_analysed:
        console.print(f"\n[yellow]{len(res.not_analysed)} tracks aren't in rekordbox yet[/yellow], so there's no BPM or key "
                      "for them. Add them to your rekordbox collection once (SoundCloud tab, then right-click > "
                      "Add to Collection, or just load them on a deck) so they get analysed:")
        for e in res.not_analysed[:15]:
            console.print(f"  - {sc.label(e)}")
        if len(res.not_analysed) > 15:
            console.print(f"  ... and {len(res.not_analysed) - 15} more")


if __name__ == "__main__":
    app()
