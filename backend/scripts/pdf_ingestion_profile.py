"""
Profiles PDF text extraction over a folder of PDFs: statistics and short excerpts only, never full text.

Run from backend/:
    python scripts/pdf_ingestion_profile.py <folder>                        # census: one row per PDF (pypdf, the production engine)
    python scripts/pdf_ingestion_profile.py <folder> --compare a.pdf b.pdf  # side-by-side of pypdf vs pypdfium2 / pdfminer.six
Comparison engines are optional and used only if importable (e.g. installed into a scratch folder and put on PYTHONPATH).
"""

import argparse
import collections
import difflib
import re
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pypdf import PdfReader

from app.services.document_parsing import UnreadableDocument, extract_text_from_pdf, normalize_pdf_text

try:
    import pypdfium2
except ImportError:
    pypdfium2 = None
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except ImportError:
    pdfminer_extract_text = None

LIGATURES = "".join(chr(c) for c in range(0xFB00, 0xFB07))
LABEL_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9 /()#.,'-]{1,45}:\s*\S")


def pypdf_pages(data: bytes):
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        reader.decrypt("")
    return [page.extract_text() or "" for page in reader.pages]


def pdfium_pages(data: bytes):
    pdf = pypdfium2.PdfDocument(data)
    try:
        return [pdf[i].get_textpage().get_text_bounded() for i in range(len(pdf))]
    finally:
        pdf.close()


def pdfminer_pages(data: bytes):
    return pdfminer_extract_text(BytesIO(data)).split("\f")


def join_pages(pages):
    return "\n\n".join(p for p in (normalize_pdf_text(p) for p in pages) if p)


def raw_stats(raw_pages):
    raw = "\n".join(raw_pages)
    private_use = collections.Counter(f"U+{ord(c):04X}" for c in raw if 0xE000 <= ord(c) <= 0xF8FF)
    lines = [ln for ln in raw.split("\n") if ln.strip()]
    return {
        "chars": len(raw),
        "lines": len(lines),
        "avg_line": round(sum(len(ln) for ln in lines) / len(lines)) if lines else 0,
        "label_value_pct": round(100 * sum(bool(LABEL_VALUE.match(ln.strip())) for ln in lines) / len(lines)) if lines else 0,
        "ligatures": sum(raw.count(c) for c in LIGATURES),
        "exotic_spaces": sum(raw.count(chr(c)) for c in (0x00A0, 0x202F, 0x2007, 0x2009, 0x200A)),
        "soft_hyphen": raw.count(chr(0x00AD)),
        "zero_width": sum(raw.count(chr(c)) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)),
        "private_use": dict(private_use),
        "replacement": raw.count(chr(0xFFFD)),
        "cid_tokens": len(re.findall(r"\(cid:\d+\)", raw)),
        "hyphen_eol": len(re.findall(r"[A-Za-z]-\n[a-z]", raw)),
        "long_tokens": len([t for t in raw.split() if len(t) >= 25 and t.isalpha()]),
        "letter_runs": len(re.findall(r"(?:\b[A-Za-z] ){5,}[A-Za-z]\b", raw)),
    }


def repeated_lines(pages):
    if len(pages) < 2:
        return 0
    seen = collections.Counter()
    for page in pages:
        for ln in {ln.strip() for ln in normalize_pdf_text(page).split("\n") if len(ln.strip()) >= 4}:
            seen[ln] += 1
    return sum(1 for n in seen.values() if n >= 2)


def fonts_and_meta(reader):
    meta = reader.metadata
    producer = (getattr(meta, "producer", None) or "-")[:24] if meta else "-"
    creator = (getattr(meta, "creator", None) or "-")[:24] if meta else "-"
    names = []
    try:
        for page in reader.pages[:2]:
            font_dict = page["/Resources"].get_object().get("/Font", {}).get_object()
            for ref in font_dict.values():
                names.append(str(ref.get_object().get("/BaseFont", "?")).lstrip("/").split("+")[-1])
    except Exception:
        pass
    return producer, creator, ",".join(sorted(set(names)))[:34] or "-"


def census(folder: Path):
    files = sorted(folder.rglob("*.pdf"))
    rows, totals = [], collections.Counter()
    producers = collections.Counter()
    print(f"{'file':32s} {'pg':>2} {'KB':>4} {'enc':>3} {'fld':>3} {'chars':>5} {'ln':>3} {'avg':>3} {'l:v%':>4} {'lig':>3} {'nbsp':>4} {'pua':>3} {'cid':>3} {'hy-':>3} {'rep':>3}  producer / creator / fonts / first line")
    for path in files:
        data = path.read_bytes()
        try:
            reader = PdfReader(BytesIO(data))
            enc = reader.is_encrypted
            if enc:
                reader.decrypt("")
            fields = len(reader.get_fields() or {})
            producer, creator, fonts = fonts_and_meta(reader)
            pages = [p.extract_text() or "" for p in reader.pages]
            st = raw_stats(pages)
            try:
                first = extract_text_from_pdf(data).split("\n", 1)[0][:44]
                prod_ok = True
            except UnreadableDocument as exc:
                first, prod_ok = f"[production ingestion refuses: {str(exc)[:40]}]", False
        except Exception as exc:  # census must survive any single bad file
            print(f"{path.name:32s} ERROR {type(exc).__name__}")
            totals["error"] += 1
            continue
        rep = repeated_lines(pages)
        pua_total = sum(st["private_use"].values())
        print(f"{path.name[:32]:32s} {len(pages):>2} {len(data)/1024:>4.1f} {'Y' if enc else '-':>3} {fields or '-':>3} {st['chars']:>5} {st['lines']:>3} {st['avg_line']:>3} {st['label_value_pct']:>4} "
              f"{st['ligatures'] or '-':>3} {st['exotic_spaces'] or '-':>4} {pua_total or '-':>3} {st['cid_tokens'] or '-':>3} {st['hyphen_eol'] or '-':>3} {rep or '-':>3}  {producer} / {creator} / {fonts} / {first!r}")
        producers[f"{producer} | {creator}"] += 1
        totals["files"] += 1
        totals["encrypted"] += enc
        totals["with_form_fields"] += bool(fields)
        totals["multi_page"] += len(pages) > 1
        totals["no_text_layer"] += st["chars"] == 0
        totals["production_refuses"] += not prod_ok
        for key in ("ligatures", "exotic_spaces", "soft_hyphen", "zero_width", "replacement", "cid_tokens", "hyphen_eol", "long_tokens", "letter_runs"):
            totals["files_with_" + key] += st[key] > 0
        totals["files_with_private_use"] += pua_total > 0
        totals["files_with_repeated_lines"] += rep > 0
    print("\n=== census totals ===")
    for key, value in totals.items():
        print(f"  {key}: {value}")
    print("  producer | creator:", dict(producers))


def excerpt(text: str, n: int) -> str:
    return re.sub(r"\s+", " ", text)[:n]


def compare(folder: Path, names, n_excerpt: int):
    engines = [("pypdf", pypdf_pages)]
    if pypdfium2:
        engines.append(("pdfium", pdfium_pages))
    if pdfminer_extract_text:
        engines.append(("pdfminer", pdfminer_pages))
    for name in names:
        path = next(iter(folder.rglob(name)))
        data = path.read_bytes()
        texts = {label: join_pages(fn(data)) for label, fn in engines}
        print(f"\n##### {path.name}: " + "  ".join(f"{label}={len(t.split())} words/{len(t)} chars" for label, t in texts.items()))
        print(f"  excerpt (pypdf): {excerpt(texts['pypdf'], n_excerpt)!r}")
        pairs = [("pdfium", "pypdf"), ("pdfminer", "pypdf"), ("pdfium", "pdfminer")]
        for b, a in pairs:
            if a not in texts or b not in texts:
                continue
            ta, tb = texts[a].split(), texts[b].split()
            word_ratio = difflib.SequenceMatcher(None, ta, tb, autojunk=False).ratio()
            ca, cb = re.sub(r"\s+", "", texts[a]), re.sub(r"\s+", "", texts[b])
            char_ratio = difflib.SequenceMatcher(None, ca, cb, autojunk=False).ratio() if len(ca) < 20000 else float("nan")
            print(f"  {b:8s} vs {a:8s}: word-level agreement {word_ratio:.3f} | content-only (spaces/line breaks ignored) {char_ratio:.3f}")
            shown = 0
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
                if tag == "equal" or shown >= 6:
                    continue
                shown += 1
                print(f"      {tag:8s} {a}: {' '.join(ta[i1:i2])[:60]!r}  ->  {b}: {' '.join(tb[j1:j2])[:60]!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--compare", nargs="+", metavar="FILE")
    parser.add_argument("--excerpt", type=int, default=150)
    args = parser.parse_args()
    if args.compare:
        compare(Path(args.folder), args.compare, args.excerpt)
    else:
        census(Path(args.folder))
