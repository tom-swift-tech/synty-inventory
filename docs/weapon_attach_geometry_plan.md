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
  - the two 0.811 Military matrix cells (one B-pack magazine class on two A-preset rifles): which child `mounts._seat` took as the reference by AABB volume and why, with a close-up of both hosts, by class. A wrong child is a bug for a fix slice, not a tolerance;
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
