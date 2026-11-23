import base64

import pytest

from qwen_test_automation.ingestion.doc_reader import (
    read_input,
    UnsupportedDocumentError,
    DocumentReadError,
)


def test_read_input_text_file(tmp_path):
    p = tmp_path / "ticket.txt"
    p.write_text("Yêu cầu: cho phép đăng nhập bằng OTP")
    result = read_input(str(p))
    assert result["text"] == "Yêu cầu: cho phép đăng nhập bằng OTP"
    assert result["images"] == []


def test_read_input_markdown_file(tmp_path):
    p = tmp_path / "ticket.md"
    p.write_text("# Ticket\n\nNoi dung")
    result = read_input(str(p))
    assert "Noi dung" in result["text"]
    assert result["images"] == []


def test_read_input_image_file(tmp_path):
    p = tmp_path / "screenshot.png"
    raw = b"\x89PNG\r\n\x1a\nfake-but-nonempty-bytes"
    p.write_bytes(raw)
    result = read_input(str(p))
    assert result["text"] == ""
    assert result["images"] == [base64.b64encode(raw).decode()]


def test_read_input_unsupported_extension_raises(tmp_path):
    p = tmp_path / "ticket.docx"
    p.write_text("irrelevant")
    with pytest.raises(UnsupportedDocumentError):
        read_input(str(p))


def test_read_input_pdf_text_only_page_produces_no_image(tmp_path):
    import fitz  # PyMuPDF

    p = tmp_path / "ticket.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Yeu cau dang nhap OTP")
    doc.save(str(p))
    doc.close()

    result = read_input(str(p))
    assert "Yeu cau dang nhap OTP" in result["text"]
    assert result["images"] == []


def test_read_input_pdf_textless_page_produces_image(tmp_path):
    import fitz  # PyMuPDF

    p = tmp_path / "scan.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Yeu cau dang nhap OTP")
    doc.new_page()  # blank/textless page, treated as a scanned image
    doc.save(str(p))
    doc.close()

    result = read_input(str(p))
    assert len(result["images"]) == 1
    assert isinstance(result["images"][0], str) and len(result["images"][0]) > 0


def test_read_input_corrupt_pdf_raises_clear_error(tmp_path):
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"%PDF-1.4 this is not a real pdf body")
    with pytest.raises(DocumentReadError, match="could not"):
        read_input(str(p))


def test_read_input_empty_text_file_raises(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("   \n  ")
    with pytest.raises(DocumentReadError, match="empty"):
        read_input(str(p))
