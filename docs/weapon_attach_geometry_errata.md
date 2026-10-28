# Errata: geometry fit gate G1

**Spec:** [weapon_attach_geometry.md](weapon_attach_geometry.md) (a bare `§N` points into it). **Plan:** [weapon_attach_geometry_plan.md](weapon_attach_geometry_plan.md).

> The public-repo rule of the spec applies here in full: algorithms, literals, classes, counts and ranges only. Every live number below was measured in a scratch folder, read-only against the a8c directory and the converted GLBs, and is not committed anywhere. Fixtures are synthetic.

## E1. Round barrel end, one landing test, strip scope

**Status: APPROVED** by Tom on 2026-10-27 (drafted by the architect the same day). Tom's words, verbatim: "Approve errata E1 at the defaults: AC131 goes to 163, fused front-sight posts are stripped and S10 reports any optic span over them. Cut the E1 slice off S7's merge, before S8."
- E1-Q1: AC131 is 163 placements ("other" 117).
- E1-Q2: the default. Fused front-sight posts are stripped, and S10 reports any optic seat whose span covers a stripped sight placement.
- E1.3's reading (strip only slot-filling placements) is in force. S7 already runs on it.

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
  > The 3 expected movers of §1.1 (the two Uzi-type SMG hosts and one nail gun) go from none to an end. E1.1's utility host with a four-sided nozzle goes from an end to none. Counted from the merged S5 detector's build-frame census of 234 with an end and 23 without, the result is 234 − 1 + 3 = 236 with an end and 21 without. (The §1.1 survey script read 233 and 24; that baseline gives 235 and 22.) The build reports the merged-detector figure. The brake preset stays without an end (E1.3). Any other mover is listed with its class.

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

## E2. Located magazine seat; the ring bore rule

**Status: APPROVED** by Tom on 2026-10-27 (drafted by the architect the same day). Tom's words, verbatim: "Use your default s". He typed this in the peer session instead of pressing either of its two buttons, "Approve as recommended" and "Approve at defaults". It is read as the peer's recommendations as put to him; the peer told him so in its closing message, and he can still correct it. The recommendations are:
- E2-Q1: no change, and S10 reports.
- E2-Q2: adopt; a ring needs two radii (E2.6).
- E2-Q3: drop the clause. The peer's line to Tom, verbatim: "Here I depart from the architect's default. Every one of the 10 preset hosts has a baked magazine child, so the authored seat wins and zero live hosts need a seat derived from a located magazine. Building it adds code and a schema tweak for nothing measurable. Drop the clause from the spec and retire the matching S7 fold-in. It can return with a fixture when a pack actually needs it." This reading supersedes E2.7's stated Q3 default (the E2.1 fix). If Tom corrects it, Q3 flips to the E2.1 fix, and the E2 slice gains that work.
- E2-Q4: no policy change.

**Found by:** S7.
- E2.1: its fold-in 4 (`build/g1-s7` at `5c8dd35`) gives a preset with a fused magazine a located well reference and no magazine seat.
- E2-Q2: its builder (at `ab6c911`, plan §0 rule 7, not tuned). A solid round rod reads as a ring bore, so `barrel_round` is not reachable through the build.

**Live effect.**
- E2.1 and E2-Q3: none (E2.3). All 10 eligible preset hosts carry a baked magazine child, so the authored seat wins on every one, and dropping the clause changes no live record.
- E2-Q2 (adopted): 19 muzzle mount records change, and no muzzle verdict does (E2.6).

| Point | Gap | Change | Sections | ACs |
|---|---|---|---|---|
| E2.1 | §3.7 admits a located magazine as the reference, but no step gives it a seat | not built (E2-Q3): §3.7 step 1 drops "or a located magazine on a preset", and S7 fold-in 4 is retired | §3.7, §3.11 | AC138 (guard, E2.4) |
| E2-Q2 (adopted) | the A0 ring estimator reads any end with a 6-point bin as a ring, a solid rod included | a ring needs an inner and an outer radius | A§4.2, §3.6 (i) | AC135 (fixtures), A-AC67 (re-pin) |

### E2.1 The gap and the fix (§3.7, §4.4, §7)

**Not built (E2-Q3).** The clause is dropped from §3.7 step 1 instead, and S7 fold-in 4 is retired (E2.4). The gap below stays as the record. The fix, its amended text, INV-30 and the AC136 sentence are the option Q3 declined, and are not in force.

**Today.**
- §3.7 step 1 admits "a located magazine on a preset" as the reference. Step 2 then places each candidate "at the reference seat", but no step derives a seat from a placement.
- §7 says the opposite: a fused magazine gives no reference, so its pairs are `not_judged`.
- S7 at `5c8dd35` follows step 1 halfway. The well reference carries `source: "located"`, but the magazine mount stays `none` (`no_child_no_probe`, no point).
- So the S8 well pair pass has no seat to place a candidate at, and compat leaves every magazine pair on such a host `not_judged` (a `pending_hosts` row).

**The fix.** The seat of a located magazine is its placement:
- `point = anchor.point + t`. `forward` and `up` are the anchor's own, because the placement is translation only.
- `anchor` is the located part's own attachment anchor (A§3.4), exactly as its record's `attachment.anchor` holds it. `t` is the stored `Placement.t` (§3.2).
- When the magazine slot has no authored seat and is not disabled, the mount becomes:

  ```json
  {"source": "probe", "feature": "well_ref", "point": "<anchor.point + t>", "forward": "<anchor.forward>", "up": "<anchor.up>",
   "span_m": null, "span_source": null, "occupied_by": [], "child_node": null, "bore_d_m": null, "bore_source": null,
   "confidence": 0.4, "reason": null}
  ```

  - **Confidence 0.4:** the value a `child_node` magazine seat gets. The evidence is the same: the part Synty authored, where Synty put it. There is no review reason, because the seat is not an estimate.
  - **Span null:** the magazine verdict reads the entry section, not a span. INV-15 allows a null span on a seated mount.
  - **`occupied_by` empty:** a fused magazine is no node. INV-16 forbids anything else on a `probe` magazine seat.
- An authored seat (`child_node`, `override`) still wins, as S7 does today.
- With several located magazines, the larger by volume is taken, then the name, then `t` (S7's tie-break, after the children rule of A§4.2).
- A frame-conflict host gets no such seat (INV-27).
- Candidates are then placed at this seat with C-21 and judged by §3.7 steps 2 and 3, unchanged.

**The `source` value: no new one.**
- **Mount `source`: `"probe"`.**
  - Q-G5 kept `MOUNT_SOURCES` at four values. A new value makes sit_armory 0.3.0 reject every such record (ARM_E70, §4.6), and would need its MINOR release first. AC145 holds.
  - `probe` is already how a detector writes a seat on a non-muzzle slot (§4.4).
  - A `probe` magazine seat with `feature: "well_ref"` arises only from a located magazine, so a record still tells the two cases apart.
- **`WellRef.source`: `"located"`**, already in `fit_types` (`Literal["child", "located"]`, S2) and in §3.11. No amendment.
- **What it amends:** the schema's feature-to-source rule only. `_FEATURE_HOMES["well_ref"]` (S7's `schema.py`) admits `probe` beside `child_node` and `override`. `MOUNT_SOURCES` and `MOUNT_FEATURES` are unchanged.

**Amended text.**
- **§3.7 step 1**, appended:
  > A located magazine's seat is its placement: the part's own anchor (A§3.4) carried through `t`, with `point` + `t` and `forward` and `up` unchanged. When the slot has no authored seat, it becomes the magazine mount: `source: "probe"`, `feature: "well_ref"`, `occupied_by` empty, span null (E2).
- **§4.4**, the `feature` bullet gains:
  > `well_ref` sits on a magazine mount whose source is `child_node` or `override`, or `probe` for a located magazine (§3.7 step 1).
- **§7**, "A real well with no authored magazine (fused or absent magazine)" reads:
  > A real well with no authored magazine (an absent magazine). There is no reference, so the pairs are `not_judged` and pending, as today. A fused magazine on a preset is located and gives the seat (§3.7 step 1).
- **§5, new invariant:**
  > **INV-30 (E2).** A located magazine's seat places its own part exactly where it was found: C-21 `place(anchor, seat)` equals `translate(t)` within 1e-4.
- **AC136** gains a fixture sentence:
  > Synthetic: on a preset whose magazine is fused (no baked child), the located magazine gives the magazine seat, and a same-size magazine of another family placed there is `fit`.

  Its break column gains: "no seat derived from the placement: the pair stays `not_judged`".

### E2.2 Fixture (not built, E2-Q3)

Not built: E2-Q3 drops the clause. The guard in E2.4 takes its place. The text below is the record of the declined option.

`PRESET_MAG` in S7's `g1_world.py`: `MAG_RIFLE` fused at `PRESET_MAG_AT` (0, 0, −0.10), with no baked magazine child. The test goes in `test_weapons_g1_seats.py`.

- **The seat.** The magazine mount is `probe` and `well_ref`, with `occupied_by` empty, `child_node` null and span null. Its point, forward and up are `MAG_RIFLE`'s anchor carried through `PRESET_MAG_AT`, as literals worked out by hand.
- **INV-30.** `attach.place(<MAG_RIFLE anchor>, <seat>)` equals `translate(PRESET_MAG_AT)` within 1e-4.
- **A candidate judged.** `MAG_PISTOL` (the other family, same size) is placed at the seat with C-21 and cut at `u_rb − 0.002`.
  - Its entry section is (0.04, 0.02).
  - `fit_geometry.verdict("magazine", ...)` is `fit` with signals `("well_entry",)`.
  - The test asserts the verdict, not a listing (E2-Q4).
- **On today's code** (`5c8dd35`) it fails at its first assertion.
  - The magazine mount is `source: "none"`, `reason: "no_child_no_probe"`, point null. S7's own `test_fold_in_4_a_fused_magazine_is_a_located_reference_without_a_seat` asserts exactly that.
  - So `"none" != "probe"`, and the candidate has no seat to be placed at. After S8, through compat, the pair is `not_judged` and goes to a `pending_hosts` row.
- **Breaks:**
  - The mount left `none`: the seat assertion fails.
  - The anchor not carried through `t` (the seat left in part space): INV-30 fails.
- **Re-pin:** S7's `test_fold_in_4_...` asserts no seat. It is re-pinned, citing E2.1.

### E2.3 Count on the live packs

- **0 of 10.** The eligible preset hosts are 10, all in the Military pack.
  - All 10 carry a baked magazine child, so their magazine mount is `child_node`, and the authored seat wins.
  - The locator also finds a magazine on every one of them, where the child stands, as on S7's `PRESET` fixture.
  - No eligible preset host has a located magazine and no authored seat.
- **How it was measured.** A throwaway scratch script, read-only against the a8c directory and the converted GLBs. Nothing was committed.
  - The hosts: every eligible host (non-null `mounts`) whose name tokens hit `attach_filled_hosts` (`preset`).
  - The locator: E1's landing test (the scratch prototype of E1.2; the E1 slice is not merged yet), on each host's whole mesh, as S7 runs it.
  - The parts: all 17 parts in the pack with `attachment.slot == "magazine"`.
  - Each host was then classed by its a8c magazine mount: authored, `slot_disabled`, or `none` with or without a located magazine.
- The plan's §8 build log records this, beside E1's live-calibration line.

### E2.4 The slice that builds E2

- **Slice:** `E2`, on branch `build/g1-e2` in worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e2`, created by the lead.
- **Lane:** Sonnet builder, or Codex Sol through dispatch. Never Opus. **Size:** S.
- **Base:** S8's merge on `integ/attach`. The order is E1 → S8 → E2 → S9 → S10, so **S9's base becomes E2's merge**.
  - E2-Q2 rides in this slice; there is no `E2b`. On S8's merge the label-era `compat.fit_bore` no longer reads `bore_source` for the muzzle (§3.8), so the 19 mount changes of E2.6 move no listing.
- **Owns (E2-Q3: retire S7 fold-in 4, the located-magazine well reference on presets).**
  - `src/synty_inventory/weapons/fit_geometry.py`:
    - `_compute`: the magazine block's `elif placements:` branch is removed. That is the code marked `# S7 fold-in 4`, which writes `slots["magazine"]["well_ref"]` with `source "located"` from the largest located magazine. The authored-child branch above it is unchanged.
    - `_volume`: removed. The fold-in was its only caller; `mounts.py` has its own.
    - The contract comment's "Located magazine" reading is removed.
    - Unchanged: the locator, `out["located"]`, the slot-part strip (E1.3) and Q-G11's `refuse_filled`. A located magazine is still stripped from the host mesh and still leaves `magazine` open under `attach_filled_open`.
  - `src/synty_inventory/weapons/fit_types.py`: `WellRef.source` narrows to `Literal["child"]` (§3.11). This is type-only: the field stays, and `test_weapons_g1_verdict.py` pins field names, not values.
  - `src/synty_inventory/weapons/fit_well.py`: the `well_reference` docstring only. The sentence that says the S7 caller sets `"located"` goes.
  - `tests/fixtures/weapons/g1_world.py`: the `PRESET_MAG` docstring line only. The mesh is unchanged.
  - `tests/test_weapons_g1_seats.py`: `test_fold_in_4_a_fused_magazine_is_a_located_reference_without_a_seat` is re-pinned as the guard below, citing E2-Q3.
  - S8's tests: any that judge or list `PRESET_MAG`'s magazine pairs re-pin to `not_judged` (a `pending_hosts` row), each citing E2-Q3. S8 had not been cut when this was written, so the builder lists them.
  - Not touched: the magazine path of `mounts.py`, `schema.py` (`_FEATURE_HOMES["well_ref"]` stays `child_node` and `override`), and `directory.py` (the `_fused_parts_factory` rows gain no anchor).
- **What a fused-magazine preset gets.**
  - With a baked magazine child: the authored child seat (`child_node`, `feature: "well_ref"`, the reference from the child), as on all 10 live presets (E2.3).
  - Without one: no well reference. `slots["magazine"]` has no `well_ref`, the mount stays `none` / `no_child_no_probe`, and its magazine pairs are `not_judged` (a `pending_hosts` row).
- **Guard (proposed, the re-pinned test).** On `PRESET_MAG`:
  - `"well_ref" not in slots["magazine"]`;
  - the magazine mount is `source "none"`, `reason "no_child_no_probe"`, with no `feature`;
  - `fit_geometry.verdict("magazine", slots["magazine"], <a magazine part with entry section (0.04, 0.02)>, None, rules)` is `("not_judged", ())`;
  - `located` still lists `MAG_RIFLE`, and `CARBINE`'s child reference still has `source "child"`.
  - On the base it fails at its first assertion: the reference is there with `source "located"`, and the verdict is `fit`. Break: fold-in 4 left in place.
  - It is the synthetic case of AC138's negative control "magazine on a host with no well reference".
- **If Tom corrects Q3,** the E2.1 work replaces the E2-Q3 block. Its owned files are listed in E2.4 as of `5a3caf1`: `fit_geometry.host_features`, `mounts._apply_features`, `schema._FEATURE_HOMES`, `directory._fused_parts_factory` and its cache key.
- **Owns (E2-Q2).**
  - `src/synty_inventory/weapons/mounts.py`: `bore_diameter` only. That is the A0 ring estimator; `geometry.muzzle_probe` collects the face, and `mount_probe.py` and `fit_bore.py` are not touched.
  - `tests/test_weapons_g1_bore.py`: the four E2.6 fixtures. They build their meshes inline from `g1_bore_meshes.tube` and `g1_world.rod_rifle`.
  - `tests/test_weapons_w8b_muzzle.py`: one re-pin, citing E2-Q2. `test_ac67_the_ring_estimator_needs_six_points_and_reads_the_innermost_ring` asserts that a lone six-point ring is `"ring"`; under E2-Q2 it is `"face_extent"`. Its two-ring case and the `Mount`, `Double` and `Plain` worlds have two radii or none, and stay.
- **Not owned:** `docs/weapon_attachments.md` (the lead routes the A§4.2 pointer), `tests/fixtures/weapons/g1_bore_meshes.py`, and `g1_world.py` beyond the one docstring line.
- **ACs:** the E2-Q3 guard, and the AC135 fixtures of E2.6. Each is shown failing on the base first (plan §0 rule 2), except E2.6's two guards, which cannot fail there. E2.1's AC136 sentence and INV-30 are not built.
- **Gate:** plan §0 rule 2: the whole suite exit 0, then the scope gate.

### E2.5 Versions, digests and consumers

- **No version bump of its own.** `WEAPON_ATTACH_VERSION` 14 lands in S8 and is not exported to a game before S11 (plan §0 rule 5). `attach_rules_digest`, `rules_digest` and `overrides_digest` are unchanged: no rule key changes.
- **Caches miss on their own.** The fit cache and the `mv` fingerprint miss on the `fit_*.py` code digests. The geometry mounts cache misses on `mounts.py`'s code digest (`md`), as A-AC123 requires.
- **The default export is unchanged.** It drops `geometry.mounts` (INV-19). The E2-Q3 retirement changes no live record: no live preset lacks an authored magazine seat (E2.3).
- **The `--attachments` export** moves only under E2-Q2: the 19 muzzle mounts of E2.6.
- **Consumers are unaffected.** No mount `source` or `feature` value changes. `bore_d_m` and `bore_source` are carried as data; no consumer code reads them. No change and no bump.

### E2.6 E2-Q2: a ring needs two radii (ADOPTED)

**Today.** `mounts.bore_diameter` (the A0 ring estimator, A§4.2) histograms the muzzle face points by radius from the face centre in 1 mm bins. The innermost bin holding ≥ 6 points is the ring: `bore_source "ring"`, `bore_d_m` twice its mean radius. There is no check that anything lies outside it.
- A solid end therefore reads as a ring. S7's `rod_rifle` (a 32-sided solid rod, r 8.5 mm, ending in a fan to one centre vertex) gives 33 face points: 32 in the 8 mm bin and the centre alone in bin 0. So `bore_diameter` returns `(0.017, "ring")`.
- §3.6 (i) takes any `"ring"` as evidence, so the rod's end is `barrel_ring`. Through the build, `barrel_round` is reachable only on an end with fewer than 6 points per bin. S7's rod test reaches it by handing `bore_source="face_extent"` to the mount.
- `mount_probe.end_ring_d` (evidence (ii), and `device_inner_d` on the part side) already refuses this case: its ring must lie inside 0.75 of the slab's outer radius.

**The rule (adopted).** It follows the S7 builder's wording, with two changes. "Inner > 0" is read at the estimator's resolution. And a one-radius end falls through §3.6 in order, instead of going straight to (iii): 16 of the 19 below land on (ii).
- **A§4.2**, the ring sentence reads:
  > ... points around the face centre (1 mm bins). A ring needs an inner and an outer radius: the innermost bin other than the centre bin (radius < 1 mm) holding at least 6 points is the ring only if a point lies in a bin beyond it. It gives `bore_d_m` and `bore_source = "ring"`. An end with one radius has no ring bore: `bore_d_m = face extent`, `bore_source = "face_extent"` (E2-Q2).
- **§3.6 (i)** keeps its text. It reads A§4.2 as amended, so a one-radius end is not evidence (i). It falls through to (ii), then (iii) with E1.1's circularity, as any end does.
- No new literal: `_RING_BIN_M` and `_RING_MIN_POINTS` are reused.

**Count** (a8c build frame before strip, E1.1 in force, 257 hosts with mounts; the A0 face re-run agrees with a8c's `bore_source` on all 200 probe mounts):
- Evidence today: ring 158, face ring 67, round section 8, none 24.
- **(i) ring ends: 19 of 158 have one radius.** By class: rifle 8, pistol 5, heavy gun 3, shotgun 2, sniper 1.
  - 3 of the 19 (2 pistols, 1 rifle) have their whole A0 face within 0.5 mm of its centre, so no bin outside the centre bin. The other 16 have no point beyond their ring bin.
- **(ii) face rings: 0 of 67 have one radius.** `end_ring_d`'s 0.75 rule already excludes them.

**What moves under the rule.**
- Of the 19:
  - **16 go to (ii) `face_ring`.** The slab behind the face holds a bore ring. The feature stays `barrel_ring`; only the evidence label changes.
  - **3 go to (iii) `round_section`**: 1 heavy gun and 2 shotguns. Hull ratio 0.83 to 0.90, extent ratio 0.87 to 1.0, OD 28 to 49 mm. All three pass `round_min`, `circ_min` and the OD cap. The signal goes `barrel_ring` → `barrel_round`.
  - **None drop to none.**
- **No muzzle verdict changes.** `od_m` comes from the slab for every evidence, the verdict table is the same for all three, and `device_inner_d` uses `end_ring_d`, which the rule does not touch.
- **The 19 mount records change** (the `--attachments` export and the directory): `bore_source` ring → `face_extent`, confidence 0.8 → 0.5, `bore_d_m` to the face extent. That moves it by under 2 mm, because all the points share one 1 mm bin.

**Effect on E1.1's calibration set: none.**
- All 7 evidence-(i) positives keep (i). Each has two radii at the A0 face: the 4 slide faces and the 3 round barrels.
- All 4 evidence-(ii) positives keep (ii). The rule does not touch `end_ring_d`. 3 of the 4 have a one-radius A0 face, but (ii) proves them, not (i).
- `circ_min` 0.75 and AC135 are unchanged.

**Alternative measured: align with `end_ring_d`** (the ring inside 0.75 of the face's outer radius). Rejected.
- It takes 30 of the 158 out of (i): 18 of the 19, plus 12 ends with two radii whose ring sits at 0.76 to 0.98 of the face's outer radius, i.e. bores in a wall thinner than a quarter of the radius. Where those 12 would land was not measured.
- The other one of the 19 is a centre-bin face; 0.75 lets it through.
- A thin-walled real bore is a ring. The two-radii rule keeps all 12 and moves only ends with nothing outside their ring.

**Reading measured: "two radial bins" as two bins of ≥ 6 points each.** Rejected.
- It gives 27 one-radius ends: the 19, plus 8 whose outline beyond the ring is sparse (1 to 16 points, under 6 in every bin).
- On 7 of the 8 the A0 ring sits at 0.45 to 0.85 of the face extent: a real bore inside a low-poly outline. 1 is a rim with a single stray point beyond it.
- All 8 land on (ii), so no verdict moves under either reading. One evidence-(i) positive (a round barrel) would move to (ii) and keep its proof; `circ_min`'s positive minimum is unchanged.
- It loses 7 real bores to catch 1 rim, so the rule takes any point beyond the ring.

**Fixtures** (AC135, in `test_weapons_g1_bore.py`). Each mount comes from the probe path: `geometry.muzzle_probe` → `mounts.bore_diameter`, as `_muzzle_mount` runs it. It is never a hand-set `bore_source`.

| Fixture | Expected under E2-Q2 | Today |
|---|---|---|
| `rod_rifle()` (solid 32-sided rod, r 8.5 mm) | `bore_source "face_extent"`; `end_ring_d` finds no ring (the rim is the outer radius); (iii) hull ratio 0.99 → `("round_section", {"feature": "barrel_round"})`, OD 0.017 | `bore_diameter` → `(0.017, "ring")`, so evidence (i). **Fails** with `("ring", {"feature": "barrel_ring"})`. |
| A face of 6 points within 1 mm of its centre plus a 12-point rim at r 10 mm (the estimator unit test) | `face_extent` | `"ring"` with `bore_d_m` under 0.002. **Fails.** |
| Thin-wall tube `tube(0.0, 0.25, 0.010, 0.008)`: OD 20 mm, modelled bore 16 mm, bore/OD 0.8 | `(0.016, "ring")`, evidence (i), `barrel_ring` | `(0.016, "ring")`. **Passes today and cannot fail there.** Today reads every bin of 6 points as a ring, a true bore included. It guards the rule against over-reach. |
| A 12-point ring at r 6.5 mm inside a 30 × 30 mm square face, 4 corners (the estimator unit test) | `(0.013, "ring")` | `(0.013, "ring")`. **Passes today and cannot fail there**, for the same reason. It guards the sparse-outline case. |

- **Breaks:**
  - The rule left out (today's code): the rod and centre-bin fixtures fail.
  - The rule aligned with `end_ring_d`'s 0.75: the thin-wall tube fails (no ring, then (iii), `barrel_round`).
  - A rule that calls an end solid when its outermost bin holds ≥ 6 points: the tube fails.
  - The two-bins-of-six reading: the square face fails (`face_extent`).

**Adopted** (Tom, 2026-10-27, read as the peer's recommendation; see the status). It was recommended because:
- It moves no verdict and keeps every positive's proof.
- It makes `barrel_round` reachable through the build for a solid round end, which §3.6 (iii) was written for.
- It adds no literal.
- It lands after S8, in the E2 slice (E2.4).

### E2.7 Questions and answers

Each was Tom's. The answers are read from his reply, as the status records.

- **E2-Q1. The flat seat takes the longest flat run** (§3.4 step 3). Default: no change.
  - On box rifles the longest flat run is the handguard, not the receiver top. `RIFLE_PLAIN` gets no optic seat, so its optic pairs are `not_judged` (a `pending_hosts` row).
  - S10 reports, as data for Tom, how many untoothed hosts have their flat seat on a run that is not their highest qualifying run (plan §3 step 4).
  - Preferring the receiver top would be a spec edit after S10's numbers, not tuning now.
  - **Answer: no change, and S10 reports.**
- **E2-Q2. A ring needs two radii.** The numbers and the reasons are in E2.6.
  - **Answer: adopted.**
- **E2-Q3. The fix, or drop the clause.** Default: the E2.1 fix.
  - E2.3 counts 0 live hosts. The alternative is to drop "or a located magazine on a preset" from §3.7 step 1, which agrees with §7 as it stands, and retire S7's fold-in 4.
  - The alternative is docs-only plus a code removal. Either way, §3.7 step 1 and §7 agree afterwards.
  - **Answer: drop the clause** (the peer's recommendation, which departs from this default). §3.7 step 1 now agrees with §7, and the E2 slice retires fold-in 4 (E2.4). If Tom corrects the reading, Q3 flips to the E2.1 fix.
- **E2-Q4. A fused magazine cannot be hidden.** Default: no policy change. The slot stays open under `attach_filled_open`, and a `fit` magazine lists.
  - A `child_node` magazine seat lists the child in `occupied_by`, and a consumer hides that node. A fused magazine is part of the preset mesh, and its seat's `occupied_by` is empty, so a listed candidate renders over the fused magazine.
  - Tom's "preset guns can take other magazines" (2026-10-24) was made when every preset magazine was a hideable child.
  - Alternative: a located magazine fills `magazine`. The verdict is then computed for calibration only, as for a policy-refused positive (E-G6). This only adds refusals, which is Q-G11's own principle.
  - With 0 live hosts, neither choice moves a listing today.
  - **Answer: no policy change.** Under E2-Q3 a fused magazine with no child gives no reference, so no candidate lists over it. The question comes back if the clause does.

### E2.8 Gate

**PASS.**
- E2.1 records the gap. Under E2-Q3 the clause is dropped from §3.7 step 1, and the retirement has a guard that fails on today's code with a stated failure.
- E2-Q2 has its rule text, the live count with what moves, its effect on E1.1's calibration set, a measured alternative, a rejected reading, and fixtures. Two fail on today's code; the other two are guards that cannot fail there, and that is said.
- The live counts are measured, with the method recorded, and no data is committed.
- The `source` question is answered against the fit_types literal, the schema enum and the consumer contract. Under E2-Q3 no mount `source` or `feature` changes, and `WellRef.source` narrows to `"child"`.
- The slice has owned files, functions and re-pins, and a base after S8.
- In force: Tom approved E2 on 2026-10-27, read as the status records.
