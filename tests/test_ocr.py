# tests/test_ocr.py
import pytest
from pathlib import Path
from ocr.engine import extract_text_from_image
from ocr.pdf_processor import extract_text_from_pdf

FIXTURES = Path("tests/fixtures")

async def test_extract_from_image():
    # Requires: tests/fixtures/sample.png — any image with visible text
    text = await extract_text_from_image(str(FIXTURES / "sample.png"))
    assert isinstance(text, str)
    assert len(text) > 0

async def test_extract_from_pdf():
    # Requires: tests/fixtures/sample.pdf — any PDF with readable text
    text = await extract_text_from_pdf(str(FIXTURES / "sample.pdf"))
    assert isinstance(text, str)
    assert len(text) > 0
