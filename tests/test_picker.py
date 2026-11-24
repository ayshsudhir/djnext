from conftest import LIKED, fake_library

from djnext.core import names, picker
from djnext.core.camelot import key_steps


def _pool():
    lib = fake_library()
    return lib, picker.pool([lib.tracks[i] for i in lib.playlists["sc:likes"]])


def test_pool_is_only_your_likes():
    lib, (pool, counts) = _pool()
    ids = {t.id for t in pool}
    assert ids == {str(i) for i in range(1, 13)}  # every liked track, but not the DJ set or a 2nd upload
    assert "20" not in ids  # not liked = never picked, however well it would mix
    assert counts["not_a_track"] == 1 and counts["duplicate"] == 1
    pool2, counts2 = picker.pool([lib.tracks[i] for i in lib.playlists["sc:likes"]], removed=["3"])
    assert not {"3", "14"} & {t.id for t in pool2} and counts2["removed"] == 2  # both uploads of Freaky 1


def test_only_smooth_mixes_are_allowed():
    a = LIKED[0]  # 127 BPM, 9B
    assert picker.mixable(a, LIKED[1])  # 9B -> 9A relative key, +0.8%
    assert not picker.mixable(a, LIKED[11])  # 145 BPM: +14%, can't beatmatch it cleanly
    far_key = LIKED[4]  # 10A: two steps from 9B
    assert key_steps(a.key, far_key.key) == 2 and not picker.mixable(a, far_key)
    assert picker.mixable(a, far_key, max_key_steps=2)


def test_tested_pairs_win():
    lib, (pool, _) = _pool()
    a, b, c = lib.tracks["1"], lib.tracks["2"], lib.tracks["10"]  # By Myself and Whatchagonnado mix equally well
    plain = picker.Evidence.build()
    assert abs(picker.move(a, b, plain).score - picker.move(a, c, plain).score) < 0.5
    ev = picker.Evidence.build(history=[])
    ev.dj_direct = {("1", "2"): 2}
    m = picker.move(a, b, ev)
    assert m.score > picker.move(a, c, ev).score + 2
    assert m.reasons[0] == "real DJs played it straight after this twice"
    mine = picker.Evidence.build(history=[["1", "10"]])
    assert "you've mixed these before (once)" in picker.move(a, c, mine).why


def test_long_intros_are_preferred():
    lib, _ = _pool()
    ev = picker.Evidence.build()
    a = lib.tracks["4"]  # 8A
    short, long_ = lib.tracks["7"], lib.tracks["8"]  # 8A short intro, 8B long intro
    assert picker.intro_bars(short) == 4 and picker.intro_bars(long_) == 32
    assert picker.move(a, long_, ev).parts["intro"] > 0 > picker.move(a, short, ev).parts["intro"]
    assert "short intro" in picker.move(a, short, ev).why


def test_playlist_flows():
    lib, (pool, _) = _pool()
    ev = picker.Evidence.build(history=lib.history)
    pl = picker.build(pool, ev, length=8)
    ids = [t.id for t in pl.tracks]
    assert len(ids) == 8 and len(set(ids)) == 8
    for a, b in zip(pl.tracks, pl.tracks[1:]):
        assert picker.tempo_gap(a, b) <= picker.MAX_TEMPO_GAP
        assert key_steps(a.key, b.key) <= 2
    for i in range(len(ids) - 1):  # the same artist never back to back
        assert names.of(pl.tracks[i]).artists[:1] != names.of(pl.tracks[i + 1]).artists[:1]
    assert pl.steps[0].why == "opener" and all(s.why for s in pl.steps[1:])


def test_start_track_and_build_shape():
    lib, (pool, _) = _pool()
    ev = picker.Evidence.build()
    pl = picker.build(pool, ev, length=5, start=lib.tracks["6"])
    assert pl.tracks[0].id == "6"
    built = picker.build(pool, ev, length=6, shape="build")
    energy = picker.energy_levels(pool)
    assert energy[built.tracks[0].id] < energy[built.tracks[-1].id]  # warm up, then build


def test_blocked_pair_is_avoided_and_alternatives():
    lib, (pool, _) = _pool()
    a = lib.tracks["1"]
    ev = picker.Evidence.build(blocked=[("1", "2")])
    assert picker.move(a, lib.tracks["2"], ev).score < -10
    alts = picker.alternatives(a, None, pool, ev, used={"1"})
    assert alts and alts[0].track.id != "2" and all(picker.mixable(a, m.track) for m in alts)


def test_remixer_counts_as_the_same_artist():
    from djnext.core.models import Track

    remix = Track("r", "Chris Lake, Green Velvet - Deceiver (Max Styler Remix)", artist="Max Styler")
    own = Track("o", "On Repeat", artist="Max Styler")
    other = Track("x", "Diet Coke", artist="Fallon")
    assert picker.same_artist(remix, own) and not picker.same_artist(remix, other)


def test_options_never_repeat_the_artist_before():
    lib, (pool, _) = _pool()
    beltran = lib.tracks["1"]  # Smack Yo' (Beltran); The Final Chapter (7) is Beltran too
    alts = picker.alternatives(beltran, None, pool, picker.Evidence.build(), used={"1"}, top=20)
    assert "7" not in {m.track.id for m in alts}
