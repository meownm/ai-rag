# parser_txt.py
#
# Версия 3.4: Финальная версия. Включает автоопределение кодировки
# для корректной работы с разными файлами и унифицированный возврат.
# --------------------------------------------------------------------------
import os
import logging
from typing import List, Dict, Tuple
import chardet

def get_filesystem_metadata(path: str) -> Dict:
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


def parse_txt(path: str, doc_id: str) -> Tuple[List[Dict], Dict]:
    """
    Парсит простой текстовый файл, разбивая его по пустым строкам.
    Автоматически определяет кодировку файла.
    """
    blocks = []
    chunk_id = 0
    doc_properties = {}
    
    try:
        # Определяем кодировку файла
        with open(path, "rb") as f:
            raw_data = f.read()
            if not raw_data: # Если файл пустой
                logging.info(f"TXT: [{doc_id}] Файл '{os.path.basename(path)}' пуст.")
                return [], {}

            result = chardet.detect(raw_data)
            encoding = result['encoding'] if result['encoding'] else 'utf-8'
            confidence = result['confidence'] if result['confidence'] is not None else 0.0
            logging.info(f"TXT: [{doc_id}] Обнаружена кодировка '{encoding}' с уверенностью {confidence:.2f}")

        content = raw_data.decode(encoding, errors='ignore')
        
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        for para in paragraphs:
            chunk_id += 1
            blocks.append({
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "section": None,
                "level": 0,
                "type": "paragraph",
                "text": para,
                "metadata": {}
            })
            
        doc_properties['encoding'] = encoding
        doc_properties['encoding_confidence'] = confidence
        return blocks, doc_properties

    except Exception as e:
        error_message = f"[TXT parse error: {e}]"
        logging.error(f"[{doc_id}] {error_message}", exc_info=True)
        blocks = [{"doc_id": doc_id, "chunk_id": 1, "type": "error", "text": error_message}]
        return blocks, {}