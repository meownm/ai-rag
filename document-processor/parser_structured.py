# parser_structured.py
#
# Версия 3.4: Финальная версия. Парсеры для Excel, JSON, XML.
# --------------------------------------------------------------------------
import os
import json
import logging
import pandas as pd
from typing import List, Dict, Tuple, Any
from bs4 import BeautifulSoup

def get_filesystem_metadata(path: str) -> Dict[str, Any]:
    """Извлекает базовые метаданные из файловой системы."""
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

# -----------------------------
# Excel (.xlsx, .xls)
# -----------------------------
def parse_excel(path: str, doc_id: str) -> Tuple[List[Dict], Dict]:
    """
    Парсит Excel файл, обрабатывая каждый лист.
    Строки объединяются в группы (батчи) для уменьшения количества мелких чанков.
    """
    blocks = []
    chunk_id = 0
    doc_properties = get_filesystem_metadata(path)
    
    try:
        with pd.ExcelFile(path) as xls:
            doc_properties['sheets'] = xls.sheet_names
            
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str).fillna('')
                if df.empty: continue

                rows_in_batch = int(os.getenv("EXCEL_ROW_BATCH_SIZE", "10"))
                
                for i in range(0, len(df), rows_in_batch):
                    batch_df = df[i:i+rows_in_batch]
                    batch_text_parts = []
                    
                    for index, row in batch_df.iterrows():
                        row_items = [f"{col}: {val}" for col, val in row.items() if str(val).strip()]
                        if row_items:
                            batch_text_parts.append(", ".join(row_items))

                    if not batch_text_parts: continue
                    
                    text = "\n".join(batch_text_parts)
                    chunk_id += 1
                    blocks.append({
                        "doc_id": doc_id, "chunk_id": chunk_id, "section": sheet_name, 
                        "level": 0, "type": "table_rows_group", "text": text,
                        "metadata": {"sheet": sheet_name, "start_row": i + 2, "end_row": i + len(batch_df) + 1}
                    })
        return blocks, doc_properties
    except Exception as e:
        error_message = f"[Excel parse error: {e}]"
        logging.error(f"[{doc_id}] {error_message}", exc_info=True)
        blocks = [{"doc_id": doc_id, "chunk_id": 1, "type": "error", "text": error_message}]
        return blocks, {}

# -----------------------------
# JSON
# -----------------------------
def parse_json(path: str, doc_id: str) -> Tuple[List[Dict], Dict]:
    """
    Парсит JSON файл, преобразуя его в отформатированную строку.
    Весь файл становится одним чанком.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        text_content = json.dumps(data, ensure_ascii=False, indent=2)
        if not text_content.strip():
            return [], {}

        blocks = [{"doc_id": doc_id, "chunk_id": 1, "section": None, "level": 0, "type": "json_content", "text": text_content, "metadata": {}}]
        return blocks, get_filesystem_metadata(path)
    except Exception as e:
        error_message = f"[JSON parse error: {e}]"
        logging.error(f"[{doc_id}] {error_message}", exc_info=True)
        blocks = [{"doc_id": doc_id, "chunk_id": 1, "type": "error", "text": error_message}]
        return blocks, {}

# -----------------------------
# XML
# -----------------------------
def parse_xml(path: str, doc_id: str) -> Tuple[List[Dict], Dict]:
    """
    Парсит XML файл, извлекая все текстовое содержимое и разбивая его на чанки.
    """
    blocks, chunk_id = [], 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml-xml')

        full_text = soup.get_text(separator='\n\n', strip=True)
        paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

        for para in paragraphs:
            chunk_id += 1
            blocks.append({"doc_id": doc_id, "chunk_id": chunk_id, "section": None, "level": 0, "type": "paragraph", "text": para, "metadata": {}})
        
        return blocks, get_filesystem_metadata(path)
    except Exception as e:
        error_message = f"[XML parse error: {e}]"
        logging.error(f"[{doc_id}] {error_message}", exc_info=True)
        blocks = [{"doc_id": doc_id, "chunk_id": 1, "type": "error", "text": error_message}]
        return blocks, {}