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

ICON_HARNESS_VERSION = 1  # bump when the harness, framing or encoding changes what a render looks like
ICONS_DIRNAME = "icons"
THUMB_SIZE = 64
MAX_SIZE = 1024
FILL = 0.88  # the opaque bounding box fills this share of the long image edge (6 % padding each side)
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


def apply_links(directory: dict, results: dict[str, dict], failed: set[str]) -> bool:
    """Write the icon links into the directory's records (in place); False when nothing changed.

    A rendered or skipped record gets its three link fields; a failed one is reset to null even when an older file
    exists (INV-8: no stale icon is presented as current). Every other field is untouched.
    """
    changed = False
    for rec in directory["weapons"]:
        vis = rec["visuals"]
        if rec["id"] in results:
            want = {"icon": results[rec["id"]]["icon"], "thumb": results[rec["id"]]["thumb"],
                    "icon_input_sha": results[rec["id"]]["sha256"]}
        elif rec["id"] in failed:
            want = {"icon": None, "thumb": None, "icon_input_sha": None}
        else:
            continue
        for key, value in want.items():
            if vis.get(key) != value:
                vis[key] = value
                changed = True
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
         ".glb": "model/gltf-binary", ".json": "application/json; charset=utf-8"}


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

    def render(self, glb: Path, nodes, scale: float, item_basis, shield: bool, size: int) -> np.ndarray:
        """Premultiplied RGBA (``size`` x ``size`` x 4 uint8, top row first) of one GLB. Raises ``RenderError``."""
        try:
            bounds = self._page.evaluate("p => window.iconPrepare(p)", {
                "glb": self._glb_url(glb), "nodes": nodes, "scale": float(scale),
                "itemBasis": [[int(c) for c in row] for row in item_basis],
                "camDir": list(camera_direction(shield)),
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


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def render_icons(records: list[dict], out_dir: Path, *, size: int = 256, variants: bool = False,
                 threejs_v2_dir: Path, synty_glb_root: Path, rebuild: bool = False, gpu: bool = False,
                 report: dict | None = None) -> dict[str, dict]:
    """``id -> {icon, thumb, sha256}`` for every record that has an icon after the call (rendered or still valid).

    ``icon``/``thumb`` are relative to ``out_dir``'s parent (the directory.json folder); ``sha256`` is the input hash
    (``visuals.icon_input_sha``). Raises ``RendererUnavailable`` before anything is written. ``report`` (optional)
    receives ``rendered``, ``skipped`` and ``failed`` (``[{id, error}]``) so a caller can list them.
    ``variants`` is accepted for the slice W5 interface and ignored: only the default colourway is rendered.
    Records without ``geometry`` or ``files.glb`` get no icon and are not mentioned.
    """
    _check_size(size)
    root = check_renderer(synty_glb_root)
    base_dir = out_dir.parent
    results: dict[str, dict] = {}
    rendered: list[str] = []
    skipped: list[str] = []
    failed: list[dict] = []
    todo: list[tuple[dict, Path, str, str, str]] = []
    sha_cache: dict[Path, str] = {}

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

    if todo:
        with Renderer(root, gpu=gpu) as renderer:  # raises RendererUnavailable before any file is touched
            for rec, glb, sha, icon_rel, thumb_rel in todo:
                files = rec["files"]
                scale = float(files.get("glb_scale") or 1.0)
                shield = rec.get("kind") == "shield" or rec.get("archetype") == "shield"
                try:
                    px = renderer.render(glb, _selection(files.get("glb_node")), scale,
                                         rec["geometry"]["item_basis"], shield, size)
                    big = encode_png(unpremultiply(px))
                    small = encode_png(unpremultiply(downsample(px, THUMB_SIZE)))
                except RenderError as exc:
                    failed.append({"id": rec["id"], "error": str(exc)})
                    for rel in (icon_rel, thumb_rel):  # no stale picture is left as if current (INV-8)
                        (base_dir / rel).unlink(missing_ok=True)
                    continue
                _write_atomic(base_dir / icon_rel, big)
                _write_atomic(base_dir / thumb_rel, small)
                rendered.append(rec["id"])
                results[rec["id"]] = {"icon": icon_rel, "thumb": thumb_rel, "sha256": sha}

    if report is not None:
        report.update(rendered=sorted(rendered), skipped=sorted(skipped), failed=failed)
    return results


# --- CLI -----------------------------------------------------------------------------------------------------------


def _csv(value) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in str(value).split(",") if p.strip()]


def _run(args, cfg) -> int:
    from ..cli import _catalogs, _threejs_v2, emit_json as _emit
    from .directory import DIRECTORY_NAME, EXCLUDED_NAME, read_json, weapons_dir
    from .schema import validate_directory

    size = getattr(args, "size", 256)
    _check_size(size)
    root = check_renderer(cfg.get("synty_glb_root"))  # exit 5 before anything is read or written
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
        wanted, wdir / ICONS_DIRNAME, size=size, variants=bool(getattr(args, "variants", False)),
        threejs_v2_dir=threejs, synty_glb_root=root, rebuild=bool(getattr(args, "rebuild", False)),
        gpu=bool(getattr(args, "gpu", False)), report=report,
    )
    failed_ids = {f["id"] for f in report["failed"]}
    changed = apply_links(directory, results, failed_ids)
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
        "directory": dpath.name, "directory_written": written,
    }
    if getattr(args, "variants", False):
        summary["variants"] = "not built yet: only the default colourway was rendered"
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
