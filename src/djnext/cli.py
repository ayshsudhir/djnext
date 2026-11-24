"""djnext command line.

  djnext app                       open djnext in your browser
  djnext djsets                    look your liked tracks up in DJ tracklists (MixesDB), once per track
  djnext genres                    your likes, sorted into genre lists
  djnext playlist -g tech-house    print a playlist from one genre list (nothing is written)
"""
from __future__ import annotations

import logging
from typing import Optional

import typer

app = typer.Typer(add_completion=False, help=__doc__, no_args_is_help=True)


def _quiet() -> None:
    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)


@app.command("app")
def run_app(port: int = typer.Option(8765, help="Port on this computer")):
    """Open djnext in your browser."""
    from .web.app import serve

    serve(port)


@app.command()
def djsets():
    """Look your likes up in DJ tracklists (about 15 seconds per new track)."""
    from . import service
    from .ingest import mixesdb

    _quiet()
    pool, _ = service.the_pool(service.load_library())
    todo = mixesdb.Store.load().todo(pool)
    typer.echo(f"{len(todo)} of {len(pool)} tracks to look up.")
    store = mixesdb.update(pool, progress=lambda i, n, t: typer.echo(f"  {i + 1}/{n}  {t.label}"))
    found = sum(1 for t in pool if store.tracks.get(t.id, {}).get("sets"))
    typer.echo(f"{found} of {len(pool)} tracks found in DJ sets.")


@app.command()
def genres():
    """Your likes, sorted into genre lists (? = a guess)."""
    from . import service
    from .core import genres as g

    _quiet()
    pool, _ = service.the_pool(service.load_library())
    v = service.sort_by_genre(pool)
    for gid, tracks in service.genre_lists(pool, v).items():
        typer.echo(f"\n{g.NAMES[gid]} ({len(tracks)})")
        for t in tracks:
            typer.echo(f"  {' ' if v[t.id].sure else '?'} {t.bpm:5.1f}  {t.label}")


@app.command()
def playlist(
    genre: str = typer.Option("tech-house", "--genre", "-g",
                              help="groovy-techno, tech-house, house, indie-melodic, hard-fast or other"),
    length: int = typer.Option(12, "--length", "-n", help="Number of tracks"),
    shape: str = typer.Option("build", help="build = warm up then build, peak = peak time"),
    start: Optional[str] = typer.Option(None, help="Start with this track ('Artist - Title' or part of it)"),
):
    """Print a playlist from one genre list of your SoundCloud likes."""
    from . import service
    from .core import picker

    _quiet()
    lib = service.load_library()
    everything, _ = service.the_pool(lib)
    v = service.sort_by_genre(everything)
    pool = [t for t in everything if v[t.id].genre == genre]
    if len(pool) < 3:
        typer.echo(f"Only {len(pool)} tracks in '{genre}'. Try: djnext genres")
        raise typer.Exit(1)
    first = lib.find(start, pool) if start else None
    pl = picker.build(pool, service.evidence(lib, everything), length=length, start=first, shape=shape)
    for i, s in enumerate(pl.steps, 1):
        typer.echo(f"{i:2d}. {s.track.label}  ({s.track.bpm:.0f} BPM, {s.track.key})")
        typer.echo(f"      {s.why}")


if __name__ == "__main__":
    app()
