"""Pure-Python decoders for ``EXT_meshopt_compression`` bufferViews.

The threejs-v2 GLBs store every vertex stream and index buffer through
meshoptimizer's vertex codec (v0) and index codec (v0/v1). Reading the exact
geometry (for socket / mating-face analysis) therefore needs these two
decoders; they are small enough to carry here rather than pulling in a
native ``meshoptimizer`` wheel — the GLB JSON chunk + ``struct`` is enough.

Only what the catalog needs is implemented: the vertex codec without
filters (positions) and the triangle index codec. Filtered streams
(octahedral normals, quaternions, exponential) and the v1 vertex codec
raise ``MeshoptError`` so callers fall back gracefully.

Ported from the public-domain-equivalent (MIT) meshoptimizer reference
(``vertexcodec.cpp`` / ``indexcodec.cpp``).
"""

from __future__ import annotations

from typing import Sequence


class MeshoptError(ValueError):
    """Unsupported or malformed meshopt stream."""


# --- vertex codec (version 0) ----------------------------------------------

_VERTEX_HEADER = 0xA0
_BLOCK_SIZE_BYTES = 8192
_BLOCK_MAX = 256
_GROUP = 16
_TAIL_MAX = 32


def _block_size(vertex_size: int) -> int:
    result = _BLOCK_SIZE_BYTES // vertex_size
    result &= ~(_GROUP - 1)
    return result if result < _BLOCK_MAX else _BLOCK_MAX


def _decode_bytes_group(data: bytes, pos: int, out: bytearray, out_pos: int, bitslog2: int) -> int:
    """Decode one 16-byte group; returns the new ``pos``."""
    if bitslog2 == 0:
        for k in range(_GROUP):
            out[out_pos + k] = 0
        return pos
    if bitslog2 == 3:
        out[out_pos:out_pos + _GROUP] = data[pos:pos + _GROUP]
        return pos + _GROUP
    if bitslog2 == 1:
        var = pos + 4
        for k in range(_GROUP):
            byte = data[pos + (k >> 2)]
            shift = 6 - 2 * (k & 3)
            v = (byte >> shift) & 3
            if v == 3:
                v = data[var]
                var += 1
            out[out_pos + k] = v
        return var
    # bitslog2 == 2
    var = pos + 8
    for k in range(_GROUP):
        byte = data[pos + (k >> 1)]
        shift = 4 - 4 * (k & 1)
        v = (byte >> shift) & 15
        if v == 15:
            v = data[var]
            var += 1
        out[out_pos + k] = v
    return var


def _decode_bytes(data: bytes, pos: int, out: bytearray, count_aligned: int) -> int:
    header_size = (count_aligned // _GROUP + 3) // 4
    header = pos
    pos += header_size
    for i in range(0, count_aligned, _GROUP):
        g = i // _GROUP
        bitslog2 = (data[header + (g >> 2)] >> ((g & 3) * 2)) & 3
        pos = _decode_bytes_group(data, pos, out, i, bitslog2)
    return pos


def decode_vertex_buffer(data: bytes, vertex_count: int, vertex_size: int) -> bytes:
    """Decode a meshopt ``ATTRIBUTES`` stream into ``vertex_count *
    vertex_size`` raw bytes (no filter applied)."""
    if not data or (data[0] & 0xF0) != _VERTEX_HEADER:
        raise MeshoptError("not a meshopt vertex stream")
    if (data[0] & 0x0F) != 0:
        raise MeshoptError(f"unsupported vertex codec version {data[0] & 0x0F}")
    if not 1 <= vertex_size <= 256 or vertex_size % 4:
        raise MeshoptError(f"bad vertex size {vertex_size}")
    tail = max(vertex_size, _TAIL_MAX)
    if len(data) < 1 + tail:
        raise MeshoptError("vertex stream too short")
    last = bytearray(data[len(data) - vertex_size:])
    out = bytearray(vertex_count * vertex_size)
    block = _block_size(vertex_size)
    planes = bytearray(_BLOCK_MAX * vertex_size)
    pos = 1
    end = len(data) - tail
    v0 = 0
    while v0 < vertex_count:
        n = min(block, vertex_count - v0)
        aligned = (n + _GROUP - 1) & ~(_GROUP - 1)
        for k in range(vertex_size):
            if pos > end:
                raise MeshoptError("vertex stream truncated")
            pos = _decode_bytes(data, pos, planes, aligned)
            # ``planes`` is reused per byte-lane: consume immediately.
            base = v0 * vertex_size + k
            acc = last[k]
            for i in range(n):
                d = planes[i]
                acc = (acc + ((d >> 1) ^ (-(d & 1) & 0xFF))) & 0xFF
                out[base + i * vertex_size] = acc
            last[k] = acc
        v0 += n
    return bytes(out)


# --- index codec (version 0 / 1) -------------------------------------------

_INDEX_HEADER = 0xE0


def _decode_vbyte(data: bytes, pos: int) -> tuple[int, int]:
    lead = data[pos]
    pos += 1
    if lead < 128:
        return lead, pos
    result = lead & 127
    shift = 7
    for _ in range(4):
        group = data[pos]
        pos += 1
        result |= (group & 127) << shift
        shift += 7
        if group < 128:
            break
    return result, pos


def decode_index_buffer(data: bytes, index_count: int) -> list[int]:
    """Decode a meshopt ``TRIANGLES`` stream into a flat index list."""
    if not data or (data[0] & 0xF0) != _INDEX_HEADER:
        raise MeshoptError("not a meshopt index stream")
    version = data[0] & 0x0F
    if version > 1:
        raise MeshoptError(f"unsupported index codec version {version}")
    if index_count % 3:
        raise MeshoptError("index count not a multiple of 3")
    if len(data) < 1 + index_count // 3 + 16:
        raise MeshoptError("index stream too short")
    code = 1
    pos = 1 + index_count // 3
    codeaux_table = data[len(data) - 16:]
    fecmax = 13 if version >= 1 else 15

    out = [0] * index_count
    edgefifo = [(0, 0)] * 16
    vertexfifo = [0] * 16
    eoff = 0
    voff = 0
    nxt = 0
    last = 0

    def decode_index(p: int, prev: int) -> tuple[int, int]:
        v, p = _decode_vbyte(data, p)
        d = (v >> 1) ^ -(v & 1)
        return prev + d, p

    for i in range(0, index_count, 3):
        codetri = data[code]
        code += 1
        if codetri < 0xF0:
            fe = codetri >> 4
            a, b = edgefifo[(eoff - 1 - fe) & 15]
            fec = codetri & 15
            if fec < fecmax:
                if fec == 0:
                    c = nxt
                    nxt += 1
                    vertexfifo[voff] = c
                    voff = (voff + 1) & 15
                else:
                    c = vertexfifo[(voff - 1 - fec) & 15]
            else:
                if fec != 15:
                    c = last + (fec - (fec ^ 3))
                else:
                    c, pos = decode_index(pos, last)
                last = c
                vertexfifo[voff] = c
                voff = (voff + 1) & 15
            out[i], out[i + 1], out[i + 2] = a, b, c
            edgefifo[eoff] = (c, b)
            eoff = (eoff + 1) & 15
            edgefifo[eoff] = (a, c)
            eoff = (eoff + 1) & 15
        else:
            if codetri < 0xFE:
                codeaux = codeaux_table[codetri & 15]
                fea = 0
            else:
                codeaux = data[pos]
                pos += 1
                fea = 0 if codetri == 0xFE else 15
                if codeaux == 0:
                    nxt = 0
            feb = codeaux >> 4
            fec = codeaux & 15
            if fea == 0:
                a = nxt
                nxt += 1
            else:
                a = 0
            if feb == 0:
                b = nxt
                nxt += 1
            else:
                b = vertexfifo[(voff - feb) & 15]
            if fec == 0:
                c = nxt
                nxt += 1
            else:
                c = vertexfifo[(voff - fec) & 15]
            if fea == 15:
                a, pos = decode_index(pos, last)
                last = a
            if feb == 15:
                b, pos = decode_index(pos, last)
                last = b
            if fec == 15:
                c, pos = decode_index(pos, last)
                last = c
            out[i], out[i + 1], out[i + 2] = a, b, c
            vertexfifo[voff] = a
            voff = (voff + 1) & 15
            vertexfifo[voff] = b
            if feb == 0 or feb == 15:
                voff = (voff + 1) & 15
            vertexfifo[voff] = c
            if fec == 0 or fec == 15:
                voff = (voff + 1) & 15
            edgefifo[eoff] = (b, a)
            eoff = (eoff + 1) & 15
            edgefifo[eoff] = (c, b)
            eoff = (eoff + 1) & 15
            edgefifo[eoff] = (a, c)
            eoff = (eoff + 1) & 15
    return out


def triangles_from_indices(indices: Sequence[int]) -> list[tuple[int, int, int]]:
    return [(indices[i], indices[i + 1], indices[i + 2]) for i in range(0, len(indices) - 2, 3)]
