"""Stdlib-only writer for tiny synthetic PDFs used by the ingestion tests (standard Helvetica, no embedded fonts)."""

from io import BytesIO


def _pdf_string(text: str) -> bytes:
    data = text.encode("cp1252", errors="replace")
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _page_stream(lines) -> bytes:
    if not lines:
        return b"72 700 200 50 re S"  # a drawn box and no text operators at all: what an image-only scan looks like to a text extractor
    parts = [b"BT", b"/F1 11 Tf", b"14 TL", b"72 720 Td"]
    for line in lines:
        if line:
            parts.append(b"(" + _pdf_string(line) + b") Tj")
        parts.append(b"T*")
    parts.append(b"ET")
    return b"\n".join(parts)


def make_pdf(pages) -> bytes:
    """pages: one list of text lines per page. An empty list makes a page with no text at all."""
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    kids = []
    next_num = 4
    for lines in pages:
        page_num, stream_num = next_num, next_num + 1
        next_num += 2
        kids.append(f"{page_num} 0 R")
        stream = _page_stream(lines)
        objects[stream_num] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        objects[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_num} 0 R >>"
        ).encode()
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()

    out = BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = out.tell()
        out.write(f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n")
    xref_at = out.tell()
    size = len(objects) + 1
    out.write(f"xref\n0 {size}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for num in range(1, size):
        out.write(f"{offsets[num]:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode())
    return out.getvalue()


def encrypt_pdf(pdf_bytes: bytes, user_password: str, algorithm: str = "RC4-128", owner_password=None) -> bytes:
    """RC4 needs no crypto package to write. An empty user_password with an owner_password gives an owner-only (restrictions) file."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf_bytes)))
    writer.encrypt(user_password, owner_password=owner_password, algorithm=algorithm)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
