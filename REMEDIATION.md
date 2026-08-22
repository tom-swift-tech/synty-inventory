# Remediation plan

Fixes for the findings in the 22 Aug 2026 project evaluation. Work in the
wave order below: each wave is independently shippable. Do not start Wave 3
until Waves 0–1 are in.

Finding IDs match the evaluation (`H1`–`H3`, `M1`–`M4`, `L1`–`L3`).

| Wave | Goal | Findings | Effort |
|---|---|---|---|
| 0 | Stop shipping known-wrong defaults | H1, H2, H3, L2 | hours |
| 1 | Make CI catch this class of bug | M4, M3, L1, L3 | half day |
| 2 | Engine overlays fail loudly, not silently | M2, M1 | half day |
| 3 | Rules become data plus dispatch | M5 | days, optional split |

Out of scope: putting licensed Synty trees or live catalogs in CI; rewriting
`infer()`; proving Unreal against a tree that does not exist.

---

## Wave 0 — correctness

### H1 — Declare numpy (and stop claiming stdlib-only)

**Problem.** `sources/glb_measure.py`, `sources/glb_geometry.py`, and
`sources/sockets.py` import `numpy` at module level. `enrich.py` always
imports sockets, so `scan` / `enrich` fail without numpy. `pyproject.toml`
lists no runtime dependencies. `requirements.txt` still says the runtime is
stdlib-only.

**Fix.**

1. Add runtime deps in `pyproject.toml`:

   ```toml
   dependencies = [
     "numpy>=1.26",
     "PyYAML>=6.0",
   ]
   ```

   numpy 1.26 is the floor that supports Python 3.11. PyYAML is already in
   `requirements.txt` and already optional-imported in `paths.py`; declaring
   it makes `pip install synty-inventory` match what the README tells people
   to install.

2. Change `requirements.txt` to:

   ```
   -e ".[dev]"
   ```

   Drop the stdlib-only comment and the duplicate `PyYAML>=6.0` line. The
   editable extra is how this repo is installed today.

3. Keep the `try: import yaml` fallback in `paths.py`. Declaring PyYAML does
   not require deleting the fallback; it just means a normal install has it.

**Files.** `pyproject.toml`, `requirements.txt`. README “Requires Python
3.11+” line: mention numpy.

**Tests.** Existing GLB / sockets tests already import numpy. After the
change, `pip install -e ".[dev]"` on a clean venv must pull numpy without a
manual extra. No new unit test required; CI install is the proof.

**Done when.** A fresh `pip install -e ".[dev]"` followed by
`python -c "from synty_inventory.enrich import enrich_catalog"` succeeds.
README / `requirements.txt` no longer say stdlib-only.

---

### H2 — Delete the shadowed `_viewer`

**Problem.** `cli.py` defines `_viewer` twice. The later copy
(`return Path(v) if v else None`) wins for every command, including `scan`.
The earlier `exists()` guard is dead. Missing `viewer_data` is no longer
treated as unset the way `_threejs_v2` / `_engine_root` are.

**Fix.**

1. Delete the second definition (currently just above `cmd_recipes`).
2. Keep one helper, same contract as `_engine_root`:

   ```python
   def _optional_root(cfg, key: str) -> Path | None:
       root = cfg.get(key)
       if root is not None and root.exists():
           return root
       return None
   ```

   `_viewer` becomes `_optional_root(cfg, "viewer_data")`. `_threejs_v2` and
   `_engine_root` can call it too so the three optional roots cannot drift
   again.

3. Do **not** wrap an already-`Path` value in `Path()` as a substitute for
   `exists()`. `load_config` already returns `Path` objects.

**Files.** `src/synty_inventory/cli.py`.

**Tests.** Add in `tests/test_cli.py`:

- configured path that does not exist → `_viewer` / `_optional_root` returns
  `None`
- configured path that exists → returns that `Path`
- `cmd_recipes` with a missing `viewer_data` still lists package recipes
  (does not crash trying to read `types/*.json` from a ghost root)

**Done when.** `cli.py` contains exactly one definition of the viewer-root
helper. A missing viewer path is indistinguishable from an unset one for
scan, enrich, recipes, and suggest.

---

### H3 — Stop defaulting review to a model that does not ground

**Problem.** `SETTING_DEFAULTS["vlm_local_model"]` is `gemma4:e4b`.
`config.example.yaml` (repo root and packaged copy) and the `review --model`
help text say the same. The README already records that e4b produces
confident, wrong descriptions and that `gemma4:26b` is the model that
grounds.

A default that stamps `reviewed: true` from a disqualified model is worse
than a slow default.

**Fix.**

1. Change the default in one place: `SETTING_DEFAULTS` in `paths.py` →
   `"gemma4:26b"`. `vlm.LOCAL_DEFAULT_MODEL` already reads from there.
2. Update both `config.example.yaml` copies, the `review --model` help
   string in `cli.py`, and the README sentences that currently say the
   default is e4b “for speed”.
3. Keep e4b as a documented *opt-in* (`--model gemma4:e4b` or
   `SYNTI_VLM_LOCAL_MODEL`) for throwaway smoke tests, not for batches.
4. Leave tests that pass `model="gemma4:e4b"` as an explicit argument
   alone. Change tests that assert the *default* is e4b
   (`test_vlm_local.py` around `LOCAL_DEFAULT_MODEL`).

Do not add a “refuse to stamp `reviewed: true` unless model is 26b”
allow-list. Operators may use other grounding models; the bug is the
default, not that e4b can be selected.

**Files.** `paths.py`, `cli.py`, `config.example.yaml`,
`src/synty_inventory/config.example.yaml`, `README.md`,
`tests/test_vlm_local.py`.

**Done when.** Unset config + unset env → `review` uses `gemma4:26b`.
README, example config, and `SETTING_DEFAULTS` agree. Existing
`test_packaged_example_and_skill_exist` still passes (the two example
configs stay identical).

---

### L2 — Emit `building/module`, not the v1 alias

**Problem.** `knowledge.TYPE_BY_KIND["building"]` is `"building/modular"`.
`schema.TYPE_MIGRATION` rewrites it to `"building/module"` later. Works, but
the rule layer still speaks v1.

**Fix.** Set `TYPE_BY_KIND["building"] = "building/module"`. Keep
`TYPE_MIGRATION` for catalogs already on disk. Grep `knowledge.py` and
tests for `building/modular`; update any assertion that the infer() type
is the v1 string.

**Files.** `knowledge.py`, `tests/test_knowledge_v2.py` (and any other hit).

**Done when.** `infer("SM_Bld_Shop_01")["type"]` is `building/module` before
migration. `TYPE_MIGRATION` remains for v1 JSON.

---

## Wave 1 — tests and CI

### M4 — Cover CLI, catalog, and query

**Problem.** 252 tests pass, but the agent-facing surface is thin:
`test_cli.py` 4, `test_catalog.py` 1, `test_query.py` 1. knowledge / sockets
/ mech / review / merge are the well-covered cores.

**Fix.** Add fixture-catalog tests (tmp_path JSON, no live packs). Minimum
set:

**CLI (`tests/test_cli.py` or `tests/test_cli_commands.py`)**

- `main(["config"])` with a temp `--config` prints JSON and exits 0 / 2
  according to whether required roots exist.
- `main(["search", "police", "--out", catalogs])` against a tiny written
  catalog returns a slim row with `id` / `pack` / `file`.
- `main(["details", "SM_Prop_Sign_Police_01", "--out", catalogs])` exits 0;
  unknown id exits 3.
- `main(["recipe", "ship_kit", "--out", catalogs])` against a catalog with
  no ship parts exits 4 and `complete: false`.
- Duplicate-helper regression from H2 lives here.

**Catalog (`tests/test_catalog.py`)**

- `write_catalog` is atomic: after a successful write the `.tmp` suffix is
  gone and `load_catalog` round-trips `pack_id` + assets.
- `rebuild_index` with two pack files writes `index.json` containing both
  `pack_id`s and does not drop the one that was not in `run_summaries`.
- `load_catalog` on v1 JSON returns a migrated v2 doc (delegate to schema
  helpers if `test_schema_v2.py` already covers the asset shape; this test
  only asserts the load path).

**Query (`tests/test_query.py`)**

- `search_assets` respects `--type` / `placeable=False` hiding /
  `--include-nonplaceable`.
- `search_assets` with `engine="unity"` puts the prefab in slim `file`.
- `suggest_assets_for("police station facade")` ranks the police sign above
  a generic prop when both are present (this is the skill’s contract; pin
  it).
- `get_asset_details` exact id wins over substring.

Do not re-test FTS internals here (`test_searchdb.py` already does). Do not
require `search.db` to exist; the linear fallback is the path under test.

**Done when.** Those three modules have enough tests that deleting
`_optional_root`’s `exists()` check, or changing slim-row keys, would fail
CI.

---

### M3 — Live tests must skip, not pass empty

**Problem.** `test_scan_city.py` returns without asserting when
`POLYGON_City` is absent. CI is green whether or not the live scan ran.
`gauntlet` is a live acceptance suite and cannot run in GitHub Actions
without licensed trees.

**Fix.**

1. Replace silent `return` in `test_scan_polygon_city_if_present` with
   `pytest.skip("POLYGON_City not on this machine")`. Same pattern for any
   other live-only test that currently no-ops.
2. Do **not** add gauntlet to `.github/workflows/test.yml`. Document in
   README Tests section:

   ```
   python -m pytest                  # fixture suite (CI)
   synty-inventory gauntlet          # live catalogs on this machine
   ```

3. Optional, only if cheap: `pytest -m live` marker so a local
   `pytest -m live` run is explicit. Not required for this wave.

**Files.** `tests/test_scan_city.py`, `README.md`. Maybe
`pyproject.toml` `[tool.pytest.ini_options]` if the marker is added.

**Done when.** `pytest` on a machine without City reports one skipped live
test, not a silent pass. CI still has no Synty assets.

---

### L1 — Ruff in CI

**Problem.** Pytest only. The duplicate `_viewer` and undeclared numpy were
cheap static misses.

**Fix.**

1. Add `ruff>=0.6` to `[project.optional-dependencies] dev`.
2. Minimal `pyproject.toml` config — don’t fight the existing style:

   ```toml
   [tool.ruff]
   target-version = "py311"
   line-length = 120
   src = ["src", "tests"]

   [tool.ruff.lint]
   select = ["E", "F", "W", "B", "I", "UP"]
   ignore = ["E501"]  # long recipe/knowledge strings
   ```

   Tune `ignore` against the first run rather than reformatting the repo
   in this wave. F401 (unused) and F811 (redefinition — the `_viewer` bug)
   are the point. Isort (`I`) only if the first run is small; drop it from
   `select` if it wants a thousand-line churn.

3. CI step after install, before pytest:

   ```yaml
   - name: Ruff
     run: python -m ruff check src tests
   ```

No mypy in this wave. The codebase is `dict`-heavy; a type-checker pass is
a separate project.

**Done when.** CI fails on a duplicate function definition. Existing tests
still pass. No mass reformat.

---

### L3 — One skill file to edit

**Problem.** `skill/SKILL.md` is what the README tells people to copy.
`src/synty_inventory/skill.md` is what the wheel ships. They can drift.
`test_packaged_example_and_skill_exist` already asserts they match when
run from a checkout — that is detection, not a single source.

Same dual-copy exists for `config.example.yaml` (repo root vs
`src/synty_inventory/config.example.yaml`). H3 already requires touching
both; fold the config copies into this item.

**Fix.** Keep the packaged copies (setuptools package-data must live inside
the package). Make the checkout copies canonical and fail fast:

1. Document at the top of each packaged copy:

   ```
   <!-- packaged copy of ../../skill/SKILL.md — edit that file, then copy -->
   ```

   YAML equivalent for `config.example.yaml`.

2. Strengthen `test_packaged_example_and_skill_exist` so a mismatch names
   both paths in the assertion message.

3. Do not add a build-time copy hook in this wave. If drift keeps
   happening, a later `scripts/sync_package_data.py` can replace the
   comment convention.

**Files.** `skill/SKILL.md`, `src/synty_inventory/skill.md`, both example
configs, `tests/test_paths.py`.

**Done when.** README says “edit `skill/SKILL.md` and
`config.example.yaml` (repo root), then copy into
`src/synty_inventory/`”. The existing equality test remains the gate.

---

## Wave 2 — engine overlays

These are honesty fixes. They do not invent Unreal or Godot packs.

### M2 — Godot: unmapped slugs must not silently misfile

**Problem.** `SLUG_PACK_OVERRIDES` covers `particle-fx`, `polygon-city-01`,
`polygon-starter`. `_normalize_slug` title-cases the rest and can produce
`Polygon_Scifi_City` for a real `POLYGON_SciFi_City` tree — close enough to
look discovered, wrong enough to attach scenes to nobody.

**Fix.**

1. Keep the explicit override table. Add a comment that new Godot export
   folders get an override *before* they are used, not a smarter guesser.
2. Change discovery so an unmapped folder is reported, not guessed into a
   pack_id:
   - `discover_pack_dirs` returns mapped dirs as today.
   - Unmapped dirs go on a `unmapped: [{slug, guess}]` list (scan summary
     and/or stderr warning), and are **not** applied as overlays.
3. `config` JSON may list godot_root exists=true plus `unmapped_slugs` if
   that stays small; otherwise a stderr line per unmapped slug during scan
   is enough.
4. When a real SciFi / Mech / etc. Godot export appears on disk, add the
   override in the same change that first scans it. Do not pre-fill
   fictional slugs.

**Files.** `sources/godot.py`, `enrich.py` / `cli.py` only if the warning
needs a place to surface, `tests/test_sources_godot.py`.

**Tests.** A temp `godot_root/polygon-scifi-city-02/` with a dummy `.tscn`
must not write `files.godot_scene` onto a `POLYGON_SciFi_City` catalog
asset. A mapped `polygon-city-01` still does.

**Done when.** Guessing cannot attach another pack’s scenes. The three
known slugs still resolve. README Godot section mentions “unmapped folders
are skipped and warned”.

---

### M1 — Unreal: keep “unproven”, fail closed

**Problem.** The Unreal overlay is implemented and documented as unproven.
The risk is a first real tree being silently mis-associated, same as Godot.

**Fix.** Mirror M2:

1. Do not add a live Unreal root to CI or to required config.
2. If `sources/unreal.py` already guesses pack_id from folder names, apply
   the same mapped-or-skip rule. If it only matches exact `pack_id` folder
   names, leave matching as-is and add a test that a differently named
   folder does not overlay.
3. Leave the README sentence “that path is implemented, not proven against
   live packs.” Add one line: overlays apply only when the folder name
   equals `pack_id` (or an explicit override table, if you introduce one).

**Files.** `sources/unreal.py`, `tests/test_sources_unreal.py`, README
(one sentence).

**Done when.** Fixture tests still pass. A stray folder under `unreal_root`
cannot stamp `files.unreal_uasset` on an unrelated pack. No claim of live
coverage is added.

---

## Wave 3 — knowledge.py as data plus dispatch

### M5 — Stop growing a 1,575-line module as each pack lands

**Problem.** `infer()` has no pack context. `CURATED` has two exact ids.
`TOKEN_TAGS` and the sci-fi / military / mech dispatch live in one file.
New packs mean more Python, not more tables.

This wave is larger and easy to over-scope. Split it.

**3a — Extract tables (do this).**

Move to package data JSON (next to `recipes/`):

| Table | Dest | Shape |
|---|---|---|
| `CURATED` | `data/curated.json` | `{id: {name, type, tags, description, …}}` |
| `TOKEN_TAGS` | `data/token_tags.json` | `{token: {tags, contexts, category}}` |
| `PACK_STYLES` | `data/pack_styles.json` | `{pack_id: style}` |

Load once at import (or `lru_cache`). `infer()` dispatch functions stay in
`knowledge.py`. Exact-id curated records remain rank `curated` in
`enrich.py`.

Add `synty_inventory = […, "data/*.json"]` to package-data.

Pin today’s behaviour with the existing `tests/test_knowledge_v2.py` (80
tests). Any extract that changes a fixture stem’s type/role is a bug.

**3b — Do not do in this plan.**

- Pack-aware `infer(stem, pack_id=…)`
- Replacing `_infer_vehicle_part` / `_infer_mech` / … with a DSL
- Generating rules from catalogs
- Growing `CURATED` to “every important asset” — that is what viewer /
  vlm_reviewed are for. Curated stays the quality bar for a handful of
  POI pieces.

**Done when (3a).** `knowledge.py` no longer contains the curated police /
barber dicts or the token-tag map as Python literals. `python -m pytest
tests/test_knowledge_v2.py` is green. Wheel still includes the JSON.

---

## Suggested commit sequence

One finding per commit keeps `gauntlet` blame usable:

1. `fix(cli): single optional-root helper for viewer_data` (H2)
2. `fix(rules): TYPE_BY_KIND building/module` (L2)
3. `fix(review): default local VLM to gemma4:26b` (H3)
4. `fix(packaging): declare numpy and PyYAML` (H1)
5. `test: CLI, catalog, query surfaces; skip live City` (M4, M3)
6. `ci: ruff check` (L1)
7. `docs: canonical skill and example config` (L3)
8. `fix(godot): skip unmapped export slugs` (M2)
9. `fix(unreal): overlay only exact pack_id folders` (M1, if needed)
10. `refactor(rules): load curated/token/style from JSON` (M5 / 3a)

---

## Verification

After each wave:

```
python -m pytest
```

After Wave 0–1, on a machine with catalogs:

```
synty-inventory config
synty-inventory gauntlet
```

Gauntlet is the live quality bar. None of these fixes should move a gate
from ok → fail. If `high_value_richness` or `search_police` flips, the
change is wrong even if pytest is green.

Wave 0 must not require a rescan. Wave 3a must not require a rescan
either (same `infer()` outputs). H2 can change scan only when
`viewer_data` was set to a missing path — that case currently feeds a
ghost root; after the fix it behaves as unset, which is the intended
contract.
