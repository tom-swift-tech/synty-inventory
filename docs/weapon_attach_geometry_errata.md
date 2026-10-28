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

## E3. Barrel-face outer diameter, stripped barrel evidence, frame fields, sight clause, two-seat well plane, foot rung, clamp bound, well section order

**Status: APPROVED** by Tom on 2026-10-28 (drafted by the architect the same day; the ruling reached the architect through the peer, which relayed it in the E3.0 brief). Tom's words, verbatim: "Approve E3 at the defaults: Q1 B, Q2 M3 (withdrawn under B plus Option 2), Q3 F1, Q4 (ii) with the population-diff gate, Q5 Option 2 at 0.69, Q6 no floor now, Q7 rail slots only. E3.12 accepted as a correction." They read as:
- E3-Q1: **B.** For ring evidence, `od_m` is the barrel face's, read on the stripped mesh (E3.1, E3.2).
- E3-Q2: M3 was the answer only if A or Option 1 were taken. Under B plus Option 2 it is **withdrawn**: E3.3 is not built, `fit_geometry.exceptions` stays empty, E-G3 is retired, and E-G7, E-G8 and E-G9 are not entered.
- E3-Q3: **F1.** The §3.7 plane is taken with every magazine node of the mount removed (E3.6). E-G7 is not entered.
- E3-Q4: **(ii)**, the A4 footprint and anchor, with a population-diff gate that reports every part whose foot width, foot length or anchor changes. (iii), a per-pair re-measure, is the fallback if the mid-line proxy misses a part (E3.7).
- E3-Q5: **Option 2.** `clamp.ratio_min` is set by §4.2 to 0.69, conditional on E3.7 (E3.8).
- E3-Q6: **no floor** on the width of a toothed run now (E3.9).
- E3-Q7: the mid-line rule applies to **rail slots only**, `optic` and `underbarrel`: 2 parts move. The 3 non-rail parts (2 `laser_light`, 1 `magazine`) are not moved (E3.7).
- E3.12: **accepted as a correction**, not a choice.

**Found by:** the S10 first run (2026-10-28, at `3e216e3`) and the peer's traces of its findings 7 to 9; the S10a tool fix (`f5af916`); the E3.1 counterfactual and two read-only runs on the a14 build (integ `4b34278`); the E3.8 rail-side and part-side traces; and the architect's build ladder, which ran each item on a scratch copy of the source. E3.12 was found by the architect's trace of the drum twin's transposed section, while the ladder emulated E3.6.

> The public-repo rule of the spec applies here in full. Every live number below was measured in a scratch folder, read-only, and is not committed anywhere. The ladder's emulations ran on copies of the source: the integ tree was never edited. Seat labels S1 to S11 name the 11 bore positives of §1.1, and T1 to T3 name the three twins that share baked seats (T1 shares S1's device, T2 S2's, T3 S3's). Fixtures are synthetic and not built.

**Where the measurements depart from the earlier text (the measurement is used, and the text says so):**
- AC133 (a): the spec's 36 of 38 is not what the build produces. The a14 build gave **31** before E3. The approved ladder runs 31, 33, 34, 34, 37, 38 (the last INFERRED). The drum twin does not read 0.000 under F1 alone; it needs E3.12.
- E3.7: the mid-line proxy moves **5 parts** when applied to every slot, not "up to 4" and not only rail parts. Under Q7 (rail slots only) it moves **2**.
- E3.1: **4** seats, not 3, sit outside the band under the slab definition (the fourth is S10 at 0.6761). With their twins that is 6 of 14 observations.
- E3.9: the survey's rail top widths, its toothed-host counts, its inner-ring count and its overhang do not reproduce (data only, no literal moves). The positives' rail top widths are 10.7 to 30.0 mm.

**Live effect** (each figure is the delta of that slice against the merged state before it; the ladder was measured in the stacked order E3.1, E3.6, E3.7, E3.8, and the four act on disjoint pair sets):
- E3.1: 85 muzzle verdicts change (68 `no_fit` to `fit`, 17 `fit` to `no_fit`); 66 listed pairs enter, 17 leave.
- E3.6: 8 magazine pair rows change, all on one host.
- E3.7: 9 pairs `no_fit` to `fit` (7 optic, 2 underbarrel), all cross-pack, all listed.
- E3.8: 79 pairs `no_fit` to `fit`; 75 listed pairs enter.
- E3.12: stored well sections of one magazine part change (inferred twin count 38 of 38).

| Point | Gap | Change | Sections | ACs | Slice |
|---|---|---|---|---|---|
| E3.1 (Q1: B) | `od_m` is read from the end slab, which on a slide or receiver face is the face, not the barrel | for ring evidence, `od_m` and `centre_su` come from the barrel face of the stripped mesh | §3.6, §4.2 | AC133, AC135, AC137 | `E3.1` |
| E3.2 | evidence (i) is the mount's ring, probed on the unstripped host, so on a fused-device preset it describes the device | the bore probe for (i) runs on the stripped mesh (W1) | §3.6 (i) | AC135, AC143, AC144 | `E3.1` |
| E3.3 | `fit_geometry.exceptions` cannot name one pair | **WITHDRAWN** (Q2): B plus Option 2 need no exception | none | none | none |
| E3.4 | the §3.3 list of frame-derived fields is short | add `geometry.bounds`, `hints.size_class`, `geometry.support`, `geometry.support_r_m`, `flags.forward_by_fallback` | §3.3 | AC146, AC147 (guards) | `E3.4` |
| E3.5 | AC139 and AC149 forbid additions that the frame change causes | a frame-changed sight-slot clause | §3.8 | AC139, AC149 | `E3.5` |
| E3.6 (Q3: F1) | the §3.7 plane meets no edge on one two-seat host | remove every magazine node of the mount | §3.7, §4.2 | AC133, AC136, AC138 (note) | `E3.6` |
| E3.7 (Q4: ii, Q7) | the foot slab can be a side feature that misses the run | the foot rung must hold the part's mid-line, on rail slots | §3.5, A4 | AC134, AC107 | `E3.7` |
| E3.8 (Q5: Option 2) | `clamp.ratio_min` 1.0 is violated by authored positives | the literal is set by §4.2 to 0.69, conditional on E3.7 | §3.5, §4.1, §4.2 | AC134, AC137 | `E3.8` |
| E3.9 (Q6) | the survey and the build disagree on six counts | data only; no floor on rail width; no literal moves | §1.1, §4.2 | none | none |
| E3.10 | items carried to later slices | four | none | none | `E3.6`, `C1`, `C3` |
| E3.12 | the directory cuts the well section before the twin forward is corrected | the order is corrected | §3.7 | AC133, AC136 | `E3.12` |

**What the items do to the twin check (AC133 (a)).** Each slice's gate reports its own delta against the state before it.

| state | twins `fit` of 38 | why |
|---|---|---|
| a14 build today | 31 | 7 not `fit`: 2 muzzle twins `no_fit` (slab OD, E3.1), 3 optic twins `no_fit` (clamp ratio, E3.8), 1 drum twin `not_judged` and 1 standard-magazine twin `unverified` (both E3.6) |
| after E3.1 | 33 | the 2 muzzle twins flip `no_fit` to `fit`; the slide-face silencer twin reads 0.9221, inside the band, with no inner ring |
| after E3.6 | 34 | the standard twin flips `unverified` to `fit`. The drum twin becomes judged but reads `no_fit`: its stored section is the reference's two dimensions with the axes swapped (deviation 0.229 against `well.tol` 0.15), while calibrate reads it at 0.0000 (E3.12) |
| after E3.7 | 34 | no twin moves |
| after E3.8 | 37 | the 3 optic twins, at ratios 0.9267 (two) and 0.7692, clear a 0.69 bound |
| after E3.12 | **38 (INFERRED)** | the drum twin's section is cut with the corrected anchor and reads 0.0000. Inferred from the 0.0000 re-cut; not built. Confirmed at S10b |

The draft's alternative to F1 (E-G7, the drum twin recorded as not a positive) would have ended at 36; it was not taken.

### E3.1 Barrel-face outer diameter (§3.6, §4.2)

**Status: APPROVED (Q1: B).**

**Today.**
- §3.6 defines `od_m` as twice the end slab's outer radius around the slab's centre, and `centre_su` as that centre. `fit_bore.barrel_end` does exactly this for all three evidences. The slab is the stripped mesh's vertices within `end_slab_m` (10 mm) of the forward extreme.
- On a pistol slide or a receiver face the foremost 10 mm holds the whole face, so the far corners of the face set the radius. The ring of the barrel is a small boss inside it.
- AC135's break line names this failure: "barrel end measured on the unreduced mesh (a baked device's face read as the barrel)". The E-G3 premise was a related one: the slide-face pistol has "no modelled barrel", so its OD ratio falls below the band.

**Evidence: the 11 bore positives under the slab (the code as it was).** The calibrate tool finds 14 placements on 11 distinct seats (baked 6, twin 3, preset 5). Seats by class: S1 pistol baked, S2, S3, S4 and S11 SMG baked, S5 and S8 presets on no host (non-host presets), S6, S7 and S9 fused-device presets on a rifle or sniper host, S10 pistol baked.
- OD ratio (mate over `od_m`) reads 0.35 to 1.65. **4 of the 11 seats are outside the live band [0.85, 2.00]**: S1 at 0.3503, S2 at 0.3784, S9 at 0.4399, S10 at 0.6761. With the twins that is 6 of 14 observations.
- Axis offset reaches 13.6 mm: 5 observations on 3 seats are over the live 5 mm (S1 and T1 13.6, S2 and T2 5.7, S9 10.5).
- Inner ratio: one of 7 placements is outside [0.47, 1.21], S9 at 0.2699.
- The four out-of-band seats are the four whose slab OD is 42.3 to 96.2 mm against a barrel-face OD of 21.3 to 25.6 mm (a factor of 1.65 to 4.2), and whose slab fill is 0.38 to 0.69. The other seven fill 0.82 to 0.90.
- AC135 expected 10 of 11 in band. Live: 7 of 11.

**Evidence: what the survey did.** The survey's definition cannot be recovered. §1.1 and §4.2 recorded an OD ratio of 0.93 to 1.92 on 10 of 11, an axis offset of at most 3.9 mm, and inner ratios of 0.55 to 1.13 on 6 placements of 4 devices. Neither definition measured here reproduces it:

| clause | survey | slab (today) | barrel face (B) |
|---|---|---|---|
| OD ratio inside [0.93, 1.92] | 10 of 11 | 6 of 11 | 9 of 11: S1 reads 0.9221 and S5 reads 0.9097; the top is 1.6526, not 1.92 |
| axis offset | at most 3.9 mm | up to 13.6 mm | at most 1.2 mm over all 14 observations |
| inner ratio | 0.55 to 1.13 on 6 placements, 4 devices | 0.27 to 1.13 on 7 placements, 5 devices | 0.5581 to 1.1315 on the same 7 placements, 5 devices |

The choice below therefore stands on the measurements, not on matching the survey.

**The rule (B).** For evidence (i), `od_m` is twice the largest distance of any point of the muzzle face from the face's mean (s, u) position, and `centre_su` is that mean. The face is the A0 probe's face (the first 1, 2, 5 or 10 mm window behind the forward extreme that holds 3 or more points), taken on the **stripped** mesh (E3.2). For evidence (ii) and (iii), `od_m` stays the slab's: the detector holds no second outer radius for them. A face is not a barrel: §3.6 asks for the barrel's outer diameter, and a slide or receiver face is a different object that sits within 10 mm of it.

**Measured under B.**
- Offline, on the 11 seats: OD ratio 0.9097 to 1.6526, **11 of 11 inside the live band** (14 of 14 observations); the tightest margin is 0.06 above the lower edge. Axis offset at most 1.2 mm. Inner ratio 0.5581 to 1.1315, inside [0.47, 1.21] on all 7 (margins 0.0881 below and 0.0785 above). The ring is found on the stripped face for all 14 observations.
- S1, the slide-face pistol silencer, reads 0.9221. Its barrel face carries a ring, so E-G3's premise ("no modelled barrel") does not hold on the barrel face.
- On the full build, with B patched in for the 140 of 191 barrel-end hosts whose evidence is a ring (the other 51 untouched): of 537 muzzle verdicts, **85 change: 68 `no_fit` to `fit`, 17 `fit` to `no_fit`**. None goes to `not_judged`, and no pair of another slot moves.
  - Listed pairs: 66 enter (15 same-pack that were listed before G1, and 51 cross-pack that no earlier build listed; 18 hosts, 8 devices) and 17 leave (3 same-pack, 14 cross-pack; 15 hosts, 5 devices). Net +49.
  - The 17 that leave fail mate over OD at 2.11 to 2.62 (14 pairs; they read 0.86 to 1.64 against the slab) or the inner ratio at 1.24 to 1.36 (3 pairs). All 17 are on hosts whose slab OD is at least 1.5 times the barrel-face OD. Of the one twin that is `fit` today, none leaves.
  - Of the 103 pairs that G1 removed from the pre-G1 list on the 61 hosts that have a barrel end, **15 return** (same-pack only, 11 hosts). 88 stay `no_fit`: 69 on mate over OD below 0.85, 8 above 2.00, 11 on the inner ratio above 1.21.
  - Every changed pair is on a host whose slab OD is at least 1.2 times its barrel-face OD (84 of 85 at 1.5 or more). Hosts below 1.1 times do not move.
- Why B reads the face on every ring-evidence host and does not switch on a cut-off: across the 191 barrel-end hosts the slab-fill histogram has no host in the bin [0.75, 0.80) (74 below, 117 at or above 0.80), and no threshold on slab over face separates a class of hosts (the widest gap with at least 10 hosts each side is 1.94 times the next, under the 2 times the check was set at beforehand).
- Neither literal moves. `bore.od_ratio` stays [0.85, 2.00] and `bore.axis_offset_max_m` stays 5 mm. The rule's own margins (0.08 each side; 1.1 mm) would put the bounds at about [0.83, 1.73] and 2.3 mm. `attach-calibrate` only checks that no positive lies beyond a literal, so it passes with the looser values. Tightening is a separate calibration and is not proposed.

**Cost, stated plainly.** 17 listed pairs leave, because read against the barrel face the device's mate is more than 2.00 times the face (14 pairs) or its inner ring is more than 1.21 times it (3 pairs). The 17, and the 15 that return, were not viewed as renders before the ruling. A render cannot change Q1: the 17 sit outside bands calibrated from the positives, and if they looked right that would be a question for the bands, which move only by §4.2. They are the slice's **capture checkpoint**: all 17 leaving and all 15 returning pairs go on `attach-preview` sheets that the lead views before the slice merges.

**Not taken.** A, keep the slab. It needed E3.3 with exceptions for the 4 seats (6 observations), left 15 pre-G1 pairs refused by a face artefact and 51 cross-pack pairs unlisted, and kept `bore.od_ratio` red.

**Amended text.**
- §3.6, "`od_m` is twice the slab's outer radius around the slab's centre. `centre_su` is that centre." is replaced by:
  > For evidence (i), `od_m` and `centre_su` are read from the muzzle face of the stripped mesh (E3.2): `centre_su` is the mean of the face points' (s, u), and `od_m` is twice their largest distance from it. For evidence (ii) and (iii), `od_m` is twice the slab's outer radius around the slab's centre, and `centre_su` is that centre.
- §4.2: the `bore.od_ratio` row reads positives (11), max observed [0.91, 1.65], literal [0.85, 2.00], exceptions none. The `bore.axis_offset_max_m` row's observed value reads 1.2 mm. **E-G3 is retired** and its number is not reused.
- AC135: "The OD ratio lies in the band on 11 of 11." The survey's 0.93 to 1.92 is not reproduced; the measured range is recorded in its place.
- AC133 (a): the slide-face silencer clause and E-G3 go; see the twin table above.

**Fixtures** (synthetic, not built; AC135, in `test_weapons_e3_bore.py`). Each mount comes from the probe path (`geometry.muzzle_probe` to `mounts.bore_diameter`), never a hand-set `bore_source`.

| Fixture | Expected under B | Today |
|---|---|---|
| `slide_face()`: a 60 x 30 mm block ending flush at f = 0.200 m, with a tube (outer 22 mm, bore 15 mm) proud of it by 3 mm; device mate 24 mm | evidence (i); `od_m` 0.022 m (bounds 0.021 to 0.023); `centre_su` within 1 mm of the tube axis; ratio 1.09 | `od_m` about 0.067 (the block's corners). **Fails.** |
| plain 30 mm tube with its own ring, flush end | `od_m` 0.030 m, equal to the slab OD within 0.1 mm | same. **Passes today and cannot fail there**: it guards B against moving a round barrel. |
| an evidence-(ii) end: a bore ring inside the slab, one radius on the A0 face | `od_m` equals today's slab value exactly | same. **Guard, cannot fail today.** |

- **Breaks.**
  - B left out (today's code): `slide_face()` fails.
  - B applied to (ii) and (iii) as well: the third fixture fails, because no second radius is defined there.
  - B with the mount's own face (the unstripped probe) instead of the stripped one: see E3.2; its fixtures fail.
  - **AC133:** under B the slide-face silencer twin reads 0.9221, inside the band, and has no inner ring, so by the §3.6 table its pair is `fit` and E-G3 stops being an exception. Of the 3 muzzle twins, 2 flip `no_fit` to `fit` and 1 stays `fit`.

**The slice that builds E3.1 (with E3.2).**
- **Slice:** `E3.1`, branch `build/g1-e3-1`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-1`. **Lane:** Sonnet builder, or Codex Sol through dispatch. Never Opus. **Size:** M.
- **Base:** the lead-resolved `integ/attach` SHA after the E3.0 merge.
- **Owns (7):** `src/synty_inventory/weapons/fit_bore.py`, `fit_geometry.py`, `mounts.py`, `cli.py`, `calibrate.py`, and new `tests/test_weapons_e3_bore.py` and `tests/fixtures/weapons/e3_bore_meshes.py`. Plan §9.4 lists what each file takes.
- **Not owned and not edited:** the 7 existing tests that hand-set a `bore_source`, and the AC143 and AC145 literals.
- **ACs:** AC135 (fixtures), AC133 (a) step, AC137 rows. **Gate:** plan §0 rule 2, the capture checkpoint above, and the live row of plan §9.5.

### E3.2 Evidence (i) must describe the stripped barrel (§3.6 (i))

**Status: APPROVED, as written (W1).** It holds under either answer to Q1; under B it also decides which seats get the barrel-face OD.

**Today.**
- Evidence (i) is the mount's `bore_source == "ring"`. The mount comes from the A0 probe, which runs on the **unstripped** host.
- `fit.strip` removes located fused parts before `barrel_end` reads the slab. Only the 14 Military presets have located parts, so only presets can differ.
- On a preset with a fused muzzle device, `bore_source` describes the device. (i) can then be proved by the device's ring bore, whatever the barrel looks like.

**Evidence: three fused-device presets.** The face the mount probed (the device face) lies 34.0, 180.9 and 204.3 mm ahead of the barrel face.

| seat | face | OD ratio | inner ratio |
|---|---|---|---|
| S6 | device face | 0.8889 | none (8 points, no ring) |
| S6 | barrel face | 1.1355 | none |
| S7 | device face | 0.6090 | 0.4170 (below 0.47) |
| S7 | barrel face | 1.1318 | 0.7749 |
| S9 | device face | 0.7306 | 0.4482 (below 0.47) |
| S9 | barrel face | 1.3239 | 0.8122 |

On the device face 2 of 3 OD ratios and 2 of 3 inner ratios fall outside the live bands; on the barrel face all are inside. Today's `od_m` does not use the device face: it uses the slab on the stripped mesh, which reads 1.1355, 1.1318 and 0.4399. The device-face figures show why B cannot reuse the mount's face.

**Amended text (W1).** §3.6 (i) reads:
> (i) the mount's existing ring bore (A§4.2: a ring needs an inner and an outer radius, errata E2.6), **read on the same stripped mesh the end slab is taken from**. The bore probe for (i) runs on the host minus muzzle `occupied_by`, minus located parts, minus collision. If the stripped face has no ring, (i) does not hold and the end falls through to (ii), then (iii). A host or preset with no muzzle mount has no evidence (i).

Why W1: one stripped A0 face gives the ring flag, the centre and the OD in one place, so it composes with B; it keeps the evidence taxonomy of §3.6 unchanged; and it is identical by construction wherever nothing is stripped, which is every host except the 14 presets. **Rejected W2** (a mount's probe face within `end_slab_m` of the stripped forward extreme): on S7 and S9 the probe face is 180.9 and 204.3 mm ahead, so W2 demotes them to (ii) and (iii), which read the slab, and S9's slab is 64.1 mm against a 21.3 mm barrel face. W2 would undo B on that seat. It was not measured across hosts.

**Plumbing.** `fit_bore` may not import `geometry` or `mounts` (AC144, and the module rule in `fit_well.py`). The stripped probe therefore runs in `fit_geometry.host_features`, which already takes the host mesh as an injected callable, and its result (ring flag, face centre, outer radius) is passed to `barrel_end` as data **inside the mount dict**. The `barrel_end` signature is unchanged, and so is §3.11. The stored `barrel_end` record keeps its four keys. A mounts code digest joins the host-features cache key. This changes feature records on presets, so the live `fit_digest` moves (AC143's and AC145's synthetic literals do not: the synthetic worlds hold no fused device and no host with two magazine seats).

**Effect on `bore.circ_min`.**
- E1.1 measured `circ_min` with the probe ring withheld, so 4 positives went through (ii) (hull ratio 0.824 to 0.900). The live calibrate hands `barrel_end` the mount's `bore_source`, so one of those 4 takes (i) today, and the row reads **n 3** (S5, S6, S8; min 0.8236, max 0.9002, margin 0.0736 over the literal 0.75).
- Under W1 the stripped face of S6 has a ring, so S6 also moves from (ii) to (i), and the row reads **n 2** (S5 and S8, the two non-host presets, which have no mount and stay on (ii)). The minimum 0.8236 belongs to S8 and does not move. The row stays `ok`.
- A literal with no positives fails with `no_positives` (exit 6); the set cannot be empty here, but 2 is thin. The hull ratios of all 7 barrel-section positives stay 0.824 to 0.900. S10b re-reads the row and says which population it enforces. Nothing else is proposed.

**Fixtures** (red first; synthetic, not built; AC135). A host built from translated parts: a solid 32-sided round rod barrel (outer 24 mm, no bore ring) plus a catalogued device part (outer 40 mm, bore 12 mm) fused over its muzzle end and located by translation. The mount comes from the probe path.

| Fixture | Expected under W1 | Today |
|---|---|---|
| rod barrel plus fused device (above) | `barrel_end.evidence == "round_section"`; `od_m` 0.024 m (bounds 0.0235 to 0.0245) | the mount's ring is the device's, so evidence is `"ring"`. **Fails.** |
| the same host with no device | `round_section`, `od_m` 0.024 | same. **Guard, cannot fail today.** |
| a barrel with its own 30 mm / 16 mm ring, plus the same fused device | evidence `"ring"`; barrel-face values | `"ring"`. **Guard, cannot fail today**: it keeps W1 from over-reaching. |
| (with B) a block 60 x 30 mm behind the barrel end, plus a fused device ahead of it | `"ring"`; `od_m` is the barrel face, 0.022 | the slab, about 0.067. **Fails.** W2 would also fail it. |
| the mount says ring but the stripped face has none | falls through to (ii), then (iii); no error | cannot arise today. **New guard.** |

- **Breaks.** The unstripped probe (today): fixtures 1 and 4 fail. W2: fixture 4 fails. No guard on the missing-ring case: fixture 5 raises.

**Data: the 15 face-ring pairs (not a change).** 24 of the 103 G1-removed pairs are on 13 hosts whose barrel end is evidence (ii) (mount `bore_source` `face_extent`: one radius on the A0 face). 15 of those 24 are on 8 of the 13 hosts, where the slab OD is 1.57 to 3.21 times the A0 face's outer extent; the other 5 hosts sit at 0.97 to 1.02. B does not touch them. The reading is that no barrel is modelled on these hosts, so `no_fit` is correct and nothing is proposed. These 8 hosts were not viewed. The 15 are a different set from the 15 pairs that return under B, which are same-pack pairs on ring-evidence hosts.

### E3.3 One-pair calibration exceptions

**Status: WITHDRAWN.** E3.3 was conditional on A (Q1) or Option 1 (Q5). Tom took B and Option 2, so no exception is needed: E-G3 is retired (E3.1), and clamp has no exception (E3.8).
- No exception mechanism is built. `fit_geometry.exceptions` stays `[]`, and its validator, `overrides.py` and `overrides_digest` are unchanged (`overrides_digest` stays `0a2948d6cab4c77e`).
- E-G7, E-G8 and E-G9 are not entered.
- The slice `E3.3` is not laddered. If a later erratum needs a one-pair exception, the measurement that a `<slot>:<class>` key cannot name one pair stands (for example `optic:twin` carries 5 observations, 3 of them violating), and M3, pair entries in the id overrides file, was the preferred design.

### E3.4 The frame-derived fields of §3.3

**Status: APPROVED, as written.**

**Today.** §3.3 "Scope of the feature frame" lists `length_m`, tip, butt, grip and pivot points, `geometry.muzzle`, and the review reasons. AC146 says that on the feature-frame records "only frame-derived fields (§3.3) differ, and each is listed", and breaks on "a non-frame field changed on a feature-frame record". AC147 pins `geometry.axes`, `item_basis`, `length_m` and `geometry.muzzle` on the fixture.

**Evidence: what changes between a8c and a14 on the 3 frame-changed hosts.**
- On all 3: `geometry.axes` (forward, `forward_source`, up), `geometry.butt`, `item_basis`, `length_m`, `geometry.muzzle`, `pivot_frac`, `review.reasons`. These are in the §3.3 list or follow from it.
- Not in the list:
  - `hints.size_class` on 2 hosts (the nail gun and one SMG; medium to small). `inventory_cells` and `weight_class` do not move on the 3.
  - `geometry.support` and `geometry.support_r_m` on the 2 SMG hosts.
  - `flags` on 1 host: `['forward_by_fallback']` becomes `[]`. §3.3 step 5 already says a ring-confirmed sign clears a pre-vote flag.
  - `geometry.bounds` (size, min and max on the two lateral axes). The default export carries it in its one changed record (1 of 165 records).

**Amended text.** §3.3, "Scope of the feature frame", the list gains:
> - `geometry.bounds` (its per-axis size, min and max follow the frame's axes);
> - `geometry.support` and `geometry.support_r_m`;
> - `hints.size_class`, which is derived from `length_m` (it was measured to move on 2 of 3 hosts; `inventory_cells` and `weight_class` did not move, and no rule says they must not);
> - `flags`, only the `forward_by_fallback` flag of step 5.

AC146 and AC147 are unchanged; the list AC146 checks is the amended one. No AC in AC131 to AC149 names `hints.size_class`, support or `flags`, and no new number is used.

**Fixtures** (synthetic, not built; guard tests only). The Uzi-shaped fixture of AC147. The default-export diff lists exactly the amended set. A pre-vote `forward_by_fallback` is cleared when a ring confirms the sign. A host with no frame change differs in no field. The code needs no change: a test that checks the diff against §3.3 as it stood fails on `bounds`, `support`, `size_class` and `flags`; against the amended list it passes.
- **Breaks.** A list with `bounds` left out fails the diff. A vote that changes a non-listed field (for example `inventory_cells`) fails the guard.

**The slice that builds E3.4.** `E3.4`, branch `build/g1-e3-4`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-4`. Sonnet builder, or Codex Sol through dispatch. Never Opus. Size S. Owns 2 new files: `tests/test_weapons_e3_frame_fields.py`, `tests/fixtures/weapons/e3_frame_fields_world.py`. No `src/`. If the fixture cannot reproduce the old-frame side, the builder stops and reports (plan §9.4).

**E3.4a (correction, from the build).** The E3.4 builder found the Uzi-shaped fixture's `inventory_cells` move when the vote shortens `length_m` across a step, so the parenthesis above ("`inventory_cells` and `weight_class` did not move") holds on the live hosts but not as a rule. Both are derived from `length_m`. §3.3 lists them: "derived from `length_m`, may move when it crosses a step; 0 live hosts do, reported". The guard keeps the fixture's cells drift as its red and pins the live count of hosts whose cells or weight class move at 0, as its own literal. AC146 and AC147 are unchanged.

### E3.5 Sight slots on frame-changed hosts (AC139, AC149; §3.8)

**Status: APPROVED, as written.** The peer ruled this a correct Q-G4 consequence.

**Today.** AC139: a14's refused (slot, host) set contains a8c's, and "the only additions are the preset fill list (Q-G11, reported)". AC149: in `laser_light`, `sight_front` and `sight_rear`, "every entry is identical to a8c's".

**Evidence.**
- The refused sets are 528 (a8c) and 534 (a14); a8c's set is wholly inside a14's. The superset holds.
- The 6 additions are 2 preset fill-list additions (one muzzle on a rifle preset, one optic on a sniper preset), which AC139 already allows, and **4 sight refusals**: `sight_front` and `sight_rear` on each of the 2 SMG hosts, which change from `probe_unavailable` to `slot_disabled`.
- Cause. In the new frame (forward `+z`, `forward_source` `body`) the fused-front-post detector (`baked_sights.fused_post`, A§4.6 item 8 (D): bin 5 mm, rise 8 mm, width 10 to 30 mm, `min_pos` 0.6) finds a real post on both hosts: position 0.698, width 25 mm, rise 25.6 mm on one; position 0.946, width 25 mm, rise 23.0 mm on the other. In the old frame no post was found. The sight probe's separation was below `min_separation` (0.06) in both frames, so no probe seat existed either way.
- Pending effect: **9 pending pairs are removed**, one per part, all against one of the two hosts (cross-pack): 5 front-sight parts and 4 rear-sight parts. 0 listed pairs change. `laser_light` is identical.
- AC147 says 3 frame-changed hosts, one of them a tool. The tool (the nail gun) is refused by policy; its sight slots do not change.

**Amended text.**
- AC139: "The only additions are the preset fill list (Q-G11, reported) and, on a host whose frame the vote changed (§3.3), the sight slots that a fused front post refuses in the new frame. Each is reported with its host class."
- AC149: "In `laser_light`, `sight_front` and `sight_rear`, every entry is identical to a8c's, except `sight_front` and `sight_rear` on a frame-changed host, where the fused-post rule may move `probe_unavailable` to `slot_disabled` and remove the pending pairs of those slots. `laser_light` is identical everywhere."
- §3.8, the "Iron sights" bullet (the rule that AC139 item (2) tests, A§4.6 item 8 (C) and (D)): one sentence that the fused-post detector runs in the record's frame, so it can find a post on a frame-changed host that the build frame missed.

**Fixtures** (synthetic, not built). The Uzi-shaped fixture of AC147 with a 25 mm wide, 24 mm tall post at the muzzle end. In the build frame the post is not found (`probe_unavailable`); in the feature frame both sight slots read `slot_disabled`. The AC139 test lists exactly the preset fill additions plus the sight refusals of frame-changed hosts. This fixture fails against the AC139 text as it stood (an unlisted addition) and passes against the amended text. It is not confirmed that the synthetic geometry reproduces the old-frame miss; the slice stops and reports if it does not.
- **Breaks.** A clause that permits any new refusal on a frame-changed host (not only sight slots) lets a muzzle or optic regression through. A detector run in the build frame leaves the fixture at `probe_unavailable`.

**The slice that builds E3.5.** `E3.5`, branch `build/g1-e3-5`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-5`. Sonnet builder, or Codex Sol through dispatch. Never Opus. Size S. Owns 2 new files: `tests/test_weapons_e3_sight_clause.py`, `tests/fixtures/weapons/e3_sight_world.py`. No `src/`.

**E3.5a (correction, from the build).** The E3.5 builder's synthetic host with no fused post shows the other direction: a frame-changed host whose sight slots read `probe_unavailable` in the build frame may seat sights in the voted frame. AC149 gains that clause: "a frame-changed host whose sight slots read `probe_unavailable` in the build frame may seat sights in the voted frame when it has no fused post; the count of such hosts is reported (0 live)". The guard pins the live count at 0 as its own literal; the synthetic no-post host documents the mechanism. AC139 is unchanged (a seat is not a refusal).

### E3.6 The well reference when a second magazine is in the way (§3.7, §4.2)

**Status: APPROVED (Q3: F1).**

**Today.** §3.7 takes `u_rb` as the lowest host crossing on the vertical line through the reference's top-face centre, "using host-minus-magazine triangles". The code (`fit_geometry.host_features`, `well(node)`) removes only the reference node. The reference is the larger child. The entry section is cut at `u_rb - 0.002`.

**Evidence: the two-seat host** (a drum and a stick magazine; `occupied_by` holds both).
- The drum is the reference. With the host minus the drum only, the lowest crossing on the drum's top-face line is u = -0.1123 m, and the plane is at -0.1143. The drum spans -0.0998 to 0.0988, so the plane lies below it, meets no edge, and the section is empty. **No reference.**
- Removing the stick magazine too takes the crossings from 7 to 5 and the lowest to 0.0296, so the lowest crossing was the stick magazine's own surface, left in the host. The plane is then 0.0276, inside the drum, and the section is 0.1295 x 0.1591.
- The stick seat's stored reference (taken with the drum still in the host) is u_rb -0.0902, L 0.0986, W 0.0357. With every seat node removed it becomes u_rb 0.017, L 0.0941, W 0.0357.
- The host has 8 magazine pair rows: 6 non-twin parts, all `not_judged`; the drum twin, `not_judged`; and the standard-magazine twin, `unverified` (signal `well_entry`, section absent).
- The calibrate tool reads that standard twin at 0.000 from the per-node reference, while the directory leaves it `unverified`. The two disagree.
- §1.1 lists 16 twin magazines: 14 identical (0.000), 1 cross-family (0.105 in width), 1 drum with no section. Calibrate judges 15 (14 at 0.0, one at 0.1044) and leaves the drum unmeasured. The directory lists 14 as `fit` (13 at 0.0, one at 0.1044), the drum twin `not_judged`, and the standard twin `unverified`. So the survey's 14 identical includes that standard twin, and the directory does not.
- Reach: 7 of the 91 hosts with an authored magazine seat have no primary reference. F1 fixes **1** of them, the drum host. 4 have no crossing at all under either definition; 2 have crossings but the lowest lies outside the child's u-range. Of the 91, 88 have one seat and 3 have two; the other two multi-seat hosts have no crossing on the primary line under either definition, so F1 changes nothing there.

**The rule (F1).** §3.7 step 1 reads: "using the host with **every** magazine node of the mount removed (the reference and any other magazine seat)". It changes 1 host of 91. It gives the drum a reference, and the standard seat a shifted one (u_rb -0.0902 to 0.017, L 0.0986 to 0.0941). The `well.tol` row reads n 16 of 16 (the drum twin reads 0.000 by construction).

**Emulated effect.** The 8 pair rows move 7 `not_judged` to `no_fit` (the 6 non-twin parts and the drum twin) and 1 `unverified` to `fit` (the standard twin). Listed pairs change by 0; the pending list shrinks by 6. The drum twin's directory reading is 0.229 with axes swapped, against calibrate's 0.0000: that divergence is E3.12, and Q3 is not reopened by it.

**Not taken.** E-G7 (record the drum twin as not a `well.tol` positive): the standard twin would stay falsely `unverified`. Taking the first seat that yields a reference as the primary: it changes which magazine a host is judged against and was not measured.

**Amended text.**
- §3.7 step 1: "using the host triangles with **every** magazine node of the mount removed (the reference and any other magazine seat)".
- §4.2: the `well.tol` row's positives read "judged twin magazines (16 of 16 once E3.6 and E3.12 are in; 15 of 16 before)".
- AC133 (a), AC136: see the twin table and E3.12.
- **AC138** (zero listed magazine entries on a host with no well reference) is **not changed**. It reads 0 of 171 such hosts on the current build. Under F1 the drum host has a primary reference, so it leaves that population; F1 cannot add an entry to the control. Whether the control counts the drum host today is not traced.

**Fixtures** (synthetic, not built). A two-seat host: a large drum child and a stick child that overlap in (f, s), so that the line through the drum's top-face centre also crosses the stick. Today the plane lies outside the drum's u-range and the reference is `None`. Expected under F1: a reference whose section is the drum's cross-section, with `u_rb` above the stick's top and a plane inside the drum range. Bounds are literals in the test (for example the plane within the drum's u-range by at least 5 mm).
- **Fails today** (reference `None`). Guards that cannot fail today: a one-seat host, unchanged; a two-seat host whose seats do not overlap in (f, s), unchanged.
- **Breaks.** Removing only the reference node (today): the first fixture fails. Removing every node of the host: the guards fail.

**Data: the stepped taped-pair part** (an observation, no change). That magazine part has a width section that steps from 26.6 mm to 53.8 mm at 68.5 mm below its top. One plane cuts it on one side of the step or the other, so the verdict depends on how far the receiver-bottom plane lies below the part's top on each host. On the rifle references (about 0.0825 x 0.0297 m) the part reads 0.1044 when the plane is above the step and 0.8114 when it is below. The 0.1044 value on one rifle host sits 0.1 mm above the step. That is single-plane sensitivity; no margin is tuned here.

**The slice that builds E3.6.** `E3.6`, branch `build/g1-e3-6`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-6`. Sonnet builder, or Codex Sol through dispatch. Never Opus. Size S.
- **Base:** the merge of `E3.1` (shared files `fit_geometry.py` and `cli.py`).
- **Owns (5):** `src/synty_inventory/weapons/fit_geometry.py` (`well(node)`), `cli.py` (`well_pos`), `fit_well.py` (the docstring, E3.10 item 2), and new `tests/test_weapons_e3_well.py` and `tests/fixtures/weapons/e3_well_meshes.py`.
- **ACs:** AC133 (a) step, AC136, AC138 (guard). **Gate:** plan §0 rule 2 and the live row of plan §9.5.

### E3.7 Foot overlap with the run (§3.5, A4)

**Status: APPROVED (Q4: ii; Q7: rail slots only).** The rule is the peer's; the place is the A4 footprint and anchor; the proxy is the architect's and is gated by a population diff.

**Today.**
- The verdict is `fit` iff `foot_l <= run_len + overhang_max_m` (0.010) **and** `foot_w >= ratio_min x run width` (§3.5). `foot_length_m` and `foot_width_m` are the part's stored A4 anchor footprint, from the first rung of the ladder [0.004, 0.008, 0.016] m that is not a lip. A lip is a slab 0.001 to 0.0045 m wide whose next rung is at least 2.0 times wider. Both the live verdict and calibrate read the stored footprint. The anchor point is the foot slab's centre.
- The foot is therefore **part-intrinsic**. It does not know the run. A slab that is not under the run (a side hook) is read as the foot.

**Evidence: the side-hook preset scope.**
- The foot slab is 6.2 mm wide at the 4 mm and the 8 mm rungs, 116.2 mm long, and centred at s = +16.1 mm. 6.2 mm is over `lip_max` 4.5 mm, so the ladder stops at the 4 mm rung.
- The host's run is 16.4 mm wide, centred near s = 0, so it covers s = -8.2 to +8.2 mm. The foot slab covers about +13.0 to +19.2 mm. **It does not intersect the run.** The 16 mm rung is 33.3 mm wide and centred at +2.6 mm. It intersects the run.
- Ratio today: 6.2 / 16.4 = **0.378**. With the intersecting rung: 33.3 / 16.4 = **2.03**. The same misread puts the part's anchor at the side hook; the seat s is 0.0161.
- `clamp.ratio_min` had five violations: 4 observations of authored pads narrower than the rail on 2 seats (E3.8), and 1 foot-measurement artefact, this 0.378.
- Live effect: this part has 8 `rail_teeth` pairs. 7 are `no_fit` with the ratio as the only failing test (ratios 0.207 to 0.403 against runs 15.4 to 30.0 mm wide), and 1 is `fit` (against the 3.7 mm ribbed run of E3.9). With the intersecting rung all 8 are `fit`.
- Other small feet: three more parts have a stored foot width under 10.5 mm and `rail_teeth` pairs (one optic at 9.5 mm, one underbarrel foregrip at 0.0 mm, one bottle-shaped optic at 0.0 mm). They do **not** change under the proxy, and whether their small feet are real or the same misread is untraced.

**The rule.** A foot rung counts only if its slab intersects the run's s-extent. The rung that does not is a side feature, and the ladder moves to the next rung. Because the foot is part-intrinsic, the run is not known when the footprint is stored, so the stored rule uses a proxy: **the first rung whose slab holds the part's mid-line along `right`**, with the lip rule unchanged, and today's ladder when no rung holds it. The mid-line is the line through the centre of the part's whole extent along `right`; the draft left it implicit, and the population diff below is what confirms that this reading picks the same 2 parts.

**Population diff (the gate).** The proxy moves **5 parts** when applied to every slot (not "up to 4"). Under Q7 it applies to `optic` and `underbarrel` only:

| slot | foot width | foot length | anchor shift | pair verdicts that flip | moved? |
|---|---|---|---|---|---|
| optic (the side-hook part) | 6.2 to 33.3 mm | unchanged | 13.5 mm | 7 `no_fit` to `fit` | **yes** |
| underbarrel | 0.0 to 48.4 mm | unchanged | 0 | 2 `no_fit` to `fit` | **yes** |
| laser_light | 0.0 to 32.9 mm | 161.4 to 202.8 mm | 20.7 mm | none | no (Q7) |
| laser_light | 0.0 to 30.6 mm | unchanged | 5.5 mm | none | no (Q7) |
| magazine | 0.0 to 35.7 mm | 60.0 to 94.1 mm | 10.9 mm | none | no (Q7) |

The slice's gate is a script, outside the repo, that lists every library part whose stored `foot_width_m`, `foot_length_m` or anchor point changes against the base. The changed set must equal the two rows marked yes. Any other part is a finding, and the slice stops. If the proxy misses a part, the fallback is (iii), a per-pair re-measure at verdict time, which needs a separate amendment.

**Not taken.** (i), calibrate only: the 7 live pairs stay refused and Option 2 would derive 0.30 from the artefact. (iii), a per-pair re-measure: exact, but it needs the part mesh at verdict time, which the stored footprint was introduced to avoid. The mid-line rule on every slot (5 parts): the two laser anchors and the magazine anchor would move with no verdict behind them (Q7).

**Amended text.**
- §3.5, after the verdict table: "The foot used is the first rung of the A4 ladder whose slab holds the part's mid-line along `right`, on `optic` and `underbarrel` parts; a rung that lies off the mid-line is a side feature and is skipped. When no rung holds the mid-line, the A4 ladder applies unchanged. The mid-line stands in for 'the slab intersects the run', because the run is not known when the footprint is stored."
- A§3.4 step 1b (weapon_attachments.md) and AC107: the same clause, with the slot scope.
- AC134's "clamp ratio ≥ 1.0" reads as E3.8 settles. No AC in AC131 to AC149 names the foot slab or the ladder; AC134 is the nearest, and no new number is used.

**Fixtures** (red first; synthetic, not built). A part with a 33.3 mm base and a 6.2 mm side hook centred 16.1 mm off the mid-line, and a host with a 16.4 mm toothed run centred at s = 0.
- Expected: foot width at the base rung, ratio about 2.03 (bounds 2.0 to 2.1), anchor within 1 mm of the mid-line. Today: ratio 0.378, anchor 16.1 mm off. **Fails.**
- Guards that cannot fail today: a part whose 4 mm rung is under the run (unchanged); a part with a true narrow lip on the mid-line (ladder behaviour unchanged); a part with no rung holding the mid-line (falls back); a non-rail-slot part with a side hook keeps its footprint (red against an unscoped build).
- **Breaks.** The overlap test left out (today): the first fixture fails. An overlap test that skips every rung with a slab narrower than the run: the narrow-pad positives (0.9267 and 0.7692 in E3.8) would move, and the narrow-lip guard fails.

**The slice that builds E3.7.** `E3.7`, branch `build/g1-e3-7`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-7`. Sonnet builder, or Codex Sol through dispatch. Never Opus. Size S.
- **Base:** the lead-resolved SHA after the E3.0 merge. Wave A: file-disjoint from E3.1, E3.4, E3.5 and C3.
- **Owns (3):** `src/synty_inventory/weapons/attach.py` (`_foot_slab`), and new `tests/test_weapons_e3_foot.py` and `tests/fixtures/weapons/e3_foot_meshes.py`.
- **ACs:** AC134, AC107. **Gate:** plan §0 rule 2, the population diff above, and the live row of plan §9.5. **E3.8 bases on this slice's merge.**

### E3.8 `clamp.ratio_min` (§3.5, §4.1, §4.2)

**Status: APPROVED (Q5: Option 2 at 0.69), conditional on E3.7.**

**Today.** The §4.2 row read: positives are the toothed optic positives (16), min ratio 1.63, margin "physical bound", literal 1.0, and the reason a one-sided physical bound: a clamp narrower than the rail cannot grip it. The calibrate tool reads 26 observations over 19 distinct seats (16 optic and 3 underbarrel) against the spec's 16. The spec's `n` counts seats; the tool counts observations (the `seats` field is C1).

**Evidence.**
- Sorted ratios of the 26: 0.378 (the preset scope of E3.7; real base 2.03), **0.7692** (a baked scope and its twin, foot 17.0 mm against a 22.1 mm run), **0.9267** (two twins on one host, foot 27.8 mm against a 30.0 mm run), then 1.1389 up to 4.0467.
- Violations against 1.0: 5. They are **4 observations on 2 authored seats whose lowest pads are narrower than the rail** (0.9267 twice, 0.7692 twice; real geometry, not clamps) **and 1 foot-measurement artefact** (0.378, E3.7).
- The spec's "min ratio 1.63" is not what the positives give. The corrected 16 optic seats have min **0.7692**, after E3.7. On the stored figures, the "physical bound" reasoning is contradicted by 2 authored seats: their feet are 7% and 23% narrower than the rail's measured top width.
- **The rail side was traced.** On both runs the rail is a square-cornered block with straight walls, cut at 5 stations each. The code's width (`fit_rails._side_width`: the top face within 1 mm of the median tooth top) matches the section to 0.03 mm, at 29.94 and 22.04 mm. There is no chamfer, and no flare where a clamp closes. With the wall width the ratios are 0.9285 and 0.7713. The rail is not over-read.
- **The part side was traced.** Each part was sliced at every 1 mm station along the run, at the rail top, 1 to 3 mm above it, 1 mm below it, and at the foot's mid-height. **Neither part has jaws at any height**: 0 stations with two material intervals, 0 straddling stations. On the 0.7692 seat, the stored foot is the bottom face of three pads, 17 to 18 mm wide, resting on the slot floors within 0.02 mm, with 2.5 mm of margin to each wall; above them a solid V-shaped body widens to 25.8 to 27.7 mm at the rail top. On the 0.9267 seat, the stored foot is the bottom face of a solid slab 14 to 18 mm inside the rail block (about 61% of the part's volume below the rail top is inside the host solid); the baked scope on the same host, at 1.55, has the same structure with a 46.5 mm slab. That is how the assembly is authored.
- So these are not narrow clamps, nor the E3.7 artefact. The ratio `foot_w` / run width measures how much of the rail width the part's lowest pads cover, not whether a clamp closes round the rail. The "physical bound" reason does not describe this quantity, and Option 2 withdraws it. E3.7's mid-line proxy keeps both rungs, correctly, since the pads lie on the run.
- `rail_teeth` verdicts by (slot, value): optic 416 `fit` and 204 `no_fit`; underbarrel 65 `fit` and 43 `no_fit`. Of the 247 `no_fit` pairs with the `rail_teeth` signal, **125 fail on the ratio alone** (the length test passes).

**The rule (Option 2).** A lower bound sits at the min minus a stated margin. The two ratio rows (`bore.od_ratio`, `bore.inner_ratio`; §4.2) use 0.08. Min 0.7692, at two decimals 0.77, minus 0.08 = **0.69**. It is **conditional on E3.7**: the 0.7692 minimum exists only after the 0.378 artefact is corrected, and without E3.7 the same rule gives 0.38 - 0.08 = 0.30, which would admit the artefact. Option 2 is therefore not built before E3.7 has merged.

**Effect on pairs.** Pairs flipping `no_fit` to `fit`, by the literal, out of the 125:

| literal | 0.9267 | 0.85 | 0.77 | 0.75 | 0.70 | **0.69** | 0.50 | 0 |
|---|---|---|---|---|---|---|---|---|
| pairs flipping | 26 | 40 | 51 | 61 | 72 | **79** | 103 | 125 |

- At 0.69, the 79 verdicts are 31 same-pack and 48 cross-pack, on 38 hosts and 20 parts; 63 are optic and 16 are underbarrel. As directory listings, **75 listed pairs enter**: 30 same-pack and 45 cross-pack. The other 4 flip without being listed. None leaves.
- Ratio histogram of the 125: [0, 0.3) 16; [0.3, 0.5) 6; [0.5, 0.69) 24; [0.69, 0.77) 28; [0.77, 0.93) 29; [0.93, 1.0) 22. The 7 pairs of E3.7's artefact part all sit below 0.69, so E3.7 and E3.8 act on disjoint pairs.
- Lowering the bound widens listings only on real rails: all 79 sit on runs 10.7 to 30.0 mm wide. None is on the two decorative patterns of E3.9 (3.7 mm and 46.2 mm).

**Not taken.** Option 1, keep 1.0 and record two exceptions (E-G8, E-G9). It needed E3.3, the premise "a narrow clamp" no longer holds (no jaws on either part), and it would leave the 125 ratio-only pairs refused.

**Amended text.**
- §4.1: `clamp: {overhang_max_m: 0.010, ratio_min: 0.69}`. The shipped `weapon_rules.yaml` takes the same one number.
- §3.5: the `Wp ≥ clamp_ratio_min × R.width_m` literal reads 0.69.
- §4.2: the `clamp.ratio_min` row reads positives (16 optic seats; 26 observations over 19 seats), min observed 0.7692, margin 0.08, literal 0.69, exceptions none. The one-sided "physical bound" reason is withdrawn and replaced by the calibration reasoning above: a lower bound at the observed minimum less the margin of the two ratio rows. The `clamp.overhang_max_m` row reads max observed -21.2 mm (E3.9 (f)).
- AC134 reads "clamp ratio ≥ the literal" in place of "≥ 1.0". AC137's test gains a case.

**Fixtures** (synthetic, not built; AC137). Calibrate on synthetic toothed positives with ratios 0.80, 1.5, 3.0. The test carries 0.80 as its own literal minimum; it never reads the rules value.
- Shipped rules (0.69): the `clamp.ratio_min` row is `ok`. **Fails today:** the shipped 1.0 lies above the 0.80 positive, so the row is `exceeded`. The whole-run exit also depends on the bore rows (E3.1), so the test reads this row, not the exit code.
- Rules overridden to 0.85 in the test: exit 6, `clamp.ratio_min` named. It passes today as well, so it is a guard that the check is not skipped.
- No positives: exit 6, `no_positives`. Guard.
- **Breaks.** A test whose expected minimum is read from the rules file loosens with the rule. A 0.69 taken without E3.7: the artefact is the min and the literal reads 0.30.

**The slice that builds E3.8.** `E3.8`, branch `build/g1-e3-8`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-8`. Sonnet builder, or Codex Sol through dispatch. Never Opus. Size S.
- **Base:** the merge of `E3.7` (the literal is conditional on it). It does not wait for E3.1 or E3.6.
- **Owns (6):** `src/synty_inventory/data/weapon_rules.yaml` (the one number; `rules.py` needs no edit), `tests/test_weapons_g1_rules.py`, `tests/test_weapons_g1_export.py`, `tests/test_weapons_g1_seats.py`, `tests/test_weapons_w8p_rules.py`, and new `tests/test_weapons_e3_clamp.py`. Exactly 5 existing tests go red on the yaml edit, and they are the five pins in plan §9.5.
- **ACs:** AC134, AC137. **Gate:** plan §0 rule 2 and the live row of plan §9.5 (`attach-calibrate` exit 0).

### E3.9 Data for the record (no change; Q6 answered)

Counts, classes and ranges only. No literal moves.

**(a) The 0.864 SMG design note.** A rifle-class magazine visibly fills the rifle-sized opening of the SMG-class preset and is refused at 0.8642, because §3.7 judges against the authored stick magazine's section (0.0464 x 0.0275 m), not against the opening. The rifle-class magazines read 0.8577 to 0.8642 on that host. This is the spec working as written. If the opening should decide, §3.7's reference would have to change, which E3 does not propose.

**(b) E2-Q1: the flat seat is not on the highest run** (the S10 report that E2-Q1's answer called for).
- 124 hosts take a flat seat: pistol 37, rifle 32, shotgun 20, revolver 13, SMG 11, heavy gun 5, LMG 4, sniper 2. On **77** of them the flat seat is not on the highest qualifying run (gap above 0).
- **30 hosts have a gap above 5 mm**: heavy gun 3, LMG 4, pistol 3, revolver 1, rifle 12, shotgun 2, SMG 3, sniper 2. The gaps run 5.3 to 543.7 mm; 20 hosts are above 10 mm, 12 above 20 mm, 7 above 50 mm.
- Of the 30, the highest run lies rearward of the chosen run in 21 and forward in 9. The chosen run is longer than the highest run in all 30 (median chosen length 0.2715 m; the highest runs are 62 to 329 mm). Of the 77 hosts with a gap, 43 have a highest run that overlaps the chosen run in f.
- Close-ups of a pistol (gap 6.1 mm), a box rifle (gap 14.4 mm, the case E2-Q1 describes) and an LMG (gap 56.7 mm) were drawn in scratch. E2-Q1's answer was "no change, and S10 reports". This is the report. Preferring the highest run would be a spec edit; none is proposed.

**(c) Inner rings: 7 against the survey's 6.** The 7 placements are on 5 distinct devices (3 baked, 1 placement each; 2 preset, 2 each). The survey said 6 placements of 4 devices. Today's range is 0.2699 to 1.1315 (baked 0.5508 to 0.8783, preset 0.2699 to 1.1315), with 1 violation, the device-face artefact; under the barrel face (B) it is 0.5581 to 1.1315, margins 0.0881 below and 0.0785 above the literal [0.47, 1.21]. Both are judged on all 7. The `bore.inner_ratio` row's `n` (6) is the survey's population, and the row is left as it stands.

**(d) Two decorative toothed patterns, and the narrow runs.**
- A ribbed barrel shroud on a vintage SMG: a top run 160.1 mm long, 8 teeth, pitch 20 mm, **3.7 mm** wide. A hexagonal jacket on a heavy MG: a bottom run 152 mm long, 4 teeth, pitch 38 mm, **46.2 mm** wide.
- The positives' rail top widths are 10.7 to 30.0 mm (one of the 16 is the 10.7 mm run on an SMG-class host; the rest are 16.4 to 30.0).
- Of the 48 toothed runs on hosts, by width: under 5 mm, 3 runs (the ribbed pattern above, and two underbarrel runs of 4.4 mm and 210.3 mm length on a pair of sci-fi plasma hosts, status untraced); 5 to 10.5 mm, none; 10.5 to 15 mm, 1; 15 to 20 mm, 14; 20 to 25 mm, 21; 25 to 31 mm, 8; over 31 mm, 1 (the 46.2 mm jacket).
- Pairs judged by `rail_teeth` on the three runs under 5 mm: 24 `fit` and 8 `no_fit`. The 46.2 mm jacket has no `rail_teeth` pairs, since no part has a foot that wide.
- **Q6 answer: no floor now.** The data separates the 3.7 and 4.4 mm runs from the 10.7 mm positive, and a floor anywhere between 4.4 and 10.7 mm would split them, removing up to 24 `fit` pairs. None is set. **The 24 `fit` pairs on the three sub-5 mm runs go on the S11 capture list** (plan §4). A floor becomes a later erratum only if those captures show the pairs wrong, and §4.2 then derives it from the 10.7 mm positive.

**(e) The survey's 45 toothed hosts reproduce under neither recount.** The survey has 45 hosts on top and 14 on the bottom (AC134). The strip recount gives 52 top (43 shared with the survey, 9 live-only, 2 survey-only) and 16 bottom (13 shared, 3 live-only, 1 survey-only). The no-strip recount gives 47 top (43 shared, 4 live-only, 2 survey-only) and 16 bottom (the same 13, 3, 1). Neither gives 45. AC134's "45 hosts on top and 14 on the bottom" stays unmatched and is reported by class; the survey's population is unspecified.

**(f) The overhang.** The spec row said max observed 8 mm, margin 2 mm, literal 10 mm. The rule's own quantity (foot length minus run length) is at most **-21.2 mm** on the positives (preset max -0.0212, baked -0.0216), a margin of 0.0312 m against the 10 mm literal. The survey's 8 mm was a positional offset, not this quantity. **No literal moves.** The row reads "max observed -21.2 mm, margin 31.2 mm, literal 10 mm". AC137's overhang case (0.007) runs on a synthetic oracle whose overhang is a test literal, so it is unaffected.

### E3.10 Carried to the next slices

So nothing is lost. None is a decision.
1. **The calibrate `seats` field** (slice `C1`). The calibrate rows count observations (`n` 26 for the clamp rows) while the spec counts seats (16). Add a `seats` count of distinct seats to each row, so the two can be compared without arithmetic. A seat is the distinct (host, slot, seat node), so a twin shares its baked sibling's seat.
2. **The `fit_well.py:6` docstring** (rides `E3.6`). It says `u_rb` is the lowest host crossing "above the reference magazine's top-face centre". The code takes the lowest crossing anywhere on the vertical line, and §3.7 says "on the vertical line". The docstring should say "on". On the drum host the lowest crossing is below the whole drum.
3. **The `preview.py` sheet-cell map fix** (slice `C3`). `preview.py` writes a sheet-cell map whose order differs from the rendered sheet (seen on S10's sheet 2). S11 cites no sheet-2 cell position until it is fixed. Red first on the saved map against the rendered order.
4. **The labels wiring before S12.** The labels source (AC141, AC142) is wired into `eval.py`, `spotcheck.py` and `cli.py`, and the labels store's count is reconciled against the 449 the spec cites (the S10 first run could not reproduce 449), before any `--draw`. The plan keeps this before S12; it is not an E3 slice and owns other files.

### E3.11 Questions and answers

Each was Tom's. The answers are his ruling quoted in the status.
- **E3-Q1. How is the barrel-end outer diameter read?** A keep the slab; B read the barrel face for ring evidence. **Answer: B** (E3.1).
- **E3-Q2. How is a one-pair calibration exception named?** M1 class key plus archetype; M2 pair entries with ids in the rules file; M3 pair entries in the overrides file. Needed only under A or Option 1. **Answer: M3, withdrawn under B plus Option 2** (E3.3).
- **E3-Q3. The well reference on the two-seat host.** F1 fix the plane; E-G7 record the drum twin as not a positive. **Answer: F1** (E3.6).
- **E3-Q4. Where does the foot-overlap rule live?** (i) calibrate only; (ii) the A4 footprint and anchor; (iii) a per-pair re-measure. **Answer: (ii) with the population-diff gate** (E3.7).
- **E3-Q5. `clamp.ratio_min`.** 1 keep 1.0 and add two exceptions; 2 set the literal by §4.2. **Answer: Option 2 at 0.69** (E3.8).
- **E3-Q6. A minimum top width for a toothed run?** **Answer: no floor now** (E3.9).
- **E3-Q7. Which slots does the mid-line proxy apply to?** Rail slots only (2 parts move), or all four slots (5 parts move). **Answer: rail slots only** (E3.7).
- **E3.12.** **Accepted as a correction.**

### E3.12 Twin forward correction runs after the well section is cut (directory build order)

**Status: APPROVED, a correction, not a choice.** Traced by the architect (the drum twin's transposed section). Exposed by F1, not caused by it.

**The defect.**
- The directory cuts every part's well section in `_apply_fit_parts` (`directory.py:873`) with the anchor as stored at that point. `apply_compat` runs next (`directory.py:874`) and its first act, `twin_forward` (`compat.py:623`), rewrites a twin part's forward axis and swaps its footprint length and width (`compat.py:604-607`). The prior that picked the pre-correction forward is the longer horizontal extent (`attach.py:179`). Calibrate places the part from the finished directory (`cli.py:567`), so it uses the corrected anchor. Host basis, seat frame and plane are the same on both routes.
- Population: one magazine part (the drum) is on the divergent path: 84 section rows at base, 87 under F1. All are reproduced from the pre-correction anchor (87 of 87). The post-correction re-cut gives L and W exchanged on 86 of 87 (the other row is square). `twin_forward` changes 5 parts in all slots (4 optic, 1 magazine); only the magazine one feeds a stored section.
- Verdicts: at base no judged twin differs between directory and calibrate. Under F1 exactly 1 judged pair differs: the drum twin, 0.2286 `no_fit` against 0.0000. The drum's 14 non-twin judged pairs are `no_fit` either way.

**The fix (the slice's design).** The well section is cut with the anchor as `twin_forward` leaves it: either the order at `directory.py:873-874` changes, or the anchor `_apply_fit_parts` reads at `directory.py:527` is the corrected one. Either moves the stored drum sections, which are part records in `fit_digest` (`directory.py:575`). The `well|` cache key carries the pre-correction anchor (`directory.py:554`), so the fix also changes cache keys. The slice picks the smaller of the two edits; the order of authority is that a twin's forward is corrected first.

**Fixture** (red first, synthetic). A part wider across than along (prior forward +x) that twins a baked child with equal per-axis extents; its stored well section must equal the post-correction re-cut (deviation 0 against the child's own section). Today it reads L and W exchanged. **Fails.**

**Not determined (the slice measures and reports):** whether the 6 other magazine parts whose stored forward is along x (none a twin) are placed correctly; the partial-build and cache-hit behaviour (inferred, not run); whether AC143 or AC145 move.

**What it moves.**
- AC133 (a): the twin count reaches **38 of 38** (INFERRED from the 0.0000 re-cut; confirmed at S10b). The standard twin on the drum host is no longer `unverified` (E3.6), and the drum twin becomes judged and `fit`.
- AC136: the drum twin reads 0.0000 in the directory as it does in calibrate.
- `fit_digest` moves again on the live library (the stored drum sections are part records). AC143 and AC145 are measured in the slice and **re-pinned in the slice if they move**.

**The slice that builds E3.12.** `E3.12`, branch `build/g1-e3-12`, worktree `D:/game_assets_library/tools/inventoryagent-wt-g1-e3-12`. Sonnet builder, or Codex Sol through dispatch. Never Opus. Size S.
- **Base:** the merge of `E3.6`.
- **Owns:** `src/synty_inventory/weapons/directory.py` and its test file only (a new `tests/test_weapons_e3_well_order.py`).
- **Gate:** plan §0 rule 2, plus: the 87 stored drum rows reproduce except the drum twin, which reads 0.0000; the 6 x-forward magazine parts are listed before and after (counts and deviations only); a cache-hit run on a partial build reproduces the full build; AC143 and AC145 are measured and re-pinned in the slice if they move (plan §9.4 says how the manifest covers the two pin lines).

### E3.13 Versions, digests and consumers

- **No version bump.** `WEAPON_ATTACH_VERSION` stays 14 and `WEAPON_GEOMETRY_VERSION` stays 6: a14 is local-only until S11 and S12, and E3.7 stores new footprints and anchors on 2 parts at the same version. A bump to 15 would re-pin 19 test files and the package constant, and is its own sweep slice after the last functional merge, if ordered.
- **`attach_rules_digest`** moves once, in E3.8: `a981c4c7c27972e8` to `2fa41961e3c387b0` (the w8d-world one `d53ba2ef587b5ee9` to `6f49a2ac6efa8120`). `rules_digest` (`7b9829af37328fe7`) and `overrides_digest` (`0a2948d6cab4c77e`) do not move.
- **`fit_digest`** moves on the live library in E3.1 and E3.6 (and again in E3.12) and does not in E3.7 and E3.8. AC143 (`9e88713e0a47d5d0`), AC145 (`e4245a0e01a13252`) and the w8d-world value (`d8a5f85413f90698`) are predicted unchanged by E3.1, E3.6, E3.7 and E3.8; E3.12 may move them and re-pins in-slice.
- **Caches miss on their own.** Editing `fit_bore.py`, `fit_geometry.py` or `fit_well.py` moves `FIT_CODE_DIGESTS`; editing `attach.py` moves the attach code digest; E3.1 adds a mounts code digest to the host-features key.
- **Consumers are unaffected.** No mount `source` or `feature` value changes, no key is added to the export, and `geometry_version` is unchanged. sit_armory 0.3.0 and sit_weapons 0.4.0 need no change. The listing changes (E3.1, E3.6, E3.8) are data, seen on the games' next re-export.

### E3.14 Gate

**PASS.**
- Every approved item has its amended text, a rule, fixtures that say which fail on today's code and which are guards that cannot, breaks, and a slice with owned files, a base and a gate. E3.3 is recorded as withdrawn.
- Every live figure is measured in scratch with the method recorded, and no data is committed. Departures from the earlier text are listed at the top, and the measurement is used.
- What is **not measured** and bears on the build: the renders of the 17 leaving and 15 returning pairs (the E3.1 capture checkpoint); W2 across hosts and a census of the 14 presets' evidence under W1; the directory effect of E3.12 on AC143 and AC145 (measured in the slice); whether the three other small-foot parts and the 4.4 mm underbarrel runs are real or artefacts; the old-frame mechanism of the E3.4 and E3.5 fixtures; the other 14 optic positives, the 3 underbarrel positives and the side-hook scope were not sliced for jaws; the seat-identity rule of C1 beyond the ruling in plan §9.6; host children measured by the A4 function (E3.7's diff covers library parts; any host child whose footprint or point moves is a finding).
- In force: Tom approved E3 on 2026-10-28, as the status records. Slices build on the plan's §9, after the E3.0 merge.

### E3.15 §4.2 observed-cell corrections (docs)

**Status: RULED by the peer, 2026-10-28, from the S10b read-back (`c5f0b95`); reported to Tom as corrections he can object to.** These slices were first named E3.13 and E3.14 in the note to Tom. They were renumbered E3.15 and E3.16 because E3.13 and E3.14 are already merged headings above, so any objection to "E3.13" or "E3.14" in that note maps here.

Every change is to an observed column (max observed, margin, positives count). No literal, band or rule moves (plan §0 rule 7).
- **`rail.zone`.** Observed [0.22, 0.80] becomes [0.1992, 0.7823], and the margins 0.07 rear / 0.05 front become 0.0492 rear / 0.0677 front. This is an update, not a mistake: the old margins were right for the old cell and reverse against the live range. The literal [0.15, 0.85] is unchanged.
- **`depth` (review list).** Observed "0 to −23.9 mm" becomes −23.9 to −7.0 mm. The band [−26, +3] mm is unchanged; its +3 mm end stays `contact.dead_m` and is not re-derived from the gap above the observed range. Cause of the shallow end moving from 0 to −7.0: the S10a oracle rewrite (merge `f5af916`, "attach-calibrate measures the spec's positive populations"), which dropped the magazine baked positives, counted the glass sheets and brake as not-positives and added the non-host presets. The row went from n 27 (baked 12, preset 10, twin 5) to n 23 (baked 5, preset 13, twin 5), and the shallow baked cells left. No E3 slice moved it: every saved calibrate output from S10a through S10b reads the same row. The old cell predates S10a.
- **`bore.inner_ratio`.** Observed [0.55, 1.13] becomes [0.5581, 1.1315] (four places, like the other ratio rows), and the margin "0.08 each side" becomes 0.0881 below / 0.0785 above. The band [0.47, 1.21] is unchanged.
- **`bore.inner_ratio` positives.** "6 placements" becomes 7 (7 observations over 7 seats). Cause: the same S10a population change took the row from n 5 (baked 3, preset 2) to n 7 (baked 3, preset 4). Inside E3 the count stays 7. The one E3 move on this row is the low end, 0.2699 to 0.5581, at E3.1 (the barrel-face read); the high end 1.1315 is unchanged. The "6" matches no saved output and is an earlier count.
- **`bore.circ_min`.** The row text already says 2 (evidence (ii)), as live does. `attach-calibrate`'s `SPEC_N` said 4 (the E1-era count); E3.16 sets it to 2.

### E3.16 `attach-calibrate` spec counts and the Seats docstring (code)

**Status: RULED by the peer, 2026-10-28.** A docs-in-code slice. It changes no verdict and no stored record.
- **`SPEC_N`** (`calibrate.py`): `bore.circ_min` goes from 4 to 2 and `bore.inner_ratio` from 6 to 7, matching §4.2 after E3.15. The comment above it says §4.2 has no circ_min row; §4.2 has the errata E1.1 row, and the comment says so.
- **The Seats docstring** (`calibrate.py`, the Seats paragraph): a preset's seat is its placed seat point clustered at 1 mm per (host, slot), not "its own fused node". A baked child's seat is its own node, and a twin shares the baked child's node. It cites C1 and plan §9.6 ruling 5.
- **Red first:** a test that the calibrate rows report `spec_n` 2 for `bore.circ_min` and 7 for `bore.inner_ratio`. It is red on the E3.15 merge and green after. The one existing pin, `test_weapons_g1_calibrate.py::test_every_row_prints_the_spec_count_beside_its_own`, holds 4 and 6 and is updated in the slice.
- **Slice:** base is the E3.15 merge tip, in one worktree. The write-once manifest is `src/synty_inventory/weapons/calibrate.py` and `tests/test_weapons_g1_calibrate.py`.
- **Gate:** plan §0 rule 2; `fit_digest`, `attach_rules_digest` and the w8d-world digest do not move and are stated; a full suite run; and a calibrate read-back on the tip with a named copy-catalog config and its rc, whose row values equal S10b's except `spec_n` on the two rows.

### E3.17 `well.tol` positives stated in seats (docs, docstrings)

**Status: APPROVED by Tom, 2026-10-28 (decision 4 (a)), verbatim: "Approve the S11 decision set at the defaults: 1 ratified, 2 (i), 4 (a), 5 (a), 6 (b), 3 at its four defaults."**
It changes no literal, band, verdict, stored record, `SPEC_N` entry or test pin.
- **Cause (S11 finding 10, trace T-well).**
  - The §4.2 row said 16, an observation count; `SPEC_N` said 15, the pre-E3.6 numerator copied at S10a (`91e818f`).
  - Live, `n` is 16 and `seats` is 15. Both numbers are right in their own unit.
  - No code compares `spec_n` with `n` or `seats`: `calibrate.py:263` prints the three side by side.
  - Two docstrings in `calibrate.py` disagreed on the unit: the Populations paragraph read `spec_n` against `n`, and the Seats paragraph said §4.2 states seats.
- **The §4.2 row.** The positives cell states 15 seats and 16 observations.
- **`SPEC_N`.** `well.tol` stays 15, now read as seats. The pins that hold it are unchanged.
- **The docstrings.** The Populations paragraph says §4.2 states its counts as seats, `spec_n` sits beside `seats`, and `n` counts observations. The Seats paragraph keeps "spec 4.2 states `n` as seats" reworded to the same reading. Both cite E3.17.
