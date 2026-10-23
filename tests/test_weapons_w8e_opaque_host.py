"""W8e (c): ``weapons attach-preview`` draws the host opaque (icon_harness/preview.js, ``previewPrepare``).

Tom judges placements by eye on these previews, and the translucent Military preset hosts (BLEND materials) showed the
placed attachment, and ghosting along the body, through the host. The fix is in ``preview.js`` only (``icon.js`` is shared
with ``weapons icons`` and stays byte for byte as it was): a drawn host mesh gets ``transparent = false``, ``opacity = 1``,
``depthWrite = true``, except an ``alphaTest`` (glTF MASK) material, which keeps cutting out.

The proof is a real picture, so these tests skip cleanly when Playwright, Chromium or three.js are missing. The scene is a
host box (x +-0.1, y +-0.1, z +-0.3; base colour 0.2 / 0.5 / 0.9, alpha 0.4, ``alphaMode`` BLEND) with the attachment box
(x +-0.03, y +-0.03, z +-0.05) placed INSIDE it with the identity matrix. Seen from outside, an opaque host hides the
attachment completely; a translucent one shows it in orange and leaves every body pixel at about 40 % opacity.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from synty_inventory.weapons import preview

_FIX = Path(__file__).parent / "fixtures" / "weapons"
_spec = importlib.util.spec_from_file_location("w8e_blend_glb", _FIX / "w8e_blend_glb.py")
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

SIZE = 192
HOST_BOX = ((-0.1, -0.1, -0.3), (0.1, 0.1, 0.3))
PART_BOX = ((-0.03, -0.03, -0.05), (0.03, 0.03, 0.05))
IDENTITY = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


@pytest.fixture(scope="module")
def renderer(tmp_path_factory):
    from tests.test_weapons_icons import renderer_root  # noqa: PLC0415 - skips with the reason when there is no renderer

    with preview.PreviewRenderer(renderer_root(), gpu=False) as r:
        yield r


@pytest.fixture(scope="module")
def glbs(tmp_path_factory):
    d = tmp_path_factory.mktemp("w8e_opaque")
    return {
        "blend": B.write_box_glb(d / "host_blend.glb", *HOST_BOX, rgba=(0.2, 0.5, 0.9, 0.4), alpha_mode="BLEND"),
        "opaque": B.write_box_glb(d / "host_opaque.glb", *HOST_BOX, rgba=(0.2, 0.5, 0.9, 1.0)),
        "mask": B.write_box_glb(d / "host_mask.glb", *HOST_BOX, rgba=(0.2, 0.5, 0.9, 0.4), alpha_mode="MASK", alpha_cutoff=0.5),
        "part": B.write_box_glb(d / "part.glb", *PART_BOX, rgba=(0.7, 0.7, 0.7, 1.0)),
    }


def job_for(glbs, host: str) -> dict:
    return {"host_glb": glbs[host], "host_nodes": None, "hide": [], "host_scale": 1.0, "item_basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "part_glb": glbs["part"], "part_nodes": None, "part_scale": 1.0, "matrix": IDENTITY, "part_tint": preview.PART_TINT}


def orange_count(flat: np.ndarray) -> int:
    return int(((flat[..., 0].astype(int) - flat[..., 2].astype(int)) > 100).sum())  # the tint e8742a; the host is blue


def warm_count(flat: np.ndarray) -> int:
    """Pixels redder than blue: the tint seen through a translucent host is a washed-out tan, not full orange. The host is blue
    and the background blue-grey, so nothing else in these pictures is warm."""
    return int(((flat[..., 0].astype(int) - flat[..., 2].astype(int)) > 10).sum())


def test_the_opaque_fix_lives_in_preview_js_and_not_in_the_shared_icon_harness():
    """Headless structure check (no renderer needed); the pixel tests below are the proof, this only keeps the fix where it belongs."""
    harness = Path(preview.__file__).parent / "icon_harness"
    pjs = (harness / "preview.js").read_text(encoding="utf-8")
    ijs = (harness / "icon.js").read_text(encoding="utf-8")
    assert "opaque(hostKept);" in pjs and "mat.depthWrite = true;" in pjs and "mat.transparent = false;" in pjs
    assert "if (mat.alphaTest > 0) continue;" in pjs  # MASK materials keep cutting out
    assert "opaque(" not in ijs and "depthWrite" not in ijs  # `weapons icons` is untouched


def test_the_fixture_hosts_really_are_translucent_and_masked(glbs):
    m = B.read_material(glbs["blend"])
    assert m["alphaMode"] == "BLEND" and m["pbrMetallicRoughness"]["baseColorFactor"][3] == 0.4
    m = B.read_material(glbs["mask"])
    assert m["alphaMode"] == "MASK" and m["alphaCutoff"] == 0.5 and m["pbrMetallicRoughness"]["baseColorFactor"][3] == 0.4
    assert "alphaMode" not in B.read_material(glbs["opaque"])


def test_a_translucent_host_is_drawn_opaque_and_hides_the_attachment_inside_it(renderer, glbs):
    px = renderer.render_pair(job_for(glbs, "blend"), SIZE)
    alpha = px[..., 3]
    body = alpha > 0
    assert body.sum() > 3000  # the host silhouette
    assert (alpha[body] == 255).mean() > 0.95  # opaque (anti-aliased edge pixels are the only partial ones); 40 % opacity gives ~102
    flat = preview.flatten(px)
    assert warm_count(flat) == 0  # the attachment inside the host does not show through (before: a tan patch)
    # and the colour is the host's own, not blended with the background: same picture as the same host authored opaque
    ref = preview.flatten(renderer.render_pair(job_for(glbs, "opaque"), SIZE))
    diff = np.abs(flat.astype(int) - ref.astype(int))
    assert diff.max() <= 6 and diff.mean() < 0.5, (diff.max(), diff.mean())
    centre = flat[SIZE // 2, SIZE // 2, :3].astype(int)
    assert centre[2] > centre[0] + 40 and tuple(centre) != preview.BACKGROUND  # blue host colour, not the grey-blue background


def test_a_mask_host_keeps_cutting_out(renderer, glbs):
    """A glTF MASK material (alphaTest) is a genuine cut-out and is not made opaque: with base alpha 0.4 under the 0.5 cutoff
    every fragment of the host is discarded, so only the attachment is drawn."""
    px = renderer.render_pair(job_for(glbs, "mask"), SIZE)
    flat = preview.flatten(px)
    assert orange_count(flat) > 100  # the attachment is visible: the host did not cover it
    blue = (flat[..., 2].astype(int) - flat[..., 0].astype(int)) > 40
    assert blue.sum() == 0  # no host body anywhere
