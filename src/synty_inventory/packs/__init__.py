"""Pack-level metadata: profile (§4.3), suggestion, and G1 contact sheet.

Asset-level catalogs (``<catalogs>/<PACK_ID>.json``) already carry everything
a per-asset query needs. This package adds the one level up: "what kind of
pack is this, and which packs cover a game brief" (studio_pipeline_spec.md
§3.3).
"""

from __future__ import annotations
