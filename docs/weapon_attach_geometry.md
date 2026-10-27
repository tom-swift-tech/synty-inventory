# Spec: geometry fit gate for weapon attachments (amendment G1 to weapon_attachments.md)

**Written:** 2026-10-27, by the architect. **Status:** **APPROVED** (Tom, 2026-10-27), with Q-G4 adopted and every other open question at its default. The build follows [weapon_attach_geometry_plan.md](weapon_attach_geometry_plan.md).
**Tom's decision (2026-10-27, verbatim):** "Yes. Replace the label gate: positives come from pack presets and Synty's assembled references, fit is decided by rail, bore and magazine-well geometry, and my labels are a one-off spot check only. Spec it first."
**Tom's approval (2026-10-27, verbatim):** "Approve the geometry spec. Take Q-G4: adopt the feature frame for the record too, geometry_version 5 to 6. Other open questions at their defaults. Start the build plan." The decisions are recorded in §8. Q-G4 is folded through this document: §1.1 (frame), §3.3, §3.6, §3.9, §3.11, §4.1, §4.2, §4.4, §4.5, §4.6, §4.7, §5 (INV-19 amended, INV-24, INV-28), §6 (AC145, AC146, AC147), §8 and §9.
**Branch:** `spec/attach-geom`, cut from `integ/attach` at `0e2637e` (a8c: `WEAPON_ATTACH_VERSION` 13, `WEAPON_GEOMETRY_VERSION` 5). Approval and plan on `plan/attach-geom`, cut from `integ/attach` at `5f106fa`. G1 builds `WEAPON_ATTACH_VERSION` 14 and `WEAPON_GEOMETRY_VERSION` 6.
**Parents:** [weapon_attachments.md](weapon_attachments.md) ("the attachment spec"; a bare `A§N` points into it) and [weapon_directory.md](weapon_directory.md) (`DS§N`). A bare `§N` points into this document. Everything in the parents still holds except what §3.8 retires and what §4.6 amends (INV-19 and AC77 for the feature-frame records, AC80(c) for the four slots).
**Errata:** [weapon_attach_geometry_errata.md](weapon_attach_geometry_errata.md). E1 (round barrel end, one landing test, strip scope) was APPROVED by Tom on 2026-10-27 at the defaults (AC131 163), and is in force.
**Errata E2:** APPROVED by Tom on 2026-10-27, and in force. His reply, "Use your default s", is read as the peer's recommendations (the errata's E2 status records the reading): the located-magazine clause of §3.7 step 1 is dropped (E2-Q3), and a ring bore needs two radii (E2-Q2).
**Consumers:** `sit_armory` 0.3.0 and `sit_weapons` 0.4.0 (sit-capabilities). §4.6 shows that neither one needs to change, with Q-G4 included.

> The public-repo rule (INV-1, INV-17) applies in full. This document carries algorithms, literals, classes, counts and ranges only. It has no per-asset measurements and no GLB node names. It names asset ids only where the attachment spec already names them. Every measured file (calibration report, fit cache, captures) lives under the catalogs folder or a scratch folder and is never committed. Fixtures are synthetic.

## 1. Problem statement

The attachment directory decides "does part P fit host H" with label-era rules: name-token families, a kind × archetype affinity table, span and bore bonuses, a size tolerance against the baked child, and a gun-class name rule. Several of their literals were fitted to Tom's hand labels. Draw #6 scored AC80(c) as not met (default view, draw alone: weighted precision 0.783, recall 0.274). Most missing fits sit in the far-refusal strata: 764 pairs, of which 8 of the 16 drawn were real fits. The tests refuse widely, not only near their cuts, because a name or a family says nothing about whether a scope clamps on a rail.

This amendment replaces that gate, for the four slots whose fit is a physical mating, with measured geometry. Positives come from Synty's own assemblies.

| slot | the mating feature | host side | part side |
|---|---|---|---|
| `optic` | top rail | toothed run (pitch, length, height, width), or an authored reference seat | foot length, clamp width |
| `underbarrel` | bottom rail | toothed run on the underside, or an authored reference seat | foot length, clamp width |
| `muzzle` | barrel end | barrel-end OD and axis | device mating OD, inner bore, axis |
| `magazine` | magazine well | entry section of the authored magazine at the receiver-bottom plane | entry section of the candidate at the same plane |

The setting gate, Tom's standing refusals and every other policy rule stay as they are (§3.8). Policy decides *whether* a slot may take anything. Geometry decides *which* parts fit it. Hand labels stop being gate data: they get one 32-pair spot check, reported as a number (§3.10), and the 449 existing labels become a descriptive comparison only.

### 1.1 Feasibility survey (2026-10-27, a8c directory, 257 eligible hosts; scratch scripts, read-only, aggregate)

**Oracle (positives).**
- *Presets.* All 14 Military presets (10 are hosts; the two Complex and two Heavy presets are not) are exact translation-only assemblies of Military Mod parts. A grid locator places 164 parts at hit fraction 1.0:
  - optic 14 (10 distinct parts at 12 positions), magazine 15, muzzle 4, underbarrel 4, laser_light 3, sight_front 6, other parts 118;
  - plus a muzzle brake and an underbarrel grenade launcher that have no attachment block (§8 Q-G9).
  - Barrel parts match at 0.935 only, which is sub-mesh aliasing, so they are rejected at hit < 1.0.
  - Preset optics are fused into the host mesh, so the build must remove a located part's triangles before measuring the host.
- *Twins (A§5.1).* 38 pairs: optic 18 (on 17 hosts), magazine 16 (on 14), muzzle 3, underbarrel 1.
- *Baked children.*
  - optic: 35 bodies on 32 hosts, plus 13 glass sheets;
  - magazine: 103 on 100 hosts;
  - muzzle: 6 on 6;
  - underbarrel: 7 on 4;
  - laser: 1.
  - Synty also bakes optics on 5 launcher hosts. Policy refuses optics on launchers, so these 5 are calibration-only positives.
- *Human-readable references.* No Synty store render exists locally (§8 Q-G8). The HUD packs ship weapon icons that show assembled guns:
  - `D:/game_assets_library/converted/extracted/INTERFACE_Military_Combat_HUD/Assets/Synty/InterfaceMilitaryCombatHUD/Sprites/Icons_Weapons/` (216 PNG)
  - `.../InterfaceMilitaryCombatHUD/Sprites/Icons_WeaponMods/` (149 PNG)
  - `D:/game_assets_library/converted/extracted/INTERFACE_Apocalypse_HUD/Assets/Synty/InterfaceApocalypseHUD/Sprites/Icons_Weapons/` (140)
  - `D:/game_assets_library/converted/extracted/INTERFACE_SciFi_Soldier_HUD/Assets/Synty/InterfaceSciFiSoldierHUD/Sprites/Icons_Weapons/` (492)
  - They match 87 of 173 distinct host names and 92 of 153 part names, and every preset has a side icon.
  - They are referenced by path only and never copied into the repo.

**Rails.**
- *Top teeth.* 45 hosts carry a run of at least 4 teeth inside 0.15 to 0.85 of the length (51 at 3 teeth).
  - By class: rifle 16, smg 11, sniper 8, shotgun 4, lmg 2, pistol 2, revolver 1, launcher 1.
  - Pitch p5/p25/p50/p75/p95: 17.0/22.5/23.5/27.0/32.0 mm. Tooth amplitude p5/p50/p95: 2.9/5.6/9.0 mm. Run length p5/p50/p95: 66.5/198/321 mm.
  - Current optic mount on these 45 hosts: 29 have none (`no_child_no_probe`), 8 are `child_node`, 8 are refused by policy.
- *Bottom teeth.* 14 hosts at 4 teeth (18 at 3). 12 of them have no underbarrel seat today; 2 are refused by policy.
- *Untoothed fallbacks.* Both candidates measured fail to discriminate:
  - A flat top run (5 mm band, 15 mm closing window, 60 mm or longer) exists on 201 of the 212 untoothed hosts, including 19 of 21 launchers.
  - A raised ridge (8 to 30 mm wide, 3 mm proud of both sides) fires on 184 of 257 hosts, including all 15 revolvers, 13 of 21 launchers and 8 of 11 heavy guns. It finds barrels and top straps as readily as rails.
  - So neither may list a pair (§3.4).
- *Toothed optic positives (16: presets, children and twins on toothed hosts).*
  - The contact interval lies inside the run, with at most 8 mm of overhang.
  - The clamp underside is 1.63 to 5.1 times the rail top width.
  - The underside sits 0 to 23.9 mm below the tooth tops; jaws wrap the rail.
  - 13 of the 14 preset optic placements sit on a toothed run. The exception is a scope on a canted adapter on a non-host preset.
  - The optic contact centre lies at 0.22 to 0.80 of the butt-to-muzzle length.
- *Twin optic hosts (17).* 4 are toothed and 13 untoothed.
  - On 10 of the 13 untoothed hosts, a flat run covers the twin's contact.
  - The other 3 are stepped seats (11 to 13 mm steps). All 3 are on the A§5.4 known-defect list of authored twin defects.
- *Underbarrel positives.* 3 of the 4 preset placements sit on bottom teeth. The underbarrel twin (a foregrip on a launcher) is off the centreline. 5 of the 7 baked underbarrel children are splayed bipod legs.

**Bore (muzzle).**
- *Positives.* 11: 5 preset placements (one is the brake) and 6 baked devices (3 of them twins).
  - The device axis lies 0 to 3.9 mm off the barrel-end centre, with 0° tilt to host forward.
  - Device mating OD / barrel-end OD is 0.93 to 1.92 on 10 of 11.
  - The exception is a pistol's silencer twin, which sits on a slide face with no modelled barrel.
  - 4 devices carry an inner bore ring (6 placements), giving inner bore / barrel OD of 0.55 to 1.13.
  - The barrel enters the device by 0 to 90 mm.
- *Barrel-end census.* This was measured in the **build frame**, on host minus children, **before strip**. 233 of 257 hosts have a barrel end, by any of: the existing ring bore, a front-face ring, or a round end section (roundness ≥ 0.8, OD ≤ 60 mm).
  - 24 have none: launcher 8, rifle 6, flamethrower 3, utility 2, pistol 2, sniper 1, smg 1, shotgun 1.
  - 10 of a8c's 200 probe muzzle seats have no barrel end. They carry 8 listed muzzle entries on 3 hosts: a preset whose fused brake is the end, a sniper with neither ring nor round end, and one of the two Uzi-type SMG hosts, whose seat sits at the magazine bottom (the frame fault below).
  - Under §3.6's definition (feature frame, after strip), about 4 hosts are expected to move from "none" to "has end", giving about 237 and 20:
    - the two Uzi-type SMG hosts and one nail gun, each with a bore ring at its feature-frame forward end (15–18 mm across the three);
    - the brake preset, whose stripped brake exposes the barrel. That preset's muzzle is then refused by the fill rule (Q-G11), not by geometry.

    A higher count at build is confirmation, not a failure.

**Well (magazine).**
- *Wells are not modelled.* 13 of 15 preset placements and 67 of 103 baked magazines sit in a solid receiver, both 3 mm and 8 mm below the magazine top. Only 5 read as open at both depths.
  - Magazine penetration into the host, p5/p50/p95: 10/61/237 mm.
  - So the host side is not a hole. It is the authored magazine's entry section (§3.7).
- *Entry-section detector on the 16 twin magazines.*
  - 14 read identical sections (0.000).
  - One cross-family Military twin (a B-family magazine on an A-family preset) reads 0.044 in length and 0.105 in width.
  - One drum has no section.
  - One cross-pack twin, a Military magazine baked into a city-pack rifle, reads 0.000 (§8 Q-G1).
- *Military matrix (15 wells × 17 magazines).*
  - Same-family rifle magazines differ by at most 0.09.
  - The A and B families differ by 0.10 to 0.13, in width.
  - The SMG and heavy magazines are at least 0.38 off every other well.
- *Coverage.* All 62 listed same-pack magazine entries sit on the 91 `child_node` hosts. The 166 hosts without a magazine mount list none today, so nothing is lost there.

**Frame.**
- 13 hosts carry `axes_unexpected`.
- The body axis changes the forward axis on 3 of them: the two Uzi-type SMG hosts and one nail gun (a tool, refused by policy). The magazine is longer than the barrel, so the bounding box picks the magazine as forward.
  - The body axis is the long axis of the host minus its named slot children (the survey dropped the children the a8c directory names; the build drops the children the child vocabulary matches, §3.3 step 1, and re-measures the count).
  - On each of the 3, a 15–18 mm bore ring sits at exactly one end of the body axis, and the other end has no ring of 25 mm or less.
  - The other 254 hosts are unchanged.
- *Rejected votes.*
  - "Magazine below the bore": 9 of 103 baked magazines sit at or above the bore line (top or side feeds).
  - "Barrel end at one end" as a sign vote: 144 hosts read barrel-like at both ends under the loose test.
  - Rails cannot vote, because they are searched along forward.

**Baseline (a8c), listed / pending.**
- Listed:
  - magazine: twin 16, same 62;
  - muzzle: twin 3, same 177, cross 29;
  - optic: twin 18, same 18, cross 42;
  - underbarrel: twin 1, same 8, cross 4;
  - sight_front: same 2; sight_rear: same 10.
- Pending:
  - optic: cross 1,098;
  - underbarrel: cross 618, same 259;
  - magazine: cross 593;
  - laser: cross 235;
  - sights: about 110 each.
- Mount sources:
  - muzzle: `probe` 200, `none` 57;
  - optic: `child_node` 26, `none` 231 (160 `no_child_no_probe`, 71 `slot_disabled`);
  - magazine: `child_node` 91, `none` 166;
  - underbarrel: `child_node` 3, the rest `none`.

**Preset fills.**
- On the 10 preset hosts, the locator finds 2 slots filled by a fused part that a8c leaves open:
  - one fused silencer, on a muzzle that lists silencers today;
  - one fused scope, on an optic slot that is `none` today.
- a8c's filled-slot rule reads baked children only, so it cannot see fused parts (§3.8, Q-G11).

## 2. Non-goals

- `laser_light`, `sight_front` and `sight_rear` keep their current rules, including family and affinity. A later amendment may give them detectors.
- No change to policy (§3.8): the setting gate, host classes, host names, filled hosts, `suppressor_never`, baked sights, the cross-pack magazine routing (A8-1) and per-id overrides.
- No change to anchors (A§3.4), twin detection (A1), settle to contact (A§5.4), muzzle setback (A6-2) or the placement formula (C-21). This gate decides *fit*. Placement stays as specced (§3.9).
- No tuning to draw #6 or to any label. No literal may cite a label count as its justification.
- No new part classification. Parts the classifier misses (§8 Q-G9) stay missed.
- No runtime change in sit_armory or sit_weapons.
- No committed measurement. Store renders, if they ever appear, are referenced by URL or path and never copied.

## 3. Interfaces and algorithms

All lengths are in metres, in the host's scaled GLB space, in the feature frame of §3.3, which is the record's frame (Q-G4). Coordinates are written `(f, s, u)` = (forward, side, up). Every literal below is a key of `attachment_rules.fit_geometry` (§4.1), except the two frame-vote constants of §3.3, which are `geometry.py` code (Q-G4).

### 3.1 Pipeline (per part P of slot X, per eligible host H)

1. **Policy.** Unchanged and run first. A refused slot is `none` / `slot_disabled`. Its pairs are neither listed nor pending, as today.
2. **Override.** An `override` entry (A§6.1) is listed as today. Geometry is not consulted.
3. **Twin.** A `twin` pair (A1) is listed as today. Its geometry verdict is still computed, for calibration only (AC133).
4. **Geometry verdict** `V(P, H, X)`, one of four values:

   | V | meaning | listing |
   |---|---|---|
   | `fit` | the detectors measured a mating feature and the part matches it within tolerance | `compatible_hosts`, tier `same_pack_fit` or `cross_pack_fit` by pack relation, then A8-1 (a cross-pack magazine is moved to `pending_hosts`) |
   | `unverified` | a seat exists, but no detector can confirm the mating (flat seat, drum, unmeasured anchor) | `pending_hosts` |
   | `no_fit` | the mating feature is measured and the part does not match, or the host has no such feature | not listed, not pending |
   | `not_judged` | the host has no seat and no detector feature in this slot (mount `none`) | `pending_hosts`, as today (D-8) |

5. **Order and score.**
   - Entries keep the sort `(tier rank, -score, host)`.
   - `score` is the tier base (`override` 1.0, `twin` 0.95, `same_pack_fit` 0.7, `cross_pack_fit` 0.4). The span and bore bonuses are retired (§3.8).
   - `signals` names the geometry evidence: `rail_teeth`, `seat_ref`, `rail_flat`, `barrel_ring`, `barrel_round`, `well_entry`, `drum`, `frame_body`.

`compat.candidate()` calls `fit_geometry.verdict()` for the four slots in place of the label-era test sequence. The other three slots take the old path unchanged.

### 3.2 Oracle

The oracle is the set of authored assemblies. It calibrates every literal (§4.2) and is the reference that AC133 to AC136 check.

- **Presets.** `locate_by_translation(host, part)` finds each candidate part (same pack, `role == "part"`) inside a preset host's mesh by translation only.
  - Key the host vertices into a 0.5 mm grid, with a 27-neighbour tolerance.
  - Take candidate translations from the part's lexicographically smallest vertex.
  - Prefilter with 24 sampled vertices.
  - Accept at hit fraction **== 1.0** (every part vertex lands on a host vertex). Merge placements within 2 mm.
  - The located triangles are removed from the host mesh before any host detector runs on it ("strip": a host triangle whose three vertices all lie on a located part).
  - The locator runs only on hosts whose name hits `attach_filled_hosts`, against parts of the same pack.
- **Twins.** The A1 twin pairs, seated on the child they match.
- **Baked children.** The children of `mounts.<slot>.occupied_by`, measured with the anchor function of A§3.4. A child is a positive for the detector of its slot even where policy refuses the slot (the launcher optics). It is never listed there.
- **Human-readable references.** The HUD icon paths of §1.1, resolved per id by name (`ICON_SM_Wep_<name>[_<pack>][_Side|_Clean].png`) for the spot-check sheet (§3.10). They are not inputs to any detector.

### 3.3 Feature frame (answers the coordinator's frame question)

Should detectors derive forward and up from the gun's own features? **Yes, for the axis.** The bounding box is the wrong authority when a child is longer than the barrel. On the two Uzi-type SMG hosts the magazine is, so the muzzle seat lands at the magazine bottom. **No, for the sign.** No feature votes the sign reliably (§1.1). Where the axis agrees, the sign stays the build's, including `forward_override`. Where the axis changes (step 3), the single end ring that confirms the change also gives the sign, and `forward_override` still wins (step 5).

`geometry.frame_vote(...) -> FrameVote` (record geometry, `geometry.py`, §3.11):

1. **Body axis.** Run `_pick_long_axis` (unchanged, `_TIE` 0.05) on the host mesh minus its slot children. The slot children are the mesh nodes the child vocabulary matches (`attachment_rules.child_tokens` and `child_never`, through `mounts.mesh_nodes` and `mounts.matching_slots`), before policy and before mount overrides.
   - It cannot use `occupied_by`, because `build_mounts` makes `occupied_by` *from* the axes. The vocabulary match is axis-free.
   - It does not drop located preset parts. The locator is attachment geometry (§3.2) and the record frame does not depend on it.
   - **Non-obvious dependency.** The record frame now reads two `attachment_rules` tables. `rules_digest` excludes `attachment_rules`, so an edit to `child_tokens` or `child_never` can move a record's frame without moving `rules_digest`. Three things catch it: the tables are already inputs of the eligible-host cache fingerprint (`ct`, `cn`), `attach_rules_digest` moves, and the build reports every record whose frame changed (§4.7).
2. **Agree.** If the body axis equals the build's forward axis, the frame is the build's frame. That holds for 254 of the 257 hosts.
3. **Differ, confirmed.** The body axis may differ from the build's forward axis. The confirmation tests each end of the body axis for a bore ring of diameter ≤ `_FRAME_BORE_MAX_M` (0.025). The ring estimator is §3.6 (ii) on the `_FRAME_END_SLAB_M` (0.010) end slab, the one the survey measured. It lives in `mount_probe.py` (`end_ring_d`), and the bore detector reuses it. `mount_probe.py` imports only `numpy`, so `geometry.py`, `mounts.py` and the detectors can all import it without an import cycle. It is already a cache input of every eligible host (`pd`). If exactly one end carries such a ring, the feature frame is set as follows:
   - forward is the body axis, signed toward that end;
   - up is the build's up rule (`axes.up` logic, unchanged) applied to the new forward;
   - `axes.forward_source` is `"body"` (a free string, §4.4), and every pair judged on the host carries signal `frame_body` (§3.1 step 5).

   This holds for 3 hosts today.
4. **Differ, unconfirmed.** If the body axis differs and the ring test fails (no end, or both ends), the host has a **frame conflict**:
   - the record keeps the build's frame;
   - every *detector* seat on it (rail, flat, barrel end, and a well reference outside the child frame) is withheld, making the slot `none` / `probe_unavailable`;
   - its pairs are `not_judged` and therefore pending;
   - the calibration report lists the host;
   - an id override resolves it (A§6.1: the new `frame_axis`, §4.5, names the axis).

   This fires on 0 hosts today.
5. **Order of authority.** `frame_axis` (when present) or a confirmed body axis decides the forward *axis*. Then `forward_override` applies to the *sign* on that axis, exactly as today against the measured axis. An override whose axis differs is ignored with the existing warning. None of the 3 hosts carries a `forward` override today.
   - **A `frame_axis` with no single end ring** (none, or both) has no measured sign. The vote takes `+` and sets `FrameVote.sign_by_fallback` (§3.11). The record then carries the flag `forward_by_fallback` (DS§3.4.5), so the guessed sign shows on the review page. The id's `forward` override sets the sign on that axis and clears the flag, as it does today.
   - A sign confirmed by one end ring is measured, so on a changed host the vote clears a pre-vote `forward_by_fallback`.
   - Classification reads neither. Pass 2 keeps the pre-vote flag ("Classification does not read the vote", below), so the vote moves no confidence.
   - `sign_by_fallback` is an additive S1 deviation, accepted by the peer on 2026-10-27.

The vote runs only on eligible hosts (`mounts.eligible`), whatever `with_mounts` says, so the default export and the `--attachments` export carry the same record frame. Every other record is measured exactly as in geometry version 5.

**Classification does not read the vote.** The build's pass 2 (`directory._measure_record`, `geometry.pass2_inputs`) keeps reading the pre-vote values: `long_axis`, `length_m` and `axes_unexpected` as the bounding-box frame gives them. `geometry.long_axis` on the record stays the bounding-box axis, because it is a measurement of the mesh, not of the frame. Otherwise a record whose kind is guessed from its long axis could alternate: it turns ranged, becomes eligible, the vote moves its axis, and it turns back. So the vote never feeds `kind`, `archetype` or `hold_class`, and the loop's convergence argument stands.

**Scope of the feature frame (Q-G4 adopted).** The feature frame is the record's frame. On the 3 hosts, `geometry.axes`, `item_basis` and every value derived from the frame follow it:
- `length_m`, tip, butt, grip and pivot points, and `geometry.muzzle`;
- the review reasons judged from them (`axes_unexpected` may drop).

The mounts are then built in that frame as before, so the muzzle seat (A0 probe) equals `geometry.muzzle` and **AC67 holds unchanged**. `WEAPON_GEOMETRY_VERSION` goes 5 → 6, and INV-19 is amended for these records (§4.6). The build reports every changed field of every record. A changed `archetype`, `genre` or `hold_class` is a finding, because it raises ARM_W06 in locked games (§4.6).

### 3.4 Rail detector (optic: top; underbarrel: bottom)

`rail_runs(mesh_fsu, side) -> list[RailRun]`, on the host mesh minus the slot's `occupied_by`, minus located parts, minus collision nodes.

1. **Profile.**
   - Take the vertices within `rail_window_m` (0.010) of the centreline.
   - The centreline side coordinate `s0` is the muzzle seat's side coordinate when the muzzle has a barrel end; otherwise it is the midpoint of the side extent.
   - Bin along f at `rail_bin_m` (0.0005).
   - A bin's height is the highest u for `top`, or the lowest for `bottom`, measured outward from the receiver.
2. **Teeth.**
   - A tooth is a local extreme that stands `tooth_amp_min_m` (0.0008) or more above both neighbouring troughs. Extremes closer than `tooth_merge_m` (0.0025) merge.
   - A **toothed run** is a sequence of `tooth_min_count` (4) or more teeth that meets three conditions:
     - successive pitches lie in [`pitch_min_m`, `pitch_max_m`] = [0.005, 0.040];
     - their coefficient of variation is ≤ `pitch_cv_max` (0.25);
     - tooth tops lie within `tooth_h_tol_m` (0.0015) of the run's median top.
   - The run must overlap the zone [`zone_lo`, `zone_hi`] = [0.15, 0.85] of the host's f extent, measured from the butt.
   - `RailRun` records `f0`, `f1`, `top_u` (the median tooth top), pitch, amplitude, tooth count, and `width_m`. `width_m` is the side extent of the run's top within 1 mm below `top_u`.
3. **Flat seat (untoothed fallback, top only).**
   - On a host with no toothed top run, `flat_seat` finds the longest run that meets three conditions:
     - its bins lie within `flat_band_m` (0.005) of their running top;
     - gaps up to `flat_close_m` (0.015) are bridged;
     - its length is ≥ `flat_min_m` (0.060) inside the zone.
   - It **places a seat but lists nothing**. Pairs on it are `unverified` (§1.1: it fires on 201 of 212 untoothed hosts and on 19 of 21 launchers). The raised-ridge variant is not specified, for the same reason.
4. **Seat.**
   - If the slot already has a `child_node` or `override` seat, that seat stays: the authored reference wins, and the run is used only for the length check.
   - Otherwise a toothed run, or for optic a flat seat, writes a mount:
     - `source: "probe"` (an existing value, §4.6), `feature: "rail_teeth"` or `"rail_flat"`, confidence 0.5, review reason `mount_estimated`;
     - `point` at the centre of the rearmost `min(run length, default_seat_len_m)` (0.20) of the run, at `top_u`;
     - `forward` = host forward; `up` = +u (top) or −u (bottom);
     - `span_m` = run length; `span_source: "probe"`.
   - **Sight seats.** When the host has a probe `sight_front` seat, the run used for the seat and for `span_m` is clipped to end `sight_clear_m` (0.010) behind it. A§4.6 gate 6(c) then holds: an optic span never covers a front sight, which `hides_slots` cannot hide. A rear sight inside the span is handled by the existing `hides_slots` rule.
   - The seat position along the rail is a preference (§3.9).

### 3.5 Optic and underbarrel verdict

Part side: `footprint.foot_length_m` (`Lp`) and `footprint.foot_width_m` (`Wp`), both existing. A part whose anchor is unmeasured gets `unverified`.

| host feature in slot X | V |
|---|---|
| policy refused | (step 1, not reached) |
| toothed run R (and no frame conflict) | `fit` iff `Lp ≤ len(R) + overhang_max_m` (0.010) **and** `Wp ≥ clamp_ratio_min × R.width_m` (1.0). Otherwise `no_fit`. Signal `rail_teeth`. |
| authored reference seat (`child_node`/`override`) and no toothed run | `fit` iff `Lp ≤ ref_len + overhang_max_m`, where `ref_len` is the flat run containing the reference contact (§3.4 step 3 parameters), or the reference child's own `foot_length_m` when no flat run covers it (stepped seat). Otherwise `no_fit`. Signal `seat_ref`. |
| flat seat only | `unverified`, signal `rail_flat` |
| no seat, no feature | `not_judged` |

Width is not checked on a `seat_ref` host. No calibration exists for an untoothed clamp, and an uncalibrated literal is not added. When the slot's mount has more than one seat (`seats`, A1), the check runs against the seat the pair uses.

### 3.6 Bore detector and muzzle verdict

`barrel_end(host_mesh_fsu) -> BarrelEnd | None`. The mesh is the host minus muzzle `occupied_by`, minus located parts, minus collision. The end slab is the vertices within `end_slab_m` (0.010) of the forward extreme. A barrel end exists if any of these holds:

- (i) the mount's existing ring bore (A§4.2: `bore_source == "ring"`; a ring needs an inner and an outer radius, errata E2.6);
- (ii) a front-face ring: the innermost 1 mm radial bin holding ≥ 6 vertices, inside 0.75 of the slab's outer radius (`mount_probe.end_ring_d`, shared with the frame vote of §3.3);
- (iii) a round end section: `min(extent_s, extent_u) / max(...)` ≥ `round_min` (0.8) and OD ≤ `barrel_od_max_m` (0.060).

`od_m` is twice the slab's outer radius around the slab's centre. `centre_su` is that centre. The **bore axis** is host forward through `centre_su`.

Part side: `footprint.mate_d_m` (existing; the mating ring's outer diameter, A§13.5 item 7), plus an inner bore ring on the mating face when one exists (`device_inner_d`, the same ring estimator).

| host | V |
|---|---|
| no barrel end (24 hosts today) | `no_fit` |
| barrel end and mate_d_m known | `fit` iff `od_ratio_lo ≤ mate_d_m / od_m ≤ od_ratio_hi` ([0.85, 2.00]) **and**, when the device has an inner ring, `inner_ratio_lo ≤ device_inner_d / od_m ≤ inner_ratio_hi` ([0.47, 1.21]). Otherwise `no_fit`. Signal `barrel_ring` (i or ii) or `barrel_round` (iii). |
| barrel end, mate_d_m null | `unverified` |

Axis offset and tilt are not per-pair tests. A candidate is placed on the detected axis by construction. They are **detector calibration** checks on the 11 positives: the authored device axis lies within `axis_offset_max_m` (0.005) of `centre_su` and within `axis_tilt_max_deg` (2) of host forward (AC135).

The muzzle seat itself still comes from the A0 probe, the same single algorithm as before (AC67, AC84). `barrel_end` gates the slot and supplies `od_m`; it never moves the seat. On the feature-frame hosts of §3.3 step 3, the A0 probe runs in the feature frame, which is the record's frame (Q-G4), so the seat still equals `geometry.muzzle`. Feature `barrel_ring` / `barrel_round`.

### 3.7 Well reference and magazine verdict

The receiver is solid where the magazine enters (§1.1), so the host side is the **authored magazine's entry section**.

1. **Reference.**
   - The host needs an authored magazine: the `child_node` magazine seat (the larger child when there are several, A§4.2). Without one the host has no well reference, and its magazine pairs are `not_judged`, which leaves the slot `none` as today. A fused magazine on a preset gives no reference (errata E2-Q3 dropped "or a located magazine on a preset").
   - The **receiver-bottom plane** `u_rb` is the lowest host crossing on the vertical line through the reference's top-face centre, using host-minus-magazine triangles and `crossings()`, a line-triangle intersection with a 1e-5 m offset off edges.
   - The **entry section** `(L_ref, W_ref)` is the f and s extent of the reference magazine's triangles cut by the plane `u = u_rb − entry_depth_m` (0.002).
2. **Candidate.**
   - Place P with the existing placement (C-21) at the reference seat. For a twin pair the twin's own seat is used.
   - Cut it at the same plane to get `(L_p, W_p)`.
   - A part whose section is empty at that plane, which covers drums and parts that do not reach the plane, is `unverified` with signal `drum`.
3. **Verdict.** `fit` iff `|L_p − L_ref| / L_ref ≤ well_tol` **and** `|W_p − W_ref| / W_ref ≤ well_tol`, with `well_tol` = 0.15. Otherwise `no_fit`. Signal `well_entry`.

A cross-pack `fit` magazine still goes to `pending_hosts` (A8-1, unchanged). The build reports how many cross-pack pairs the detector judges `fit`, as data for Tom's decision (§8 Q-G1). `drum_min_m` (0.11) keeps its role in kind classification only.

### 3.8 Policy kept, rules retired

**Kept unchanged (policy, applied in step 1):**
- the setting gate `attach_genre_by_pack`;
- `attach_host_class` with `attach_class_never`:
  - launcher refuses muzzle and optic;
  - tool and `fixed_heavy` (minigun) refuse every slot;
- `attach_host_never`;
- `suppressor_never` (no suppressor on any shotgun, every tier but override);
- `attach_filled_hosts` [preset] with `attach_filled_open` [magazine];
- `baked_sights` rules A to F (A§4.6 items 7 to 9);
- per-id overrides, including the `Sniper_Heavy_01` muzzle ruling (A6-6 iii, §8 Q-G6);
- A8-1 `cross_pack_unverified_slots` [magazine];
- the settle cap `cap_m` (A6).

Tom's standing refusals map onto these rules as shipped (AC139):
- **"A built-in part fills its slot."** On an `attach_filled_hosts` (preset) host, a slot filled by a baked child refuses, except the magazine. So does a slot filled by a located fused part (below).
- **Iron sights.** A baked sight refuses both sight slots on any host (`baked_sights` A and C).
- **Optics.** A glass-only host refuses `optic` (`baked_sights` B).
- **Not a refusal.** On any other host, a baked optic body or muzzle device stays **replaceable**: it is hidden through `occupied_by` when a part mounts (A§4.3). That is not a refusal, and this amendment does not make it one.

**Policy input, additive (§8 Q-G11).** On a preset host, a slot filled by a located fused part counts as filled for `attach_filled_hosts`, exactly as a baked child does. This implements "a built-in optic, sights or silencer fills its slot" for parts Synty fused into the preset mesh. It can only add refusals: 2 slots today.

**Retired for `optic`, `muzzle`, `underbarrel` and `magazine` (they stay in force for the other three slots):**
- `family_overlap`;
- `attach_affinity` (the kind × archetype table);
- the `fit_span` and `fit_bore` bonus and penalty;
- `cross_pack_size_tol` (R-a, label-fitted);
- the gun-class name rule (R-b);
- `fit_span_min` 0.75 (A6-3);
- the tokenless waiver (A7-4) with `family_free_slots` and `tokenless_family_free_slots`.

`bore_mismatch` was measured and never adopted (A§13.5 item 7), so nothing retires there. The keys stay in `weapon_rules.yaml` for the remaining slots. The validator rejects a retired key that names one of the four slots.

### 3.9 Placement note ("Fits, but placed wrong")

fit-v1 separates *fits* from *placed wrong*. This gate decides only the first. What it leaves as placement, and the measured state of each:

1. **Along the rail.**
   - The default seat sits at the centre of the rearmost 0.20 m of the run.
   - Against the authored positions, presets fall within ±30 mm on 10 of 12 placements (the worst is the canted adapter at about 56 mm), and toothed children fall 9 to 86 mm off.
   - Position on a rail is a preference, not a fit. A game overlay moves it (D-5).
2. **Height.**
   - Settle to contact (A§5.4) is unchanged.
   - Authored clamps sit 0 to 23.9 mm *below* the tooth tops because their jaws wrap the rail, and settle puts the contact face on the outer surface. So a jawed mount can read a few millimetres high.
   - The build reports seat depth against the tooth tops for every `rail_teeth` pair. Pairs outside [`depth_lo_m`, `depth_hi_m`] = [−0.026, +0.003] are listed in the calibration report. This is a review list, not a gate.
3. **Muzzle.** The part sits on the detected axis. Setback (A6-2) is unchanged. Barrels enter authored devices by 0 to 90 mm.
4. **Magazine.** This is a mesh swap at the reference child's seat (W8g). The entry plane is a check, not a placement.
5. **Frame faults.** With Q-G4 adopted, the 3 feature-frame hosts get correct mounts and a corrected record frame (hold frame, `item_basis`, muzzle), so the gun is held barrel-forward in the game too (the k15 finding, A§13.10).
6. **Stepped seats.** The 3 untoothed twin hosts with stepped seats remain the A§5.4 known defects.

A spot-check answer "Fits, but placed wrong" counts as a fit, and its count is reported beside the fit number (§3.10).

### 3.10 Spot check (one-off) and labels (descriptive)

- **Draw.** `weapons attach-spotcheck --draw` runs once, after the first geometry build.
  - It draws **32 listed pairs**: 8 per slot (optic, muzzle, magazine, underbarrel), split between `same_pack_fit` and `cross_pack_fit` in proportion to that slot's listed counts, with at least 2 per non-empty tier.
  - It excludes `twin` and `override` entries (authored) and every pair already in the 449 labels.
  - Order: ascending `sha256("spotcheck-1|" + part + "|" + host)`.
  - It writes `src/synty_inventory/data/weapon_attach_spotcheck.json` (ids only; §4.4), and refuses to run if that file exists.
- **View.** One contact sheet is made with `attach-preview`. Each pair sits beside its host's and part's HUD icon by path where one exists. Tom answers each pair once under fit-v1. The answers go into the same file as booleans plus a `placed_wrong` flag.
- **Score.** `weapons attach-spotcheck --score` prints `fits k of 32 (placed wrong m)`. The number is recorded in the impact record once.
- **Status.** The spot check is **never a gate** and **never re-drawn**. No rule, tolerance or test reads it.
- **Labels.** `weapons attach-eval` keeps working against `weapon_attach_labels.json`, the 449 labels. It prints an agreement table of geometry verdict against label per slot. That table is a descriptive comparison only: no exit code, AC or literal depends on it. AC80(c) is retired for the four slots; it no longer gates the build.

### 3.11 Python interface (new module `src/synty_inventory/weapons/fit_geometry.py`; frame vote in `geometry.py`)

The frame vote is record geometry (Q-G4), so it lives in `geometry.py`, beside `_pick_long_axis` and `_TIE`. Its two literals are module constants versioned by `WEAPON_GEOMETRY_VERSION` 6, not rules keys, so `rules_digest` does not move (§4.6).

```python
# geometry.py (record geometry, WEAPON_GEOMETRY_VERSION 6)
_FRAME_END_SLAB_M = 0.010             # end slab of the frame vote's ring test (section 3.3 step 3)
_FRAME_BORE_MAX_M = 0.025             # largest bore ring that confirms a muzzle end

@dataclass(frozen=True)
class FrameVote:
    forward: tuple[str, int]          # ("x"|"y"|"z", +1|-1)
    up: tuple[str, int]
    changed: bool                     # forward axis differs from the build's
    conflict: bool                    # differs and the bore-ring test failed (section 3.3 step 4)
    sign_by_fallback: bool = False    # a frame_axis moved the axis and no single end ring gave the sign: forward carries "+"
                                      # and the record is flagged forward_by_fallback (section 3.3 step 5; additive S1 deviation)

def frame_vote(verts, body_verts, build_forward: tuple[int, int], frame_axis: str | None = None) -> FrameVote: ...
    # verts: the whole host mesh (the build's up rule reads it, unchanged); body_verts: minus the slot children (step 1)

# mount_probe.py (a numpy-only leaf: no import cycle with geometry.py, mounts.py or the detectors)
def end_ring_d(verts, axis: int, sign: int, slab_m: float) -> float | None: ...   # section 3.6 (ii); frame vote and barrel_end
```

`fit_geometry.py` is the interface below. The build may put each detector in a sibling module (`fit_locate.py`, `fit_rails.py`, `fit_bore.py`, `fit_well.py`) and the dataclasses in `fit_types.py`, all re-exported by `fit_geometry`, so the detectors build in parallel (plan §2). Callers import from `fit_geometry` only. AC144 applies to every one of these files.

```python
# Pure functions over plain sequences; vertices are (N, 3) arrays in the host's scaled GLB space.
@dataclass(frozen=True)
class RailRun:
    f0: float; f1: float; top_u: float
    pitch_m: float; amp_m: float; teeth: int; width_m: float
    toothed: bool                     # False only for a flat seat

@dataclass(frozen=True)
class BarrelEnd:
    centre_su: tuple[float, float]; face_f: float; od_m: float
    evidence: Literal["ring", "face_ring", "round_section"]

@dataclass(frozen=True)
class WellRef:
    u_rb: float; length_m: float; width_m: float
    source: Literal["child"]  # "located" retired with its producer, errata E2-Q3

@dataclass(frozen=True)
class Placement:
    part: str; t: tuple[float, float, float]; hit: float

@dataclass(frozen=True)
class Verdict:
    value: Literal["fit", "unverified", "no_fit", "not_judged"]
    signals: tuple[str, ...]          # section 3.1 step 5 vocabulary

def locate_by_translation(host_verts, part_verts, rules: dict) -> list[Placement]: ...
def strip(host_verts, host_tris, placements: list[Placement], part_meshes: dict) -> tuple: ...
def rail_runs(verts_fsu, tris, side: Literal["top", "bottom"], s0: float, rules: dict) -> list[RailRun]: ...
def flat_seat(verts_fsu, tris, s0: float, rules: dict) -> RailRun | None: ...
def barrel_end(verts_fsu, tris, mount: dict, rules: dict) -> BarrelEnd | None: ...
def device_inner_d(part_verts_fsu, anchor: dict, rules: dict) -> float | None: ...
def well_reference(host_verts_fsu, host_tris, mag_verts_fsu, mag_tris, rules: dict) -> WellRef | None: ...
def entry_section(mag_verts_fsu, mag_tris, u_plane: float) -> tuple[float, float] | None: ...
def verdict(slot: str, host_feats: dict, part: dict, pair_seat: dict | None, rules: dict) -> Verdict: ...
def fit_digest(measure_records: list[dict]) -> str: ...   # section 4.3
```

Host features are computed once per host and cached in `<catalogs>/weapons/_fit_cache.json`. The cache key is (GLB sha256, `glb_node`, `glb_scale`, `WEAPON_GEOMETRY_VERSION`, `WEAPON_ATTACH_VERSION`, `attach_rules_digest`, the code digests of `fit_geometry` and its detector modules). The detectors measure in the record frame, which `WEAPON_GEOMETRY_VERSION` versions (Q-G4), so a geometry bump must miss this cache too. The eligible-host fingerprint of the geometry cache (`mv`) gains the `fit_geometry` block and the same code digests, because rail seats are mounts. The cache is pack-derived and never committed.

**CLI** (subcommands of `synty-inventory weapons`):

```text
attach-calibrate [--directory PATH] [--json OUT]
    Runs every detector on the oracle (section 3.2) and prints, per literal, its positives (class and count), the max
    observed error, the margin and the literal. Exit 0 when every literal covers its positives except the listed
    exceptions; exit 6 (as `validate`) otherwise. --json writes the full report to OUT (must be outside the repo).
attach-spotcheck (--draw | --score) [--directory PATH]
    Section 3.10. --draw exits 6 if weapon_attach_spotcheck.json exists.
attach-preview ... [--pairs FILE] [--icons ROOT ...]
    Existing verb, two additive flags: render the listed pairs (a spotcheck file or a pair list, such as the
    toothed-host and frame sheets that attach-calibrate --json writes), with HUD icons beside each pair by path.
```

## 4. Data shapes, versions and migration

### 4.1 Rules block (`weapon_rules.yaml` → `attachment_rules.fit_geometry`; excluded from `rules_digest`, hashed into `attach_rules_digest`)

```yaml
fit_geometry:
  slots: [optic, muzzle, underbarrel, magazine]
  locator: {grid_m: 0.0005, sample_n: 24, hit_min: 1.0, merge_m: 0.002}
  # no frame: key. The frame vote is record geometry (Q-G4): geometry.py constants, section 3.11
  rail:
    window_m: 0.010
    bin_m: 0.0005
    tooth_amp_min_m: 0.0008
    tooth_merge_m: 0.0025
    pitch_min_m: 0.005
    pitch_max_m: 0.040
    pitch_cv_max: 0.25
    tooth_min_count: 4
    tooth_h_tol_m: 0.0015
    zone: [0.15, 0.85]
    default_seat_len_m: 0.20
    sight_clear_m: 0.010
  flat: {band_m: 0.005, close_m: 0.015, min_m: 0.060}
  clamp: {overhang_max_m: 0.010, ratio_min: 1.0}
  depth: {lo_m: -0.026, hi_m: 0.003}            # review list only (section 3.9)
  bore:
    end_slab_m: 0.010
    round_min: 0.8
    barrel_od_max_m: 0.060
    od_ratio: [0.85, 2.00]
    inner_ratio: [0.47, 1.21]
    axis_offset_max_m: 0.005
    axis_tilt_max_deg: 2
  well: {entry_depth_m: 0.002, tol: 0.15}
  exceptions: []        # calibration exceptions by class key (section 4.2), no asset ids
```

Every key is required. The validator rejects a missing key, a negative length, and an inverted interval.

### 4.2 Tolerances (each literal = max error on its positives + a stated margin)

| literal | positives (n) | max observed | margin | literal | exceptions (reasoned) |
|---|---|---|---|---|---|
| `clamp.overhang_max_m` | toothed optic positives (16) | 8 mm | 2 mm | 10 mm | none |
| `clamp.ratio_min` (clamp underside ≥ rail width) | toothed optic positives (16) | min ratio 1.63 | physical bound | 1.0 | **rule exception:** a one-sided physical bound (a clamp narrower than the rail cannot grip it), so the literal sits below the data, not beyond it. "Clamp width matches rail width" as an equality fails on Synty's own presets at any useful tolerance, because undersides are 26 to 75 mm against 16 to 18 mm rail tops. |
| `rail.zone` | optic contact centres, all optic positives | [0.22, 0.80] | 0.07 rear, 0.05 front | [0.15, 0.85] | none |
| `depth` (review list only) | toothed optic positives (16) | 0 to −23.9 mm | 2 mm below, 3 mm above (= `contact.dead_m`) | [−26, +3] mm | not a fit literal |
| `bore.od_ratio` | bore positives (11) | [0.93, 1.92] | 0.08 each side | [0.85, 2.00] | E-G3 |
| `bore.inner_ratio` | devices with an inner ring (6 placements) | [0.55, 1.13] | 0.08 each side | [0.47, 1.21] | none |
| `bore.axis_offset_max_m` | bore positives (11) | 3.9 mm | 1.1 mm | 5 mm | none |
| `bore.axis_tilt_max_deg` | bore positives (11) | 0° | 2° | 2° | none |
| `well.tol` | judged twin magazines (15 of 16) | 0.105 | 0.045 | 0.15 | E-G2. Alternative 0.095 in Q-G2. |
| `geometry._FRAME_BORE_MAX_M` (a `geometry.py` constant, Q-G4; not in `fit_geometry`) | frame-changed hosts (3) | 18 mm | 7 mm | 25 mm | none |

The detector parameters (locator grid, tooth amplitude, pitch window, CV, count, merge, band, closing, minimum run, round section, OD cap, entry depth) are not tolerances on a pair. They cover the measured distributions in §1.1: pitch p5 to p95 is 17 to 32 mm inside a 5 to 40 mm window, and tooth amplitude p5 is 2.9 mm against a 0.8 mm floor. `attach-calibrate` prints them with those distributions.

**Calibration exceptions (AC133 to AC136; reasons, not ids, are recorded in `fit_geometry.exceptions`):**
- **E-G1. Stepped optic seats.** 3 untoothed twin hosts whose twin sits on a stepped seat (the A§5.4 known defects). They pass only through `seat_ref` with the child's own foot length. No flat run covers them.
- **E-G2. Cross-family twin magazine.** It reads 0.105 in width. It passes at `well.tol` 0.15 and would be an exception at 0.095 (Q-G2). The drum twin has no section, so it is `unverified` (the twin listing is unaffected).
- **E-G3. Slide-face silencer twin** (a pistol). The device mates on a slide face with no modelled barrel, so its OD ratio is below the band. It stays listed as `twin`. Other suppressors on that host are judged by the band.
- **E-G4. Off-centreline underbarrel twin** (a launcher's foregrip) and the splayed bipod children. These are not on the centreline, so the rail check is skipped (`seat_ref` decides). They are not calibration data for `rail_runs(bottom)`.
- **E-G5. The canted-adapter optic** on a non-host preset. The rail is an adapter part, not host geometry (Q-G10).
- **E-G6. Policy-refused positives.** These are the launcher optics and every positive on a slot that policy refuses. They calibrate detectors and are never listed.

### 4.3 Determinism and digest

- Vertices are sorted lexicographically before any binning.
- Bins use integer indices (`floor(x / bin_m)`), and no set iteration order reaches the output.
- Stored measures are rounded to 1e-4 m, as A§8 requires.
- `fit_digest` is the first 16 hex characters of the sha256 of a canonical JSON (sorted keys, no spaces) of the list of measure records, sorted by `(host, slot)` for host features and `(part)` for part features.
- `fit_digest` is written to the directory's top level next to `attach_rules_digest`, and to `generated_from` only with `--attachments`.

### 4.4 New and changed shapes

- **Host mount, optional key `feature`.** One of `rail_teeth`, `rail_flat`, `seat_ref`, `barrel_ring`, `barrel_round`, `well_ref`, or absent.
  - It is present only on the four slots, and only when a detector measured the seat or confirmed an authored one.
  - `source` keeps its four values. A rail seat is `probe`, which the sight probe already uses for non-muzzle slots (A§4.2).
- **Compat entry `signals`.** The vocabulary of §3.1 step 5 replaces the label-era signals on the four slots.
- **Directory-form pending entry**, optional `signals`. The export form stays ids only.
- **Directory top level and `generated_from`** (with `--attachments` only): `fit_digest`.
- **Record `geometry.axes.forward_source`, new value `"body"`** (Q-G4), on the feature-frame records only. The schema keeps `forward_source` a free string, so this needs no schema change. `item_basis` stays a signed permutation (a proper rotation built from the two axis units, as today).
- **`weapons/schema.py`.** Its schemas are strict (`additionalProperties: false`). They gain exactly these optional keys and the new enum values (`feature`; `signals` on pending entries; `fit_digest`), and stay strict.
- **`weapon_attach_spotcheck.json`** (committed; ids, booleans and fixed strings only, like the labels file):

  ```json
  {"schema": "weapon-attach-spotcheck/1", "drawn_at": "<attach_rules_digest>", "salt": "spotcheck-1",
   "pairs": [{"part": "<id>", "host": "<id>", "slot": "optic", "tier": "same_pack_fit",
              "fits": null, "placed_wrong": null}]}
  ```

### 4.5 Overrides

`weapon_overrides.json` gains one categorical host key: `frame_axis`, which is `"x"`, `"y"` or `"z"`. It names the forward axis of a frame-conflict host (§3.3 step 4). With Q-G4 it sets the **record's** forward axis too, and `forward` then sets the sign on it (§3.3 step 5). It is categorical like `forward_override`, carries no number, so INV-17 holds, and is hashed into `overrides_digest`. It is an input of the geometry cache fingerprint, present only when set, as `fo` is. No entry is needed today, so `overrides_digest` is unchanged until one is written.

### 4.6 Versions, digests and consumer impact (tools/vendor/spec.md §3.8)

- **Directory.**
  - `WEAPON_ATTACH_VERSION` goes 13 → **14**, which invalidates the attachment cache.
  - `WEAPON_GEOMETRY_VERSION` goes 5 → **6** (Q-G4, Tom 2026-10-27), which invalidates the geometry cache. Its comment in `weapons/__init__.py` records "6: the body-axis frame vote on eligible hosts (G1, §3.3)".
  - `rules_digest` is unchanged, because the new tables live in `attachment_rules` and the frame constants are code. `attach_rules_digest` changes. `overrides_digest` is unchanged.
  - The **default export is identical to a8c's except** the feature-frame records (3 today) and `generated_from.geometry_version` (5 → 6). INV-19 and AC77 are amended to say so. On a record, only the frame-derived fields of §3.3 may change; any other changed field is a finding.
  - **The W7 reference files stay untouched.** `w7_default_export.json` and the `w8d_w7_*` files are outputs of the W7 tree and cannot be regenerated. The byte-identity tests compare after replacing `geometry_version` 5 with 6 in the reference, and assert `geometry_version == 6` on their own. The synthetic worlds hold no feature-frame host, so nothing else differs there. The 3-record difference shows only on the live a8c → a14 comparison (AC146).
- **`--attachments` export.** Data changes:
  - more `probe` optic and underbarrel mounts (rail seats on up to 29 + 12 hosts);
  - muzzle seats on the 3 frame hosts move to the barrel end;
  - entries and scores change.
  - Additive keys: `feature` on mounts and `fit_digest` in `generated_from`.
  - C-18 already says `mounts` may later gain keys (C-25), and C-24 says `sit_armory` ignores unknown keys.
- **sit_armory 0.3.0.**
  - The loader requires `[source, point, forward, up, span_m, occupied_by, child_node]` and ignores extra mount keys.
  - `source` stays inside `MOUNT_SOURCES = [override, child_node, probe, none]`, so no ARM_E70.
  - Tiers are unchanged, so no ARM_E71.
  - **Q-G4 (`geometry_version` 6, a changed frame on 3 records), checked against the 0.3.0 sources:**
    - `geometry_version` is metadata: `sit_armory_listing.gd` (around line 306) and `sit_armory_refresh.gd` (`_WHOLE_META_KEYS`) only check that it is a whole number, and `sit_armory_result.gd` passes it through. There is no minimum geometry version; the only floor is `MIN_ATTACH_VERSION := 1` (`sit_armory.gd`).
    - The new `item_basis` is still a signed permutation, which is what `sit_directory_snapshot.gd` (`_is_signed_permutation`, around line 406) requires. `sit_armory_geometry.gd` and the resolver copy `item_basis` and `length_m` through as data. Neither addon reads `geometry.long_axis`.
    - A game with a lock sees ARM_E04 (snapshot hash differs) on its next re-export, the normal re-export flow. ARM_W06 fires only if `archetype`, `genre` or `hold_class` changes. The build's pass 2 can move archetype or hold class by the measured length (`directory._measure_record`). On the 3 hosts, a8c took all three from name rules (provenance `rules`), so no change is expected. The build reports any change as a finding.
  - **No change, no bump.**
- **sit_weapons 0.4.0.** `SitMountSpec.slot_faults` checks only that `source` is a String, and the frame, `occupied_by`, `span_m` and `child_node` keys. Unknown keys pass. It does not read `geometry_version`, `axes` or `item_basis`. **No change, no bump.**
- **If a consumer later reads `feature`,** that addon bumps MINOR (a new optional key in its contract).
- **If Tom picks a new `source` value instead (Q-G5),** sit_armory must ship MINOR 0.4.0 first, adding the value to `MOUNT_SOURCES` with AT6 and AC43 edits. An unpatched 0.3.0 would reject every such host record with ARM_E70. sit_weapons would need nothing. This is one addon, so the "spanning two addons" rule does not apply.
- **The attachment spec's contract table** (A§10) gains a PATCH note: C-18 lists `feature`, and C-23 lists the signal vocabulary. The lead applies it on adoption.
- **Existing ACs and invariants of the attachment spec that this edits:**
  - AC80(c) is retired for the four slots (§3.10).
  - AC67 holds unchanged (Q-G4 adopted: the record frame is the feature frame, so muzzle parity needs no exception).
  - INV-19 and AC77: "byte-identical to W7" becomes "identical to W7 except `generated_from.geometry_version` (6) and the feature-frame records". AC77's break "bump `WEAPON_GEOMETRY_VERSION`" now reads "bump it to 7".
  - AC78 holds; its bump test now runs from 6.
  - The "`WEAPON_GEOMETRY_VERSION` stays 5" clauses of AC93, AC96, AC103, AC110, AC116, AC123 and AC129 are history, true at their builds. Their tests follow the new value, 6.
  - Gates scored on the label-era rules (AC117 to AC130, where they test a retired rule) are re-pointed to AC131 to AC149 for the four slots.

  These are edits to the directory's own spec, recorded with `WEAPON_ATTACH_VERSION` 14 and `WEAPON_GEOMETRY_VERSION` 6. They are not consumer contract changes.

### 4.7 Migration from a8c

1. Build a14 on `integ/attach` with the gate behind no flag. The retired rules are inert for the four slots from that version on.
2. Make the impact record with `attach-calibrate`, plus a before/after table of **raw listed and pending counts per slot × tier** (a8c against a14) and the count of pairs moving each way. It also lists:
   - every record whose default-export bytes changed, with each changed field (expected: the 3 feature-frame records, frame-derived fields only);
   - the hosts that lose a listed muzzle entry because they have no barrel end (3 on a8c's seats; under §3.6 about 1 is expected, the sniper, because the Uzi-type host finds its end in the feature frame and the brake preset is refused by the fill rule instead);
   - the new rail seats;
   - the preset fill additions;
   - the cross-pack magazine count judged `fit`.

   There is no target count.
3. **Draw #6 as context only.** The label gate refused widely: R 0.274 on the draw, with the far strata (764 pairs) carrying most of the missed fits. The geometry gate removes the name, family, affinity and gun-class tests that produced those far refusals, so far-strata pairs are now judged on rails, barrel ends and wells. This is expected to list more muzzle and same-pack magazine pairs and fewer optic pairs on untoothed hosts. These are expectations to read the impact table against, not gates. Draw #6's labels are not re-scored against a14.
4. Take the spot check once (§3.10) and record the number in the impact record.
5. Games re-export. Overlays keyed by part id are unaffected (C-26). A game's own `fits` adds still extend the lists.

## 5. Invariants

- **INV-22.** Every `compatible_hosts` entry of an `optic`, `muzzle`, `underbarrel` or `magazine` part whose tier is `same_pack_fit` or `cross_pack_fit` has verdict `fit`, and at least one geometry signal from §3.1 step 5. No such entry exists with `rail_flat` alone.
- **INV-23.** For the four slots, a verdict depends only on geometry, the part's anchor and footprint, and the policy rules of §3.8. Renaming a part or host (tokens) changes no verdict unless a policy rule reads the name.
- **INV-24.** Every literal in `fit_geometry`, and the frame constant `geometry._FRAME_BORE_MAX_M`, is ≥ the max error of its positives (or ≤ the min, for lower bounds) except the listed exceptions. `attach-calibrate` enforces this.
- **INV-25.** `fit_digest` and the directory bytes are identical across two builds and across `PYTHONHASHSEED` values.
- **INV-26.** `weapon_attach_spotcheck.json` is write-once. Only its `fits` and `placed_wrong` fields change after the draw, and only from null.
- **INV-27.** A frame-conflict host has no detector seat (`feature` absent and `source` not `probe` on the four slots).
- **INV-28 (Q-G4).** A record's frame differs from the bounding-box frame only on an eligible host whose body axis is confirmed by exactly one end ring (§3.3 step 3) or named by `frame_axis`. Such a record has `axes.forward_source` `"body"` (or `"override"` when `forward` sets the sign), and its `geometry.muzzle` equals its muzzle mount's point when `occupied_by` is empty (AC67).
- INV-14 to INV-21 still hold. **INV-19 is amended** (Q-G4): the default export is identical to the W7 export except `generated_from.geometry_version` (6) and the records of INV-28, whose frame-derived fields (§3.3) may differ; no other byte differs.

## 6. Acceptance criteria

Each criterion is paired with the deliberate break that must fail it. Counts are those measured in §1.1. The builder re-measures them, and any deviation is a finding to report, not a number to tune.

| # | criterion | must fail when |
|---|---|---|
| AC131 | **Oracle: presets.** `locate_by_translation` on the 14 Military presets returns 164 placements at hit 1.0. By slot: optic 14, magazine 15, muzzle 4, underbarrel 4, laser_light 3, sight_front 6, other 118. No placement below 1.0 is returned. Synthetic fixture: a host built from 3 translated parts returns exactly those 3 translations. | `hit_min` lowered to 0.9, so the barrel aliases appear; the 27-neighbour tolerance dropped, so placements are lost |
| AC132 | **Strip.** On the synthetic fixture, the host mesh after `strip` equals the base mesh, triangle for triangle. On every preset, no remaining host triangle has all three vertices on a located part. | strip skipped: a fused scope's top reads as the rail |
| AC133 | **(a) Twins.** The geometry verdict is `fit` on 36 of the 38 twin pairs. The cross-family twin magazine (E-G2) is among the 36, at `well.tol` 0.15. The stepped optic seats (E-G1) are too, through `seat_ref`. The 2 others are the drum twin (`unverified`, E-G2) and the slide-face silencer (`no_fit`, E-G3). Each is printed with its reason. Twin listing is unchanged on all 38. | `seat_ref` disabled (the 13 untoothed optic twins fail); `well.tol` set to 0.09 (the cross-family twin fails, not reported as an exception) |
| AC134 | **Rails on positives.** 13 of the 14 preset optic placements and all 16 toothed optic positives lie on a detected run of 4 or more teeth, with overhang ≤ 10 mm and clamp ratio ≥ 1.0. The odd one is E-G5. 3 of the 4 preset underbarrel placements lie on bottom teeth. The detected counts are 45 hosts on top and 14 on the bottom at 4 teeth, reported by class. | `tooth_min_count` 6, or `pitch_max_m` 0.016, drops positives |
| AC135 | **Bore on positives.** On all 11 bore positives, the axis offset is ≤ 5 mm and the tilt ≤ 2°. The OD ratio lies in the band on 10 of 11, the exception being E-G3. The inner ratio lies in the band on all 6 ring placements. The has-end and no-end host counts are reported by class. The survey's 233 and 24 were measured in the build frame before strip. The 4 expected movers of §1.1 (the two Uzi-type SMG hosts, one nail gun, the brake preset) take the spec definition to about 237 and 20. Any other mover is listed with its class. | barrel end measured on the unreduced mesh (a baked device's face read as the barrel) |
| AC136 | **Well on positives.** 14 twin magazines read 0.000. The Military matrix gives same-family ≤ 0.09, and the SMG and heavy magazines ≥ 0.38 off every rifle well, so they are `no_fit` there at 0.15. | section taken at the magazine's own top instead of `u_rb − 0.002` |
| AC137 | **Tolerance rule.** `attach-calibrate` exits 0 on a14 and prints every row of §4.2. With `clamp.overhang_max_m` set to 0.007, it exits 6 and names the literal. The test's expected maxima are literals in the test, not values read from the rules file. | the check skipped; or the test's bound read from the rules file (which would loosen with the rule) |
| AC138 | **(b) Negative controls.** Zero listed entries of each kind: optic on a `launcher`, `tool` or `fixed_heavy` host; any slot on a melee record (no mounts); muzzle on a host with no barrel end; magazine on a host with no well reference. On a8c the barrel-end control has 8 entries, on 3 hosts. | the barrel-end requirement removed: the count is 8 or more |
| AC139 | **(c) Policy unchanged.** For every rule of §3.8, a14's refused (slot, host) set ⊇ a8c's. The only additions are the preset fill list (Q-G11, reported). One fixture test per standing refusal, as shipped (§3.8): (1) on a preset host, a baked child or a located fused optic or silencer refuses its slot, and the magazine stays open; (2) a baked iron sight refuses both sight slots on any host; (3) a glass-only host refuses `optic`; (4) on a non-preset host, a baked optic body or muzzle device stays replaceable (`occupied_by`), **not** refused; (5) no silencer on a launcher or any shotgun, no optic on a launcher, a tool and a minigun take nothing, `Sniper_Heavy_01` refuses muzzle (as recorded), a preset refuses only filled slots and keeps the magazine open, and a cross-setting pair is never a candidate. | any policy rule moved after the geometry step, or skipped for `fit` pairs |
| AC140 | **(c) Cross-pack magazines.** Zero `cross_pack_fit` magazine entries in `compatible_hosts`. The count of cross-pack magazine pairs judged `fit` is printed for Q-G1. | A8-1 routing dropped |
| AC141 | **(d) Spot check.** `--draw` writes 32 pairs (8 per slot), none of them twin, override or among the 449 labels, in hash order. A second `--draw` exits 6. `--score` prints `fits k of 32 (placed wrong m)`. No test, AC or rule reads the answers. | a draw that overwrites; any AC reading the file |
| AC142 | **(d) Labels descriptive.** `attach-eval` prints the agreement table per slot and exits 0 whatever the agreement. AC80(c) is marked retired for the four slots. | an exit code tied to agreement |
| AC143 | **(e) Determinism.** Two clean builds with `PYTHONHASHSEED` 0 and 1 give an identical `directory.json` (bytes) and identical `fit_digest`. A synthetic fixture's digest is a literal in the test. | set iteration or an unsorted dict reaching the measures |
| AC144 | **(f) Dependencies.** `pyproject.toml` `dependencies` and `optional-dependencies` are unchanged. `fit_geometry.py` imports only the standard library, `numpy` (already declared and used by every geometry module) and `synty_inventory` (Q-G7). | a new import (scipy, trimesh) |
| AC145 | **(g) Consumer schema.** Every mount `source` in an a14 `--attachments` export is in {override, child_node, probe, none}. `feature` and `fit_digest` are optional, and the export validates against the shipped JSON schema with only those keys added. On the sit-capabilities side, the lead loads a synthetic export with the new keys, `geometry_version` 6 and one host whose `item_basis` is a rotated signed permutation (the feature-frame case) through sit_armory 0.3.0's loader and sit_weapons 0.4.0's `SitMountSpec.from_dicts`, unchanged: no ARM_E70 or E71, no snapshot error, no slot fault. This is a read-only run from a scratch script; no sit-capabilities file changes. | a rail seat written as `source: "rail"` (ARM_E70) |
| AC146 | **Migration.** `WEAPON_ATTACH_VERSION` == 14 and `WEAPON_GEOMETRY_VERSION` == 6 (Q-G4). `rules_digest` and `overrides_digest` are unchanged from a8c, and `attach_rules_digest` is changed. The default export is identical to a8c's **except** the feature-frame records (3 today) and `generated_from.geometry_version` (amended INV-19, AC77). On those records only frame-derived fields (§3.3) differ, and each is listed. On the synthetic worlds the default export equals the untouched W7 references once `geometry_version` 5 is read as 6. The impact record holds the raw before/after table of §4.7 step 2. | geometry keys placed outside `attachment_rules` (`rules_digest` moves); the vote run on a non-eligible record, or a non-frame field changed on a feature-frame record (the default export differs on more than those records and that field) |
| AC147 | **Frame.** `frame_vote` changes the forward axis on exactly the hosts whose body axis differs and whose bore-ring test holds at exactly one end: 3 today, one of them a tool. The frame-conflict count is reported (0 today). An Uzi-shaped synthetic fixture (magazine longer than barrel, 15 mm ring at the muzzle) gets its muzzle seat at the ring, not at the magazine bottom. A fixture with rings at both ends is a conflict with no detector seat, and keeps its build frame. **`geometry.axes` changes on exactly those 3 hosts** (Q-G4), with `forward_source` `"body"`, and on no other record. On the Uzi-shaped fixture, `geometry.axes`, `item_basis`, `length_m` and `geometry.muzzle` follow the body axis. Its muzzle mount equals `geometry.muzzle` (AC67, unchanged), and `item_basis` is a signed permutation. A `frame_axis` override on the both-rings fixture sets the record's axis, and `forward` then sets its sign. | the bounding-box frame used for detectors (the fixture's seat lands at the magazine); the vote applied to mounts only (record axes unchanged, AC67 parity fails on the fixture); a `forward` override applied before the axis is chosen |
| AC148 | **Low poly and sight seats.** No optic or underbarrel pair is listed through `rail_flat` alone. On untoothed hosts with an authored optic child, pairs list through `seat_ref`. The number of hosts carrying each `feature` value is reported. A§4.6 gate 6(c) passes on every host with a rail seat. | flat seats treated as toothed (listed optic pairs appear on untoothed hosts with no authored seat); the sight clip removed (6(c) fails on a railed host with a front sight seat) |
| AC149 | **Retired rules inert.** In the four slots, permuting part-name tokens (fixture) and blanking `attach_affinity` change no entry. In `laser_light`, `sight_front` and `sight_rear`, every entry is identical to a8c's. | a retired rule still consulted for a geometry slot; or a geometry rule leaking into a sight slot |

## 7. Failure modes

- **Periodic non-rail tops read as teeth** (ribs, heat shields, vent slots, a revolver rib).
  - The build writes the toothed-host sheet to the catalogs folder, and the lead views it once at the first build.
  - A wrong rail is removed with an existing `mounts` override (`slot_disabled`, or a named child). The spot check samples the result.
- **A rail seat that would cover a probe front sight.** The run is clipped (§3.4 step 4). On a host where the clip leaves less than the shortest optic foot, every optic is `no_fit` there, and the calibration report lists the host.
- **A rail with no modelled teeth** (low poly). A flat seat is placed and its pairs stay `unverified`. That costs recall, and is intended: the measured flat and ridge detectors cannot tell a rail from a barrel (§1.1).
- **Stepped or adapter seats** (E-G1, E-G5). Only an authored reference lists them.
- **A fused device reads as a barrel end** (a fused silencer or brake). On presets, the locator's fill list refuses the slot (Q-G11). On other hosts, a fused brake has no ring or round end, so it is `no_fit`. A fused silencer with a front ring would read as a barrel end; the existing census overrides (A§4.6 F) refuse those slots.
- **A real well with no authored magazine** (fused or absent magazine). There is no reference, so the pairs are `not_judged` and pending, as today.
- **A drum or a magazine that does not reach the plane.** The pair is `unverified`.
- **Node transforms** (NB-15). The detectors measure in the selected node's world frame, as the anchor function does, and inherit its `node_transform` reason.
- **A part with an unmeasured anchor** (A§3.4). The pair is `unverified`.
- **A frame conflict.** No detector seat. The host is listed in the report and resolved by `frame_axis`.
- **The locator on a non-Military pack.** It runs only on `attach_filled_hosts` hosts, against same-pack parts. A preset whose parts were re-modelled (hit < 1.0) has no placements, and its slots fall back to children.

## 8. Decisions (were open questions)

**Decided by Tom, 2026-10-27:** "Take Q-G4: adopt the feature frame for the record too, geometry_version 5 to 6. Other open questions at their defaults." The build takes these decisions:

| Q | decision | what the build does |
|---|---|---|
| Q-G1 | default: cross-pack magazines stay pending | A8-1 unchanged; AC140 prints the count judged `fit` for a later decision |
| Q-G2 | default: `well.tol` 0.15 | the A and B Military families interchange; the cross-family twin is inside the tolerance (E-G2) |
| Q-G3 | default: a flat seat lists nothing. Tom saw the per-pack rail table and kept this. | flat-seat pairs are `unverified` (pending); INV-22, AC148 |
| Q-G4 | **adopted**: the feature frame is the record's frame | `WEAPON_GEOMETRY_VERSION` 5 → 6; the frame vote moves to `geometry.py` (§3.3, §3.11); INV-19 and AC77 amended, INV-28 added, AC67 unchanged (§4.6) |
| Q-G5 | default: the optional mount key `feature`, `source` unchanged | no consumer bump (§4.6) |
| Q-G6 | default: the recorded ruling (A6-6 iii), muzzle only | no policy change for `Sniper_Heavy_01` |
| Q-G7 | default: no new dependency | standard library, `numpy` and `synty_inventory` only (AC144) |
| Q-G8 | default: the HUD icons are the human-readable references | no store renders; icons by path only |
| Q-G9 | default: unclassified parts stay unclassified | the impact record lists them |
| Q-G10 | default: canted adapters not modelled | E-G5 stays an exception |
| Q-G11 | default, **adopted**: the preset fill list | located fused parts fill their slots on presets (2 slots today) |
| Q-G12 | default: the other three slots wait for a later amendment | `laser_light` and the sights keep the label-era rules (AC149) |

The questions as they were put to Tom, kept for the record:

- **Q-G1 Cross-pack magazines.** They stay pending (A8-1) unless Tom lifts that. The well detector can judge them, and Synty itself bakes a Military magazine into a city-pack rifle (entry section 0.000). Default: pending. The build reports the count judged `fit` (AC140), so Tom decides on a number.
- **Q-G2 Well tolerance.**
  - 0.15 (default, by the rule): the A and B Military families interchange, as the cross-family twin shows.
  - 0.095: separates the families (same family ≤ 0.09, A against B 0.10 to 0.13); the cross-family twin becomes an exception.
- **Q-G3 Untoothed seats.**
  - Default: a flat seat lists nothing (pending).
  - Alternative: list same-pack pairs on a flat seat. That would put optics back on most barrels and top straps (§1.1), so it is not recommended.
- **Q-G4 Record frame fix.** (Adopted.)
  - Default (not taken): the feature frame is used by the attachment detectors only. The 3 hosts keep their built `geometry.axes`, so 2 SMGs are still held with the magazine forward.
  - Recommended, and taken: adopt the feature frame for the record too. `WEAPON_GEOMETRY_VERSION` goes 5 → 6, and INV-19 is amended for 3 records, `geometry_version` included. Consumers treat `geometry_version` as metadata.
- **Q-G5 Mount schema.**
  - Default: the optional `feature` key, with `source` unchanged. No consumer bump.
  - Alternative: new `source` values. sit_armory MINOR 0.4.0 must ship first (§4.6).
- **Q-G6 `Sniper_Heavy_01`.** The brief's list says it "takes nothing". Tom's recorded ruling (A6-6 iii, in the override note) is "takes no barrel attachments", read as muzzle only, with underbarrel and laser left for Tom. a8c lists optics on it, Synty's own twin scopes among them. Default: the recorded ruling, with no policy change. If "nothing" is meant, it is a one-line override, outside this spec.
- **Q-G7 "Stdlib only".** Default: no new dependency. The module uses the standard library plus `numpy`, which the package already declares and every geometry module imports. A strict "no numpy" reading would mean re-implementing the GLB loaders, and is not recommended.
- **Q-G8 Store renders.** None exist locally. The HUD icons (§1.1) are the human-readable references. If Tom wants store pages, they are referenced by URL in the spot-check sheet and never stored.
- **Q-G9 Unclassified parts.** A Military muzzle brake and an underbarrel grenade launcher are located on presets but have no attachment block (`part_misc`). Classification is out of scope here. Default: leave them, and list them in the impact record.
- **Q-G10 Canted adapters.** The one preset optic not on teeth sits on a canted rail adapter. Adapters are not attachments. Default: not modelled.
- **Q-G11 Preset fill list.** Default: adopt. Fused parts located on a preset fill their slots for `attach_filled_hosts` (2 slots today: a fused silencer and a fused scope). This applies Tom's standing refusal and only adds refusals.
- **Q-G12 The other three slots.** `laser_light` and the sights stay on the label-era rules. Default: a later amendment.

## 9. Gate

**PASS.**
- Every section is present.
- The interfaces carry concrete signatures, a rules block and CLI verbs.
- Every literal is stated with its positives, max error and margin, and the exceptions are reasoned.
- AC131 to AC149 are testable and each names a break that fails it.
- The open questions were all NON-BLOCKING with defaults, and are now decided (§8).
- With Q-G4 adopted, sit_armory 0.3.0 and sit_weapons 0.4.0 need no change (checked against their sources, §4.6). The default export differs from a8c only in the feature-frame records and `geometry_version` (amended INV-19).
- **Approved by Tom, 2026-10-27.** The build follows [weapon_attach_geometry_plan.md](weapon_attach_geometry_plan.md).
