# PDF test fixtures

Everything here is synthetic: no real person, facility or report. Real test PDFs
stay outside git (`backend/data/pdf_test_reports/` is ignored, and `.gitignore`
lets `*.pdf` through only directly inside this folder).

| File | What it is | Used by |
|---|---|---|
| `chromium_case_report.html` + `.pdf` | 3-page report printed by headless Edge (Chromium/Skia, embedded subset fonts): a letterhead and a footer on every page, numbered sections, a form-style table, a wrapped `9-year-old`, and a deliberately soft-hyphenated sentence | `test_pdf_static_fixtures.py` |
| `aes128_user_password.pdf`, `aes256_user_password.pdf`, `aes128_owner_only.pdf` | Tiny AES-encrypted PDFs (user password `secret`; the owner-only file has owner password `ownersecret`). Each one is refused at a different point inside pypdf: `decrypt("")` returns NOT_DECRYPTED (AES-128, user password), the constructor raises `DependencyError` (AES-256), `extract_text()` raises `DependencyError` (AES-128, owner password only) | `test_pdf_static_fixtures.py` |

The other PDFs in the tests (text, multi-page, no-text, damaged, RC4-encrypted)
are built at test time by `tests/pdf_fixtures.py`.

The AES tests assume no crypto package (`cryptography`, PyCryptodome) is installed,
which is the decision recorded for PDF support (D4). If one is installed, the
owner-only test skips itself.

## Regenerating

Bytes differ between runs (Edge stamps metadata, AES uses random salts); the tests
assert behaviour, not bytes.

Chromium report (PowerShell; needs Microsoft Edge):

```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless=new --disable-gpu --no-first-run `
  --user-data-dir="$env:TEMP\edge_pdf_profile" --no-pdf-header-footer `
  --print-to-pdf="C:\mednexus-public-health\backend\tests\fixtures\chromium_case_report.pdf" `
  "file:///C:/mednexus-public-health/backend/tests/fixtures/chromium_case_report.html"
```

AES files: pypdf needs a crypto package only to WRITE them, so use a throwaway
install that is not part of the project:

```powershell
pip install --target "$env:TEMP\crypto_libs" pycryptodome
$env:PYTHONPATH = "$env:TEMP\crypto_libs"
# then run the script below from backend/ with the project's Python
```

```python
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from tests.pdf_fixtures import make_pdf

plain = make_pdf([["Patient: Test Person", "Age: 34 years"]])


def write(name, user_pw, owner_pw, algorithm):
    writer = PdfWriter(clone_from=PdfReader(BytesIO(plain)))
    writer.encrypt(user_pw, owner_password=owner_pw, algorithm=algorithm)
    with open(f"tests/fixtures/{name}", "wb") as f:
        writer.write(f)


write("aes128_user_password.pdf", "secret", None, "AES-128")
write("aes256_user_password.pdf", "secret", None, "AES-256")
write("aes128_owner_only.pdf", "", "ownersecret", "AES-128")
```
