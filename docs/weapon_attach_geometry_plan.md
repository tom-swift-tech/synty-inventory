# Build plan: geometry fit gate G1

**Spec:** [weapon_attach_geometry.md](weapon_attach_geometry.md) (G1, "the spec"; a bare `§N` points into it). APPROVED by Tom on 2026-10-27, with Q-G4 adopted. **Parent:** [weapon_attachments.md](weapon_attachments.md) (`A§N`).
**Written:** 2026-10-27, by the architect, on `plan/attach-geom` (cut from `integ/attach` at `5f106fa`).
**Delivers:**
- `WEAPON_ATTACH_VERSION` 14 and `WEAPON_GEOMETRY_VERSION` 6;
- AC131 to AC149;
- the Q-G4 edits: INV-19 and AC77 amended, INV-28 added, AC67 unchanged.

**Out of scope:**
- sit-capabilities: no file there changes. sit_armory 0.3.0 and sit_weapons 0.4.0 need nothing (§4.6).
- any push;
- merging `integ/attach` into `main`, which is Tom's call;
- the other three slots (Q-G12).

## 0. Rules for every slice

1. **Bases and worktrees.**
   - **B0** is the `integ/attach` commit that merges this plan. The lead resolves the SHA; a brief never names a branch as its base.
   - Each slice gets branch `build/g1-<slice>` and worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-<slice>`, created by the lead at the slice's base before spawn.
   - The lead writes `.agent-scope.json` there (`owned` = the slice's list below, `new_under` = `[]`). Manifests are write-once. A wider scope means a fresh worktree with a new manifest.
   - The builder never rebases, pulls or merges. Blocked means stop and report.
   - The lead verifies the gate, then merges the slice into `integ/attach` locally (`merge: build/g1-<slice> <sha>, ...`). The next slice's base is that merge SHA.
2. **Gate (every slice), run from the slice's worktree.**
   - **Suite.** `python -m pytest`, the whole suite (`testpaths = tests`; `live`-marked tests skip without the packs).
     - Pass means exit code 0 and a summary line with no `failed` and no `error`.
     - Report the passed and skipped counts, and the base's counts.
     - Gate the commit on that output explicitly; never chain a commit after the test run.
   - **Scope gate, last.** `git diff --name-only <base>` and `git status --porcelain` show only owned paths. Any other path fails the slice.
   - **Failing first.** Each new test is shown failing on the base, or on the deliberate break its AC names, before it goes green.
   - **Literal bounds.** A test's bounds are literals in the test, never values read from the rules file or from the constant under test (AC137).
   - **Re-pins.** An existing test may be edited only where a G1 clause changes its expectation. The report lists each edit with that clause.
3. **Synthetic fixtures only.**
   - Meshes are generated in `tests/fixtures/weapons/g1_*.py`, through the existing `wfx` and `make_glbs` helpers.
   - Fake packs (`FAKE_*`) only. No pack mesh, no measured number, no pack-derived id list.
   - The W7 references (`w7_default_export.json`, `w8d_w7_*`) are W7 outputs and stay untouched (§4.6). No slice owns them.
4. **Live data.**
   - Only S10 and S12 touch real packs.
   - They go through the lead's scratch config: a scratch copy of the catalogs, with the GLBs read-only.
   - Nothing runs against `D:/game_assets_library/synty_catalogs`.
   - Measured files stay in scratch and are never committed.
5. **Versions (D-12: each bump lands with the change it versions).**
   - `WEAPON_GEOMETRY_VERSION` 5 → 6 lands in S1, with the frame vote.
   - `WEAPON_ATTACH_VERSION` 13 → 14 lands in S8, with the gate.
   - Between slices, `integ/attach` carries intermediate states. It is local and is exported to no game until S11 passes.
6. **Lanes.**
   - A Sonnet builder agent (brief from `~/.claude/builder-brief-template.md`), or a child through the `dispatch` skill: Codex Sol or Luna, or the Cursor lane (which runs the Grok lane while Grok is out of credit).
   - **Never Opus.** Astra is not used.
   - A dispatch child's writes bypass the scope hook, so the git scope gate is the enforcement. The lead checks each child's RESULT against the slice's ACs and gate.
7. **Findings, not tuning.**
   - These are findings, reported to the lead: a count that differs from §1.1, a literal that does not cover its positives, a frame change on an unexpected record, or a changed `archetype`, `genre` or `hold_class`.
   - No literal, tolerance or rule moves to make a number match.
   - A spec change goes to the lead and then Tom.

## 1. Slice map

| # | slice | lane | parallel group | base | ACs closed |
|---|---|---|---|---|---|
| S1 | frame vote, record frame, geometry version 6 | Sonnet builder | spine | B0 | AC147 (record, fixtures), AC67 (unchanged), AC77 and INV-19 amended, AC78, INV-28, AC146 (geometry part), §4.5 `frame_axis` |
| S2 | fit interface: types, verdict tables, digest, rules block, detector stubs | Codex Sol | spine | S1 | §3.1 step 4, §3.5, §3.6 and §3.7 verdict tables, AC143 (digest literal), AC144, §4.1 validator |
| S3 | locator and strip | Cursor lane | **P1** | S2 | AC131 (fixture), AC132 (fixture) |
| S4 | rails, flat seat, sight clip | Sonnet builder | **P1** | S2 | AC134 (fixture), AC148 (detector part) |
| S5 | bore: barrel end, device inner ring | Codex Sol | **P1** | S2 | AC135 (fixture), AC138 (barrel-end part) |
| S6 | well reference and entry section | Codex Luna | **P1** | S2 | AC136 (fixture), the drum case |
| S7 | seats: host features into mounts, `feature`, frame conflict, preset fill | Sonnet builder | spine | S3 to S6 merged | AC147 (conflict), INV-27, AC148 (seats, gate 6(c)), AC139 item 1, Q-G11 |
| E1 | errata E1: round-end circularity, one landing test, strip rules | Sonnet builder or Codex Sol | spine | S7 | AC131, AC132 and AC135 (fixtures), INV-29 |
| S8 | verdict in compat, retired rules, export, attach version 14 | Sonnet builder | spine | E1 | AC133, AC138, AC139, AC140, AC143, AC145 (export), AC146, AC148, AC149, INV-22, INV-23, INV-25 |
| E2 | errata E2: retire S7 fold-in 4 (E2-Q3), a ring needs two radii (E2-Q2) | Sonnet builder or Codex Sol | spine | S8 | AC135 (E2.6 fixtures), AC138 (E2-Q3 guard) |
| S9 | tools: `attach-calibrate`, `attach-spotcheck`, eval table, preview pairs and icons | Codex Sol | spine | E2 | AC137, AC141 (fixture), AC142, AC144 (re-run), INV-24, INV-26 |
| S10 | first full build and re-measurement (live) | operator agent runs, lead verifies | none | S9 | live parts of AC131 to AC140, AC143, AC145 (consumer side), AC146 to AC148; the §4.7 impact record |
| S11 | final review | reviewer agent, plus the lead's look | none | S10 | every AC, the captures |
| S12 | spot check (once) | lead | none | after S11 **and the peer's word** | AC141 (live), §3.10 |

**Parallel group P1** (S3, S4, S5, S6) is the only parallel phase. Each slice owns new files only, disjoint from the others, in its own worktree at the same base (S2's merge). The lead merges all four before S7. Everything else is the spine and runs one slice at a time. That is why the spine slices may own a test glob: no sibling runs beside them.

## 2. Slices

### S1. Frame vote and record frame (Q-G4), geometry version 6

- **Lane:** Sonnet builder. **Base:** B0. **Size:** M.
- **Owns:**
  - `src/synty_inventory/weapons/geometry.py`
  - `src/synty_inventory/weapons/mount_probe.py` (adds `end_ring_d` only)
  - `src/synty_inventory/weapons/__init__.py` (the `WEAPON_GEOMETRY_VERSION` line and its comment only)
  - `src/synty_inventory/weapons/overrides.py`
  - `src/synty_inventory/weapons/directory.py` (passing `frame_axis` from the id override into `_measure_record` and `measure_cached` only)
  - `tests/test_weapons_g1_frame.py` (new), `tests/fixtures/weapons/g1_frame_world.py` (new), `tests/fixtures/weapons/g1_refs.py` (new)
  - `tests/test_weapons_*.py` (re-pins only, rule 2)
- **Builds:**
  - In `mount_probe.py`: `end_ring_d` (§3.6 (ii)). It lives in this numpy-only leaf because `geometry.py` imports `mounts.py`, and S7 makes `mounts.py` reach the detectors. A detector importing from `geometry.py` would close an import cycle.
  - In `geometry.py`, per §3.3 and §3.11:
    - `_FRAME_END_SLAB_M`, `_FRAME_BORE_MAX_M`, `FrameVote` and `frame_vote`, which calls `mount_probe.end_ring_d`;
    - in `measure_weapon_detail`, on an eligible host only, the body mesh is the host minus the nodes the child vocabulary matches. Read `mounts.mesh_nodes` and `mounts.matching_slots`; do not edit `mounts.py`;
    - steps 1 to 5 of §3.3, with `forward_source` `"body"`. Everything after the axes (length, tip, butt, grip, pivot, muzzle, `item_basis`, reasons, mounts) follows the voted frame;
    - `pass2_inputs` returns the pre-vote `long_axis`, `length_m` and `axes_unexpected` (§3.3, "Classification does not read the vote"). `geometry.long_axis` stays the bounding-box axis;
    - the frame state (`changed`, `conflict`) travels beside `geometry` in the detail, like `child_extents`, for S7. It is not a record key;
    - the fingerprint gains `fa` (the `frame_axis` value) only when one is set, as `fo` does.
  - `WEAPON_GEOMETRY_VERSION = 6`, with the comment "6: the body-axis frame vote on eligible hosts (G1, §3.3)".
  - `overrides.py`: `frame_axis` in `ID_ENTRY_KEYS`, validated to `x`, `y` or `z`, and returned by `effective_override`.
  - Re-pins, `geometry_version` 5 → 6. Found by grep at B0:
    - `test_weapons_directory`, `_export`, `_forward_override`, `_geometry`, `_w2f_cache`, `_w7_geometry`;
    - `_w8b_cache`, `_w8b_identity`, `_w8d_export`, `_w8f_forward`, `_w8h_versions`, `_w8i_rules`, `_w8j_baked`;
    - `_w8k_pending`, `_w8l_versions`, `_w8m_cache`, `_w8n_versions`, `_w8o_rules`, `_w8p_rules`.
  - The comparisons against the W7 references read the reference's `geometry_version` 5 as 6 through one helper, `g1_refs.as_geometry_v6(text)`. It replaces exactly one occurrence and fails if there is not exactly one. Each comparison asserts `geometry_version == 6` on its own. The comparisons are in `test_weapons_w8b_identity`, `_w8d_export`, `_w8d_regression` (header check), `_w8o_export` and `_w8p_export`.
- **Fixtures (synthetic):**
  - an Uzi-shaped host: magazine longer than the barrel, a 15 mm ring at the muzzle end, no ring at the stock end;
  - a both-rings host;
  - a normal rifle;
  - an Uzi-shaped record that is not eligible (role `part`);
  - an Uzi-shaped record whose kind is guessed.
- **ACs:**
  - AC147, record side:
    - On the Uzi fixture, forward is the barrel axis toward the ring, with `forward_source` `"body"`; `item_basis` is a signed permutation; `length_m` and `geometry.muzzle` follow the barrel.
    - The muzzle mount equals `geometry.muzzle` (AC67).
    - The both-rings fixture keeps its build frame and reports `conflict`.
    - `frame_axis` on it sets the axis, and `forward` then sets the sign.
    - The normal rifle and the ineligible record are unchanged.
  - AC67: its existing tests pass untouched.
  - AC77 and INV-19, amended: the default exports of the synthetic worlds equal the W7 references read as version 6.
  - AC78: a bump to 7 misses the cache, and a hit equals a recompute on the Uzi fixture.
  - AC146, geometry part: `rules_digest` `7b9829af37328fe7` and `overrides_digest` are unchanged.
  - Convergence: the guessed-kind record converges, with its kind taken from the pre-vote long axis.
- **Stop and report if** any record of an existing synthetic world changes frame. That is a finding, not a re-pin.

### S2. Fit interface: types, verdict tables, digest, rules block, detector stubs

- **Lane:** Codex Sol (dispatch). **Base:** S1 merged. **Size:** M.
- **Owns:**
  - `src/synty_inventory/weapons/fit_types.py` (new)
  - `src/synty_inventory/weapons/fit_geometry.py` (new)
  - `src/synty_inventory/weapons/fit_locate.py`, `fit_rails.py`, `fit_bore.py`, `fit_well.py` (new, stubs)
  - `src/synty_inventory/data/weapon_rules.yaml`
  - `src/synty_inventory/weapons/rules.py`
  - `tests/test_weapons_g1_verdict.py`, `tests/test_weapons_g1_rules.py`, `tests/test_weapons_g1_deps.py` (new)
  - `tests/test_weapons_*.py` (re-pins only, rule 2; expected: the `attach_rules_digest` pin in `test_weapons_w8p_rules.py`)
- **Builds:**
  - `fit_types.py`: the §3.11 dataclasses except `FrameVote` (`RailRun`, `BarrelEnd`, `WellRef`, `Placement`, `Verdict`) and the §3.1 step 5 signal vocabulary. The detector modules import from here, so the facade has no import cycle.
  - Detector stubs: each has the exact §3.11 signature, a docstring citing its spec section, and `raise NotImplementedError`. P1 replaces them.
  - `fit_geometry.py`:
    - re-exports the types and the detector functions;
    - `verdict()` implements the §3.1 step 4 values and the §3.5, §3.6 and §3.7 step 3 tables over host feature dicts;
    - `fit_digest()` implements §4.3.
  - The §4.1 block in `weapon_rules.yaml`, with no `frame:` key.
  - The validator in `rules.py`: every key required, no negative length, no inverted interval.
  - `attach_rules_digest` moves, so its pin is re-pinned with the comment "G1 S2: fit_geometry block".
- **ACs:**
  - **Verdict tables.** One test per row:
    - an unmeasured anchor gives `unverified`;
    - `seat_ref` uses the flat run, or the child's own foot length on a stepped seat;
    - width is not checked on `seat_ref`;
    - no barrel end gives `no_fit`;
    - a null `mate_d_m` gives `unverified`;
    - the inner-ring band applies only when a ring exists;
    - an empty section gives `unverified` with signal `drum`;
    - no seat and no feature gives `not_judged`.
  - **AC143, digest part.** A synthetic list of measure records has a literal `fit_digest`, the same under `PYTHONHASHSEED` 0 and 1 (subprocess runs).
  - **AC144.** An AST scan of every `fit_*.py` import finds only the standard library, `numpy` and `synty_inventory`. `pyproject.toml` `dependencies` and `optional-dependencies` equal literals in the test.
  - **§4.1.** The validator rejects a missing key, a negative length and an inverted interval, one test each.

### P1. Detectors (S3 to S6, in parallel)

All four have base S2 merged, and each runs in its own worktree. Each owns exactly one stub module (now built), one new test file and one new fixture module. All are pure functions over `(f, s, u)` arrays, so none needs a real host record. Rule values come from literal dicts in the tests. A detector module imports only the standard library, `numpy`, `fit_types` and `mount_probe`, never `geometry`, `mounts` or `fit_geometry`, which keeps the S7 wiring free of import cycles.

#### S3. Locator and strip

- **Lane:** Cursor lane (dispatch). **Size:** S.
- **Owns:** `src/synty_inventory/weapons/fit_locate.py`, `tests/test_weapons_g1_locate.py`, `tests/fixtures/weapons/g1_locate_meshes.py`.
- **Builds:** `locate_by_translation` and `strip`, per §3.2:
  - a 0.5 mm grid with a 27-neighbour tolerance;
  - candidate translations from the smallest vertex;
  - a 24-vertex prefilter;
  - acceptance at hit 1.0, and placements within 2 mm merged.
- **ACs:**
  - **AC131, fixture.**
    - A host built from 3 translated parts returns exactly those 3 translations.
    - A part with one vertex moved 1 mm is not located.
    - Break: at `hit_min` 0.9 it is located.
    - Break: without the 27-neighbour tolerance, a placement on a half-grid offset is lost.
  - **AC132, fixture.**
    - After `strip`, the host equals the base mesh triangle for triangle.
    - No remaining triangle has all three vertices on a located part.

#### S4. Rails, flat seat, sight clip

- **Lane:** Sonnet builder. **Size:** M.
- **Owns:** `src/synty_inventory/weapons/fit_rails.py`, `tests/test_weapons_g1_rails.py`, `tests/fixtures/weapons/g1_rail_meshes.py`.
- **Builds:**
  - `rail_runs`, top and bottom, per §3.4 steps 1 and 2;
  - `flat_seat`, per step 3;
  - two pure helpers for S7:
    - `clip_run(run, sight_front_f, sight_clear_m)` (step 4, sight seats);
    - `seat_point(run, default_seat_len_m)` (step 4).
- **ACs:**
  - **AC134, fixture.**
    - A 6-tooth rail at 23.5 mm pitch is found, with its pitch, amplitude, count and width.
    - A run outside the [0.15, 0.85] zone is not found.
    - Uneven tooth tops beyond 1.5 mm break the run.
    - Break: `tooth_min_count` 6 drops a 5-tooth rail.
    - Break: `pitch_max_m` 0.016 drops the 23.5 mm rail.
  - **AC148, detector part.**
    - A smooth 80 mm top gives a flat seat with `toothed` false.
    - A toothed host gives no flat seat.
    - `clip_run` ends a run 10 mm behind a front sight.

#### S5. Bore

- **Lane:** Codex Sol (dispatch). **Size:** S.
- **Owns:** `src/synty_inventory/weapons/fit_bore.py`, `tests/test_weapons_g1_bore.py`, `tests/fixtures/weapons/g1_bore_meshes.py`.
- **Builds:**
  - `barrel_end`: (i) the mount's `bore_source`; (ii) `mount_probe.end_ring_d`, imported from S1's work, not re-implemented, and never imported through `geometry.py`; (iii) the round section with the OD cap. All per §3.6.
  - `device_inner_d`.
- **ACs:**
  - **AC135, fixture.**
    - A ringed end and a round end are found, with `od_m` within 0.5 mm.
    - A square end gives none.
    - A 70 mm round end gives none.
    - A device at OD ratios 0.84 and 2.01 falls out of band, and at 0.86 and 1.99 falls in.
    - The inner-ring band behaves the same way.
    - Break: measuring the unreduced mesh (a baked device's face read as the barrel) is caught by a fixture with a baked device.
  - **AC138, barrel-end part.** On a host with no barrel end, `fit_geometry.verdict` gives `no_fit` for muzzle.

#### S6. Well

- **Lane:** Codex Luna (dispatch). **Size:** S.
- **Owns:** `src/synty_inventory/weapons/fit_well.py`, `tests/test_weapons_g1_well.py`, `tests/fixtures/weapons/g1_well_meshes.py`.
- **Builds:** `crossings` (the 1e-5 m offset off edges), `well_reference` and `entry_section`, per §3.7 steps 1 and 2.
- **ACs:**
  - **AC136, fixture.**
    - An identical magazine reads 0.000.
    - One 12 % wider fits at 0.15; one 40 % wider does not.
    - Break: cutting at the magazine's own top instead of `u_rb − 0.002` misjudges a tapered magazine.
  - **Drum.** A magazine that does not reach the plane gives no section, which `verdict` turns into `unverified`, signal `drum`.

### S7. Seats: host features into mounts

- **Lane:** Sonnet builder. **Base:** `integ/attach` with S3 to S6 merged. **Size:** L.
- **Owns:**
  - `src/synty_inventory/weapons/mounts.py`
  - `src/synty_inventory/weapons/geometry.py`
  - `src/synty_inventory/weapons/directory.py`
  - `src/synty_inventory/weapons/schema.py`
  - `src/synty_inventory/weapons/fit_geometry.py`
  - `tests/test_weapons_g1_seats.py` (new), `tests/fixtures/weapons/g1_world.py` (new)
  - `tests/test_weapons_*.py` (re-pins only, rule 2)
- **Builds:**
  - **`fit_geometry.host_features(...)`** computes each eligible host's features once, in the record frame:
    - located placements (presets only) and strip;
    - top and bottom runs, and the flat seat;
    - the barrel end;
    - the well reference.
  - It caches them in `<catalogs>/weapons/_fit_cache.json` under the §3.11 key, which includes `WEAPON_GEOMETRY_VERSION` and the `fit_*.py` code digests.
  - **`mounts.build_mounts`**, per §3.4 step 4:
    - writes rail seats (`source: "probe"`, `feature`, confidence 0.5, `mount_estimated`) when there is no child or override seat, with flat seats for optic only;
    - applies the sight clip;
    - sets `feature` on muzzle seats (`barrel_ring` or `barrel_round`) and on magazine child seats with a well reference (`well_ref`);
    - withholds every detector seat on a frame-conflict host (§3.3 step 4, INV-27);
    - `refuse_filled` reads the located placements (Q-G11).
  - **`geometry.py`:** the `mv` fingerprint gains `fg` (the `fit_geometry` block) and `fd` (the `fit_*.py` code digests).
  - **`directory.py`:** carries the host features beside `geometry`, as `child_extents` is carried, for S8.
  - **`schema.py`:** the optional mount key `feature` and its enum.
  - **`g1_world.py`**, a `FAKE_G1` pack world, used by S8 and S9 too:
    - a preset with a fused scope and a fused silencer;
    - a toothed rifle with a front sight seat;
    - an untoothed rifle with an authored optic child;
    - a stepped seat and a flat-top host;
    - the Uzi-shaped SMG and the both-rings host;
    - a launcher with a baked optic, a shotgun, a tool, a minigun;
    - magazines of two families plus a drum;
    - devices with and without an inner ring;
    - a cross-pack twin.
- **ACs:**
  - **AC147, conflict part, and INV-27.** The both-rings host has no detector seat.
  - **AC148, seats.** Rail seats sit on toothed hosts and flat seats on the flat-top host. A§4.6 gate 6(c) holds on the railed host with a front sight. Break: without the clip, 6(c) fails.
  - **AC139 item 1 and Q-G11.** The fused scope and silencer slots of the preset are refused, and its magazine stays open.
  - **Counts.** The number of hosts carrying each `feature` value is reported.
  - **Cache.** The fit cache and the `mv` fingerprint each miss on a bump of `WEAPON_GEOMETRY_VERSION`, on a bump of `WEAPON_ATTACH_VERSION`, on an edit of the `fit_geometry` block and on a `fit_*.py` code change. A hit equals a recompute (the AC78 pattern).
- **Expected re-pins:** existing synthetic hosts with a smooth top of 60 mm or more gain an optic flat seat (§3.4 step 3). Each such re-pin cites §3.4 step 3. Any other mount change is a finding.

### S8. Verdict in compat, retired rules, export, attach version 14

- **Lane:** Sonnet builder. **Base:** E1 merged (errata E1.5). **Size:** L.
- **Owns:**
  - `src/synty_inventory/weapons/compat.py`
  - `src/synty_inventory/weapons/directory.py`
  - `src/synty_inventory/weapons/export.py`
  - `src/synty_inventory/weapons/schema.py`
  - `src/synty_inventory/weapons/rules.py`
  - `src/synty_inventory/data/weapon_rules.yaml`
  - `src/synty_inventory/weapons/__init__.py` (the `WEAPON_ATTACH_VERSION` line and its comment only)
  - `src/synty_inventory/weapons/fit_geometry.py`
  - `tests/test_weapons_g1_compat.py`, `tests/test_weapons_g1_export.py` (new), `tests/fixtures/weapons/g1_world.py`
  - `tests/test_weapons_*.py` (re-pins only, rule 2)
- **Builds:**
  - **`compat.candidate()`** calls `fit_geometry.verdict()` for the four slots (§3.1). It sets the tier by pack relation, applies A8-1 after it, scores from the tier base only, and fills `signals` from the §3.1 vocabulary.
  - **Retired rules (§3.8)** are removed from the four slots in `weapon_rules.yaml`. `rules.py` rejects a retired key that names one of them.
  - **The well pair pass in `directory.py`**, before compat:
    - for each magazine part and each host with a well reference, place the part at the reference seat (C-21) and cut it at `u_rb − 0.002`;
    - the result is cached per pair, as `settle_cached` does, so `compat` stays a pure function over records and carried maps;
    - `fit_digest` goes at the directory top level.
  - **`export.py`:** `fit_digest` goes in `generated_from` with `--attachments` only, and `feature` passes through.
  - **`schema.py`:** optional `signals` on directory-form pending entries, and `fit_digest`.
  - **Versions.** `WEAPON_ATTACH_VERSION = 14`, with the comment "14: G1, the geometry fit gate for optic, muzzle, underbarrel and magazine". The `attach_version` 13 pins are re-pinned, and so is `attach_rules_digest`.
- **ACs (on `g1_world` and the existing worlds):**
  - **AC133.** Fixture twins give `fit`; the drum twin gives `unverified`; the slide-face silencer gives `no_fit`. Twin listing is unchanged.
  - **AC138.** Zero listed entries for each negative control.
  - **AC139.** One fixture test per standing refusal (items 2 to 5). The refused (slot, host) set is a superset of the set at S7's merge.
  - **AC140.** Zero `cross_pack_fit` magazine entries listed, and the count judged `fit` is printed.
  - **AC143.** Two builds of `g1_world` under `PYTHONHASHSEED` 0 and 1 give identical `directory.json` bytes and `fit_digest`.
  - **AC145.** Every mount `source` is in the four values; the export validates; `feature` and `fit_digest` are optional.
  - **AC146.** Attach version 14; `rules_digest` and `overrides_digest` unchanged; `attach_rules_digest` changed. The default exports equal the W7 references read as version 6.
  - **AC148.** No listing through `rail_flat` alone; `seat_ref` lists on the untoothed host with an authored child.
  - **AC149.** Permuting tokens and blanking `attach_affinity` change no entry in the four slots. In the other three slots, every entry equals the entry at S7's merge.
  - **INV-22, INV-23, INV-25.**

### S9. Tools

- **Lane:** Codex Sol (dispatch). **Base:** E2 merged (errata E2.4). **Size:** M.
- **Owns:**
  - `src/synty_inventory/weapons/cli.py`
  - `src/synty_inventory/weapons/fit_calibrate.py` (new)
  - `src/synty_inventory/weapons/spotcheck.py` (new)
  - `src/synty_inventory/weapons/eval.py`
  - `src/synty_inventory/weapons/preview.py`
  - `tests/test_weapons_g1_calibrate.py`, `tests/test_weapons_g1_spotcheck.py`, `tests/test_weapons_g1_tools.py` (new)
  - `tests/test_weapons_*.py` (re-pins only, rule 2)
- **Builds:**
  - **`attach-calibrate`** (§3.11):
    - runs over the oracle: presets through the locator, twins, baked children;
    - prints, per literal, its positives by class, the max error, the margin and the literal, `_FRAME_BORE_MAX_M` included;
    - exits 6 on an uncovered literal;
    - `--json` writes outside the repo only.
  - The JSON also carries two pair lists for `attach-preview`:
    - `sheets.toothed`: one listed `rail_teeth` pair per toothed host, or the host's best pending pair when none is listed;
    - `sheets.frame`: one muzzle pair per frame-changed host.
  - **`attach-spotcheck --draw | --score`** (§3.10):
    - the data path can be injected for tests;
    - the real `weapon_attach_spotcheck.json` is written only in S12.
  - **`attach-eval`:** the agreement table per slot (AC142); no exit code depends on agreement for the four slots.
  - **`attach-preview`:**
    - `--pairs FILE` takes a `weapon-attach-spotcheck/1` file or `{"pairs": [{"part", "host"}]}`;
    - `--icons ROOT...` puts each pair's HUD icons beside its render on the sheet. Icons are resolved by the §3.2 name rule and read by path, never copied.
    - It renders against any `--directory`, so the same pairs render from a8c and from a14.
- **ACs:**
  - **AC137.** On a synthetic oracle, `attach-calibrate` exits 0. With `clamp.overhang_max_m` 0.007 it exits 6 and names the literal. The expected maxima are literals in the test.
  - **AC141, fixture.**
    - The draw gives 32 pairs, 8 per slot, at least 2 per non-empty tier.
    - It contains no twin, no override and no labelled pair, in hash order.
    - A second draw exits 6.
    - `--score` prints `fits k of 32 (placed wrong m)`.
  - **AC142.** Exit 0 at any agreement.
  - **AC144.** Re-run, covering the two new modules.
  - **INV-24.** Covered by AC137.
  - **INV-26.** A fixture shows `fits` and `placed_wrong` change only from null.
- **Plan decision for the lead to confirm:** AC79's exit-4 path (gates passed explicitly) stays for `laser_light` and the sight slots, which keep the label-era rules (Q-G12). For the four slots, AC142 rules.

## 3. S10: first full build and re-measurement (live)

- **Where:**
  - In the integ worktree `D:/game_assets_library/tools/inventoryagent-wt-integ`, at the S9b merge SHA, with `PYTHONPATH=<integ>/src`.
  - Through the lead's scratch config (§0 rule 4).
  - Outputs go to a new scratch folder, `g1_build/`.
- **Who:** an operator agent runs the commands and returns raw numbers and files. The lead compares them with §1.1 and writes the impact record.
- **Before side, a8c:**
  - `integ/attach` `5633ded`: 3,502 entries, `attach_version` 13;
  - `attach_rules_digest` `bcd5dbd0b3d7a651`, `rules_digest` `7b9829af37328fe7`, `overrides_digest` `0a2948d6cab4c77e`.
  - Its directory and exports sit in the lead's session scratch (`w8o_captures/a8c/` when this was written). If they are gone, rebuild them from `5633ded` in a separate worktree with the same config.

**Steps:**

1. `weapons build` (cold geometry cache, version 6), then `weapons validate`, then the default export and the `--attachments` export.
2. `weapons attach-calibrate --json <scratch>/g1_build/calibrate.json`. Expect exit 0 (AC137, live).
3. Re-measure against §1.1. Each number is reported beside its §1.1 value, and any deviation is a finding:

   | AC | what is checked |
   |---|---|
   | AC131, AC132 | 163 placements, by slot ("other" 117; errata E1-Q1); on every preset, no remaining host triangle has all three vertices on a located part |
   | AC133 | 36 of 38 twins `fit`, and the 2 others by reason |
   | AC134 | 45 top and 14 bottom toothed hosts by class; 13 of 14 preset optics and all 16 toothed positives on runs; 3 of 4 preset underbarrels on bottom teeth |
   | AC135 | the 11 bore positives; has-end 236, none 21 (errata E1.3, merged-detector census); movers listed by class |
   | AC136 | 14 twin magazines at 0.000, and the Military matrix |
   | AC138 | zero entries in every negative control |
   | AC139 | a14's refused (slot, host) set is a superset of a8c's, and the only additions are the preset fill list |
   | AC140 | zero listed cross-pack magazines, and the count judged `fit` |
   | AC143 | a second build under `PYTHONHASHSEED=1` gives identical bytes and `fit_digest` |
   | AC146 | the default export diff a8c → a14 is exactly `geometry_version` plus the frame-derived fields of the feature-frame records; `rules_digest` and `overrides_digest` unchanged |
   | AC147 | 3 frame-changed hosts, one of them a tool, and 0 conflicts; `archetype`, `genre` and `hold_class` unchanged on all 3 |
   | AC148 | hosts per `feature` value, and no `rail_flat`-only listing |
   | AC149 | every `laser_light`, `sight_front` and `sight_rear` entry is identical to a8c's |
   | AC142 | `attach-eval` on the 449 labels prints the agreement table, recorded as a description and not scored |

4. **Impact record** (§4.7 step 2):
   - raw listed and pending counts per slot × tier, before and after;
   - the pairs moving each way;
   - the changed records and their fields;
   - the muzzle-loss hosts;
   - the new rail seats by class;
   - the preset fill additions;
   - the cross-pack magazine count judged `fit`;
   - the Q-G9 parts;
   - the untoothed hosts whose flat seat is not on their highest qualifying run, by class (errata E2-Q1, data for Tom);
   - the live same-pack and cross-pack muzzle listing counts, and the live underbarrel and magazine pending counts. On the w8d world S8 moved muzzle listings 38 → 32 (same-pack 30 → 3, cross-pack 6 → 27), underbarrel pending 136 → 200 and magazine pending 178 → 319, explained by square fixture barrels; the live counts confirm or refute that reading;
   - measured lines (peer, at S9b): AC131 placements (expected 163, "other" 117) and AC135 ends (expected has-end 236, none 21);
   - the E1.1 calibrate row: the live `bore.circ_min` minimum and its margin against the 0.75 literal, and the full §4.2 table with its exit code (expected 0);
   - E1-Q2: every optic span over a stripped fused front-sight post, by count and span range;
   - E2.6 ring-end census: expected 16 stay `barrel_ring`, 3 go to `barrel_round`, 0 drop, reported as measured;
   - spot-check feasibility: the listed pairs per slot × draw tier. If any slot has fewer than 8 listed pairs across the two tiers, S10 says so and stops before any draw, because the draw is made once and "fits k of 32" would be wrong.

   Counts and ranges only; no pack ids in anything committed. A value off its expected one is reported, not tuned, and the peer rules on it.

   The classes and counts go into the spec as a new §10, committed by the lead on `integ/attach`. Per-asset lists stay in scratch.
5. **Captures** (look-first; the lead views every one):
   - the toothed-host sheet: `attach-preview --pairs` from `sheets.toothed`, with `--sheet`;
   - the frame captures: `sheets.frame` rendered from the a8c directory and from the a14 directory, before and after, for the 3 frame-changed hosts.
6. **AC145, consumer side.** This step is read-only in sit-capabilities.
   - The lead puts a synthetic `--attachments` export of `g1_world` in scratch: `geometry_version` 6, with `feature` and `fit_digest`, and one host with a rotated signed-permutation `item_basis`.
   - The lead runs a scratch GDScript against the sit-capabilities `main` tree: `pwsh -NoProfile -File D:/Projects/games/sit-capabilities/tools/run_godot.ps1 --headless --path D:/Projects/games/sit-capabilities --log-file <scratch abs path> -s <scratch>/g1_consumer_probe.gd`.
   - The script loads the export through sit_armory 0.3.0's snapshot loader and sit_weapons 0.4.0's `SitMountSpec.from_dicts`.
   - Expected: no ARM_E70 or E71, no snapshot error, no slot fault.
   - `git -C D:/Projects/games/sit-capabilities status --porcelain` is the same before and after.

**A finding stops the line.** The lead takes it to Tom when it touches a literal, a rule or a spec clause. Nothing is tuned.

## 4. S11: final review

- **Reviewer agent** (Sonnet), given base SHA B0 and the head of `integ/attach` after S10. Brief: the spec and this plan. It checks:
  - every AC has a test that fails on its named break, and every test bound is a literal;
  - each re-pinned existing test cites its G1 clause;
  - no pack-derived data is committed: no pack mesh, measured number or real asset id in `tests/` or `data/`, apart from the existing labels file;
  - no new dependency (AC144);
  - determinism (INV-25);
  - the conventions in CLAUDE.md.
- **Coverage list** (the reviewer confirms each, or the gap goes to a fix slice):
  - A§4.6 gate 6(c) is proven only on runs under 0.20 m with a local twin;
  - the covered branch of `ref.flat_run_m` is untested;
  - `w8m_placement` no longer exercises the magazine placement matrix: confirm a g1 test covers the well-seat placement matrix on `CARBINE`, else E2 adds one (the E2 builder checks this first; S11 confirms);
  - a break that calls `attach.place` correctly and then edits the matrix is caught only by the placed-AABB assert of the E2 placement test; that break was not run;
  - part and well cache keys: every rule input each measure reads is in its key (checked against the code);
  - AC145: the S10 consumer probe did not load the overlay block (where ARM_E71 lives), and its (part, host) pairing is the probe's own reading of armory §4.11, since armory has no overlay-free pairing function;
  - the build report has no fill-list entry and no frame-changed or frame-conflict count, though AC139 and AC147 say they are "reported" (unless S10a closes it);
  - close-ups (S10 capture candidates): a foregrip hanging low and far back under a scoped sniper; an optic on a Thompson-style barrel shroud and one along a heavy MG barrel jacket (periodic non-rail tops read as teeth, §7); bipods sitting well below the handguard on four renders; the two frame-corrected SMG hosts, to show whether a fused front post is really there (S10 finding 7, before AC139 and AC149 are re-pinned);
  - the seven top-toothed hosts beyond the survey's 45, by class, with the two shroud and jacket candidates (S10 finding 9);
  - the bottom-toothed set differences (3 live-only, 1 survey-only), traced;
  - the two 0.811 Military matrix cells (a taped-pair magazine class on two A-preset rifles): traced, `_seat` had one child; correct §3.7 verdicts. S11 close-up of both hosts to confirm the second magazine clashes with the well;
  - `attach-calibrate` gains a `seats` count beside `n`, and `spec_n` compares to `seats` (next slice that owns `calibrate.py`, with a test);
  - `preview.py` writes a sheet-cell map whose order differs from the rendered sheet (seen on S10 sheet 2). S11 cites no sheet-2 cell position until it is fixed; the fix rides in the next slice that owns `preview.py`, red-first on the saved map against the rendered order.
- **The lead looks at the captures:**
  - **The toothed-host sheet.** Every detected run should be a rail. A periodic non-rail top (§7) is removed with an existing `mounts` override, and that is reported.
  - **The frame captures.** The 3 hosts are held barrel-forward, and the muzzle device sits at the barrel end.
- **Fixes** go into a new slice: a fresh worktree, a new manifest, base = the current `integ/attach`. Then the affected S10 steps re-run.

## 5. S12: spot check (once)

- **Starts** only after S11 passes **and the peer's word**.
- **Draw.** `weapons attach-spotcheck --draw` runs once on the final a14 directory.
  - The lead commits `src/synty_inventory/data/weapon_attach_spotcheck.json` on `integ/attach`. It holds ids, booleans and fixed strings only, like the labels file.
- **Sheet.** `attach-preview --pairs <that file> --icons <the HUD icon roots of §1.1> --sheet`, written to scratch.
- **Answers.** Tom answers each pair once under fit-v1. The answers go into the file (`fits`, and `placed_wrong`, each from null only, INV-26).
- **Score.** `--score` prints `fits k of 32 (placed wrong m)`. The number goes into the impact record once.
- **Status.** The spot check is never a gate and is never re-drawn. **Draw #6's labels are not re-scored** (§4.7 step 3).

## 6. Closing state

- **`integ/attach`** holds G1 and is pushed to origin as it lands, under Tom's standing word of 2026-10-27: "Yes: push integ/attach commits (doc commits and merged build slices) to origin as they land. Nothing else: no main, no new remotes, no PRs." Merging it into `main` is Tom's call. [Superseded: "holds G1 and stays local. There is no push; merging it into `main` is Tom's call."]
- **sit-capabilities** is unchanged. Games pick up attach version 14 and geometry version 6 on their next re-export: a locked game sees ARM_E04, the normal flow (§4.6).
- **Worktrees.** The lead removes the `inventoryagent-wt-g1-*` worktrees after Tom's merge call.

## 7. Risks the plan carries

| risk | where it shows | handling |
|---|---|---|
| Flat seats appear on synthetic box hosts and move existing mount expectations | S7 suite | expected (§3.4 step 3); each re-pin cites the clause; any other mount change is a finding |
| The vote fires on an existing synthetic host | S1 suite | stop and report |
| The well pair pass is slow on the live packs (magazines × hosts with a reference) | S10 build time | measure and report; per-pair cache as `settle_cached`; no shortcut that changes a verdict |
| Fit cache and geometry cache disagree after a version or rules edit | S7, S8 | both keys carry `WEAPON_GEOMETRY_VERSION`, the attach version and the fit digests (§3.11); AC78-style miss tests in S7 |
| A count differs from §1.1 at S10 | S10 | a finding to the lead, never tuned (§0 rule 7) |

## 8. Build log

The merge commits of the landed slices on `integ/attach`:

- S1: `3a9a064`
- S2: `aa1fbe2`
- P1: S3 `51f40a4`, S4 `dc7815b`, S5 `c42aa41`, S6 `097bfcc`
- `00bd68c` (on integ, before the P1 merges): retired S2's stub-state leg of `test_weapons_g1_verdict.py`. The S2 verification missed that the test asserted `NotImplementedError`, which P1 had to break.
- Errata E1 (`4dfdfdb`): the E1.1 calibration and the E1.2 counts were measured on live packs in scratch before S10. §0 rule 4 keeps live data to S10 and S12, but the §4.2 calibration rule needs its positives measured. The readings were read-only and uncommitted, and the positives are the preset oracle, not Tom's labels. Not a rule 7 breach.
- 937ea4d lists 288 unverified optic pairs (w8d world) through the label-era compat path; interim on integ/attach only, closed by S8 under AC148.
- Errata E2 (proposed, `docs/g1-errata2`): two more live readings were taken in scratch before S10, read-only against a8c and uncommitted, as for E1. E2.3: 0 of the 10 eligible preset hosts has a located magazine and no authored seat. E2-Q2: 19 of the 158 ring ends have one radius (16 would go to (ii), 3 to (iii), none to no end; 27 under the rejected two-bins-of-six reading), 0 of the 67 face rings do, and all 11 bore positives keep their proof. Counts and classes only. Not a rule 7 breach.
- Errata E2 APPROVED by Tom on 2026-10-27, read as the peer's recommendations. The E2 slice bases on S8's merge and S9 on E2's: it retires S7 fold-in 4 (E2-Q3) and builds the two-radii ring rule (E2-Q2). The order is E1 → S8 → E2 → S9 → S10.
- E1: `0934b2f` (3300 passed / 5 skipped). E2 docs approved: `b049f80`. S8: `fbb5c52` (`732a3aa` on `0934b2f`, 3469 / 5, attach version 14, `attach_rules_digest` `a981c4c7c27972e8`, `rules_digest` and `overrides_digest` unchanged). The repo is CRLF throughout; every S8 file keeps the convention it had (new files CRLF too), so there is no line-ending churn.
- S8 closed 937ea4d's interim listing: the 288 pairs are `pending_hosts` rows with signal `rail_flat`, no optic or underbarrel pair reaches the default export through `rail_flat` alone, and the AC148 tests are red on `937ea4d`. On the w8d world `pending_hosts` is 1129 (408 at `0934b2f`) and the w8p optic cross count is 17.
- S8 design call (peer-confirmed): `compat.pair_verdict` raises `ValueError` when a host has features but `fit_rules` is None. Through a build the state is unreachable (`directory.py` measures no features without the `fit_geometry` block); it is reached only when stored feature records meet a rules file that lost its block, and that must not quietly become `not_judged`. The comment at `compat.py:234` that says otherwise is corrected in the next slice that owns `compat.py` (S9).
- S8 non-discriminating fixture edits: `test_weapons_w8l_prop.py`, `test_weapons_w8m_placement.py`, `test_weapons_w8n_muzzle.py` and `test_weapons_w8n_shipped_overrides.py` pass in full on the old source. They are fixture edits, not pure re-pins. `w8n_shipped_overrides` regains discrimination through `g1_world.rod_rifle`; `w8n_muzzle` is a fixture rebuild that keeps every hand-worked distance; `w8l_prop` lost its muzzle prop-host refusal and the E2 slice restores it on `rod_rifle`; `w8m_placement` no longer exercises the magazine placement matrix (S11 coverage list, §4; E2 adds a g1 test if none covers it on `CARBINE`).
- E2: `906be0b` (`08cbdb9` + `4f7f613` on `fbb5c52`, 3474 / 5, digests unchanged). Plan doc `13c95dc` merged before it. Beyond the brief (peer-accepted): `fit_geometry.part_tris` removed, dead once the located-magazine branch went (an internal name, not a spec interface). The `fit_digest` literals of AC143 (`9e88713e0a47d5d0`) and AC145 (`e4245a0e01a13252`) moved with the feature output under E2-Q2 / E2-Q3; the hash-seed identity asserts stay beside them. No g1 test covered the well-seat placement on `CARBINE` (a 0.05 m seat shift left 188 g1 tests green); E2 added `test_the_well_pass_places_the_magazine_part_at_the_hosts_reference_seat`, red on four named breaks.
- Fit cache keys (peer ruling at S9): spec §3.11 keys host features only, and that key carries `attach_rules_digest` (`mounts.py`). The part and well caches (`directory._fit_cached`) are per-input by design: each key carries the exact rule inputs its measure reads (the `bore` block for `device_inner_d`, `well.entry_depth_m` for the entry section) plus `WEAPON_ATTACH_VERSION` and the code digest. S9 tests a miss on each.
- S9: `0310747` (`ecca7b7` + `18bd510` on `906be0b`, 3587 / 5, digests unchanged). Plan doc `e8e56d2` merged before it. The three cache-miss tests are each red on their named key break, and an over-keyed break is red too; no rule input is read but unkeyed. Spot-check quotas (peer-accepted reading of §3.10): 8 per slot in proportion to the listed counts per tier, half up, at least 2 per non-empty tier, at most 6, capped by availability when a tier is short.
- S9b (peer ruling at S9): `fit_calibrate.py` is a reporting tool, not a detector, but the `fit_*.py` glob put it into `FIT_CODE_DIGESTS`, which keys the fit caches and the geometry cache fingerprint (`geometry.py`), so an edit to it would rebuild every host. S9b renames it `calibrate.py` beside `eval.py`, `preview.py` and `spotcheck.py` (the `attach-calibrate` verb stays), restores the six-detector set plus `mount_probe`, reverts S9's key-list re-pin, and pins `FIT_CODE_DIGESTS` to that literal list so a seventh `fit_*.py` is a conscious re-pin. `fit_geometry.py` is untouched. It also adds an INV-26 case that passes the schema check and trips only the write-once diff (an answer changed from one boolean to the other), asserting the INV-26 error text; S9's rewritten-host case stays as a schema case.
- S9b: `3e216e3` (`d1ed6b1` on `0310747`, 3587 / 5, digests unchanged, g1_world and cross_world directories and exports byte-identical before and after). Plan doc `8b52499` merged before it.
- S10 first run (2026-10-28, live, at `3e216e3`): the line stopped. Held: AC131 (163, every slot count, min hit 1.0), AC132 (0 on all 14 presets), AC138 (0 in every control), AC143 (identical bytes; `fit_digest` `26920f0cbd5d880e`), AC147 (3 hosts, `forward_source` body, one a tool, 0 conflicts; archetype, genre and hold_class unchanged everywhere), AC148 (0 listed optic or underbarrel on `rail_flat`), AC149's `laser_light` identity, the E2.6 ring-end census 16 / 3 / 0, and spot-check feasibility (every slot at least 8 listed pairs across the two draw tiers). AC145 PASS on the consumer probe, with the overlay caveat on S11's list. Stopped on: `attach-calibrate` exit 6, which the peer traced to a spec defect and a tool defect, not to five literals. Spec §3.6 defines `od_m` as twice the end slab's outer radius and `centre_su` as the slab centre, and `fit_bore.py` implements exactly that; but §1.1's 0.93 to 1.92 (10 of 11, E-G3 the one exception) and E1's slide-face fill of 0.39 to 0.69 could not have come from the slab extent, so the text contradicts its own calibration table. Separately, the calibrate tool's slot vocabulary counts baked sight-glass sheets as optics (28 toothed positives, not 16) and passes the mount's `bore_source`, so every bore positive takes evidence (i) and the `circ_min` row is empty by construction. Order (peer): S10a fixes the tool's positive population; a read-only scratch counterfactual on the reconciled 11 tests the `od_m` diagnosis; traces for findings 7 to 9; labels wiring before any draw; errata E3 carries proven items only, through the peer to Tom. No §4.2 row is a finding until S10a lands.
- S10 trace rulings (peer): finding 7 is a correct Q-G4 consequence (a real fused front post on both frame-changed SMGs); AC139 and AC149 are re-pinned only through E3.5. Finding 8 is one cause: the twin host has no well reference because the §3.7 plane at `u_rb` − 2 mm meets no edge of its magazine, while the survey counted it among its identical sections; E3.6 explains the difference and proposes a §3.7 correction or an exception E-G7, Tom decides, and `fit_well` does not move before then. Finding 9 is accepted as traced; E3 states the survey's 45 reproduces under neither recount, and gives the two decorative patterns that pass as teeth beside the positives' rail top widths, with an optional question to Tom on a minimum top width.
- S10a: `f5af916` (`91e818f` + `a30d672` on `3e216e3`, 3593 / 5, versions 14 and 6, no `fit_*.py` or yaml touched, test-world bytes identical). Plan doc `3037e71` merged before it. The calibrate tool now measures the spec's populations (163 placements by slot; 16 toothed seats; 11 bore seats; 15 of 16 judged twin magazines). Live it still exits 6 on clamp.ratio_min and the three bore rows; inner-ring placements are 7, not 6.
- S10a rulings (peer): the overhang row's quantity is covered (the rule's length difference, max −21 mm on positives; the survey's 8 mm was positional), no literal moves. The preset scope at 0.378 is a foot-measurement defect (a side-hook slab off the rail passed the lip rule; the real base reads 2.03), E3.7. The two authored narrow-foot assemblies (0.927 and 0.769) are real positives refused by the 1.0 bound: E3.8, Tom chooses between exceptions and a literal set by §4.2 from the corrected 16. Inner rings are reported as 7 and judged on all 7 after the `od_m` correction. The report gains a `seats` field beside `n` in the next slice that owns `calibrate.py`. The two 0.811 cells are correct §3.7 verdicts (a taped pair's second magazine would clash with the well), with the 0.104 baseline 0.1 mm from the step noted as a robustness observation.
- E3.1 counterfactual (architect, read-only scratch, definition written before computing): bore `od_m` = twice the largest radial distance of a ring-evidence face point from the face centre, centre = the face centre. The survey's definition is not reproduced: 9 of 11 seats in the survey's [0.93, 1.92], two at 0.91 to 0.92 under both definitions, top 1.65 under both. The 0.864 and 0.764 Military cells were traced the same way: both are correct §3.7 verdicts. The 0.764 cell is the taped-pair single-plane sensitivity (the 0.104 / 0.764 / 0.811 verdicts follow only the host magazine child's height above `u_rb`). The 0.864 cell is a rifle-class magazine against the A-preset SMG's authored stick well, a design note for Tom.
- E3.1 run 1 (peer's order): on three preset positives the unstripped face is the fused device's front (34 to 204 mm ahead of the barrel end). Taken on the stripped mesh, all 11 seats read 0.91 to 1.65 inside the live band [0.85, 2.00]; on the device face two of the three fall out. Axis offsets are at most 1.2 mm, and inner ratios 0.56 to 1.13 on 7 placements.
- E3.1 run 2, the live effect of the same definition on the stripped mesh (real fit path, only `od_m` and the centre substituted for ring evidence; baseline byte-identical to the S10 build). The peer's 103 lost muzzle pairs on 61 hosts reconcile exactly. Of those, 15 become fit (pistol 6, revolver 4, SMG 4, rifle 1), 88 stay no_fit (69 device narrower than 0.85, 8 wider than 2.00, 11 inner ratio above 1.21), and none goes to not_judged. Across all 537 muzzle verdicts, 68 go to fit and 17 leave fit (14 cross-pack), net +49 listed, and 51 of the entries are cross-pack pairs no earlier build listed. Every changed pair is on a host whose slab OD is at least 1.2 times its barrel-face OD. 15 pairs on 8 front-face-ring hosts (slab 1.57 to 3.21 times the face extent) are outside any ring-based definition. No wide-face criterion met the pre-written gap rule; the slab-fill distribution has an empty bin at [0.75, 0.80).
- E3.8 traces g_ (rail side) and h_ (part side), read-only, definitions written before measuring. On the two narrow-foot seats (0.9267 and 0.7692) the rails are square-cornered blocks, and the code's run width matches the section to 0.03 mm, so the rail is not over-read. Neither part has jaws at any height: the stored foot is the bottom face of solid pads, seated on the slot floors on one seat and 14 to 18 mm inside the rail block on the other. The jaw census was not triggered. Clarification of the S10a rulings line, which stands: the two assemblies remain real positives, and "narrow-foot" there means narrow pads, not narrow clamps.
- E3 drafted (decisions Q1 to Q6, each with a default) and delivered to Tom by the peer. No building until Tom rules.
- E3 APPROVED by Tom on 2026-10-28 (the ruling reached the architect through the peer): "Approve E3 at the defaults: Q1 B, Q2 M3 (withdrawn under B plus Option 2), Q3 F1, Q4 (ii) with the population-diff gate, Q5 Option 2 at 0.69, Q6 no floor now, Q7 rail slots only. E3.12 accepted as a correction." E3.3 is **withdrawn**: no exception mechanism is built, `fit_geometry.exceptions` stays empty, E-G3 is retired, and E-G7, E-G8 and E-G9 are not entered. E3.0 writes the approved text on `docs/g1-e3` (base `4c9d9e7`), in the spec, the errata, `weapon_attachments.md` and this plan. The slices of §9 start after its merge.
- E3.0 text departs from the E3 draft where later measurements disagree, and the measurement is used: the twin ladder is 31, 33, 34, 34, 37, 38 (the last INFERRED), replacing the spec's 36 of 38; the E3.7 mid-line proxy moves 5 parts on every slot and 2 on rail slots (Q7), not "up to 4"; 4 bore positives, not 3, sit outside the band under the slab (6 of 14 observations); the drum twin reads `no_fit` under F1 alone and `fit` only with E3.12; the positives' rail top widths are 10.7 to 30.0 mm; the 24 `fit` pairs on the three sub-5 mm runs (with 8 `no_fit`) go to the S11 capture list.
- The E3 build ladder is §9. Its rulings (no version bump, the `barrel_end` signature, the host-features cache key, one worktree per slice, the C1 seat rule, the E3.12 ownership, the B capture checkpoint) are in §9.6.
- E3.7 (peer ruling, merged first in Wave A): the population diff equals the 2 rail-slot parts of Q7. The toothed render sheet (49 cells) changes by one cell; that is a downstream effect of the two ruled flips, not a third change. The side-hook part's stored foot sits 13.45 mm off its own mid-line and 16.1 mm from the run centre; the stored footprint cannot know the run, so the 16.1 mm figure is the offset against the run, not off the mid-line.
- Wave A build findings, corrected in the docs as errata E3.4a and E3.5a (peer rulings): `hints.inventory_cells` and `hints.weight_class` follow `length_m` across a step (the E3.4 fixture's cells move; 0 live hosts do); a frame-changed host with no fused post may seat sights in the voted frame (the E3.5 synthetic host; 0 live hosts). Each guard pins its live count at 0 as its own literal.
- E3.1 capture checkpoint (peer ruling): the returning cell on a shrouded SMG is a data item, not a defect. The stripped barrel face lies 26.2 mm ahead of the shroud front, on a narrow stub, and the strip under the shroud is the host's own mesh (it stays in a control render with the part moved away). The three rifle cans that leave on inner ratio alone read 1.236 (two pairs) and 1.363 against the band's 1.21; they stay `no_fit` and go on the S11 capture list.
- E3.6 fixture-wording deviation (peer ruling, accepted): §9.4 asked for the drum reference above the stick's top, which cannot hold while the stick twin judges through its own reference. The fixture puts the plane on the receiver bottom (`u_rb` 0.0, not the stick bottom −0.155) at −0.002, inside the drum's range (−0.10 to 0.02) by over 5 mm at both ends, and the reference-node-only code fails it. The drum twin's test asserts judged, not `fit`; `fit` arrives with E3.12.
- Finding (E3.12, test harness) [Superseded: "pre-existing test fragility"]: `test_weapons_w8f_forward.py::test_apply_compat_twice_gives_identical_records` calls `apply_compat` a second time without `part_fit`, and its world has a drum magazine part although its comment said none. [Superseded, see the correction below: "On the base it already failed when run alone and passed in the full suite only because `fit_geometry` was imported earlier. E3.12 made it fail in both orders (the drum pair now always carries `well_entry`)."] Fixed in the E3.12 slice by passing `part_fit` to both calls and correcting the comment (peer ruling: a harness defect, not a product one).
- Correction to the E3.12 finding (E3.12b, peer ruling): the builder's "fails alone on base" did not reproduce under DM-A's archive check. Unedited, the test is green on the base (`b52e584`), alone and in its file; the defect was the missing `part_fit`, so the test compared the build path (with it) against a re-run without it. The edited test passes `part_fit` to all three `apply_compat` calls; it is red on the base and green under E3.12, so it is a regression test for E3.12. The ruling's condition "red alone on base" is replaced by "red on base with the edit, green on E3.12".
- Process: a builder's red-first claim is reproduced by DM-A before a ruling rests on it. That check caught the E3.12 claim above.
- C1 merged (`1034804`): `clamp.ratio_min` seats 19 (builder's split 16 optic / 3 underbarrel, re-derived at S10b from the rows' seat keys by slot); bore rows 11. The calibrate row carries the total only.
- C1 seat definition, settled after the ledger miss was seen (peer ruling, recorded in full): the first version keyed a preset's seat on its located part id and gave `clamp.ratio_min` 21 seats (18 optic, 3 underbarrel) against the ledger's 19. Cause: on two preset host variants, two scope variants are located at the identical spot, so one place counted twice. The change keys preset seats on the placed seat point, clustered at 1 mm, which gives 19 (16 optic, 3 underbarrel) with the bore rows at 11. It is not a tuning: `seats` bounds nothing, `n` still counts observations, and no row literal moves. §9.6 ruling 5 is amended to match.
- Process: the merge message of `fe4d401` (the docs line after E3.1) was amended once before any push. That breaks the new-commits-only rule; it was not repeated, and every correction from here on is a new commit.
- Fixture names (peer ruling): a new synthetic name that equals a real catalog id is renamed before merge; pattern-following names stay. Each Wave A merge reports names checked, collisions and renames.
- E3.12b merged (`1b85019`), 3710 passed / 7 skipped, rc 0. On the live library `fit_digest` moved from `4b1d244491948493` to `9eed3cc0bf14e986`, the only header key to move. One verdict changed in 6722 pairs: the drum twin's magazine slot, `no_fit` to `fit`. Twins measured 38; AC143 and AC145 unmoved. Docs merged as `c5f0b95`.
- S10b (on `c5f0b95`, fresh copy-catalog config, build rc 0, calibrate rc 0, `failed` empty): every §9.5 row equals its expectation. The 19 clamp seats split 16 optic / 3 underbarrel, derived from the seat keys by slot by a script that asserts its counts equal the rows' `seats`. The E3.4 and E3.5 live-count guards ran with the config and passed (not skipped), rc 0, each pinning 0. Five §4.2 observed cells disagreed with the live rows; the peer ruled them observed-column corrections (errata E3.15) and the `SPEC_N` and docstring fix a code slice (errata E3.16). S10b's are the proof-of-record values.
- E3.12 fixture names: the new test's five synthetic id patterns (the Ord, OrdOdd and OrdLong variants of the existing family) were checked against the S10b copy catalog (133 top-level JSON files) by substring, which is stricter than id equality: 0 collisions, 0 renames. No suite test compares synthetic ids against the real catalogs; AC7 checks uniqueness inside the synthetic world only.
- Cause traces for E3.15 (read-only, from the saved calibrate outputs): the depth row's shallow end (0 to −7.0 mm) and `bore.inner_ratio`'s count (5 to 7) both moved at S10a (`f5af916`, the oracle's population rewrite), not in E3. Within E3, the only move on either row is `bore.inner_ratio`'s low end, 0.2699 to 0.5581 at E3.1.
- Renumbering: the peer's "E3.13" (docs) and "E3.14" (code) are errata E3.15 and E3.16, because E3.13 and E3.14 are merged headings. The note to Tom used the first names.

## 9. Errata E3: the build ladder (E3.0 to S10b)

**Source:** the errata's E3 section ([weapon_attach_geometry_errata.md](weapon_attach_geometry_errata.md)), APPROVED by Tom on 2026-10-28, with E3.3 withdrawn. This section places its slices. It adds to §0 to §8 and changes none of them: where §0 says "S10" or "the next slice that owns `calibrate.py`", read it with this section.

**Counts and digests below were measured on read-only scratch copies of the source (integ `4c9d9e7`, source-identical to `e8495a1`), cumulative in the order E3.1, E3.6, E3.7, E3.8.** They are emulations, not the slices. The E3.1 emulation ran the stripped probe inside `barrel_end`, which the real slice must not (AC144). The E3.7 emulation used the mid-line proxy on every slot. Every live digest is therefore a prediction that holds if a slice stores no new key in its feature records. A mismatch means: diff the host records before assuming a bug. The four slices act on disjoint pair sets (muzzle; magazine; optic and underbarrel; optic and underbarrel above 0.69), so the order of landing should not change a slice's delta. That is an inference from the disjoint sets, not a measurement of other orders.

### 9.1 Rules for every E3 slice

1. **Protocol as §0.** Branch `build/g1-<slice>` and worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-<slice>`, created by the lead from a lead-resolved base SHA, never the literal `main`. One worktree per slice. The lead writes `.agent-scope.json` (`owned` = the list in §9.4, `new_under` = `[]`). Manifests are write-once; blocked means stop and report; the builder never rebases, pulls or merges. Slice names: `e3-1`, `e3-4`, `e3-5`, `e3-6`, `e3-7`, `e3-8`, `e3-12`, `c1-seats`, `c3-preview`.
2. **Explicit file lists, no `tests/test_weapons_*.py` glob.** An unexpected red outside the list means STOP and report; the lead extends the list. Measured: across all 106 weapons test files the E3.6 and E3.7 variants add 0 reds and E3.8 adds exactly 5 (§9.5).
3. **New behaviour tests go in new files** (`tests/test_weapons_e3_<x>.py`, fixtures in `tests/fixtures/weapons/e3_<x>_*.py`). Edits to existing test files are limited to pins that must move. That keeps every slice's file set disjoint, so slices run in parallel.
4. **Gate (every slice), from the slice's worktree.**
   - G-1 the whole suite, `python -m pytest`, exit 0. Baseline at S10a: 3593 passed, 5 skipped. Report the new-test count.
   - G-2 scope gate: `git diff --name-only <base>` and `git status --porcelain` show only owned paths.
   - G-3 line endings: the worktree files are CRLF and the index is LF (`core.autocrlf=true`). Write in binary mode, new files CRLF, and read `git diff --stat` for whole-file churn before commit.
   - G-4 pins: the lines named in the slice's row, and no others, change. The AC143 and AC145 literals are never edited, except by E3.12 when they move (§9.4).
   - G-5 red-first: the RESULT carries the failing output of each "red" fixture on the base, and names each "guard" as green on the base.
   - G-6 test bounds are the test's own literals, never read from the rules (the shipped-block pin test excepted).
   - G-7 live check (operator): rebuild on a COPY of the catalogs with empty caches, then `python -m synty_inventory --config <cfg> weapons attach-calibrate --directory <dir> --json <out outside the repo>`. Compare with the slice's live row in §9.5. Never build in the shared catalogs. This extends §0 rule 4 (live data only at S10 and S12) to the E3 slices, on the same terms (scratch copy, GLBs read-only, nothing committed); S10b is the same kind of run.
   - G-8 findings, not tuning (§0 rule 7): a deviation from the ledger is reported, never tuned away.
   - Live-count tests (E3.4, E3.5) skip without a catalog config, so the integ suite does not exercise them. The slice's report carries the builder's run line showing each passed against the copy catalog; S10b runs them with the config.
5. **Environment:** `PYTHONDONTWRITEBYTECODE=1`; `pythonpath = ["src"]` in `pyproject.toml` makes pytest use the worktree's own `src`.

### 9.2 Order of work

- **Wave 0:** E3.0, this docs branch.
- **Wave A, parallel, pairwise file-disjoint:** E3.1, E3.7, E3.4, E3.5, C3.
- **Then E3.6** on E3.1's merge (shared: `fit_geometry.py`, `cli.py`), **then E3.12** on E3.6's merge.
- **E3.8** on E3.7's merge. It does not wait for E3.1 or E3.6.
- **C1** on the merges of E3.1 and E3.6 (shared: `calibrate.py`, `cli.py`).
- **Then S10b.** Longest chain: E3.1 (with the lead's capture review), E3.6, E3.12, S10b; C1 beside E3.12.

| slice | title | base | owned | `fit_digest` | attach version |
|---|---|---|---|---|---|
| E3.0 | spec, errata and plan text (docs branch, not a build slice) | Tom's ruling | 4 docs | n | n |
| E3.1 | barrel-face OD (B) and stripped-mesh ring evidence (W1, E3.2) | E3.0 | 7 (5 existing, 2 new) | y (live only) | n |
| E3.7 | foot rung holds the part's mid-line, rail slots (A4) | E3.0 | 3 (1 existing, 2 new) | n | n |
| E3.4 | guard tests for the amended §3.3 field list | E3.0 | 2 (new) | n | n |
| E3.5 | guard tests for the frame-changed sight clause | E3.0 | 2 (new) | n | n |
| C3 | `preview.py` sheet-cell map (carried) | E3.0 | 2 (1 existing, 1 new) | n | n |
| E3.6 | well plane with every magazine node removed (F1), docstring (carried) | E3.1 merged | 5 (3 existing, 2 new) | y (live only) | n |
| E3.12 | well section cut after `twin_forward` | E3.6 merged | `directory.py` and its test file | y (stored drum sections) | n |
| E3.8 | `clamp.ratio_min` 1.0 to 0.69 and the re-pins | E3.7 merged | 6 (5 existing, 1 new) | n | n |
| C1 | calibrate `seats` field (carried) | E3.1 and E3.6 merged | 3 (2 existing, 1 new) | n | n |
| S10b | live re-read after the last merge (operator run, no owned files) | all above | 0 | - | - |

E3.3 is not on the ladder: it is withdrawn.

### 9.3 Shared files

| file | slices that edit it | rule |
|---|---|---|
| `src/.../weapons/fit_geometry.py` | E3.1, E3.6 | sequential: E3.1 then E3.6 |
| `src/.../weapons/cli.py` | E3.1, E3.6, C1 | sequential: E3.1, E3.6, C1 |
| `src/.../weapons/calibrate.py` | E3.1, C1 | sequential: E3.1, C1 |
| `src/.../weapons/fit_bore.py`, `mounts.py` | E3.1 only | - |
| `src/.../weapons/fit_well.py` | E3.6 only | the docstring rides it |
| `src/.../weapons/attach.py` | E3.7 only | - |
| `src/.../weapons/directory.py` | E3.12 only | - |
| `src/.../data/weapon_rules.yaml` | E3.8 only | - |
| `tests/test_weapons_g1_export.py` | E3.8 (and E3.12 if AC145 moves) | E3.8 first |
| `tests/test_weapons_g1_seats.py`, `g1_rules.py`, `w8p_rules.py` | E3.8 only | - |

All other owned files are new. No `src/` file is edited by two slices that run in parallel.

### 9.4 Slices

#### E3.0 Spec, errata and plan text (docs branch)

Branch `docs/g1-e3`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3doc`, base `4c9d9e7`. Owned (4): `docs/weapon_attach_geometry.md`, `docs/weapon_attach_geometry_errata.md` (the E3 section), `docs/weapon_attachments.md` (the A4 foot clause and the AC107 wording), `docs/weapon_attach_geometry_plan.md` (this section and the §8 lines). The plan is append-only. Gate: a docs-only diff, pure CRLF, no asset or pack ids, and every number traceable to the errata. Digest effect: none.

#### E3.1 Barrel-face OD (B) and stripped-mesh ring evidence (W1)

**Owned (7).**
- `src/synty_inventory/weapons/fit_bore.py` (`barrel_end` reads face data from `mount`)
- `src/synty_inventory/weapons/fit_geometry.py` (`host_features` takes the injected probe)
- `src/synty_inventory/weapons/mounts.py` (one shared helper; the injection; the host-features cache key)
- `src/synty_inventory/weapons/cli.py` (`_gather_oracle` stops probing the unstripped muzzle)
- `src/synty_inventory/weapons/calibrate.py` (`centreline` and `_observe_muzzle` pass the face data into `barrel_end`'s `mount`)
- new `tests/test_weapons_e3_bore.py` and `tests/fixtures/weapons/e3_bore_meshes.py`

**Not owned and stay green unmodified:** the 7 existing tests that hand-set a `bore_source` (`test_weapons_g1_bore.py`: `test_a_ringed_end_is_found_with_its_od`, `test_the_mounts_ring_bore_is_the_first_evidence`, `test_a_square_end_on_a_mount_with_a_ring_bore_is_still_the_mounts_ring`, `test_the_roundness_edge`, `test_the_unreduced_mesh_reads_the_device_face_as_the_barrel`, `test_the_verdict_signals_follow_the_evidence`; `test_weapons_g1_seats.py`: `test_a_round_rod_barrel_without_a_ring_bore_is_barrel_round_and_a_square_one_is_not_asserted`). The scratch emulation turned all 7 red because it ignored a hand-set source; the real design must not (face data absent from `mount` means today's behaviour).

**Design constraints the brief states** (they keep the pins and AC144 true):
- `fit_bore` stays pure. The stripped probe is an injected callable on `host_features` (a new keyword, default None = today). Probing inside `barrel_end` fails the AC144 import test for `fit_bore`.
- One helper in `mounts.py` serves the build injection and `cli._gather_oracle`, so the two cannot drift. Its input is the stripped (f, s, u) mesh; it runs `geometry.muzzle_probe` and `mounts.bore_diameter` and returns the ring flag, the face centre (s, u) and the face OD.
- The face data is carried **inside the existing `mount` dict**; the `barrel_end` signature (pinned in `test_weapons_g1_verdict.py`) and spec §3.11 are untouched.
- The stored `barrel_end` record keeps its four keys (`od_m`, `evidence`, `centre_su`, `face_f`). A new stored key would move AC143, AC145 and the w8d-world digest.
- No (i) evidence for a host or preset with no muzzle mount (`bore_source` None).
- Cache: `_MOUNT_KEYS` already carries `bore_source`, but the helper's code is in neither `FIT_CODE_DIGESTS` nor the host-features cache key. A mounts code digest joins that key (§9.6 ruling 3).

**Fixtures:** errata E3.1 and E3.2 (red: slide face, fused device over a rod, block behind the barrel, missing ring on the stripped face, oracle and build sharing the probe, host-features cache key covering the probe code; guards: round barrel with its own ring, evidence-(ii) end, rod without device, ringed barrel plus device, non-host preset has no ring evidence).

**Capture checkpoint (the lead views both sheets before the merge).**
- Tool: `weapons attach-preview --pairs`. Software rasteriser (no `--gpu`). Once per file: `python -m synty_inventory --config <cfg> weapons attach-preview --pairs <file> --directory <E3.1 directory.json> --out <dir outside the repo and the catalogs> --sheet --size 384`. A pair the new directory no longer lists is drawn as tier `unlisted`.
- Sample: all of them, no sampling. Leaving = listed in the base directory and absent from the E3.1 directory (expected 17: 3 same-pack, 14 cross-pack). Returning = `same_pack_fit` entries in the E3.1 directory absent from base (expected 15). Sheets are 5 x 4 cells (17) and 4 x 4 (15).
- The builder regenerates the two pair files from the real E3.1 directory and reports any count other than 17 and 15. Until C3 lands read cells in `--pairs` file order, not index order.
- Render time and the visual verdict are not measured.

**Digests and versions.**
- `fit_digest` moves on the live library (26920f0cbd5d880e predicted to 87c7c8dd6acad060; 71 hosts' muzzle slot records change). It does **not** move on the synthetic worlds (measured: per world 11 `barrel_end` calls, 5 ring-evidence, face OD equal to slab OD on all 5, none with a mount ring different from the stripped ring, no host with two magazine seats). Do not add a host to `world()`: it breaks the per-feature host count (`N_HOSTS = 15`) and the AC139 refused-set test.
- `FIT_CODE_DIGESTS` (the seven names `fit_bore`, `fit_geometry`, `fit_locate`, `fit_rails`, `fit_types`, `fit_well`, `mount_probe`; `calibrate.py` is not one): `fit_bore` and `fit_geometry` change, so the host-features cache key, the geometry cache fingerprint and the `directory._fit_cached` keys move. No pin moves. The mounts code digest moves (cache only).
- `attach_rules_digest`, `rules_digest`, `overrides_digest`, AC143, AC145, the w8d-world digest, `WEAPON_ATTACH_VERSION` 14 and `WEAPON_GEOMETRY_VERSION` 6: unchanged.

**Gate.** G-1 to G-8, plus G-4: AC143, AC145 and the w8d-world literals not edited; the 7 hand-set tests not edited. Live row: §9.5.

#### E3.7 Foot rung holds the part's mid-line (A4), rail slots

**Owned (3).** `src/synty_inventory/weapons/attach.py` (`_foot_slab`; the ladder [0.004, 0.008, 0.016] and the lip rule otherwise unchanged), new `tests/test_weapons_e3_foot.py`, new `tests/fixtures/weapons/e3_foot_meshes.py`. Not owned, stay green unmodified: `test_weapons_w8l_anchor.py` (AC107 lip ladder, `foot_of`), `test_weapons_w8a_anchor.py`, `fixtures/weapons/w8l_meshes.py`.

**Rule under test.** On `optic` and `underbarrel` parts a rung counts only if its slab holds the part's mid-line along `right`; when no rung holds it, the A4 ladder applies unchanged. Other slots keep their footprint. The proxy stands in for "intersects the run", which is not known when the footprint is stored.

**Fixtures:** errata E3.7 (red: the side-hook part; guards: the 4 mm rung under the run, a true narrow lip on the mid-line, no rung holding the mid-line, and red against an unscoped build: a non-rail-slot part keeps its footprint).

**Population-diff gate (required).** An operator script outside the repo (a committed tool would hold pack-derived output) lists every library part whose stored `foot_width_m`, `foot_length_m` or anchor point changes against the base: slot, old and new foot width and length, anchor shift in mm, and the part's pair-verdict flips. Acceptance: the changed set equals the set the lead ruled on, **2 parts**:

| slot | foot width | foot length | anchor shift | pair verdicts that flip |
|---|---|---|---|---|
| optic (the side-hook part) | 6.2 to 33.3 mm | unchanged | 13.5 mm | 7 `no_fit` to `fit` |
| underbarrel | 0.0 to 48.4 mm | unchanged | 0 | 2 `no_fit` to `fit` |

Anything else: STOP. The proxy applied to every slot also moves 2 `laser_light` parts (anchor shift 5.5 to 20.7 mm, no verdict flips) and 1 `magazine` part (10.9 mm, none); under Q7 these are **not** moved, and a change on any of them is a finding. The 9.5 mm optic and the bottle-shaped optic do not change. The A4 function also measures a host's baked children; the diff is on library parts, and any host child whose foot or `point` moves is a finding (not measured). If the proxy misses a part, the fallback is (iii), a per-pair re-measure at verdict time, by a separate amendment.

**Digests and versions.**
- `fit_digest` unchanged (live and synthetic): it hashes the feature records, not stored footprints.
- The attach code digests (`geometry.py` and `directory._ATTACH_CODE`) move: the geometry cache and the well-section cache recompute. No pin.
- Stored footprints and anchors change on the 2 parts at the same attach version (§9.6 ruling 1). `attach_rules_digest`, `rules_digest`, `overrides_digest`, AC143, AC145: unchanged. No yaml or rules change.

**Dependencies.** E3.0. File-disjoint from E3.1, E3.6, E3.4, E3.5, C3: runs in parallel with them. **E3.8 bases on its merge.**

**Gate.** G-1 to G-8, plus the population diff, plus the live row of §9.5.

#### E3.4 Guard tests for the §3.3 field list

**Owned (2, both new).** `tests/test_weapons_e3_frame_fields.py`, `tests/fixtures/weapons/e3_frame_fields_world.py`. It imports `tests/fixtures/weapons/g1_frame_world.py` read-only. No `src/`.

Test-only: the code needs no change. The red is the same assertion with the old §3.3 list as its literal: the frame-changed fixture's default-export diff lists `bounds`, `support`, `support_r_m`, `size_class` and `flags` outside the old list. Guards: a pre-vote `forward_by_fallback` clears when a ring confirms the sign; a host without a frame change differs in no field; `inventory_cells` and `weight_class` do not move. Unknown: how the fixture builds the "old frame" side. The likeliest is the `frame_axis` override that forces the build axis (`test_weapons_g1_frame.py`, helper `overrides()` in `g1_frame_world.py`); unverified. **If no mechanism reproduces it, STOP and report.** Digests: none move. Dependencies: E3.0; parallel with everything. Gate: G-1 to G-3, G-5, G-6. No live check.

#### E3.5 Guard tests for the frame-changed sight clause

**Owned (2, both new).** `tests/test_weapons_e3_sight_clause.py`, `tests/fixtures/weapons/e3_sight_world.py`. Reads `g1_frame_world.py`; no `src/`.

Red: the fused post is found only in the voted frame (build frame `probe_unavailable`, feature frame both sight slots `slot_disabled`), and the AC139 additions test against the AC139 text as it stood. Guards: `laser_light` identical everywhere; a muzzle or optic refusal on a frame-changed host is not permitted by the clause. The draft did not confirm that the synthetic geometry reproduces the old-frame miss: **STOP and report if it does not.** Digests: none move. Dependencies: E3.0; parallel with everything. Gate: G-1 to G-3, G-5, G-6. No live check.

#### C3 `preview.py` sheet-cell map (carried)

**Owned (2).** `src/synty_inventory/weapons/preview.py` (`render_pairs`), new `tests/test_weapons_e3_preview_cells.py`.

Cause (verified on 4 S10 sheets): `index.json` is sorted by (part, host) and merged with earlier runs, while `sheet.png` holds this run's images in job order minus failed renders. Recommended fix: an additive per-entry `cell` index. A sheet-writing run sets `cell` on its own entries and clears it on kept entries; a run without `--sheet` leaves existing `cell` keys. Sorting the sheet into index order cannot place a pair when older entries are in the index and breaks the `--pairs` file-order reading, so it is not recommended. Red: three jobs in non-sorted order, one render failing, a stub renderer returning a per-pair colour; each entry's `cell` equals the sheet position of its picture. Guards: a run without `--sheet` keeps older `cell` keys; kept entries lose `cell` when a new sheet is written. Pins expected to hold (not run): `test_weapons_w8d_preview.py`, `test_weapons_g1_tools.py`; a red there means STOP. Digests: none. Dependencies: none; needed before S11 cites a sheet cell. Gate: G-1 to G-3, G-5, G-6.

#### E3.6 Well plane with every magazine node removed (F1), and the docstring

**Owned (5).** `src/synty_inventory/weapons/fit_geometry.py` (`well(node)`: drop the node, every `m_mag["seats"]` node and `child_node`), `src/synty_inventory/weapons/cli.py` (`well_pos`: `ref_host` drops every `by_slot["magazine"]` node), `src/synty_inventory/weapons/fit_well.py` (the docstring, line 6: "above" to "on"; carried), new `tests/test_weapons_e3_well.py`, new `tests/fixtures/weapons/e3_well_meshes.py`. `test_weapons_g1_well.py` and `g1_well_meshes.py` stay green unmodified.

**Fixtures:** errata E3.6 (red: a two-seat host gets a reference where the plane would miss the drum; the oracle's reference host drops all magazine nodes; directory and calibrate agree on the standard twin; guards: a one-seat host, a two-seat host without overlap). `test_drum_twin_is_judged` asserts only that the drum twin is no longer `not_judged`. It does **not** assert `fit`: with F1 alone the drum twin reads `no_fit` through the transposed section (E3.12).

**Digests and versions.** `fit_digest` live 87c7c8dd6acad060 to 4b1d244491948493 (one host's magazine slot record); synthetic worlds unchanged (no two-seat host). AC143, AC145, w8d-world: unchanged. `FIT_CODE_DIGESTS`: `fit_geometry` and `fit_well` change (the docstring included: any byte edit moves the key), cache keys only. All other digests and versions unchanged.

**Dependencies.** E3.0 and **E3.1 merged first**.

**Gate.** G-1 to G-8, plus the live row of §9.5.

#### E3.12 Well section cut after `twin_forward`

**Owned.** `src/synty_inventory/weapons/directory.py` and its test file only (a new `tests/test_weapons_e3_well_order.py`, fixture inline). `compat.py` is owned only if the lead says so in the manifest before the base is cut. **AC143 and AC145:** if either moves, the pin lines (`tests/test_weapons_g1_compat.py`, `tests/test_weapons_g1_export.py`) are re-pinned in this slice. The manifest is write-once, so the lead decides at cut time whether those two files are listed as owned; if they are not, a move stops the slice and is reported.

**The defect and the fix:** errata E3.12. The section is cut in `_apply_fit_parts` (`directory.py:873`) before `apply_compat` (`directory.py:874`) runs `twin_forward` (`compat.py:623`), which rewrites the anchor forward (`compat.py:604-607`) after the prior at `attach.py:179` chose the longer horizontal extent. Fix site: the order at `directory.py:873-874`, or the anchor read at `directory.py:527`. The `well|` cache key carries the pre-correction anchor (`directory.py:554`), so the fix changes cache keys too.

**Gate.** G-1 to G-8, plus:
- the 87 stored drum rows reproduce except the drum twin, which reads 0.0000;
- the 6 other x-forward magazine parts are listed before and after (counts and deviations only);
- a cache-hit run on a partial build reproduces the full build;
- AC143 and AC145 are measured, and re-pinned in the slice if they move.

**After E3.12 the numbers change as follows.** The drum twin is judged and `fit`, so the twin count is **38 (INFERRED** from the 0.0000 re-cut; confirmed at S10b). `fit_digest` moves again on the live library (the stored drum sections are part records), by a value not measured. AC143 and AC145 are measured and re-pinned in the slice if they move.

#### E3.8 `clamp.ratio_min` 0.69 and the re-pins

**Owned (6).** `src/synty_inventory/data/weapon_rules.yaml` (`clamp: {overhang_max_m: 0.010, ratio_min: 1.0}` to 0.69; `rules.py` needs no edit), `tests/test_weapons_g1_rules.py` (`BLOCK` and its shipped-block equality test), `tests/test_weapons_g1_export.py`, `tests/test_weapons_g1_seats.py`, `tests/test_weapons_w8p_rules.py`, new `tests/test_weapons_e3_clamp.py` (the AC137 case). Measured: exactly these 5 existing tests go red, and no other.

| test | pin | old | new |
|---|---|---|---|
| `g1_export::test_ac146_the_versions_and_the_digests` | `attach_rules_digest` (shipped table) | a981c4c7c27972e8 | **2fa41961e3c387b0** |
| `g1_export::test_ac146_the_directory_header_of_the_w8d_world` | w8d-world `attach_rules_digest` (the world carries its own `attach_genre_by_pack`) | d53ba2ef587b5ee9 | **6f49a2ac6efa8120** |
| `g1_seats::test_the_versions_and_digests_are_those_of_the_base` | `attach_rules_digest` | a981c4c7c27972e8 | 2fa41961e3c387b0 |
| `w8p_rules::test_ac129_the_versions_and_the_digests` | `attach_rules_digest` | a981c4c7c27972e8 | 2fa41961e3c387b0 |
| `g1_rules::test_the_shipped_block_is_spec_4_1_with_no_frame_key_and_validates` | `BLOCK["clamp"]["ratio_min"]` | 1.0 | 0.69 |

The new digests are the scratch values for a yaml edit of exactly that one number (the digest hashes parsed rules, so comments do not matter). A different value means the builder changed something else. The re-pin edits are red-first by construction: run the five pin tests on the new yaml before editing them and record the five failures.

**Fixtures:** errata E3.8 (red: the shipped rules clear a 0.80 positive, reading the row, not the exit code; guards: rules overridden to 0.85 exit 6 and name the literal; no positives exit 6).

**Digests and versions.** `attach_rules_digest` moves (above). `fit_digest` unchanged. `rules_digest` 7b9829af37328fe7 never moves for attachment_rules edits. `overrides_digest` unchanged. AC143, AC145 unchanged. Versions unchanged.

**Dependencies.** E3.0 and **E3.7 merged** (logical: without it the minimum is the 0.378 artefact and the rule would give 0.30, so the live gate fails). File-disjoint from E3.1, E3.6 and C1 under the new-file policy.

**Gate.** G-1 to G-8, plus the live row of §9.5 (`attach-calibrate` exit 0).

#### C1 Calibrate `seats` field (carried)

**Owned (3).** `src/synty_inventory/weapons/calibrate.py` (`_row`: add `seats`; observations gain a seat id), `src/synty_inventory/weapons/cli.py` (`add()`, `rail()` and `device()` supply it), new `tests/test_weapons_e3_seats.py`. `test_weapons_g1_calibrate.py` (the `spec_n` checks) stays green; `seats` is additive. **A seat is the distinct (host, slot, seat node)** (§9.6 ruling 5).

Red: a row's `seats` counts distinct seats, not observations (synthetic: a twin shares its baked sibling's seat, n 3, seats 2). Guards: a preset keeps its own seat; the pure `calibrate()` layer stays free of `cli`. Live (S10b): `clamp.ratio_min` n 26 to seats 19 (16 optic, 3 underbarrel) and the bore rows n 14 to seats 11. A different count is a finding. Digests: none move (neither file is one of the seven). Dependencies: **after E3.1 and E3.6** (shared `calibrate.py` and `cli.py`). Gate: G-1 to G-8; live: the rows are otherwise identical to the preceding state.

#### S10b Live re-read (operator run, not a slice)

An operator run on the merged result (G-7), with the final rows of §9.5, plus the §4.2 observed-column check (the rewrite is already in the spec). No owned files. It confirms the inferred twin count (38) and the E3.12 numbers, and it says which population `bore.circ_min` enforces (n 2). It also runs the E3.4 and E3.5 live-count tests with the catalog config (each pins 0) and reports them passed, not skipped. A value off its expected one is reported, not tuned.

### 9.5 Ledgers

**Digests, versions and pins** (the live `fit_digest` values are predictions; E3.12 moves the live value again, not measured).

| item | base | E3.1 | E3.6 | E3.7 | E3.8 |
|---|---|---|---|---|---|
| live `fit_digest` | 26920f0cbd5d880e | 87c7c8dd6acad060 | 4b1d244491948493 | same | same |
| AC143 `world()` `fit_digest` | 9e88713e0a47d5d0 | same | same | same | same |
| AC145 `cross_world()` | e4245a0e01a13252 | same | same | same | same |
| w8d-world `fit_digest` | d8a5f85413f90698 | same | same | same | same |
| shipped `attach_rules_digest` | a981c4c7c27972e8 | same | same | same | **2fa41961e3c387b0** |
| w8d-world `attach_rules_digest` | d53ba2ef587b5ee9 | same | same | same | **6f49a2ac6efa8120** |
| `rules_digest` | 7b9829af37328fe7 | same | same | same | same |
| `overrides_digest` (shipped) | 0a2948d6cab4c77e | same | same | same | same |
| `WEAPON_ATTACH_VERSION` / `GEOMETRY` | 14 / 6 | same | same | same | same |
| `FIT_CODE_DIGESTS` keys moved | - | `fit_bore`, `fit_geometry` | `fit_geometry`, `fit_well` | none | none |
| other code digests moved | - | mounts | none | attach (two copies) | none |

AC143 is the directory `fit_digest` of the FAKE_G1 `world()` alone (`tests/test_weapons_g1_compat.py:653`; a subprocess probe under `PYTHONHASHSEED` 0 and 1). AC145 is the `fit_digest` of `cross_world()` (`tests/test_weapons_g1_export.py:101`). `fit_digest` hashes values, not code: a code edit moves it only if a measure changes, and a rules edit only if a rule changes a measure. Measured on the four stacked variants, both pins and both directory sha256 values are identical to base. The one way to move them is a new stored key or a new host in a world (E3.1's design constraint), or E3.12.

**Live-check ledger** (`attach-calibrate` on the copy catalogs; counts). Each row is the state after that slice, stacked in the measured order.

| state | exit | failed literals | `od_ratio` viol | `inner` viol | `axis_offset` viol | `circ_min` n | `ratio_min` viol (min) | `well.tol` n | pair verdicts changed (vs previous) | twins `fit` of 38 |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 6 | `clamp.ratio_min`, `bore.od_ratio`, `bore.inner_ratio`, `bore.axis_offset_max_m` | 6 | 1 | 5 | 3 | 5 (0.378) | 15 | - | 31 |
| E3.1 | 6 | `clamp.ratio_min` | 0 | 0 | 0 | 2 | 5 (0.378) | 15 | 85 (68 up, 17 down), listed +66 / -17 | 33 |
| E3.6 | 6 | `clamp.ratio_min` | 0 | 0 | 0 | 2 | 5 (0.378) | 16 | 8 on 1 host, listed 0 | 34 |
| E3.7 | 6 | `clamp.ratio_min` | 0 | 0 | 0 | 2 | 4 (0.7692) | 16 | 9, listed +9 | 34 |
| E3.8 | **0** | none | 0 | 0 | 0 | 2 | 0 (0.7692) | 16 | 79, listed +75 | 37 |
| E3.12 | 0 | none | 0 | 0 | 0 | 2 | 0 (0.7692) | 16 | drum twin `no_fit` to `fit`; stored drum sections; not measured | **38 (INFERRED)** |

Constant across all states: `unmeasured` underbarrel `no_toothed_run` 5 baked, 1 preset, 1 twin; `skipped` `located_magazine_without_reference` 5; placements 163 (spec 163); hosts 257. `unmeasured` `magazine:twin:no_well_reference` is 1 until E3.6, then absent. Details per slice:
- **E3.1** (live): `attach-calibrate` exit 6, `failed` = `clamp.ratio_min` only. Flipped from base: `bore.od_ratio` (6 violations to 0; observed [0.3503, 1.6526] to [0.9097, 1.6526]), `bore.inner_ratio` (1 to 0; [0.2699, 1.1315] to [0.5581, 1.1315]), `bore.axis_offset_max_m` (5 to 0; max 0.0136 to 0.0012). `bore.circ_min` n 3 to 2, observed 0.8236, margin 0.0736, still `ok`. Pairs: 85 muzzle verdicts change, no other slot moves; listed 66 enter (15 same-pack, 51 cross-pack) and 17 leave (3 same-pack, 14 cross-pack); pending unchanged (4704). Report both lists' counts; a different count is a finding.
- **E3.6** (live, against E3.1): `well.tol` n 15 to 16, observed max 0.1044, margin 0.0456; `unmeasured` `magazine:twin:no_well_reference` 1 to 0. One host's feature record changes; 8 magazine pair verdicts change on it: 7 `not_judged` to `no_fit` (6 non-twin parts and the drum twin) and 1 `unverified` to `fit` (the standard twin). Listed pairs change by 0; the pending list shrinks 4704 to 4698. Twins: `fit` 33 to 34, `no_fit` 3 to 4, `not_judged` and `unverified` 1 and 1 to 0.
- **E3.7** (live, against E3.6): exit 6; `failed` = `clamp.ratio_min`, violations 5 to 4, observed min 0.378 to 0.7692, margin -0.2308. 9 `no_fit` to `fit` (7 optic, 2 underbarrel), 2 parts, 9 hosts, all cross-pack; 9 listed pairs enter, none leave. No twin moves. `fit_digest` identical to the E3.6 state. These were measured with the proxy on every slot; the 3 non-rail parts flip no verdict and store nothing in `fit_digest`, so rail slots only is expected to give the same row. The slice confirms.
- **E3.8** (live, against E3.7): `attach-calibrate` exit 0, `failed` empty. `clamp.ratio_min` n 26 (spec_n 16), violations 4 to 0, observed 0.7692, margin 0.0792, literal 0.69. 79 `no_fit` to `fit` (63 optic, 16 underbarrel; 38 hosts, 20 parts; 31 same-pack and 48 cross-pack); 75 listed enter (30 same-pack, 45 cross-pack), 4 flip without being listed; none leave. Twins `fit` 34 to 37. `fit_digest` unchanged.

**S10b expectation (final rows):** `clamp.overhang_max_m` n 26 / spec 16 obs -0.0212 margin 0.0312; `clamp.ratio_min` n 26 / 16 obs 0.7692 margin 0.0792 literal 0.69; `rail.zone` n 67 obs [0.1992, 0.7823]; `depth` n 23 / 16 review row; `bore.od_ratio` n 14 / 11 obs [0.9097, 1.6526] margins [0.0597, 0.3474]; `bore.inner_ratio` n 7 / 6 obs [0.5581, 1.1315] margins [0.0881, 0.0785]; `bore.axis_offset_max_m` n 14 / 11 obs 0.0012 margin 0.0038; `bore.axis_tilt_max_deg` n 14 / 11 obs 0.0; `bore.circ_min` n 2 / 4 obs 0.8236 margin 0.0736; `well.tol` n 16 / 15 obs 0.1044 margin 0.0456; frame constant n 3 obs 0.0178 margin 0.0072.

**Reds the variants produced in existing weapons tests:** E3.1: 7 hand-set-source tests plus the AC144 import test in the emulation (artefacts of probing inside `barrel_end`; the real slice keeps all 8 green). E3.6: 0. E3.7: 0. E3.8: 5 (the pin edits above).

### 9.6 Rulings on the E3 ladder

1. **No version bump.** `WEAPON_ATTACH_VERSION` 14 and `WEAPON_GEOMETRY_VERSION` 6 stay: a14 is local-only until S11 and S12, and E3.7 stores new footprints and anchors on 2 parts at the same version. If a bump to 15 is ordered, 19 test files pin 14 plus the package constant: its own sweep slice, after the last functional merge.
2. **`barrel_end` keeps its signature.** Face data is carried inside the mount dict. The alternative (new arguments) would re-pin `test_weapons_g1_verdict.py` and amend §3.11.
3. **The `mounts.py` host-features cache key gets a pinned code digest.** The helper's code is in neither `FIT_CODE_DIGESTS` nor the host-features key today. A mounts code digest joins the key, and a test pins that it does (mirror of the key test in `test_weapons_g1_seats.py`).
4. **One worktree per slice.**
5. **C1 seats = distinct (host, slot, place)** (amended at C1, peer ruling): the place is the seat node for baked and twin seats, and the placed seat point clustered at 1 mm for presets (two preset points within 1 mm on the same host and slot are one seat). A twin shares its baked sibling's seat. A preset never merges with a baked child or another host.
6. **E3.12 owns `directory.py` and its test file only.** Its gate items: the 87 stored drum rows reproduce except the drum twin at 0.0000; the 6 x-forward magazine parts listed before and after; a partial-build cache hit equals the full build; AC143 and AC145 measured and re-pinned in-slice if they move.
7. **The B capture checkpoint.** All 17 leaving and 15 returning pairs are viewed by the lead before the E3.1 merge.
8. **E3.7 scope (Tom, Q7).** Rail slots only. The population diff must equal the 2 parts of E3.7.

Conventions the ladder assumed, **not rulings** (the architect's recommendations; the lead may overrule): explicit file lists with no test glob (§9.1 rule 2); new behaviour tests in new files (rule 3); S10b is an operator run and not a slice; the population-diff script stays outside the repo; E3.4 and E3.5 stop if the old-frame fixture cannot be reproduced.

### 9.7 Carried items and what is not determined

Carried, so nothing is lost:
- **The labels wiring** stays before S12 (§4 and §5). The labels source is wired into `eval.py`, `spotcheck.py` and `cli.py`, and the labels store's count is reconciled against the 449 the spec cites, before any `--draw`. It is not an E3 slice.
- **The `preview.py` cell map** is slice C3.
- **The `fit_well.py:6` docstring** rides E3.6.
- **The calibrate `seats` field** is slice C1.
- **The 24 `fit` pairs on the three sub-5 mm toothed runs** go on the S11 capture list (errata E3.9 (d), Q6: no floor now). A floor becomes a later erratum only if the captures show them wrong.
- **Three rifle cans refused on inner ratio** (E3.1) go on the S11 capture list with their mate, OD and inner values stated. They leave as specified.
- **Preset `point_s` from the unstripped probe** (E3.1 builder item 1): presets still take `point_s` from the unstripped probe. No change in E3.1.
- **Oracle and fused-set alignment** (E3.1 builder item 2): the test keeps its literal of 1 unmatched oracle call as a tripwire, with a comment naming the two sets and when it goes red. Aligning the two sets is later work.
- **`_used_vertices` made public** (E3.1 builder item 3): E3.1 imports a private helper; the next slice that owns its module makes it public.

Not determined from the tree:
- the real E3.1 output (the live digests are emulation predictions; the keys the slice stores decide whether AC143 and AC145 move);
- the directory effect of E3.12 on AC143 and AC145, and the partial-build and cache-hit behaviour;
- whether the mid-line proxy is complete for host children (the A4 function measures them too);
- renders of the 17 leaving and 15 returning pairs (the E3.1 capture checkpoint), and render time;
- the old-frame mechanism for the E3.4 and E3.5 fixtures;
- non-weapons tests under each variant (only the 106 weapons files were run; the full suite is each slice's gate);
- whether the preview tests survive an additive `cell` key (expected, not run).
