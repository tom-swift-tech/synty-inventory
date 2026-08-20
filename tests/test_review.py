"""Local VLM review pipeline: resume, per-view render skip, failure handling,
and round-trip validity against the real threejs-v2 overlay. No live Ollama,
no live Playwright -- render_fn/query_fn are injected fakes throughout.
"""

import json
from pathlib import Path

from synty_inventory.merge import stamp_auto
from synty_inventory.review import DEFAULT_VIEWS, RenderError, review_pack
from synty_inventory.schema import empty_placement
from synty_inventory.sources.threejs_v2 import apply_threejs_overlay


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _pack(tmp_path: Path, pack_id: str, models: list[str]) -> Path:
    pack_dir = tmp_path / pack_id
    _write(pack_dir / "manifest.json", {"models": models})
    for rel in models:
        glb = pack_dir / rel
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.write_bytes(b"fake-glb")
    return pack_dir


def _fake_render(calls: list) -> callable:
    def render(glb, stills_dir, views, root):
        calls.append((glb.name, tuple(views)))
        stills_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for v in views:
            p = stills_dir / f"{v}.png"
            if not p.is_file():
                p.write_bytes(b"fake-png")
            paths.append(p)
        return paths

    return render


def _fake_query(draft_by_stem: dict) -> callable:
    def query(images, prompt):
        # infer stem from the still path's parent dir name
        stem = Path(images[0]).parent.name
        return draft_by_stem.get(stem)

    return query


def test_reviews_new_assets_and_writes_catalog(tmp_path: Path):
    pack_dir = _pack(tmp_path, "POLYGON_Pack", ["models/SM_Prop_Crate_01.glb"])
    render_calls: list = []
    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,  # unused, render_fn is injected
        limit=None,
        render_fn=_fake_render(render_calls),
        query_fn=_fake_query(
            {
                "SM_Prop_Crate_01": {
                    "name": "Wooden Crate",
                    "description": "A weathered wooden crate with metal bands.",
                    "tags": ["crate", "wood", "container"],
                    "category": "prop",
                    "semantic_role": "exterior_prop",
                }
            }
        ),
    )
    assert result["ok"] is True
    assert result["reviewed"] == ["SM_Prop_Crate_01"]
    assert result["failed"] == []
    assert render_calls == [("SM_Prop_Crate_01.glb", DEFAULT_VIEWS)]

    doc = json.loads((pack_dir / "catalog.json").read_text(encoding="utf-8"))
    entry = doc["assets"][0]
    assert entry["id"] == "SM_Prop_Crate_01"
    assert entry["reviewed"] is True
    assert entry["file"] == "models/SM_Prop_Crate_01.glb"
    assert entry["name"] == "Wooden Crate"
    assert entry["tags"] == ["crate", "wood", "container"]


def test_resume_skips_already_reviewed_assets(tmp_path: Path):
    pack_dir = _pack(
        tmp_path,
        "POLYGON_Pack",
        ["models/SM_Prop_Crate_01.glb", "models/SM_Prop_Barrel_01.glb"],
    )
    _write(
        pack_dir / "catalog.json",
        {
            "pack_id": "POLYGON_Pack",
            "assets": [
                {"id": "SM_Prop_Crate_01", "name": "Crate", "reviewed": True, "file": "models/SM_Prop_Crate_01.glb"}
            ],
        },
    )
    render_calls: list = []
    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=_fake_render(render_calls),
        query_fn=_fake_query(
            {"SM_Prop_Barrel_01": {"name": "Barrel", "description": "A barrel.", "tags": ["barrel"], "category": "prop"}}
        ),
    )
    assert result["skipped_already_reviewed"] == 1
    assert result["reviewed"] == ["SM_Prop_Barrel_01"]
    # never rendered the already-reviewed asset
    assert [name for name, _ in render_calls] == ["SM_Prop_Barrel_01.glb"]

    doc = json.loads((pack_dir / "catalog.json").read_text(encoding="utf-8"))
    ids = {a["id"] for a in doc["assets"]}
    assert ids == {"SM_Prop_Crate_01", "SM_Prop_Barrel_01"}


def test_limit_counts_only_newly_reviewed_assets(tmp_path: Path):
    _pack(
        tmp_path,
        "POLYGON_Pack",
        ["models/SM_A.glb", "models/SM_B.glb", "models/SM_C.glb"],
    )
    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        limit=2,
        render_fn=_fake_render([]),
        query_fn=_fake_query(
            {
                "SM_A": {"name": "A", "description": "a", "tags": [], "category": "prop"},
                "SM_B": {"name": "B", "description": "b", "tags": [], "category": "prop"},
                "SM_C": {"name": "C", "description": "c", "tags": [], "category": "prop"},
            }
        ),
    )
    assert result["reviewed"] == ["SM_A", "SM_B"]
    assert "SM_C" not in result["reviewed"]


def test_render_stills_skips_views_already_on_disk(tmp_path: Path, monkeypatch):
    """The real (non-injected) renderer must only invoke the synty-glb
    subprocess for views missing from the stills cache -- a full re-render
    of a partially-cached asset would be wasted wall time on a real pilot."""
    from synty_inventory import review as review_mod

    glb = tmp_path / "SM_Prop_Crate_01.glb"
    glb.write_bytes(b"fake-glb")
    stills_dir = tmp_path / "_review_stills" / "SM_Prop_Crate_01"
    stills_dir.mkdir(parents=True)
    (stills_dir / f"{DEFAULT_VIEWS[0]}.png").write_bytes(b"already-here")

    subprocess_calls: list = []

    def fake_run(cmd, **kwargs):
        subprocess_calls.append(cmd)

        class _Proc:
            returncode = 0
            stderr = ""

        # simulate the renderer producing only the views it was asked for
        for v in cmd[5:]:
            (stills_dir / f"{v}.png").write_bytes(b"rendered")
        return _Proc()

    monkeypatch.setattr(review_mod.subprocess, "run", fake_run)
    result = review_mod._render_stills(glb, stills_dir, DEFAULT_VIEWS, tmp_path)

    assert len(result) == len(DEFAULT_VIEWS)
    assert subprocess_calls, "expected a render call for the missing view"
    requested_views = subprocess_calls[0][5:]
    assert DEFAULT_VIEWS[0] not in requested_views
    assert (stills_dir / f"{DEFAULT_VIEWS[0]}.png").read_bytes() == b"already-here"


def test_render_stills_skips_subprocess_when_all_views_cached(tmp_path: Path, monkeypatch):
    from synty_inventory import review as review_mod

    glb = tmp_path / "SM_Prop_Crate_01.glb"
    glb.write_bytes(b"fake-glb")
    stills_dir = tmp_path / "_review_stills" / "SM_Prop_Crate_01"
    stills_dir.mkdir(parents=True)
    for v in DEFAULT_VIEWS:
        (stills_dir / f"{v}.png").write_bytes(b"cached")

    def fake_run(cmd, **kwargs):
        raise AssertionError("should not invoke the renderer when every view is cached")

    monkeypatch.setattr(review_mod.subprocess, "run", fake_run)
    result = review_mod._render_stills(glb, stills_dir, DEFAULT_VIEWS, tmp_path)
    assert len(result) == len(DEFAULT_VIEWS)


def test_bundle_stems_are_skipped(tmp_path: Path):
    _pack(tmp_path, "POLYGON_Pack", ["models/Characters.glb", "models/SM_Prop_Crate_01.glb"])
    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=_fake_render([]),
        query_fn=_fake_query(
            {"SM_Prop_Crate_01": {"name": "Crate", "description": "d", "tags": [], "category": "prop"}}
        ),
    )
    assert result["skipped_bundle"] == ["Characters"]
    assert result["reviewed"] == ["SM_Prop_Crate_01"]


def test_render_failure_is_logged_and_skipped_not_fatal(tmp_path: Path):
    _pack(tmp_path, "POLYGON_Pack", ["models/SM_Bad.glb", "models/SM_Good.glb"])

    def render(glb, stills_dir, views, root):
        if "Bad" in glb.name:
            raise RenderError("boom")
        stills_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for v in views:
            p = stills_dir / f"{v}.png"
            p.write_bytes(b"fake-png")
            paths.append(p)
        return paths

    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=render,
        query_fn=_fake_query(
            {"SM_Good": {"name": "Good", "description": "g", "tags": [], "category": "prop"}}
        ),
    )
    assert result["ok"] is False
    assert result["reviewed"] == ["SM_Good"]
    assert result["failed"] == [{"id": "SM_Bad", "error": "render: boom"}]


def test_vlm_no_json_reply_is_logged_and_skipped_not_fatal(tmp_path: Path):
    _pack(tmp_path, "POLYGON_Pack", ["models/SM_Unclear.glb"])
    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=_fake_render([]),
        query_fn=lambda images, prompt: None,  # simulates query_local_vlm exhausting retries
    )
    assert result["ok"] is False
    assert result["reviewed"] == []
    assert result["failed"] == [{"id": "SM_Unclear", "error": "vlm: no usable JSON reply"}]


def test_deterministic_ordering_is_alphabetical_by_stem(tmp_path: Path):
    _pack(tmp_path, "POLYGON_Pack", ["models/SM_Zebra.glb", "models/SM_Apple.glb", "models/SM_Mango.glb"])
    order: list = []

    def query(images, prompt):
        stem = Path(images[0]).parent.name
        order.append(stem)
        return {"name": stem, "description": "x", "tags": [], "category": "prop"}

    review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=_fake_render([]),
        query_fn=query,
    )
    assert order == ["SM_Apple", "SM_Mango", "SM_Zebra"]


def test_match_filters_candidates(tmp_path: Path):
    _pack(tmp_path, "POLYGON_Pack", ["models/SM_Prop_Crate_01.glb", "models/SM_Veh_Car_01.glb"])
    result = review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        match="veh",
        render_fn=_fake_render([]),
        query_fn=_fake_query(
            {"SM_Veh_Car_01": {"name": "Car", "description": "c", "tags": [], "category": "vehicle"}}
        ),
    )
    assert result["candidates"] == 1
    assert result["reviewed"] == ["SM_Veh_Car_01"]


def test_missing_manifest_returns_error_not_exception(tmp_path: Path):
    result = review_pack(
        "NoSuchPack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=_fake_render([]),
        query_fn=_fake_query({}),
    )
    assert result["ok"] is False
    assert "error" in result


def _base_asset(aid: str) -> dict:
    asset = {
        "id": aid,
        "name": aid,
        "type": None,
        "category": [],
        "tags": [],
        "description": "",
        "semantic_role": None,
        "semantic_detail": None,
        "placement": empty_placement(),
        "ai_notes": "",
        "files": {"glb": None},
    }
    return stamp_auto(asset)


def test_reviewed_entry_round_trips_through_the_real_overlay(tmp_path: Path):
    """The exact shape review_pack writes must be exactly what
    apply_threejs_overlay (the overlay this catalog exists to feed) expects --
    this is the contract with sources/threejs_v2.py, not just review.py's
    own file format."""
    _pack(tmp_path, "POLYGON_Pack", ["models/SM_Prop_Crate_01.glb"])
    review_pack(
        "POLYGON_Pack",
        threejs_v2_root=tmp_path,
        synty_glb_root=tmp_path,
        render_fn=_fake_render([]),
        query_fn=_fake_query(
            {
                "SM_Prop_Crate_01": {
                    "name": "Wooden Crate",
                    "description": "A weathered wooden crate with metal bands.",
                    "tags": ["crate", "wood", "container"],
                    "category": "prop",
                    "semantic_role": "exterior_prop",
                }
            }
        ),
    )
    doc = json.loads((tmp_path / "POLYGON_Pack" / "catalog.json").read_text(encoding="utf-8"))
    entry = doc["assets"][0]

    asset = _base_asset("SM_Prop_Crate_01")
    apply_threejs_overlay(asset, entry, entry["file"])

    assert asset["name"] == "Wooden Crate"
    assert asset["description"] == "A weathered wooden crate with metal bands."
    assert set(["crate", "wood", "container"]).issubset(asset["tags"])
    assert asset["semantic_role"] == "exterior_prop"
    assert asset["provenance"]["name"] == "vlm_reviewed"
    assert asset["provenance"]["description"] == "vlm_reviewed"
    assert asset["provenance"]["tags"] == "vlm_reviewed"
    assert asset["files"]["glb"] == "POLYGON_Pack/models/SM_Prop_Crate_01.glb" or asset["files"]["glb"] == entry["file"]


def test_render_stills_passes_no_gizmo(tmp_path: Path, monkeypatch):
    """Review stills must render without the harness's human-scale gizmo --
    on small assets it dominates the frame and the VLM describes the gizmo
    (observed: a wall anchor reviewed as 'cotton_candy')."""
    from synty_inventory import review as review_mod

    glb = tmp_path / "SM_Prop_Crate_01.glb"
    glb.write_bytes(b"fake-glb")
    stills_dir = tmp_path / "_review_stills" / "SM_Prop_Crate_01"

    calls: list = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _Proc:
            returncode = 0
            stderr = ""

        for v in DEFAULT_VIEWS:
            (stills_dir / f"{v}.png").write_bytes(b"rendered")
        return _Proc()

    monkeypatch.setattr(review_mod.subprocess, "run", fake_run)
    review_mod._render_stills(glb, stills_dir, DEFAULT_VIEWS, tmp_path)
    assert calls and "--no-gizmo" in calls[0]


def test_views_for_swaps_thin_z_planar_to_front(tmp_path: Path, monkeypatch):
    """A wall sign (thin along Z) is edge-on in BOTH default views; review
    must render it face-on. Volumetric and thin-Y (floor) assets keep the
    default views, and a measurement failure must never kill the review."""
    from synty_inventory import review as review_mod

    glb = tmp_path / "SM_Sign_Hangar_01.glb"
    glb.write_bytes(b"fake-glb")

    cases = {
        # (min, max) -> expected views
        "thin_z_sign": (([0.0, 0.0, 0.0], [1.0, 0.6, 0.02]), ("front", "top")),
        "volumetric": (([0.0, 0.0, 0.0], [1.0, 1.0, 1.0]), DEFAULT_VIEWS),
        "thin_y_floor": (([0.0, 0.0, 0.0], [2.0, 0.05, 2.0]), DEFAULT_VIEWS),
        "thin_pole": (([0.0, 0.0, 0.0], [0.02, 3.0, 0.01]), DEFAULT_VIEWS),
    }
    for name, (measured, expected) in cases.items():
        monkeypatch.setattr(review_mod, "measure_glb", lambda p, m=measured: m)
        assert tuple(review_mod._views_for(glb, DEFAULT_VIEWS)) == tuple(expected), name

    def boom(p):
        raise ValueError("corrupt glb")

    monkeypatch.setattr(review_mod, "measure_glb", boom)
    assert tuple(review_mod._views_for(glb, DEFAULT_VIEWS)) == tuple(DEFAULT_VIEWS)
