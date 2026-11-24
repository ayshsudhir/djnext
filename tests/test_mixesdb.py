from conftest import LIKED

from djnext.ingest import mixesdb

SET_A = """[[Category:Tech House]]
== Tracklist ==
# [00] Fallon - Diet Coke [Hot Creations]
# [04] Beltran - Smack Yo' [Solid Grooves Raw]
# [08] OMNOM feat. XKYLAR - By Myself (ROB MÂRK Remix)
# [12] Someone Else - Not Yours
# [16] Max Styler - Freaky 1
"""
SET_B = """# [00] Dan Molinari - XTC
# [03] Beltran - Smack Yo'
# [06] OMNOM - By Myself (ROB MARK Remix)
# [09] ?
"""


def fake_get(calls):
    def get(params):
        calls.append(params)
        if params.get("prop") == "categories":
            cats = {"Set A": ["Tech House", "House", "Players"], "Set B": ["Techno"]}
            return {"query": {"pages": {str(i): {"title": t, "categories": [{"title": f"Category:{c}"} for c in cats[t]]}
                                        for i, t in enumerate(params["titles"].split("|"))}}}
        if params["action"] == "query":
            q = params["srsearch"].lower()
            hits = []
            if "smack yo" in q or "by myself" in q:
                hits = ["Set A", "Set B"]
            elif "diet coke" in q or "freaky" in q:
                hits = ["Set A"]
            return {"query": {"search": [{"title": h} for h in hits]}}
        return {"parse": {"wikitext": {"*": {"Set A": SET_A, "Set B": SET_B}[params["page"]]}}}
    return get


def test_lookup_caches_sets_and_finds_pairs(monkeypatch):
    monkeypatch.setattr(mixesdb, "PAUSE_S", 0)
    calls = []
    store = mixesdb.Store()
    tracks = [LIKED[0], LIKED[1], LIKED[2], LIKED[3], LIKED[8]]  # Smack Yo', By Myself, Freaky 1, Diet Coke, XTC
    for t in tracks:
        mixesdb.lookup(t, store, get=fake_get(calls))
    assert store.tracks["1"]["sets"] == ["Set A", "Set B"]
    assert store.tracks["9"]["sets"] == []  # "Dan Molinari - XTC" is not Cloonee's XTC
    assert sum(1 for c in calls if c["action"] == "parse") == 2  # each set downloaded once

    p = mixesdb.pairs(tracks, store)
    assert p.direct[("1", "2")] == 2  # Smack Yo' straight into By Myself, in both sets
    assert p.direct[("4", "1")] == 1 and ("1", "4") not in p.direct
    assert p.same_set[frozenset(("1", "3"))] == 1 and p.near[frozenset(("2", "3"))] == 1
    assert p.plays == {"1": 2, "2": 2, "3": 1, "4": 1, "9": 0}


def test_store_round_trip_and_todo(tmp_path, monkeypatch):
    monkeypatch.setattr(mixesdb, "PAUSE_S", 0)
    monkeypatch.setattr(mixesdb, "_get", fake_get([]))
    path = tmp_path / "mixesdb.json"
    store = mixesdb.update(LIKED[:2], path=path)
    again = mixesdb.Store.load(path)
    assert again.tracks.keys() == store.tracks.keys() and again.todo(LIKED[:3]) == [LIKED[2]]
    assert again.sets["Set A"][1] == ("Beltran", "Smack Yo' [Solid Grooves Raw]")
    assert again.categories == {"Set A": ["Tech House", "House", "Players"], "Set B": ["Techno"]}  # genre tags too
