"""
tests/unit/test_data_processor.py — Unit tests for modules/data_processor.py

Focuses on _validate_upload (the fixed BUG-002 logic), detect_file_type,
and the ProcessResult dataclass.
"""
import sys
import os
import io
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from modules.data_processor import (
    _validate_upload,
    detect_file_type,
    _MAX_FILE_BYTES,
    ProcessResult,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _xlsx_bytes() -> bytes:
    """Minimal valid XLSX magic (ZIP PK header)."""
    return bytes([0x50, 0x4B, 0x03, 0x04]) + b"\x00" * 100

def _xls_bytes() -> bytes:
    return bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1]) + b"\x00" * 100

def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n%..." + b"\x00" * 100

def _csv_bytes() -> bytes:
    return b"date,outlet,revenue\n2026-07-01,Lounge,100000\n"

def _png_bytes() -> bytes:
    return bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 100

def _fake_exe_bytes() -> bytes:
    return b"MZ" + b"\x00" * 100  # Windows PE header

def _file(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)


# ── detect_file_type ─────────────────────────────────────────────────────────

class TestDetectFileType:
    def test_pdf(self):
        assert detect_file_type("report.pdf") == "pdf"

    def test_xlsx(self):
        assert detect_file_type("data.xlsx") == "excel"

    def test_xls(self):
        assert detect_file_type("data.xls") == "excel"

    def test_xlsm(self):
        assert detect_file_type("data.xlsm") == "excel"

    def test_csv(self):
        assert detect_file_type("data.csv") == "text"

    def test_tsv(self):
        assert detect_file_type("data.tsv") == "text"

    def test_txt(self):
        assert detect_file_type("data.txt") == "text"

    def test_docx(self):
        assert detect_file_type("report.docx") == "docx"

    def test_json(self):
        assert detect_file_type("data.json") == "json"

    def test_png(self):
        assert detect_file_type("scan.png") == "image"

    def test_jpg(self):
        assert detect_file_type("scan.jpg") == "image"

    def test_msg(self):
        assert detect_file_type("email.msg") == "msg"

    def test_unknown(self):
        assert detect_file_type("weird.xyz") == "unknown"

    def test_case_insensitive(self):
        assert detect_file_type("REPORT.PDF") == "pdf"
        assert detect_file_type("DATA.XLSX") == "excel"


# ── _validate_upload ─────────────────────────────────────────────────────────

class TestValidateUploadSize:
    def test_oversized_file_rejected(self):
        big = io.BytesIO(_xlsx_bytes() + b"\x00" * (_MAX_FILE_BYTES + 1))
        err = _validate_upload(big, "big.xlsx")
        assert err is not None
        assert "MB" in err

    def test_exactly_max_size_accepted(self):
        # Build a minimal valid XLSX just under the limit
        data = _xlsx_bytes()[:4] + b"\x00" * (_MAX_FILE_BYTES - 4)
        err = _validate_upload(io.BytesIO(data), "ok.xlsx")
        # Size is fine; magic bytes match for xlsx
        assert err is None


class TestValidateUploadBinaryFormats:
    def test_valid_xlsx_accepted(self):
        assert _validate_upload(_file(_xlsx_bytes()), "report.xlsx") is None

    def test_valid_xls_accepted(self):
        assert _validate_upload(_file(_xls_bytes()), "data.xls") is None

    def test_valid_xlsm_accepted(self):
        assert _validate_upload(_file(_xlsx_bytes()), "data.xlsm") is None

    def test_valid_pdf_accepted(self):
        assert _validate_upload(_file(_pdf_bytes()), "report.pdf") is None

    def test_exe_renamed_to_xlsx_rejected(self):
        err = _validate_upload(_file(_fake_exe_bytes()), "malware.xlsx")
        assert err is not None
        assert "magic bytes" in err.lower() or "valid" in err.lower()

    def test_xlsx_renamed_to_xls_rejected(self):
        # ZIP magic is wrong for .xls (expects OLE2)
        err = _validate_upload(_file(_xlsx_bytes()), "data.xls")
        assert err is not None


class TestValidateUploadTextFormats:
    def test_valid_csv_accepted(self):
        assert _validate_upload(_file(_csv_bytes()), "data.csv") is None

    def test_valid_tsv_accepted(self):
        data = b"date\toutlet\trevenue\n2026-07-01\tLounge\t100000\n"
        assert _validate_upload(_file(data), "data.tsv") is None

    def test_valid_txt_accepted(self):
        assert _validate_upload(_file(b"hello world\n"), "notes.txt") is None

    def test_binary_data_as_csv_rejected(self):
        # Use null-byte-dense data — null bytes >1% trigger the binary detector.
        # Real CSV/JSON/HTML files never contain null bytes; executables, ZIP
        # headers, and OLE2 containers do (the fake_exe_bytes fixture is all \x00
        # after the MZ marker, which is >1% nulls).
        binary_data = b"MZ" + b"\x00" * 200  # 200/202 = 99% null bytes
        err = _validate_upload(_file(binary_data), "data.csv")
        assert err is not None
        assert "binary" in err.lower() or "null" in err.lower() or "text" in err.lower()

    def test_json_accepted(self):
        assert _validate_upload(_file(b'{"key": "value"}\n'), "data.json") is None

    def test_html_accepted(self):
        assert _validate_upload(_file(b"<html><body>hi</body></html>"), "page.html") is None


class TestValidateUploadImages:
    def test_valid_png_accepted(self):
        assert _validate_upload(_file(_png_bytes()), "scan.png") is None

    def test_exe_renamed_to_png_rejected(self):
        err = _validate_upload(_file(_fake_exe_bytes()), "photo.png")
        assert err is not None

    def test_valid_jpg_accepted(self):
        data = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100
        assert _validate_upload(_file(data), "photo.jpg") is None


class TestValidateUploadUnsupportedExtension:
    def test_exe_rejected(self):
        err = _validate_upload(_file(_fake_exe_bytes()), "virus.exe")
        assert err is not None
        assert "not supported" in err.lower() or "not allowed" in err.lower()

    def test_zip_rejected(self):
        err = _validate_upload(_file(_xlsx_bytes()), "archive.zip")
        assert err is not None

    def test_py_rejected(self):
        err = _validate_upload(_file(b"import os\nos.system('rm -rf /')"), "hack.py")
        assert err is not None

    def test_seek_reset_after_validation(self):
        """File pointer must be back at 0 after validate so the parser can read it."""
        f = _file(_xlsx_bytes())
        _validate_upload(f, "data.xlsx")
        assert f.tell() == 0


# ── ProcessResult ─────────────────────────────────────────────────────────────

class TestProcessResult:
    def test_defaults(self):
        r = ProcessResult(success=True, file_name="x.xlsx", message="ok")
        assert r.df is None
        assert r.report_date is None
        assert r.total_revenue == 0.0
        assert r.total_pax == 0.0
        assert r.inserted == 0
        assert r.skipped == 0
        assert r.warnings == []

    def test_warnings_list_not_shared(self):
        """Each instance must get its own warnings list (dataclass mutable default)."""
        r1 = ProcessResult(success=True, file_name="a.xlsx", message="")
        r2 = ProcessResult(success=True, file_name="b.xlsx", message="")
        r1.warnings.append("warn")
        assert r2.warnings == []
