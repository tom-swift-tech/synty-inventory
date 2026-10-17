"""``weapons icons``: 256 px icons and 64 px thumbnails for measured weapons (docs/weapon_directory.md section 3.8).

Option B of the spec: an own orthographic, transparent-background harness (``icon_harness/``) that imports three.js
and the meshopt decoder from the already installed ``synty-glb`` tree, driven by the Playwright that ``synty_glb.qa``
uses. A render has two page calls: ``iconPrepare`` loads and orients the GLB and reports the view-space bounds of
its meshes; Python fits the frustum from those bounds (``fit_frustum``, pure, unit-tested without a browser); then
``iconRender`` draws and returns the pixels. Python encodes the PNGs itself (fixed filter, fixed zlib level), so the
bytes depend only on the pixels. The browser runs a software ANGLE/SwiftShader backend unless ``--gpu`` is given,
which makes repeated runs on one machine byte-identical (AC17).

No placeholder is ever written (INV-8): when the renderer is unavailable nothing at all is written and the verb
exits 5; a failed asset keeps ``visuals.icon: null`` and is listed under ``failed``.

``--variants`` (spec 3.7) adds one icon per colourway of an atlas-alt record: the same render with the albedo atlas
swapped for the sibling material's texture (``variants.resolve_variant_texture``). Outputs sit beside the default
icon as ``<id>@<L>.png`` / ``<id>@<L>@64.png`` and are cached on a hash that includes the texture file's bytes.

A picture with no visible pixel is a failure, not an icon: a glTF MASK material whose base-colour alpha is under its
cutoff discards every fragment. The render is then tried once more with MASK materials drawn as BLEND
(``visuals.icon_mode = "blend_retry"``); a second blank result fails the asset with the error ``blank_render``.
Every colourway icon is also compared with the default icon (``icon_difference``) and flagged ``visually_identical``
when they look the same, so a shop does not list duplicates.
"""

from __future__ import annotations

import base64
import hashlib
import math
import struct
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np

from . import EXIT_OK, EXIT_RENDERER, InputError, WeaponsError, digest, to_text, write_text_lf
from .guards import ensure_sole_runner
from .variants import TextureNotFound, resolve_variant_texture, variant_link_paths

ICON_HARNESS_VERSION = 1  # bump when the harness, framing or encoding changes what a render looks like
ICONS_DIRNAME = "icons"
THUMB_SIZE = 64
MAX_SIZE = 1024
FILL = 0.88  # the opaque bounding box fills this share of the long image edge (6 % padding each side)
ICON_MODE_BLEND = "blend_retry"  # visuals.icon_mode of an icon that only appeared after MASK materials were forced to BLEND
BLANK_RENDER = "blank_render"  # the error text of an asset that renders no visible pixel even after the retry
# A colourway looks the same as the default icon when fewer than this share of the covered pixels differ by more than
# ICON_DIFF_CHANNEL (of 255, max over straight RGBA channels). One named constant: it is calibrated on live data.
VISUALLY_IDENTICAL_MAX_SHARE = 0.005
ICON_DIFF_CHANNEL = 12
AZIMUTH_DEG = 25.0  # fixed 3/4 view, the same for every icon so icons are comparable
ELEVATION_DEG = 15.0
HARNESS_DIR = Path(__file__).resolve().parent / "icon_harness"
THREE_ENTRY = Path("node_modules") / "three" / "build" / "three.module.js"

# Same flags as synty_glb.qa._launch_browser: software ANGLE so a run does not depend on the GPU or its driver.
_SOFTWARE_ARGS = [
    "--ignore-gpu-blocklist",
    "--enable-webgl",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
]
_GPU_ARGS = ["--ignore-gpu-blocklist", "--enable-webgl"]

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


class RendererUnavailable(RuntimeError):
    """No icon can be rendered here: no synty-glb/three.js, no Playwright, or no Chromium (spec section 7)."""


class RenderError(RuntimeError):
    """One asset could not be rendered; the batch goes on and that asset keeps ``visuals.icon: null``."""


# --- pure parts (no browser) ---------------------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def node_tag(glb_node) -> str | None:
    """The same tag the geometry cache uses: a name stays as it is, a list joins with ``+``."""
    if glb_node is None or isinstance(glb_node, str):
        return glb_node
    return "+".join(glb_node)


def icon_input_sha(glb_sha256: str, glb_node, scale: float, item_basis) -> str:
    """16 hex over everything that changes the picture: the GLB bytes, the node selection, ``glb_scale``, the
    orientation (``item_basis``: a corrected axis must not keep a stale icon) and the harness version.

    The spec lists the GLB sha, node, scale and harness version; ``item_basis`` is added because the render depends
    on it, and a record whose axes were corrected after an icon was made would otherwise keep the wrong picture.
    The output size is not hashed: a PNG of the wrong size is detected from its header (``png_ok``).
    """
    return digest({
        "glb": glb_sha256,
        "node": node_tag(glb_node),
        "scale": float(scale),
        "basis": [[int(c) for c in row] for row in item_basis],
        "harness": ICON_HARNESS_VERSION,
    })


def camera_direction(shield: bool) -> tuple[float, float, float]:
    """Unit vector from the model's centre towards the camera, in the item frame (forward +Z, up +Y, x = up x forward).

    A weapon is seen from the -X side looking towards +X: with +Y up the screen's right is look x up = +Z, so
    ``axes.forward`` points to screen RIGHT (the sign matters: a camera on +X would flip the weapon to point left).
    Azimuth swings the camera towards the forward end, elevation raises it, both constants for every icon.
    A shield is seen face-on: the camera sits on the +forward (outer face) side looking back at the arm face, with the
    same azimuth/elevation offsets so shields carry the same depth cues as every other icon.
    """
    az, el = math.radians(AZIMUTH_DEG), math.radians(ELEVATION_DEG)
    if shield:
        return (math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el))
    return (-math.cos(az) * math.cos(el), math.sin(el), math.sin(az) * math.cos(el))


def fit_frustum(view_min, view_max, fill: float = FILL) -> dict:
    """Orthographic frustum (camera at the origin looking down -z) that centres the projected bounds and makes the
    longer side fill ``fill`` of the square image.

    ``view_min``/``view_max`` are the extreme camera-space coordinates of the drawn vertices, so this is the
    projected extent of the geometry actually shown: the opaque bounding box lands on ``fill`` of the long edge and
    on the image centre, whatever the shape (the 8 corners of the 3D AABB would overshoot the silhouette).
    """
    w, h = view_max[0] - view_min[0], view_max[1] - view_min[1]
    long_side = max(w, h)
    if not (long_side > 1e-9) or not all(math.isfinite(c) for c in (*view_min, *view_max)):
        raise RenderError("degenerate or non-finite projected bounds")
    half = long_side / fill / 2.0
    cx, cy = (view_min[0] + view_max[0]) / 2.0, (view_min[1] + view_max[1]) / 2.0
    depth = view_max[2] - view_min[2]
    pad = max(depth, 0.01)
    return {
        "left": cx - half, "right": cx + half, "bottom": cy - half, "top": cy + half,
        "near": -view_max[2] - pad,  # the camera looks down -z: distance along the view = -z
        "far": -view_min[2] + pad,
    }


def link_paths(out_dir: Path, pack: str, asset_id: str) -> tuple[str, str]:
    """``(icon, thumb)`` as written into ``visuals``: relative to directory.json, forward slashes."""
    base = f"{out_dir.name}/{pack}/{asset_id}"
    return f"{base}.png", f"{base}@{THUMB_SIZE}.png"


def png_ok(path: Path, size: int) -> bool:
    """Cheap integrity check: PNG signature, an RGBA IHDR of ``size`` x ``size`` and a closing IEND chunk."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(33)
            fh.seek(-12, 2)
            tail = fh.read(12)
    except OSError:
        return False
    if len(head) < 33 or head[:8] != _PNG_SIG or head[12:16] != b"IHDR" or tail != _PNG_IEND:
        return False
    width, height, depth, ctype = struct.unpack(">IIBB", head[16:26])
    return (width, height, depth, ctype) == (size, size, 8, 6)


def needs_render(visuals: dict, expected_sha: str, icon_rel: str, thumb_rel: str, base_dir: Path, size: int,
                 rebuild: bool) -> bool:
    """Skip logic: a record is skipped only when its stored input sha and links match and both PNGs are intact.

    Anything else (``--rebuild``, a changed GLB/node/scale/basis, a missing, truncated or wrong-size file) renders.
    """
    if rebuild:
        return True
    if (visuals.get("icon_input_sha") != expected_sha or visuals.get("icon") != icon_rel
            or visuals.get("thumb") != thumb_rel):
        return True
    return not (png_ok(base_dir / icon_rel, size) and png_ok(base_dir / thumb_rel, THUMB_SIZE))


def unpremultiply(px: np.ndarray) -> np.ndarray:
    """Premultiplied RGBA uint8 -> straight-alpha RGBA uint8 (integer math, round to nearest)."""
    a = px[..., 3].astype(np.uint32)
    rgb = px[..., :3].astype(np.uint32)
    safe = np.maximum(a, 1)[..., None]
    straight = np.minimum(255, (rgb * 255 + safe // 2) // safe)
    straight[a == 0] = 0
    return np.concatenate([straight, a[..., None]], axis=-1).astype(np.uint8)


def downsample(px: np.ndarray, size: int) -> np.ndarray:
    """Box-filter a premultiplied RGBA image to ``size`` x ``size`` (an integer divisor) with integer math.

    Averaging in premultiplied space keeps the transparent edge from pulling dark colour into the thumbnail.
    """
    h = px.shape[0]
    if h % size:
        raise ValueError(f"{h} is not a multiple of {size}")
    k = h // size
    if k == 1:
        return px
    total = px.reshape(size, k, size, k, 4).astype(np.uint32).sum(axis=(1, 3))
    return ((total + (k * k) // 2) // (k * k)).astype(np.uint8)


def encode_png(rgba: np.ndarray) -> bytes:
    """8-bit RGBA PNG, filter 0, zlib level 9, an sRGB chunk and nothing else: bytes are a function of the pixels."""
    h, w, _ = rgba.shape
    rows = np.zeros((h, 1 + w * 4), dtype=np.uint8)
    rows[:, 1:] = rgba.reshape(h, w * 4)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (_PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"sRGB", b"\x00")
            + chunk(b"IDAT", zlib.compress(rows.tobytes(), 9)) + chunk(b"IEND", b""))


def decode_png(data: bytes) -> np.ndarray:
    """An 8-bit RGBA, non-interlaced PNG (all five filter types) as an (h, w, 4) uint8 array; ``ValueError`` otherwise.

    The inverse of ``encode_png`` for any conforming encoder. Pillow is not a core dependency, so this is numpy plus a
    byte loop for the filters that need the left neighbour (Average and Paeth; Sub is a running sum).
    """
    if data[:8] != _PNG_SIG:
        raise ValueError("not a PNG")
    pos, idat, header = 8, [], None
    while pos + 8 <= len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if tag == b"IHDR" and len(body) == 13:
            header = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
    if header is None or not idat:
        raise ValueError("PNG without IHDR or IDAT")
    w, h, depth, ctype, _comp, _filt, interlace = header
    if (depth, ctype, interlace) != (8, 6, 0):
        raise ValueError("only 8-bit RGBA, non-interlaced PNGs are supported")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise ValueError(f"PNG data does not inflate: {exc}") from exc
    stride = w * 4
    if len(raw) != h * (stride + 1):
        raise ValueError("PNG data has the wrong length")
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.int32)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = np.frombuffer(raw, np.uint8, stride, y * (stride + 1) + 1).astype(np.int32)
        if ft == 0:
            cur = line
        elif ft == 1:  # Sub: each pixel adds the pixel on its left, per channel
            cur = np.cumsum(line.reshape(w, 4), axis=0).reshape(stride) & 255
        elif ft == 2:  # Up
            cur = (line + prev) & 255
        elif ft in (3, 4):
            row, up = line.tolist(), prev.tolist()
            cur_l = [0] * stride
            for i in range(stride):
                a = cur_l[i - 4] if i >= 4 else 0
                b = up[i]
                if ft == 3:
                    pred = (a + b) >> 1
                else:
                    c = up[i - 4] if i >= 4 else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur_l[i] = (row[i] + pred) & 255
            cur = np.array(cur_l, dtype=np.int32)
        else:
            raise ValueError(f"unknown PNG filter type {ft}")
        out[y] = cur
        prev = cur.astype(np.int32)
    return out.reshape(h, w, 4)


def icon_difference(default_png, variant_png) -> float:
    """Share of the covered pixels on which two icon PNGs differ visibly (0.0 = the same picture, 1.0 = nothing alike).

    Covered = alpha > 0 in either image; visibly = the largest absolute difference over the straight R, G, B and A
    channels is more than ``ICON_DIFF_CHANNEL`` (of 255). Two empty pictures do not differ (0.0). The PNGs must have the
    same size (``ValueError`` otherwise, as for an unreadable PNG; a missing file raises ``OSError``).
    """
    a = decode_png(Path(default_png).read_bytes()).astype(np.int16)
    b = decode_png(Path(variant_png).read_bytes()).astype(np.int16)
    if a.shape != b.shape:
        raise ValueError(f"icons differ in size: {a.shape[:2]} vs {b.shape[:2]}")
    covered = (a[..., 3] > 0) | (b[..., 3] > 0)
    n = int(covered.sum())
    if n == 0:
        return 0.0
    visible = covered & (np.abs(a - b).max(axis=-1) > ICON_DIFF_CHANNEL)
    return int(visible.sum()) / n


def is_blank(px: np.ndarray) -> bool:
    """True when no pixel of an RGBA image has alpha above 0 (nothing was drawn)."""
    return not bool((px[..., 3] > 0).any())


def _put(holder: dict, key: str, value) -> bool:
    """Set ``holder[key]``, or drop the key when ``value`` is None; True when that changed anything."""
    if value is None:
        return holder.pop(key, None) is not None
    if holder.get(key) != value or key not in holder:
        holder[key] = value
        return True
    return False


def apply_links(directory: dict, results: dict[str, dict], failed: set[str]) -> bool:
    """Write the icon links into the directory's records (in place); False when nothing changed.

    A rendered or skipped record gets its three link fields and its ``icon_mode`` (present only for a blend-retry icon;
    the key is dropped when the result carries none, so a re-render that no longer needs the retry clears it). A failed
    record is reset to null (and loses ``icon_mode``) even when an older file exists (INV-8: no stale icon is presented
    as current). Every other field is untouched.
    """
    changed = False
    for rec in directory["weapons"]:
        vis = rec["visuals"]
        if rec["id"] in results:
            res = results[rec["id"]]
            want = {"icon": res["icon"], "thumb": res["thumb"], "icon_input_sha": res["sha256"]}
            mode = res.get("icon_mode")
        elif rec["id"] in failed:
            want = {"icon": None, "thumb": None, "icon_input_sha": None}
            mode = None
        else:
            continue
        for key, value in want.items():
            if vis.get(key) != value:
                vis[key] = value
                changed = True
        changed = _put(vis, "icon_mode", mode) or changed
    return changed


def variant_input_sha(default_sha: str, texture_sha256: str, variant_id: str) -> str:
    """16 hex for one colourway icon: everything the default icon hashes (``default_sha``) plus the bytes of the
    texture that replaces the atlas, so a repainted sibling texture renders again and an untouched one does not."""
    return digest({"base": default_sha, "texture": texture_sha256, "variant": variant_id})


def apply_variant_links(directory: dict, links: dict[str, dict[str, dict]], failed: dict[str, set[str]]) -> bool:
    """Write colourway icon links into ``visuals.variants[]`` (in place); False when nothing changed.

    ``links`` is ``id -> variant_id -> {icon, thumb, sha256[, icon_mode][, visually_identical]}`` for rendered or still
    valid icons, ``failed`` is ``id -> {variant_id}``: those go back to ``icon: null`` and lose their
    ``icon_input_sha``, ``icon_mode`` and ``visually_identical`` (INV-8). A variant with a link carries ``icon`` and
    ``icon_input_sha``, plus ``icon_mode`` / ``visually_identical`` only when the link has them (a key the link lacks is
    dropped); one without carries the five spec keys only.
    """
    changed = False
    for rec in directory["weapons"]:
        mine, bad = links.get(rec["id"], {}), failed.get(rec["id"], set())
        for var in rec["visuals"]["variants"]:
            letter = var["variant_id"]
            if letter in mine:
                link = mine[letter]
                want = {"icon": link["icon"], "icon_input_sha": link["sha256"]}
                extra = {"icon_mode": link.get("icon_mode"), "visually_identical": link.get("visually_identical")}
            elif letter in bad:
                want = {"icon": None}
                extra = {"icon_input_sha": None, "icon_mode": None, "visually_identical": None}
            else:
                continue
            for key, value in want.items():
                if var.get(key) != value:
                    var[key] = value
                    changed = True
            for key, value in extra.items():
                changed = _put(var, key, value) or changed
    return changed


# --- renderer ------------------------------------------------------------------------------------------------------


def check_renderer(synty_glb_root) -> Path:
    """The configured synty-glb root, or ``RendererUnavailable``. Touches nothing on disk but reads."""
    if not synty_glb_root:
        raise RendererUnavailable("synty_glb_root is not configured (set it in config.yaml or SYNTI_SYNTY_GLB_ROOT)")
    root = Path(synty_glb_root)
    if not (root / THREE_ENTRY).is_file():
        raise RendererUnavailable(f"three.js not found under synty_glb_root ({root / THREE_ENTRY} is missing)")
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError as exc:
        raise RendererUnavailable("the playwright package is not installed") from exc
    return root


def _launch_browser(playwright, gpu: bool):
    """Chromium from Playwright's own install first (a pinned build), then an installed Chrome."""
    args = list(_GPU_ARGS if gpu else _SOFTWARE_ARGS)
    try:
        return playwright.chromium.launch(headless=True, args=args)
    except Exception:  # noqa: BLE001 - any launch failure falls through to the Chrome channel
        return playwright.chromium.launch(channel="chrome", headless=True, args=args)


_MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".wasm": "application/wasm",
         ".glb": "model/gltf-binary", ".json": "application/json; charset=utf-8", ".png": "image/png",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"

    def log_message(self, fmt, *args):  # quiet
        return

    def do_GET(self):  # noqa: N802
        route = unquote(urlparse(self.path).path)
        target = None
        if route.startswith("/harness/"):
            target = self._inside(self.server.harness_dir, route[len("/harness/"):])
        elif route.startswith("/three/"):
            target = self._inside(self.server.three_dir, route[len("/three/"):])
        elif route.startswith("/glb/"):
            target = self.server.glbs.get(route[len("/glb/"):])
        elif route.startswith("/tex/"):
            target = self.server.textures.get(route[len("/tex/"):])
        if target is None or not Path(target).is_file():
            self.send_error(404, route)
            return
        data = Path(target).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _MIME.get(Path(target).suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _inside(base: Path, rel: str) -> Path | None:
        path = (base / rel).resolve()
        try:
            path.relative_to(base.resolve())
        except ValueError:
            return None  # a path that climbs out of the served directory
        return path


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, harness_dir: Path, three_dir: Path):
        super().__init__(("127.0.0.1", 0), _Handler)  # loopback only, ephemeral port: no network
        self.harness_dir, self.three_dir = harness_dir, three_dir
        self.glbs: dict[str, Path] = {}
        self.textures: dict[str, Path] = {}


class Renderer:
    """One headless Chromium page kept open for a whole batch. Use as a context manager."""

    def __init__(self, synty_glb_root: Path, *, gpu: bool = False, timeout_ms: int = 120_000):
        self.root = synty_glb_root
        self.gpu = gpu
        self.timeout_ms = timeout_ms
        self._server = None
        self._pw = None
        self._browser = None
        self._page = None
        self._log: list[str] = []
        self._glb_keys: dict[str, str] = {}
        self._tex_keys: dict[str, str] = {}

    def __enter__(self) -> "Renderer":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RendererUnavailable("the playwright package is not installed") from exc
        self._server = _Server(HARNESS_DIR, self.root / "node_modules" / "three")
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        try:
            self._pw = sync_playwright().start()
            self._browser = _launch_browser(self._pw, self.gpu)
            self._boot()
        except RendererUnavailable:
            self.__exit__(None, None, None)
            raise
        except Exception as exc:  # noqa: BLE001 - Playwright raises its own Error types
            self.__exit__(None, None, None)
            raise RendererUnavailable(f"could not start Chromium: {str(exc).splitlines()[0] if str(exc) else exc!r}") from exc
        return self

    def _boot(self) -> None:
        """(Re)open the harness page; a page that cannot start means the renderer is unusable."""
        if self._page is not None:
            self._page.close()
        self._page = self._browser.new_page(viewport={"width": 64, "height": 64}, device_scale_factor=1)
        self._page.set_default_timeout(self.timeout_ms)
        self._log = []
        self._page.on("console", lambda m: self._log.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        self._page.on("pageerror", lambda e: self._log.append(f"pageerror: {e}"))
        port = self._server.server_address[1]
        self._page.goto(f"http://127.0.0.1:{port}/harness/icon.html", wait_until="domcontentloaded")
        try:
            self._page.wait_for_function("() => window.__ICON__ && window.__ICON__.ready", timeout=60_000)
        except Exception as exc:  # noqa: BLE001
            detail = "; ".join(self._log[-3:]) or str(exc).splitlines()[0]
            raise RendererUnavailable(f"the icon harness did not start: {detail}") from exc

    def __exit__(self, *exc) -> None:
        for closer in (lambda: self._browser and self._browser.close(), lambda: self._pw and self._pw.stop(),
                       lambda: self._server and (self._server.shutdown(), self._server.server_close())):
            try:
                closer()
            except Exception:  # noqa: BLE001 - tearing down must not mask the real error
                pass
        self._browser = self._pw = self._server = self._page = None

    def _glb_url(self, path: Path) -> str:
        key = self._glb_keys.get(str(path))
        if key is None:
            key = f"{len(self._glb_keys)}.glb"
            self._glb_keys[str(path)] = key
            self._server.glbs[key] = path
        return f"/glb/{key}"

    def _tex_url(self, path: Path) -> str:
        key = self._tex_keys.get(str(path))
        if key is None:
            key = f"{len(self._tex_keys)}{path.suffix.lower()}"
            self._tex_keys[str(path)] = key
            self._server.textures[key] = path
        return f"/tex/{key}"

    def render(self, glb: Path, nodes, scale: float, item_basis, shield: bool, size: int,
               texture: Path | None = None, force_blend: bool = False) -> np.ndarray:
        """Premultiplied RGBA (``size`` x ``size`` x 4 uint8, top row first) of one GLB. Raises ``RenderError``.

        ``texture`` (a variant's atlas image) replaces the base-colour map of every drawn material that has one.
        ``force_blend`` (the blank-render retry) draws every MASK material (alphaTest > 0) as BLEND; false leaves the
        render exactly as it was before the option existed.
        """
        try:
            bounds = self._page.evaluate("p => window.iconPrepare(p)", {
                "glb": self._glb_url(glb), "nodes": nodes, "scale": float(scale),
                "itemBasis": [[int(c) for c in row] for row in item_basis],
                "camDir": list(camera_direction(shield)),
                "texture": self._tex_url(texture) if texture is not None else None,
                "forceBlend": bool(force_blend),
            })
            frustum = fit_frustum(bounds["min"], bounds["max"])
            out = self._page.evaluate("p => window.iconRender(p)", {"frustum": frustum, "size": size})
            raw = base64.b64decode(out["pixels"])
            if len(raw) != size * size * 4:
                raise RenderError(f"the page returned {len(raw)} bytes, expected {size * size * 4}")
        except RenderError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc).splitlines()[0] if str(exc) else repr(exc)
            try:
                self._boot()  # a crashed context must not poison the rest of the batch
            except Exception:  # noqa: BLE001
                pass
            raise RenderError(message) from exc
        return np.frombuffer(raw, dtype=np.uint8).reshape(size, size, 4)[::-1].copy()  # GL rows run bottom-up


# --- batch ---------------------------------------------------------------------------------------------------------


def _selection(glb_node) -> list[str] | None:
    if glb_node is None:
        return None
    return [glb_node] if isinstance(glb_node, str) else list(glb_node)


def _check_size(size: int) -> None:
    if not isinstance(size, int) or size % THUMB_SIZE or not (THUMB_SIZE <= size <= MAX_SIZE):
        raise InputError(f"--size must be a multiple of {THUMB_SIZE} between {THUMB_SIZE} and {MAX_SIZE}, got {size}")


def _render_icon_pair(renderer, glb, nodes, scale, item_basis, shield, size, texture=None) -> tuple[bytes, bytes, str | None]:
    """``(icon PNG, thumbnail PNG, icon_mode)`` of one render. A picture with no visible pixel is drawn once more with
    MASK materials forced to BLEND (``icon_mode`` ``"blend_retry"``); still blank raises ``RenderError("blank_render")``.
    A first render that shows something is used as it is (mode None) and the retry never runs."""
    extra = {} if texture is None else {"texture": texture}
    px = renderer.render(glb, nodes, scale, item_basis, shield, size, **extra)
    mode = None
    if is_blank(px):
        px = renderer.render(glb, nodes, scale, item_basis, shield, size, **extra, force_blend=True)
        if is_blank(px):
            raise RenderError(BLANK_RENDER)
        mode = ICON_MODE_BLEND
    return encode_png(unpremultiply(px)), encode_png(unpremultiply(downsample(px, THUMB_SIZE))), mode


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def render_icons(records: list[dict], out_dir: Path, *, size: int = 256, variants: bool = False,
                 threejs_v2_dir: Path, synty_glb_root: Path, rebuild: bool = False, gpu: bool = False,
                 report: dict | None = None, extracted_root: Path | None = None) -> dict[str, dict]:
    """``id -> {icon, thumb, sha256}`` for every record that has an icon after the call (rendered or still valid).

    ``icon``/``thumb`` are relative to ``out_dir``'s parent (the directory.json folder); ``sha256`` is the input hash
    (``visuals.icon_input_sha``); ``icon_mode`` is present (``"blend_retry"``) only for an icon that needed the BLEND
    retry, and a skipped icon keeps the mode stored in its record. Raises ``RendererUnavailable`` before anything is
    written. ``report`` (optional) receives ``rendered``, ``skipped``, ``failed`` (``[{id, error}]``) and
    ``blend_retry`` (the ids, variants as ``<id>@<L>``, that were rendered through the retry in this call; an asset
    that is blank even then fails with the error ``blank_render``) so a caller can list them.
    With ``variants`` the colourway icons of every record's ``visuals.variants`` are rendered as well. They need
    ``extracted_root`` (the folder with one extracted tree per pack) to find each sibling texture; without it the
    call raises ``InputError``. Their outcome goes into ``report["variants"]`` = ``{rendered: ["<id>@<L>"],
    skipped: [...], failed: [{id, variant, error}], visually_identical: ["<id>@<L>"], links: {id: {L: {icon, thumb,
    sha256[, icon_mode][, visually_identical]}}}}``; ``visually_identical`` is set on every link whose default icon
    and colourway icon both exist (``icon_difference`` under ``VISUALLY_IDENTICAL_MAX_SHARE``); the return value
    stays the default icons only. Records without ``geometry`` or ``files.glb`` get no icon and are not mentioned.
    """
    _check_size(size)
    root = check_renderer(synty_glb_root)
    if variants and extracted_root is None:
        raise InputError("--variants needs extracted_root (the folder with one extracted tree per pack)")
    base_dir = out_dir.parent
    results: dict[str, dict] = {}
    rendered: list[str] = []
    skipped: list[str] = []
    failed: list[dict] = []
    todo: list[tuple[dict, Path, str, str, str]] = []
    sha_cache: dict[Path, str] = {}
    vtodo: list[tuple[dict, Path, dict, Path, str, str, str]] = []  # rec, glb, variant, texture, sha, icon, thumb
    vlinks: dict[str, dict[str, dict]] = {}
    vrendered: list[str] = []
    vskipped: list[str] = []
    vfailed: list[dict] = []
    blend: list[str] = []
    listing_cache: dict = {}
    tex_sha: dict[Path, str] = {}

    for rec in sorted(records, key=lambda r: r["id"]):
        geo, rel = rec.get("geometry"), (rec.get("files") or {}).get("glb")
        if not geo or not rel:
            continue
        glb = Path(threejs_v2_dir) / rel
        try:
            if glb not in sha_cache:
                sha_cache[glb] = file_sha256(glb)
        except OSError as exc:
            failed.append({"id": rec["id"], "error": f"glb not readable: {exc.strerror or exc}"})
            continue
        scale = float((rec["files"].get("glb_scale")) or 1.0)
        sha = icon_input_sha(sha_cache[glb], rec["files"].get("glb_node"), scale, geo["item_basis"])
        icon_rel, thumb_rel = link_paths(out_dir, rec["pack"], rec["asset_id"])
        if needs_render(rec.get("visuals") or {}, sha, icon_rel, thumb_rel, base_dir, size, rebuild):
            todo.append((rec, glb, sha, icon_rel, thumb_rel))
        else:
            skipped.append(rec["id"])
            results[rec["id"]] = {"icon": icon_rel, "thumb": thumb_rel, "sha256": sha}
            if (rec.get("visuals") or {}).get("icon_mode") == ICON_MODE_BLEND:  # the stored mode stays true
                results[rec["id"]]["icon_mode"] = ICON_MODE_BLEND
        if variants:
            _plan_variants(rec, glb, sha, out_dir, Path(extracted_root), size, rebuild, listing_cache, tex_sha,
                           vtodo, vlinks, vskipped, vfailed)

    if todo or vtodo:
        with Renderer(root, gpu=gpu) as renderer:  # raises RendererUnavailable before any file is touched
            for rec, glb, sha, icon_rel, thumb_rel in todo:
                files = rec["files"]
                scale = float(files.get("glb_scale") or 1.0)
                shield = rec.get("kind") == "shield" or rec.get("archetype") == "shield"
                try:
                    big, small, mode = _render_icon_pair(renderer, glb, _selection(files.get("glb_node")), scale,
                                                         rec["geometry"]["item_basis"], shield, size)
                except RenderError as exc:
                    failed.append({"id": rec["id"], "error": str(exc)})
                    for rel in (icon_rel, thumb_rel):  # no stale picture is left as if current (INV-8)
                        (base_dir / rel).unlink(missing_ok=True)
                    continue
                _write_atomic(base_dir / icon_rel, big)
                _write_atomic(base_dir / thumb_rel, small)
                rendered.append(rec["id"])
                results[rec["id"]] = {"icon": icon_rel, "thumb": thumb_rel, "sha256": sha}
                if mode:
                    results[rec["id"]]["icon_mode"] = mode
                    blend.append(rec["id"])
            for rec, glb, var, texture, vsha, icon_rel, thumb_rel in vtodo:
                files = rec["files"]
                shield = rec.get("kind") == "shield" or rec.get("archetype") == "shield"
                letter = var["variant_id"]
                try:
                    big, small, mode = _render_icon_pair(renderer, glb, _selection(files.get("glb_node")),
                                                         float(files.get("glb_scale") or 1.0),
                                                         rec["geometry"]["item_basis"], shield, size, texture=texture)
                except RenderError as exc:
                    vfailed.append({"id": rec["id"], "variant": letter, "error": str(exc)})
                    for rel in (icon_rel, thumb_rel):  # no stale picture is left as if current (INV-8)
                        (base_dir / rel).unlink(missing_ok=True)
                    continue
                _write_atomic(base_dir / icon_rel, big)
                _write_atomic(base_dir / thumb_rel, small)
                vrendered.append(f"{rec['id']}@{letter}")
                link = vlinks.setdefault(rec["id"], {})[letter] = {"icon": icon_rel, "thumb": thumb_rel, "sha256": vsha}
                if mode:
                    link["icon_mode"] = mode
                    blend.append(f"{rec['id']}@{letter}")

    identical = _flag_identical(base_dir, results, vlinks) if variants else []
    if report is not None:
        report.update(rendered=sorted(rendered), skipped=sorted(skipped), failed=failed, blend_retry=sorted(blend))
        if variants:
            report["variants"] = {"rendered": sorted(vrendered), "skipped": sorted(vskipped),
                                  "failed": sorted(vfailed, key=lambda f: (f["id"], f["variant"])),
                                  "visually_identical": identical, "links": vlinks}
    return results


def _flag_identical(base_dir: Path, results: dict[str, dict], vlinks: dict[str, dict[str, dict]]) -> list[str]:
    """Set ``visually_identical`` on every colourway link whose default icon and own icon are both on disk (judged from
    the PNGs, so skipped icons are covered and the answer does not depend on how the files got there). A pair that
    cannot be compared (missing default, unreadable or differently sized PNG) gets no key. Returns the ``<id>@<L>`` that
    look the same as the default icon, sorted."""
    same: list[str] = []
    for rid, per_letter in vlinks.items():
        default = results.get(rid)
        if default is None:
            continue
        for letter, link in per_letter.items():
            try:
                share = icon_difference(base_dir / default["icon"], base_dir / link["icon"])
            except (OSError, ValueError):
                continue
            link["visually_identical"] = share < VISUALLY_IDENTICAL_MAX_SHARE
            if link["visually_identical"]:
                same.append(f"{rid}@{letter}")
    return sorted(same)


def _plan_variants(rec, glb, default_sha, out_dir, extracted_root, size, rebuild, listing_cache, tex_sha,
                   vtodo, vlinks, vskipped, vfailed) -> None:
    """Sort each colourway of ``rec`` into render / still valid / failed (renders nothing, writes nothing new).

    A variant whose material or texture cannot be resolved (missing file, a ``.tga`` the harness cannot load, a
    pack tree that is not there) is a per-variant failure with the reason, not a batch failure; its stale files
    are removed so no old picture stays as if it were current.
    """
    base_dir = out_dir.parent
    tree = extracted_root / rec["pack"]
    for var in (rec.get("visuals") or {}).get("variants") or []:
        letter = var["variant_id"]
        icon_rel, thumb_rel = variant_link_paths(out_dir.name, rec["pack"], rec["asset_id"], letter)
        try:
            if not tree.is_dir():
                raise TextureNotFound(f"no extracted tree for pack {rec['pack']}")
            texture = resolve_variant_texture(tree, var["source"], listing_cache)
            if texture not in tex_sha:
                tex_sha[texture] = file_sha256(texture)
        except (TextureNotFound, OSError) as exc:
            vfailed.append({"id": rec["id"], "variant": letter, "error": str(exc)})
            for rel in (icon_rel, thumb_rel):
                (base_dir / rel).unlink(missing_ok=True)
            continue
        vsha = variant_input_sha(default_sha, tex_sha[texture], letter)
        # a variant stores no thumb path: it is derived from the icon path, so a stored link is "current" only
        # when it is exactly the derived icon path
        stored = {"icon": var.get("icon"), "icon_input_sha": var.get("icon_input_sha"),
                  "thumb": thumb_rel if var.get("icon") == icon_rel else None}
        if needs_render(stored, vsha, icon_rel, thumb_rel, base_dir, size, rebuild):
            vtodo.append((rec, glb, var, texture, vsha, icon_rel, thumb_rel))
        else:
            vskipped.append(f"{rec['id']}@{letter}")
            link = vlinks.setdefault(rec["id"], {})[letter] = {"icon": icon_rel, "thumb": thumb_rel, "sha256": vsha}
            if var.get("icon_mode") == ICON_MODE_BLEND:  # a valid picture that is not drawn again keeps its mode
                link["icon_mode"] = ICON_MODE_BLEND


# --- CLI -----------------------------------------------------------------------------------------------------------


def _csv(value) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in str(value).split(",") if p.strip()]


def _run(args, cfg) -> int:
    from ..cli import _catalogs, _threejs_v2, emit_json as _emit
    from .directory import DIRECTORY_NAME, EXCLUDED_NAME, read_json, weapons_dir
    from .schema import validate_directory

    ensure_sole_runner()  # exit 2 naming the pid when another inventory process runs: both write cache files
    size = getattr(args, "size", 256)
    _check_size(size)
    root = check_renderer(cfg.get("synty_glb_root"))  # exit 5 before anything is read or written
    want_variants = bool(getattr(args, "variants", False))
    extracted = cfg.get("extracted_root")
    if want_variants and not extracted:
        raise InputError("--variants needs extracted_root in the config (the folder with one extracted tree per pack)")
    wdir = weapons_dir(_catalogs(args, cfg))
    dpath = wdir / DIRECTORY_NAME
    if not dpath.is_file():
        raise InputError(f"no weapon directory at {dpath}; run `weapons build` first")
    directory = read_json(dpath)

    packs, ids = _csv(getattr(args, "pack", None)), _csv(getattr(args, "ids", None))
    known_packs = {w["pack"] for w in directory["weapons"]}
    if packs and set(packs) - known_packs:
        raise InputError(f"unknown pack(s): {', '.join(sorted(set(packs) - known_packs))}")
    known_ids = {w["id"] for w in directory["weapons"]}
    if ids and set(ids) - known_ids:
        raise InputError("unknown id(s): " + ", ".join(sorted(set(ids) - known_ids)))
    chosen = [w for w in directory["weapons"]
              if (not packs or w["pack"] in packs) and (not ids or w["id"] in ids)]

    wanted = [w for w in chosen if w.get("geometry") and w["files"].get("glb")]
    threejs = _threejs_v2(cfg)
    if wanted and threejs is None:
        raise InputError("threejs_v2 is not configured: the GLBs cannot be found")

    report: dict = {}
    results = render_icons(
        wanted, wdir / ICONS_DIRNAME, size=size, variants=want_variants,
        threejs_v2_dir=threejs, synty_glb_root=root, rebuild=bool(getattr(args, "rebuild", False)),
        gpu=bool(getattr(args, "gpu", False)), report=report,
        extracted_root=Path(extracted) if want_variants else None,
    )
    failed_ids = {f["id"] for f in report["failed"]}
    changed = apply_links(directory, results, failed_ids)
    vreport = report.get("variants")
    if vreport is not None:
        vfailed: dict[str, set[str]] = {}
        for f in vreport["failed"]:
            vfailed.setdefault(f["id"], set()).add(f["variant"])
        changed = apply_variant_links(directory, vreport["links"], vfailed) or changed
    written = False
    if changed:
        excluded_path = wdir / EXCLUDED_NAME
        errors = validate_directory(directory, read_json(excluded_path) if excluded_path.is_file() else None)
        if errors:
            raise WeaponsError("the directory violates weapon-directory/1 after linking icons:\n  "
                               + "\n  ".join(errors[:25]), 6, {"errors": errors})
        text = to_text(directory)
        if dpath.read_bytes() != text.encode("utf-8"):  # byte-identical content is never rewritten
            write_text_lf(dpath, text)
            written = True

    summary = {
        "ok": True, "size": size, "rendered": report["rendered"], "skipped": report["skipped"],
        "failed": report["failed"], "no_geometry": sum(1 for w in chosen if w not in wanted),
        "blend_retry": len(report["blend_retry"]),
        "directory": dpath.name, "directory_written": written,
    }
    if vreport is not None:
        summary["variants"] = {"rendered": vreport["rendered"], "skipped": vreport["skipped"],
                               "failed": vreport["failed"], "visually_identical": len(vreport["visually_identical"])}
    _emit(summary)
    return EXIT_OK


def cmd(args, cfg) -> int:
    """``synty-inventory weapons icons``. Exit 5 when the renderer is unavailable (nothing written, INV-8)."""
    from ..cli import emit_json as _emit

    try:
        return _run(args, cfg)
    except RendererUnavailable as exc:
        _emit({"ok": False, "error": str(exc), "renderer": "unavailable"})
        return EXIT_RENDERER
    except WeaponsError as exc:
        _emit({"ok": False, "error": str(exc), **exc.details})
        return exc.code
