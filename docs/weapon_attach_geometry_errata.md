# Errata: geometry fit gate G1

**Spec:** [weapon_attach_geometry.md](weapon_attach_geometry.md) (a bare `§N` points into it). **Plan:** [weapon_attach_geometry_plan.md](weapon_attach_geometry_plan.md).

> The public-repo rule of the spec applies here in full: algorithms, literals, classes, counts and ranges only. Every live number below was measured in a scratch folder, read-only against the a8c directory and the converted GLBs, and is not committed anywhere. Fixtures are synthetic.

## E1. Round barrel end, one landing test, strip scope

**Status: PROPOSED** (2026-10-27, architect). This goes to Tom. Until he approves it, the build follows the spec as approved.

**Found by:** the P1 detector slices (S3 locator and strip, S5 bore). Confirmed against the merged code at `097bfcc` (S1 to S6 merged). E1.3 was found while measuring E1.2.

| Point | Gap | Change | Sections | ACs |
|---|---|---|---|---|
| E1.1 | A square end reads as a round barrel end | (iii) adds a circularity test, `bore.circ_min` 0.75 | §3.6, §4.1, §4.2 | AC135 |
| E1.2 | The locator and strip use different landing tests | one landing test on the stored `t`, at the locator grid; `strip` takes `rules` | §3.2, §3.11, §5 (INV-29) | AC131, AC132 |
| E1.3 | "Minus located parts" read literally empties a preset | strip removes only the placements that fill a slot | §1.1, §3.2, §3.4, §3.6, §3.7 | AC132, AC135 |

### E1.1 Round end section (§3.6 (iii))

**Today.**
- `fit_bore.barrel_end` (iii) tests only `min(extent_s, extent_u) / max(...) ≥ round_min` (0.8) and the OD cap.
- Every square has an extent ratio of 1.0. A 40 × 40 mm end therefore reads as a round end: `round_section`, OD 56.6 mm (the diagonal).
- The plan's S5 AC said "a square end gives none". The S5 fixture used a 50 × 30 mm rectangle, which the extent ratio rejects. A true square was never tested.

**The measure: hull area over the circumscribed circle.**
- `c = A_hull / (π (od_m / 2)²)`.
  - `A_hull` is the area of the convex hull of the slab's (s, u) points.
  - `od_m` is the end's existing OD: twice the largest radius from the slab's bounding-box centre.
  - So `c` is the share of the disc of diameter `od_m` that the section fills.
- Reference values:

  | Section | c |
  |---|---|
  | Regular n-gon centred in its box | (n / 2π) sin(2π / n) |
  | Any square | 0.637 |
  | Any rectangle | at most 2/π = 0.637 |
  | Hexagon | 0.827 |
  | Octagon | 0.900 |
  | 32-gon | 0.994 |
  | Ellipse | about its axis ratio |

- Rejected: the CV of the slab vertices' radial distances.
  - It reads every regular polygon as perfectly round. A square's four corners share one radius, so its CV is 0.
  - It is also polluted by the inner bore. On the round positives the CV is 0.19 to 0.32, because a tube's slab holds its inner ring too.
  - So it ranks a square as rounder than every positive.
- Also rejected: the CV of the hull's radius sampled around the perimeter.
  - It does separate a square (0.105) from a hexagon (0.044).
  - It needs a sampling count and the hull anyway. The area ratio needs neither, so it is parameter-free and does not depend on vertex density.
- Implementation:
  - Andrew's monotone chain over lexicographically sorted points, with collinear points dropped. Shoelace area.
  - numpy and the standard library only (AC144). Deterministic (§4.3).

**Calibration (the §4.2 rule: a lower bound sits at the min over its positives minus a stated margin).**
- The 11 bore positives of §1.1 split in two (measured in scratch with the merged S5 code):
  - **7 barrel sections**, hull ratio 0.824 to 0.900:
    - 4 are proved by a face ring on the end slab (evidence (ii)): 0.824 to 0.900;
    - 3 are proved by the mount's ring bore (evidence (i)): 0.862 to 0.899.
    - The minimum, 0.824, is a six-sided section.
  - **4 pistol slide faces** that carry a ring bore: extent ratio 0.43 to 0.86, hull ratio 0.39 to 0.69.
    - Evidence (i) proves them, so (iii) never reads them.
    - They are not round sections, so they do not calibrate a roundness test.
- The enforced positives are the evidence-(ii) positives: the slab holds the barrel's own bore ring, so the section is a barrel's. `attach-calibrate` can select them mechanically.
- The nearest negative is any square, at 0.637. The literal sits 0.113 above it.

| literal | positives (n) | min observed | margin | literal | exceptions (reasoned) |
|---|---|---|---|---|---|
| `bore.circ_min` (lower bound, E1) | bore positives proved by a face ring, evidence (ii) (4); all 7 barrel-section positives agree | 0.824 (six-sided) | 0.074 | 0.75 | none. The 4 slide-face positives (0.39 to 0.69) are proved by (i) and never read by (iii). |

**Live effect (a8c build frame, before strip, merged S5 detector).**
- Today:
  - 234 hosts have an end: ring 158, face ring 67, round section 9. 23 have none. The survey's own script read 233 and 24.
  - The 9 round sections:
    - 8 octagonal ends at 0.89 to 0.90: 7 launchers and 1 utility host. All 8 stay.
    - 1 four-sided nozzle on a utility host: OD about 5 mm, 0.635. It drops to none.
- With E1.1: 233 and 24.
- The dropped host has no muzzle seat in a8c, so no listing changes.

**Amended text.**
- **§3.6 (iii):**
  > (iii) a round end section: `min(extent_s, extent_u) / max(...)` ≥ `round_min` (0.8), **and** the section fills its circle, `A_hull / (π (od_m / 2)²)` ≥ `circ_min` (0.75), **and** OD ≤ `barrel_od_max_m` (0.060). `A_hull` is the area of the convex hull of the slab's (s, u) points. A regular hexagon or finer polygon passes. A square or any rectangle never does (≤ 2/π).
- **§4.1 `bore`:** add `circ_min: 0.75` after `round_min: 0.8`, with the comment `# E1: hull area / circle of od_m, section 3.6 (iii)`. It is required, of kind `frac`, like `round_min`.
- **§4.2:** add the row above to the table, so `attach-calibrate` prints and enforces it (AC137, INV-24). The detector-parameter paragraph's "round section" now means `round_min` alone.
- **§3.11:** no signature change. The hull helper stays private to `fit_bore.py`.

**Fixtures** (in `g1_bore_meshes.py` and `test_weapons_g1_bore.py`, with a mount that has no ring bore).

| Fixture | Expected | Today |
|---|---|---|
| `box(0.0, 0.50, 0.020, 0.020)`, a 40 × 40 mm square end, beside the existing 50 × 30 mm rectangle | None | `round_section`, OD 0.0566. **Fails on today's code.** |
| Regular six- and eight-sided tubes, r 15 mm | `round_section`, OD 0.030 | passes today; guards against an over-tight literal |

- **Break:** `circ_min` 0.60, or (iii) without the hull test, accepts the square.
- **Break:** `circ_min` 0.85 loses the hexagon.

### E1.2 One landing test for the locator and strip (§3.2, §3.11)

**Today.** The locator and strip ask "does this part vertex land on the host?" in two different ways.
- **The locator** tests `cell(p) + shift`, where `shift = cell(h_first) − cell(p0)`, against the host cells with 27 neighbours. It then reports `t = h_first − p0`, rounded to 0.1 mm. The test is on whole-cell shifts, not on `t`.
- **Strip** keys `p + t` on its own 0.1 mm grid (`_STRIP_CELL_M`), with 27 neighbours: about ±0.1 to 0.2 mm.
- The locator therefore accepts copies, at hit 1.0, that strip cannot remove. It also loses copies whose vertices are well inside the 0.5 mm tolerance: `floor(a + b − c)` and `floor(a) + floor(b) − floor(c)` differ by up to one cell.
- Putting strip on the 0.5 mm grid is not enough. The shift-based test and the `t`-based test still disagree at the tolerance edge, whatever grid strip uses.

**Evidence.**
- Synthetic.
  - A fused copy whose vertices sit 0.1 mm off the part is located at hit 1.0. After strip, 24 triangles remain, against the base mesh's 12. The same happens at 0.15 and 0.2 mm.
  - A copy at a translation that is not a whole number of cells, with one vertex 0.1 mm off, is not located at all.
- Live, on the 14 Military presets. Today's merged locator returns **159** placements; the survey said 164.
  - Underbarrel is 3, not 4: the fourth preset underbarrel placement, which AC134 counts, is lost.
  - It misses 5 clean copies whose vertices sit at most about 0.1 mm off.
  - It places 1 copy at a translation 0.4 mm off.
  - It keeps 1 slot-less handguard alias.
  - Today's strip, applied to today's placements, leaves 1,493 triangles on 13 placements that the shared test removes. AC131 and AC132 would fail at S10.
- With the shared test: **163** placements. Optic 14, magazine 15, muzzle 4, underbarrel 4, laser_light 3, sight_front 6, other 117.
  - Every slot count equals the survey's.
  - Other is 117, not 118. The survey placement not reproduced is that slot-less alias: its vertices sit up to about 0.9 mm off. The survey keyed vertices to the nearest cell, about ±0.75 mm effective. That is beyond the guaranteed 0.5 mm below.
  - The worst vertex deviation of a placement, over the 163: p50 0.06 mm, p90 0.11 mm, max 0.70 mm (one copy).
- The merged S3 and S5 tests pass against the scratch prototypes of E1.1 and E1.2: 69 with the E1 cases. Only the `strip` call and the rules block were adapted. No P1 test's expectation changes; only the tests' literal rules copies gain the new key (E1.5).

**The landing test (amended §3.2).** Replace the locator bullets and the strip bullet of §3.2 with:

> - **Landing test** (one test, shared by the locator and strip). A part vertex `p` lands at translation `t` when a host vertex lies in the `grid_m` (0.5 mm) cell of `p + t` or in one of its 26 neighbours. `t` is the placement's stored translation. A vertex lands whenever some host vertex is within `grid_m` of `p + t` on every axis. It never lands when every host vertex is `2 × grid_m` or farther on some axis. Between the two, the outcome depends on the grid.
> - **Candidates.** One per occupied host cell: `t = h − p0`, rounded to 0.1 mm. `p0` is the part's lexicographically smallest vertex, and `h` is the lexicographically first host vertex in that cell.
> - **Prefilter.** Run the landing test on 24 sampled part vertices.
> - **Accept** at hit fraction **== 1.0**: every part vertex lands at `t`. Merge placements within 2 mm. Ties go to the fewest misses, then to the most vertices landing in their own cell, then to the smallest `t`.
> - **Strip.** Before any host detector runs, the placements that fill a slot (E1.3) are removed from the host mesh. A host vertex is on a placement when it and some `p + t` share a cell or neighbouring cells: the landing relation, read from the host side. A host triangle is removed when all three of its vertices are on stripped placements.

- **§3.11:**
  ```python
  def strip(host_verts, host_tris, placements: list[Placement], part_meshes: dict, rules: dict) -> tuple: ...
  ```
  It reads `rules["locator"]["grid_m"]`, so the locator and strip cannot drift apart. `_STRIP_CELL_M` is retired.
- **§5, new invariant:**
  > **INV-29 (E1).** The locator and strip share one landing relation (§3.2). For a placement returned at hit 1.0, strip leaves no host triangle whose three vertices are the placement's copy.

**Amended ACs.**

| AC | Amended text | Break |
|---|---|---|
| AC131 | `locate_by_translation` on the 14 Military presets returns **163** placements at hit 1.0. By slot: optic 14, magazine 15, muzzle 4, underbarrel 4, laser_light 3, sight_front 6, other **117**. No placement below 1.0 is returned. Synthetic fixtures: a host built from 3 translated parts returns exactly those 3 translations. **A copy at a translation that is not a whole number of cells, with one vertex 0.1 mm off, is located at hit 1.0.** | `hit_min` lowered to 0.9, so the barrel aliases appear; the 27-neighbour tolerance dropped, so placements are lost; **the landing test run on whole-cell shifts instead of on `t`, so the 0.1 mm copy is lost** |
| AC132 | On the synthetic fixture, the host mesh after `strip` equals the base mesh, triangle for triangle. **It does so as well for a fused copy whose vertices sit 0.1 mm off the part, which the locator places at hit 1.0.** On every preset, strip runs on the placements that fill a slot (E1.3), and no remaining host triangle has all three vertices on one of them. | strip skipped: a fused scope's top reads as the rail; **strip on its own finer grid, so the 0.1 mm copy keeps its triangles; strip on every placement, so a preset's rail and barrel go** |

AC131's live count moves from 164 to 163 (other 118 → 117). This is a spec number, so it is Tom's call (E1-Q1).

**Fixtures** (in `g1_locate_meshes.py` and `test_weapons_g1_locate.py`).
- **Jittered fused copy.**
  - Build: `asymmetric_part()` at `T_A = (0.100, 0.060, 0.020)`, fused into the 12-triangle base box with `host_from`. Move the copy's smallest vertex +0.1 mm on each axis, and every other vertex −0.1 mm.
  - Expected: one placement at hit 1.0, and `strip` returns the base mesh triangle for triangle.
  - Today: located, but 24 triangles remain. **Fails on today's code.**
- **Off-grid copy.**
  - Build: a 4-vertex part whose smallest vertex is not on a cell corner, translated by a non-whole number of cells on one axis. Move one vertex that is not the smallest 0.1 mm along that axis.
  - Expected: one placement at hit 1.0.
  - Today: no placement. **Fails on today's code.**
- The existing "one vertex moved 1 mm is not located" case stays: 1 mm is `2 × grid_m`, so it never lands.
- The existing `..._moved_0_4_mm_...` test moves the vertex 0.2 mm. Make it move 0.4 mm, which lands under the guarantee.

**Alternative considered: a crisp distance test** (Chebyshev distance ≤ `grid_m`, with the cells used only as the search).
- It makes the 0.5 to 1.0 mm band unambiguous.
- It also rejects the 0.70 mm copy, which takes other to 116, and it departs further from the approved 27-neighbour wording.
- Recommendation: the shared 27-neighbour test above.

### E1.3 Strip scope (§1.1, §3.2, §3.4, §3.6, §3.7)

**Today's text.** §3.2 removes "the located triangles", and §3.4 and §3.6 measure the host "minus located parts".
- Read literally, strip removes every located placement. On a preset, that is the whole weapon.
- Of the 163 placements, only 46 fill a slot. The other 117 are the preset's own receiver, barrel, handguard, rail, stock and grip parts, plus 7 small parts with no attachment block (Q-G9).
- Live, stripping every placement:
  - leaves 2,180 of the presets' 67,194 triangles;
  - empties 10 of the 14 presets, including 9 of the 10 host presets.
- That removes the rail AC134 measures, the barrel AC135 measures, and the receiver whose bottom plane §3.7 reads.
- The synthetic world would not show it, because its preset fuses only a scope and a silencer.
- The S7 work in progress strips every placement today (E1.6).

**Amendment.**
- Strip removes **the placements that fill a slot**: the placements whose part has an `attachment.slot`. This is exactly the set the preset fill rule reads (Q-G11).
- Placements of parts without one stay in the mesh. They are located and counted (AC131), but not stripped. These are the host's structure, and the unclassified parts of Q-G9.
- Live: 46 of 163 placements are stripped, and 50,214 of 67,194 triangles remain.
- Apply it as follows:
  - §3.2 reads as amended in E1.2.
  - §3.4 and §3.6 read "minus the placements that fill a slot (§3.2)" for "minus located parts".
  - §3.7's host-minus-magazine triangles are the host after strip, minus the reference magazine. The receiver is not stripped, so the vertical line through the reference still finds a `u_rb` crossing.
  - §1.1's "remove a located part's triangles" reads "remove the triangles of a located part that fills a slot".

**The brake preset (§1.1, AC135).**
- Its fused brake has no attachment block (Q-G9). It is neither a fill nor stripped, so the preset keeps no barrel end and its muzzle is `no_fit` by geometry.
- §1.1 expected the opposite: strip the brake, then refuse the muzzle by the fill rule. That could not have worked. The fill rule reads slots, and the brake fills none, so the exposed barrel would have listed devices on a preset.
- Live check, barrel end of that preset:
  - no strip: none;
  - slot parts stripped: none;
  - slot parts and slot-less devices stripped: a 31 mm face ring.
- The fourth mover of §1.1 is withdrawn. AC135 is amended:
  > The 3 expected movers of §1.1 (the two Uzi-type SMG hosts and one nail gun) go from none to an end. E1.1's utility host with a four-sided nozzle goes from an end to none. Together they take the spec definition to about 235 and 22. The brake preset stays without an end (E1.3). Any other mover is listed with its class.

  The fixture part of AC135 gains the square end of E1.1.

**Fused front sights (E1-Q2, non-blocking).**
- Fused front sight posts fill `sight_front`, so they are stripped.
- §3.4 step 4 clips a rail run at the probe `sight_front` seat, and reads the seat, not the mesh.
- In a8c, 4 host presets carry a fused front sight post, and none of them has a `sight_front` seat. On them the clip does not fire, so an optic span could cover the stripped post.
- Default: strip them (one rule: the fill set). S10 reports every optic seat on a host preset whose span covers a stripped sight placement.
- Alternative: keep sight placements in the mesh, or let the clip also read located sight placements.

### E1.4 Versions, digests and consumers

- **No version bump of its own.**
  - `WEAPON_ATTACH_VERSION` 14 lands in S8, and `WEAPON_GEOMETRY_VERSION` 6 landed in S1. Neither is exported to a game before S11 (plan §0 rule 5).
- **`attach_rules_digest` moves** (the new `bore.circ_min` key). `rules_digest` and `overrides_digest` do not: `fit_geometry` is excluded from `rules_digest`.
- **Caches miss on their own.** The fit cache key and the `mv` fingerprint carry the `fit_geometry` block and the `fit_*.py` code digests (§3.11), so no manual bump is needed.
- **The default export is unchanged** (INV-19 as amended). The `feature` vocabulary is unchanged. sit_armory 0.3.0 and sit_weapons 0.4.0 need no change.

### E1.5 The slice that builds E1

- **Slice:** `E1`, on branch `build/g1-e1` in worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e1`. It is created by the lead after Tom approves E1.
- **Lane:** Sonnet builder, or Codex Sol through dispatch. Never Opus. **Size:** S.
- **Base:** S7's merge on `integ/attach`. **S8's base becomes E1's merge.**
  - E1 edits `fit_geometry.py`, `rules.py` and `weapon_rules.yaml`, which belong to the S7/S8 spine. So it lands between them.
  - Landing it before S8 also means S8 builds its muzzle verdict tests against E1.1 from the start (E1.6 (d)).
- **Fallback:** if S8 has started when Tom approves, E1's base is S8's merge and S9's base becomes E1's merge. E1 then also re-pins S8's muzzle tests on square-barrel hosts. Either way, E1 lands before S10.
- **Owns:**
  - `src/synty_inventory/weapons/fit_locate.py`: the shared landing test; `strip(..., rules)`; `_STRIP_CELL_M` retired.
  - `src/synty_inventory/weapons/fit_bore.py`: the hull ratio in (iii).
  - `src/synty_inventory/weapons/fit_geometry.py`:
    - the `strip` call in `host_features`, which passes `rules`;
    - the strip scope (E1.3), if S7 lands without it.
  - `src/synty_inventory/weapons/rules.py`: one validator entry, `bore.circ_min` of kind `frac`.
  - `src/synty_inventory/data/weapon_rules.yaml`: one key, `bore.circ_min: 0.75`.
  - `tests/test_weapons_g1_locate.py`, `tests/fixtures/weapons/g1_locate_meshes.py`.
  - `tests/test_weapons_g1_bore.py`, `tests/fixtures/weapons/g1_bore_meshes.py`.
  - `tests/test_weapons_g1_seats.py`: only if S7 lands without the strip scope. It then gains one scope test: on the preset, a located slot-less part keeps its triangles.
  - `tests/test_weapons_*.py`: re-pins only, each citing E1.1 or E1.2. Expected re-pins:
    - the literal rules block in `test_weapons_g1_rules.py`;
    - the literal `bore` copies in `test_weapons_g1_verdict.py` and `test_weapons_g1_well.py`, since every key is required;
    - any S7 assertion of `barrel_round` on a host with a square barrel.
- **Not owned:** `make_glbs.py` and `w8h_world.py`. Their square barrels stay square (the W7 references must not move, §4.6). Under E1.1 those hosts have no barrel end unless their mount carries a ring bore. That is the intended reading.
- **ACs:**
  - E1.1: the AC135 fixtures above.
  - E1.2: the AC131 and AC132 fixtures above.
  - INV-29 on both E1.2 fixtures.
  - Each new fixture is shown failing on the base before it goes green (plan §0 rule 2).
- **Gate:** plan §0 rule 2: the whole suite exit 0, then the scope gate.
- **S9 follows from it.** `attach-calibrate` prints and enforces the new §4.2 `bore.circ_min` row, over the evidence-(ii) bore positives. The lead adds that row to S9's brief.

### E1.6 Effect on S7 (running at `097bfcc`)

These were read from the S7 worktree without changing it. They are for the lead to send as a mid-task correction.

**(a) Urgent, needed even before Tom rules on E1.** `host_features` strips every located placement: `strip(v, t, placements, part_meshes)` in `reduced()`.
- On the synthetic preset this is harmless: only a scope and a silencer are located.
- On the live presets it empties 9 of the 10 host presets (E1.3).
- S7 already keeps `part_slot`. The fix is to pass strip only the placements whose part has a slot.
- The literal reading cannot be the intent: it removes the rail AC134 measures. The slot scope is the narrowest reading that keeps every approved AC satisfiable. S7 can apply it now, and E1.3 records it for Tom.

**(b) The `strip` signature.**
- S7 calls the merged four-argument `strip`. That is correct at its base.
- E1 adds `rules` and edits that one call site after S7 merges. S7 needs no action.

**(c) Barrels in `g1_world.py`.**
- The carbine's barrel is a round tube with a ring bore, so it is unaffected.
- Every host built on the W8h box rifle has a 12 × 12 mm square barrel: FLAT, SCOPED, PRESET, ROCKET, SHOTGUN, NAILGUN and MINIGUN. Today it reads `barrel_round`; under E1.1 it has no barrel end.
- S7 should not assert `barrel_round` or a barrel end on box-rifle hosts. A `barrel_round` case belongs on a host with a tube of six sides or more and no ring bore. Then E1 re-pins nothing of S7's.

**(d) `make_glbs.gun()`.**
- Its 20 × 20 mm square barrel with a 4-vertex muzzle face reads `barrel_round` today (OD 28.3 mm) and has no end under E1.1.
- Any S7 re-pin that adds `feature: "barrel_round"` to such a host flips back under E1. E1 owns that re-pin, citing E1.1.

### E1.7 Open questions

- **E1-Q1 (Tom). AC131's count, 164 → 163.**
  - The one survey placement not reproduced is a slot-less alias whose vertices sit up to about 0.9 mm off.
  - Default: amend to 163 (other 117). All slot counts are unchanged.
- **E1-Q2 (non-blocking). Fused front sights.** See E1.3. Default: strip them, and S10 reports any optic span over a stripped sight placement.

### E1.8 Gate

**PASS for review.**
- Each point has its amended text, the ACs it touches, a synthetic fixture that fails on today's code, and a break.
- The new literal is calibrated by the §4.2 rule on a stated, mechanically selectable positive set. Its exclusions are reasoned.
- The slice has owned files, a base and a fallback, and its effect on S7 is stated.
- No interface outside `fit_geometry` changes, and consumers are unaffected.
- Not in force until Tom approves. E1.6 (a) is the exception: it applies the approved spec's intent.
