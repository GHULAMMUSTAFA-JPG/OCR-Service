# ocr/pdf_processor.py
import asyncio
import tempfile
from pathlib import Path
from pdf2image import convert_from_path
from ocr.engine import extract_text_from_image


async def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file by converting each page to an image,
    then running Tesseract on each page concurrently.

    WHY convert_from_path needs asyncio.to_thread:
    pdf2image calls poppler (a C library) to render PDF pages. It's CPU-intensive
    and blocking — same problem as Tesseract. Wrap it in asyncio.to_thread().

    WHY asyncio.gather for pages:
    A for loop with 'await' processes pages sequentially — page 2 waits for page 1.
    asyncio.gather() fires all page OCR tasks at once and waits for all of them.
    For a 10-page PDF, gather is ~10x faster.

    Args:
        file_path: path to the PDF file

    Returns:
        Extracted text from all pages, joined with double newlines.
    """
    # TODO: implement this
    # Step 1: convert PDF pages to images (blocking — use asyncio.to_thread)
    #   images = await asyncio.to_thread(convert_from_path, file_path)
    #
    # Step 2: save each PIL image to a temp file so Tesseract can read it
    #   with tempfile.TemporaryDirectory() as tmpdir:
    #       paths = []
    #       for i, img in enumerate(images):
    #           p = Path(tmpdir) / f"page_{i}.png"
    #           img.save(str(p))
    #           paths.append(str(p))
    #
    # Step 3: run OCR on ALL pages concurrently using asyncio.gather
    #   pages = await asyncio.gather(*[extract_text_from_image(p) for p in paths])
    #
    # Step 4: join all page texts with "\n\n"
    #   return "\n\n".join(pages)
    raise NotImplementedError("implement extract_text_from_pdf")
