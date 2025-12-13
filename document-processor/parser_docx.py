# parser_docx.py
#
# Версия 3.6: Финальный фикс для совместимости с python-docx 0.8.11+
# Реализован корректный обход элемента .element.body документа.
# --------------------------------------------------------------------------
import os
import io
import logging
import subprocess
import tempfile
import shutil
from typing import List, Dict, Any, Tuple

from PIL import Image, UnidentifiedImageError
import pytesseract
from dotenv import load_dotenv

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P

load_dotenv()
OCR_ENABLED = os.getenv("OCR_ENABLED", "false").strip().lower() == "true"
OCR_LANG = os.getenv("OCR_LANG", "rus+eng")


def make_block(
    doc_id: str, chunk_id: int, block_type: str, text: str, section: str | None,
    level: int, caption: str | None = None, metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "doc_id": doc_id, "chunk_id": chunk_id, "section": section, "level": level,
        "type": block_type, "text": text.strip(), "caption": caption, "metadata": metadata or {}
    }

def get_filesystem_metadata(path: str) -> Dict[str, Any]:
    import datetime
    try:
        return {
            "source_filename": os.path.basename(path),
            "created_fs": datetime.datetime.fromtimestamp(os.path.getctime(path)).isoformat(),
            "modified_fs": datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
            "size_bytes": os.path.getsize(path),
        }
    except Exception as e:
        logging.warning(f"Не удалось получить метаданные файловой системы для '{path}': {e}")
        return {"source_filename": os.path.basename(path)}

def iter_block_items(parent):
    """
    Корректно итерируется по блокам верхнего уровня (параграфам и таблицам)
    внутри документа или ячейки таблицы.
    """
    if isinstance(parent, DocumentObject):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._element
    else:
        raise ValueError("Unsupported parent type for block iteration")

    for child in parent_elm: # Простая итерация эквивалентна .iterchildren()
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)

def get_heading_level(p: Paragraph) -> int:
    style_name = (p.style.name or "").lower()
    if style_name.startswith(("heading", "заголовок")):
        level_str = style_name.replace("heading", "").replace("заголовок", "").strip()
        return int(level_str) if level_str.isdigit() else 1
    return 0

def table_to_markdown(table: Table) -> str:
    rows_text = [[cell.text.strip().replace("\n", " ") for cell in row.cells] for row in table.rows]
    if not rows_text: return ""
    header = rows_text[0]
    if not any(header) and len(rows_text) > 1:
        header, rows_text = rows_text[1], rows_text[1:]
    if not any(header): return ""
    md = "| " + " | ".join(header) + " |\n"
    md += "| " + " | ".join(["---"] * len(header)) + " |\n"
    md += "\n".join("| " + " | ".join(r) + " |" for r in rows_text[1:])
    return md

def parse_docx(path: str, doc_id: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    try:
        doc = Document(path)
    except Exception as e:
        error_message = f"[DOCX open error: {e}]"
        logging.error(f"[{doc_id}] Не удалось открыть docx файл '{os.path.basename(path)}': {e}", exc_info=True)
        return [{"doc_id": doc_id, "chunk_id": 1, "type": "error", "text": error_message}], {}

    blocks, chunk_id_counter = [], 0
    current_section, current_level = None, 0

    props = doc.core_properties
    doc_properties = {
        "author": props.author, "title": props.title, "keywords": props.keywords,
        "comments": props.comments, "category": props.category,
        "created": props.created.isoformat() if props.created else None,
        "modified": props.modified.isoformat() if props.modified else None,
        **get_filesystem_metadata(path)
    }

    doc_items, i = list(iter_block_items(doc)), 0
    while i < len(doc_items):
        item = doc_items[i]
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if text:
                level = get_heading_level(item)
                block_type = "heading" if level > 0 else "paragraph"
                if level > 0: current_section, current_level = text, level
                chunk_id_counter += 1
                blocks.append(make_block(doc_id, chunk_id_counter, block_type, text, current_section, current_level))
        elif isinstance(item, Table):
            md_text = table_to_markdown(item)
            caption_text = None
            if (i + 1) < len(doc_items) and isinstance(doc_items[i + 1], Paragraph):
                next_p, next_text = doc_items[i + 1], doc_items[i + 1].text.strip()
                style_name = (next_p.style.name or "").lower()
                if "caption" in style_name or next_text.lower().startswith(("таблица", "table", "рис.", "рисунок")):
                    caption_text, i = next_text, i + 1
            if md_text:
                chunk_id_counter += 1
                blocks.append(make_block(doc_id, chunk_id_counter, "table", md_text, current_section, current_level, caption=caption_text))
        i += 1

    if OCR_ENABLED and doc.part and doc.part.rels:
        logger = logging.getLogger(f"parser_docx.{doc_id}")
        logger.info("Поиск и распознавание изображений (OCR)...")
        image_count = 0
        imagemagick_present = shutil.which('magick') is not None or shutil.which('convert') is not None
        
        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                image_count += 1
                image_bytes = rel.target_part.blob
                image = None
                try:
                    image = Image.open(io.BytesIO(image_bytes))
                except UnidentifiedImageError:
                    if imagemagick_present and ('.wmf' in rel.target_ref or '.emf' in rel.target_ref):
                        logger.warning(f"Неподдерживаемый формат '{rel.target_ref}'. Попытка конвертации через ImageMagick...")
                        try:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(rel.target_ref)[1]) as tmp_in:
                                tmp_in.write(image_bytes); tmp_in_path = tmp_in.name
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_out:
                                tmp_out_path = tmp_out.name
                            
                            cmd = ['magick', tmp_in_path, tmp_out_path] if shutil.which('magick') else ['convert', tmp_in_path, tmp_out_path]
                            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
                            if result.returncode != 0: raise RuntimeError(result.stderr)
                            
                            image = Image.open(tmp_out_path)
                            os.remove(tmp_in_path); os.remove(tmp_out_path)
                        except Exception as convert_e:
                            logger.error(f"Ошибка при конвертации '{rel.target_ref}': {convert_e}"); continue
                    else:
                        logger.warning(f"Неподдерживаемый формат '{rel.target_ref}' пропущен."); continue
                
                if image:
                    try:
                        ocr_text = pytesseract.image_to_string(image, lang=OCR_LANG)
                        if ocr_text.strip():
                            chunk_id_counter += 1
                            blocks.append(make_block(doc_id, chunk_id_counter, "image_text", ocr_text, current_section, current_level, metadata={"source": "ocr_from_embedded_image", "image_ref": rel.target_ref}))
                    except Exception as ocr_e:
                        logger.warning(f"Ошибка OCR для изображения '{rel.target_ref}': {ocr_e}")
        logger.info(f"Найдено и предпринята попытка обработки изображений: {image_count}.")

    return blocks, doc_properties