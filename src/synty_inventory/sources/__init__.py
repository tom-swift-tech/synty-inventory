"""Enrichment data sources merged into a catalog record.

Each module here loads one external source (asset-viewer profiles, the
threejs-v2 VLM-reviewed catalogs, or raw GLB geometry) and exposes small,
side-effect-free readers plus an ``apply_*`` overlay that mutates one asset
dict in place using ``merge.may_overlay`` for provenance precedence.
"""
