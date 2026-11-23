import base64
import pathlib

import fitz  # PyMuPDF

_TEXT_SUFFIXES = {".txt", ".md"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class UnsupportedDocumentError(Exception):
    pass


class DocumentReadError(Exception):
    pass


def read_input(path: str) -> dict:
    suffix = pathlib.Path(path).suffix.lower()

    if suffix == ".pdf":
        result = _read_pdf(path)
    elif suffix in _TEXT_SUFFIXES:
        with open(path, "r", encoding="utf-8") as f:
            result = {"text": f.read(), "images": []}
    elif suffix in _IMAGE_SUFFIXES:
        with open(path, "rb") as f:
            raw = f.read()
        result = {"text": "", "images": [base64.b64encode(raw).decode()]}
    else:
        raise UnsupportedDocumentError(f"unsupported document type: {path}")

    if not result["text"].strip() and not result["images"]:
        raise DocumentReadError(f"document has no extractable text or images: {path}")

    return result


def _read_pdf(path: str) -> dict:
    try:
        doc = fitz.open(path)
    except Exception as e:
        raise DocumentReadError(f"could not read PDF: {path} ({e})") from e

    texts = []
    images = []
    try:
        for page in doc:
            page_text = page.get_text()
            texts.append(page_text)
            # Only render a page image when the page itself has no
            # extractable text (likely a scanned page) — attaching a
            # vision-model image for every page of a normal, text-heavy
            # PDF bloats the prompt far past a typical Ollama context
            # window for no benefit.
            if not page_text.strip():
                images.append(base64.b64encode(page.get_pixmap().tobytes("png")).decode())
    finally:
        doc.close()

    return {"text": "\n\n".join(texts), "images": images}
