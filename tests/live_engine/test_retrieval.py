"""LE3-C: device-index retrieval (BM25+phonetic), edge case 11."""

from vox.engine.retrieval import DeviceIndex


def build_index() -> DeviceIndex:
    index = DeviceIndex()
    index.index_apps(["Notepad", "Calculator", "Chrome", "Photos", "Word", "WordPad", "Paint"])
    index.index_windows(["Chrome — Docs", "Untitled — Notepad", "Budget — Sheets"])
    index.index_monitors(["left Dell", "right laptop panel"])
    index.index_folders(
        {"my project folder": "D:\\work\\vox", "Downloads": "C:\\Users\\me\\Downloads"}
    )
    index.index_aliases({"code editor": "Visual Studio Code"})
    return index


def test_search_ranks_exact_and_variant_matches():
    index = build_index()
    hits = index.search("notepad")
    assert hits and hits[0].chunk.title == "Notepad"
    assert index.search("no pad")[0].chunk.title == "Notepad"  # alias variant indexed
    assert index.search("budget sheets")[0].chunk.title == "Budget — Sheets"
    assert index.search("left monitor", source="monitor")[0].chunk.title == "left Dell"
    assert index.search("project folder", source="folder")[0].chunk.data["path"] == "D:\\work\\vox"


def test_phonetic_match_finds_soundalikes():
    index = build_index()
    hits = index.search("krom", source="app")  # not a known variant: phonetic key
    assert hits and hits[0].chunk.title == "Chrome"


def test_edge11_absent_app_is_honest_with_nearest_options():
    index = build_index()
    assert index.find_app("Notepad") is not None
    assert index.find_app("Photoshop") is None  # never claim it exists
    nearest = index.nearest_apps("photo")
    assert nearest and nearest[0] == "Photos"  # offer the closest real option
    assert index.find_app("totally-not-real-app-xyz") is None


def test_search_is_deterministic_and_bounded():
    index = build_index()
    assert index.search("chrome", k=2) == index.search("chrome", k=2)
    assert len(index.search("chrome", k=2)) <= 2
    assert index.search("") == []
    assert index.search("zzzzqqqq") == []


def test_remove_source_refreshes_index():
    index = build_index()
    index.remove_source("window")
    assert all(hit.chunk.source != "window" for hit in index.search("chrome docs"))
    assert index.find_app("Chrome") is not None
