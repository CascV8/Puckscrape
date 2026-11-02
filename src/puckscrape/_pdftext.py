"""Positioned text from the IIHF's report PDFs (stats.iihf.com/Hydra).

The reports are made by Apache FOP 0.20.5, which embeds subset Arial fonts with
no ToUnicode map and no cmap: the text is glyph ids only, so ordinary PDF text
extraction returns noise. Each glyph's outline is still a copy of Arial's, so
glyphs are identified by a hash of their outline points (composites, the accented
letters, by their parts), looked up in ``data/arial_glyphs.json`` (hash ->
character, built from Arial by ``scripts/build_arial_glyphs.py``; it holds
hashes, not the font).
"""

from __future__ import annotations

import hashlib
import io
import json
import struct
from dataclasses import dataclass
from functools import cache
from importlib import resources

import pypdf
from pypdf.generic import ContentStream

UNKNOWN = "�"


@cache
def _glyph_table() -> dict[str, str]:
    return json.loads(resources.files("puckscrape").joinpath("data/arial_glyphs.json").read_text("utf-8"))


def _simple_points(g: bytes) -> tuple:
    """A simple glyph's contours as absolute (x, y, on-curve) points, hinting left out
    (Arial's builds differ in their hinting instructions, not their outlines)."""
    n = struct.unpack(">h", g[:2])[0]
    ends = struct.unpack(f">{n}H", g[10:10 + 2 * n])
    count = ends[-1] + 1 if n else 0
    p = 10 + 2 * n
    p += 2 + struct.unpack(">H", g[p:p + 2])[0]   # skip the instructions
    flags = []
    while len(flags) < count:
        f = g[p]
        p += 1
        flags.append(f)
        if f & 8:
            flags.extend([f] * g[p])
            p += 1
    flags = flags[:count]

    def coords(short_bit, same_bit):
        nonlocal p
        out, v = [], 0
        for f in flags:
            if f & short_bit:
                d = g[p]
                p += 1
                v += d if f & same_bit else -d
            elif not f & same_bit:
                v += struct.unpack(">h", g[p:p + 2])[0]
                p += 2
            out.append(v)
        return out

    xs = coords(2, 16)
    ys = coords(4, 32)
    return ends, tuple(zip(xs, ys, (f & 1 for f in flags)))


def _components(g: bytes) -> list[tuple]:
    """A composite glyph's parts: (glyph id, x offset, y offset, transform)."""
    out, p = [], 10
    while True:
        flags, gid = struct.unpack(">HH", g[p:p + 4])
        p += 4
        if flags & 1:
            a1, a2 = struct.unpack(">hh", g[p:p + 4])
            p += 4
        else:
            a1, a2 = struct.unpack(">bb", g[p:p + 2])
            p += 2
        if flags & 8:
            xf = g[p:p + 2]
            p += 2
        elif flags & 0x40:
            xf = g[p:p + 4]
            p += 4
        elif flags & 0x80:
            xf = g[p:p + 8]
            p += 8
        else:
            xf = b""
        out.append((gid, a1, a2, flags & 2, xf))
        if not flags & 0x20:
            return out


def glyph_keys(outlines: list[bytes]) -> list[str | None]:
    """A key per glyph id that's the same for the same drawing in any Arial build or subset:
    simple glyphs by their points, composites (accented letters) by their parts' keys."""
    keys: dict[int, str | None] = {}

    def key(gid: int, depth: int = 0) -> str | None:
        if gid in keys:
            return keys[gid]
        g = outlines[gid] if gid < len(outlines) else b""
        if not g or depth > 8:
            k = None
        elif struct.unpack(">h", g[:2])[0] >= 0:
            k = hashlib.sha1(repr(_simple_points(g)).encode()).hexdigest()[:16]
        else:
            parts = [(key(c, depth + 1), a1, a2, xy, xf.hex()) for c, a1, a2, xy, xf in _components(g)]
            k = hashlib.sha1(("C" + repr(parts)).encode()).hexdigest()[:16]
        keys[gid] = k
        return k

    return [key(i) for i in range(len(outlines))]


# ---------------------------------------------------------------- TrueType

def _tables(font: bytes) -> dict[str, tuple[int, int]]:
    n = struct.unpack(">H", font[4:6])[0]
    out = {}
    for i in range(n):
        tag, _, off, length = struct.unpack(">4sIII", font[12 + 16 * i:28 + 16 * i])
        out[tag.decode("latin-1")] = (off, length)
    return out


def glyph_outlines(font: bytes) -> list[bytes]:
    """Every glyph's raw 'glyf' record, by glyph id."""
    t = _tables(font)
    long_loca = struct.unpack(">h", font[t["head"][0] + 50:t["head"][0] + 52])[0] == 1
    lo, ll = t["loca"]
    if long_loca:
        offs = struct.unpack(f">{ll // 4}I", font[lo:lo + ll])
    else:
        offs = [x * 2 for x in struct.unpack(f">{ll // 2}H", font[lo:lo + ll])]
    go = t["glyf"][0]
    return [font[go + offs[i]:go + offs[i + 1]] for i in range(len(offs) - 1)]


def unicode_cmap(font: bytes) -> dict[int, str]:
    """glyph id -> character, from a full font's Windows Unicode (3,1) format-4 cmap."""
    t = _tables(font)
    co = t["cmap"][0]
    for i in range(struct.unpack(">H", font[co + 2:co + 4])[0]):
        pid, eid, off = struct.unpack(">HHI", font[co + 4 + 8 * i:co + 12 + 8 * i])
        if (pid, eid) != (3, 1):
            continue
        sub = co + off
        segx2 = struct.unpack(">H", font[sub + 6:sub + 8])[0]
        seg = segx2 // 2
        ends = struct.unpack(f">{seg}H", font[sub + 14:sub + 14 + segx2])
        starts = struct.unpack(f">{seg}H", font[sub + 16 + segx2:sub + 16 + 2 * segx2])
        deltas = struct.unpack(f">{seg}h", font[sub + 16 + 2 * segx2:sub + 16 + 3 * segx2])
        ro_at = sub + 16 + 3 * segx2
        range_offs = struct.unpack(f">{seg}H", font[ro_at:ro_at + segx2])
        out: dict[int, str] = {}
        for s in range(seg):
            for c in range(starts[s], ends[s] + 1):
                if c == 0xFFFF:
                    continue
                if range_offs[s] == 0:
                    g = (c + deltas[s]) & 0xFFFF
                else:
                    p = ro_at + 2 * s + range_offs[s] + 2 * (c - starts[s])
                    g = struct.unpack(">H", font[p:p + 2])[0]
                    g = (g + deltas[s]) & 0xFFFF if g else 0
                if g:
                    out.setdefault(g, chr(c))
        return out
    raise ValueError("font has no Windows Unicode cmap")


# ---------------------------------------------------------------- PDF

@dataclass(frozen=True)
class Span:
    x: float
    y: float
    text: str
    bold: bool


def _by_shape(outline: bytes) -> str:
    """Fallback for a glyph no Arial build in the table matches: a hyphen is a lone
    rectangle, wider than tall, around mid-height (2013-14 reports' hyphen differs by a unit).
    Everything else stays UNKNOWN."""
    try:
        if struct.unpack(">h", outline[:2])[0] == 1:
            _, pts = _simple_points(outline)
            xs, ys = {p[0] for p in pts}, {p[1] for p in pts}
            if len(pts) == 4 and len(xs) == 2 and len(ys) == 2 and all(p[2] for p in pts):
                w, h = max(xs) - min(xs), max(ys) - min(ys)
                if w > 1.5 * h and 400 < min(ys) + h / 2 < 900:   # Arial's hyphen sits at ~ 0.3 em of 2048
                    return "-"
    except (struct.error, IndexError, ValueError):
        pass
    return UNKNOWN


class _Font:
    def __init__(self, font_dict):
        self.bold = "bold" in str(font_dict.get("/BaseFont", "")).lower()
        self.cid = "/DescendantFonts" in font_dict
        self.map: dict[int, str] = {}
        if self.cid:
            desc = font_dict["/DescendantFonts"][0].get_object()["/FontDescriptor"].get_object()
            table = _glyph_table()
            outlines = glyph_outlines(desc["/FontFile2"].get_object().get_data())
            for gid, (outline, k) in enumerate(zip(outlines, glyph_keys(outlines))):
                self.map[gid] = " " if not outline else table.get(k) or _by_shape(outline)

    def decode(self, raw: bytes) -> str:
        if not self.cid:
            return raw.decode("cp1252", errors="replace")
        return "".join(self.map.get(int.from_bytes(raw[i:i + 2], "big"), UNKNOWN)
                       for i in range(0, len(raw) - 1, 2))


def spans(pdf: bytes) -> list[list[Span]]:
    """Every text-showing operation in the PDF, page by page, with its start position.

    FOP writes each table cell as its own text-showing operation, so a span is a
    cell (or a run of words within one)."""
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    pages = []
    for page in reader.pages:
        fonts = {name: _Font(f.get_object()) for name, f in page["/Resources"].get("/Font", {}).items()}
        out: list[Span] = []
        font = None
        tm = [1, 0, 0, 1, 0, 0]   # text matrix (only translation matters for FOP's output)
        line = [0.0, 0.0]
        leading = 0.0
        for operands, op in ContentStream(page.get_contents(), reader).operations:
            if op == b"BT":
                tm, line = [1, 0, 0, 1, 0, 0], [0.0, 0.0]
            elif op == b"Tf":
                font = fonts.get(operands[0])
            elif op == b"TL":
                leading = float(operands[0])
            elif op in (b"Td", b"TD"):
                line = [line[0] + float(operands[0]), line[1] + float(operands[1])]
                if op == b"TD":
                    leading = -float(operands[1])
            elif op == b"Tm":
                tm = [float(v) for v in operands]
                line = [tm[4], tm[5]]
            elif op == b"T*":
                line = [line[0], line[1] - leading]
            elif op in (b"Tj", b"'", b'"', b"TJ") and font is not None:
                if op in (b"'", b'"'):
                    line = [line[0], line[1] - leading]
                parts = operands[-1] if op == b"TJ" else [operands[-1]]
                text = ""
                for p in parts:
                    if isinstance(p, (bytes, str)) or hasattr(p, "original_bytes"):
                        raw = p.original_bytes if hasattr(p, "original_bytes") else (
                            p if isinstance(p, bytes) else p.encode("latin-1"))
                        text += font.decode(raw)
                    elif float(p) < -200:   # a wide negative kern is a word gap
                        text += " "
                if text.strip():
                    out.append(Span(round(line[0], 1), round(line[1], 1), text, font.bold))
        pages.append(out)
    return pages


def rows(page: list[Span], tolerance: float = 1.5) -> list[list[Span]]:
    """Spans grouped into lines (top to bottom), each line left to right."""
    lines: list[list[Span]] = []
    for s in sorted(page, key=lambda s: (-s.y, s.x)):
        if lines and abs(lines[-1][0].y - s.y) <= tolerance:
            lines[-1].append(s)
        else:
            lines.append([s])
    return [sorted(line, key=lambda s: s.x) for line in lines]
