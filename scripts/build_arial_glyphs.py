"""Build src/puckscrape/data/arial_glyphs.json: glyph-outline hash -> character
for Arial (regular, bold, italic, bold italic), so the IIHF's report PDFs can be
read (see puckscrape/_pdftext.py). It stores hashes, not the fonts.

    python scripts/build_arial_glyphs.py C:/Windows/Fonts/arial.ttf C:/Windows/Fonts/arialbd.ttf \
        C:/Windows/Fonts/ariali.ttf C:/Windows/Fonts/arialbi.ttf

Only Latin, Greek and Cyrillic letters, digits and common punctuation are kept.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from puckscrape._pdftext import glyph_keys, glyph_outlines, unicode_cmap  # noqa: E402

KEEP = [(0x20, 0x7E), (0xA0, 0x24F), (0x370, 0x3FF), (0x400, 0x4FF), (0x1E00, 0x1EFF), (0x2010, 0x2044), (0x20AC, 0x20AC)]


def keep(ch: str) -> bool:
    return any(lo <= ord(ch) <= hi for lo, hi in KEEP)


table: dict[str, str] = {}
for path in sys.argv[1:]:
    font = Path(path).read_bytes()
    cmap = unicode_cmap(font)
    outlines = glyph_outlines(font)
    for gid, (outline, key) in enumerate(zip(outlines, glyph_keys(outlines))):
        ch = cmap.get(gid)
        if ch and outline and key and keep(ch):
            # Identical outlines (Latin A, Greek Alpha, Cyrillic A) keep the first, Latin, character.
            table.setdefault(key, ch)

out = Path(__file__).resolve().parents[1] / "src" / "puckscrape" / "data" / "arial_glyphs.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(dict(sorted(table.items())), ensure_ascii=False, separators=(",", ":")), "utf-8")
print(f"{len(table)} glyphs -> {out}")
