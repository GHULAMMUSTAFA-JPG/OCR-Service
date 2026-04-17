# ocr/engine.py
import asyncio
import pytesseract
from PIL import Image


async def extract_text_from_image(file_path: str) -> str:
    """
    Extract text from an image file using Tesseract OCR.

    WHY asyncio.to_thread:
    pytesseract.image_to_string() is a blocking call — it runs a C program (Tesseract)
    and freezes the Python thread until it finishes. In an async program, blocking the
    thread means no other coroutines can run while OCR is working (no DB queries,
    no HTTP requests, nothing). asyncio.to_thread() moves the blocking call into a
    thread pool worker, freeing the event loop for other work.

    Args:
        file_path: absolute or relative path to the image file (jpg, png, etc.)

    Returns:
        Extracted text as a string. Empty string if no text found.
    """
    image = Image.open(file_path)
    text = await asyncio.to_thread(pytesseract.image_to_string, image)
    return text
