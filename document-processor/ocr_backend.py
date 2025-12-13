import logging
import os
from typing import List

import numpy as np
import pytesseract


OCR_ENABLED = os.getenv("OCR_ENABLED", "false").strip().lower() == "true"
OCR_LANG = os.getenv("OCR_LANG", "rus+eng")
OCR_BACKEND = os.getenv("OCR_BACKEND", "tesseract").strip().lower()

_easyocr_reader = None


def _init_easyocr_reader(langs: List[str]):
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr

        _easyocr_reader = easyocr.Reader(langs, gpu=False)
    return _easyocr_reader


def ocr_image_to_text(image) -> str:
    """Runs OCR on a PIL image with a selectable backend."""

    # Normalize languages: "rus+eng" -> ["rus", "eng"]
    lang_parts = [part for part in OCR_LANG.replace("+", ",").split(",") if part.strip()]
    if not lang_parts:
        lang_parts = ["eng"]

    if OCR_BACKEND == "easyocr":
        try:
            reader = _init_easyocr_reader(lang_parts)
            result = reader.readtext(np.array(image), detail=0, paragraph=True)
            joined = "\n".join([text.strip() for text in result if text and text.strip()])
            if joined:
                return joined
        except Exception as e:
            logging.warning("EasyOCR failed (%s); falling back to Tesseract", e)

    # Default and fallback backend
    return pytesseract.image_to_string(image, lang="+".join(lang_parts))
