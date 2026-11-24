"""Pure-Python Snappy (raw block & Xerial framed) and GZIP decompressor.

KNIME stores executed tables in `data.zip -> data.bin` using Xerial Snappy
framing (`\\x82SNAPPY\\x00`), GZIP, or raw uncompressed bytes. Implementing
Snappy in pure Python avoids any C-extension installation issues on Windows,
macOS, or Linux.
"""

from __future__ import annotations

import gzip
import struct

XERIAL_MAGIC = b"\x82SNAPPY\x00"
GZIP_MAGIC = b"\x1f\x8b"


def decompress_snappy_block(src: bytes | memoryview) -> bytes:
    """Decompress a single raw Snappy-compressed block."""
    mv = memoryview(src)
    n = len(mv)
    pos = 0

    # Read little-endian varint uncompressed length
    ulen = 0
    shift = 0
    while pos < n:
        b = mv[pos]
        pos += 1
        ulen |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7

    out = bytearray()
    out_extend = out.extend
    out_append = out.append

    while pos < n:
        tag = mv[pos]
        pos += 1
        ttype = tag & 0x03

        if ttype == 0:
            # Literal bytes
            length = tag >> 2
            if length < 60:
                length += 1
            else:
                nbytes = length - 59
                length = int.from_bytes(mv[pos : pos + nbytes], "little") + 1
                pos += nbytes
            out_extend(mv[pos : pos + length])
            pos += length
        else:
            if ttype == 1:
                length = ((tag >> 2) & 0x07) + 4
                offset = ((tag & 0xE0) << 3) | mv[pos]
                pos += 1
            elif ttype == 2:
                length = (tag >> 2) + 1
                offset = mv[pos] | (mv[pos + 1] << 8)
                pos += 2
            else:
                length = (tag >> 2) + 1
                offset = int.from_bytes(mv[pos : pos + 4], "little")
                pos += 4

            if offset == 0 or offset > len(out):
                raise ValueError(f"Invalid Snappy copy offset {offset} at out_len={len(out)}")

            if offset >= length:
                start = len(out) - offset
                out_extend(out[start : start + length])
            elif offset == 1:
                out_extend(bytes([out[-1]]) * length)
            else:
                # Overlapping RLE-style copy
                for _ in range(length):
                    out_append(out[-offset])

    if len(out) != ulen:
        raise ValueError(f"Snappy uncompressed length mismatch: got {len(out)}, expected {ulen}")
    return bytes(out)


def decompress_knime_stream(data: bytes, compression: str | None = None) -> bytes:
    """Decompress KNIME `data.bin` payload (Xerial Snappy, raw Snappy, GZIP, or plain)."""
    if not data:
        return b""

    comp = (compression or "").strip().upper()
    if data[:8] == XERIAL_MAGIC:
        # 8-byte magic + 4-byte version + 4-byte compatible_version
        pos = 16
        chunks: list[bytes] = []
        total = len(data)
        while pos + 4 <= total:
            clen = struct.unpack_from(">I", data, pos)[0]
            pos += 4
            chunks.append(decompress_snappy_block(memoryview(data)[pos : pos + clen]))
            pos += clen
        return b"".join(chunks)

    if data[:2] == GZIP_MAGIC or comp == "GZIP":
        return gzip.decompress(data)

    if comp == "SNAPPY":
        return decompress_snappy_block(data)

    # NONE / uncompressed
    return data
