# chunker.py
#
# Версия 3.6: Добавлено детальное комментирование алгоритмов.
# --------------------------------------------------------------------------

import tiktoken
import logging
from typing import List, Dict, Iterable, Tuple
import re

class SmartChunker:
    """
    Умный чанкер, который объединяет мелкие семантические блоки в чанки
    оптимального размера, обеспечивая естественное перекрытие.
    """
    def __init__(self,
                 chunk_tokens: int = 500,
                 overlap_tokens: int = 80,
                 section_limit: int = 2000,
                 doc_limit: int = 3000,
                 list_limit: int = 1500,
                 table_limit: int = 2000,
                 encoding: str = "cl100k_base"):
        
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.section_limit = section_limit # Жесткий лимит для одного блока
        self.doc_limit = doc_limit
        self.list_limit = list_limit
        self.table_limit = table_limit
        
        try:
            self.enc = tiktoken.get_encoding(encoding)
        except Exception:
            logging.warning(f"Кодировка '{encoding}' не найдена, используется fallback 'gpt2'.")
            self.enc = tiktoken.get_encoding("gpt2")

    def _build_combined_meta(self, sections: Iterable[Tuple[int, Dict]], is_whole_doc: bool = False) -> Dict:
        """
        Собирает метаданные объединенных секций без потери границ и заголовков.
        Для каждого блока сохраняются именованные префиксы и структурированный список секций.
        """
        combined_meta: Dict = {"sections": []}

        for idx, sec in sections:
            sec_meta = sec.get("meta", {})
            combined_meta["sections"].append({"index": idx, **sec_meta})

            for key, value in sec_meta.items():
                combined_meta[f"section_{idx}.{key}"] = value

        if is_whole_doc:
            combined_meta["is_whole_doc"] = True

        return combined_meta

    def count_tokens(self, text: str) -> int:
        """Считает количество токенов в тексте."""
        return len(self.enc.encode(text, disallowed_special=()))

    def _combine_sections_metadata(self, sections: List[Dict]) -> Dict:
        """
        Собирает метаданные всех секций без потери информации.

        Ранее метаданные объединялись простым update()/comprehension, что приводило к
        перезаписи одинаковых ключей (например, заголовков разделов). Теперь каждая
        секция сохраняется отдельно в sections_meta с указанием порядка.
        """
        sections_meta = []
        for idx, sec in enumerate(sections, start=1):
            meta = sec.get("meta", {}) or {}
            sections_meta.append({"section_index": idx, **meta})

        return {"sections_meta": sections_meta} if sections_meta else {}

    def _split_large_text_block(self, text: str, meta: dict) -> List[Dict]:
        """
        Внутренняя функция для семантической нарезки одного очень большого блока текста.
        Разбивает текст на предложения и собирает их в чанки, не разрывая слова.
        """
        if not text:
            return []

        sentences = self._split_to_sentences(text)

        chunks = []
        current_chunk_sentences = []
        current_token_count = 0

        for sentence in sentences:
            sentence_token_count = self.count_tokens(sentence)

            if current_chunk_sentences and current_token_count + sentence_token_count > self.chunk_tokens:
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append({"text": chunk_text, "meta": meta, "block_type": "section_part"})

                overlap_sentences = []
                overlap_token_count = 0
                for s in reversed(current_chunk_sentences):
                    s_tokens = self.count_tokens(s)
                    if overlap_token_count + s_tokens > self.overlap_tokens:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_token_count += s_tokens
                
                current_chunk_sentences = overlap_sentences
                current_token_count = overlap_token_count

            current_chunk_sentences.append(sentence)
            current_token_count += sentence_token_count
        
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append({"text": chunk_text, "meta": meta, "block_type": "section_part"})

        return chunks

    def _build_overlap_items(self, items: List[str]) -> List[str]:
        overlap_items: List[str] = []
        accumulated_tokens = 0

        for item in reversed(items):
            item_tokens = self.count_tokens(item)
            if overlap_items and accumulated_tokens + item_tokens > self.overlap_tokens:
                break
            overlap_items.insert(0, item)
            accumulated_tokens += item_tokens
            if accumulated_tokens >= self.overlap_tokens:
                break

        return overlap_items

    def _handle_list(self, text: str, meta: Dict) -> List[Dict]:
        """Обработка списков. Если список слишком длинный, он разбивается на части."""
        if self.count_tokens(text) <= self.list_limit:
            return [{"text": text, "meta": meta, "block_type": "list"}]

        items = text.split("\n")
        block, res = [], []
        current_token_count = 0

        for item in items:
            item_tokens = self.count_tokens(item)
            if block and current_token_count + item_tokens > self.chunk_tokens:
                block_text = "\n".join(block)
                res.append({"text": block_text, "meta": meta, "block_type": "list_part"})

                overlap_items = self._build_overlap_items(block) if self.overlap_tokens > 0 else []
                block = overlap_items
                current_token_count = sum(self.count_tokens(i) for i in overlap_items)

            block.append(item)
            current_token_count += item_tokens

        if block:
            block_text = "\n".join(block)
            res.append({"text": block_text, "meta": meta, "block_type": "list_part"})

        return res

    def _build_overlap_rows(self, rows: List[str], max_tokens: int) -> List[str]:
        overlap_rows: List[str] = []
        accumulated_tokens = 0

        for row in reversed(rows):
            row_tokens = self.count_tokens(row)
            if overlap_rows and accumulated_tokens + row_tokens > max_tokens:
                break
            overlap_rows.insert(0, row)
            accumulated_tokens += row_tokens
            if accumulated_tokens >= max_tokens:
                break

        return overlap_rows

    def _handle_table(self, text: str, meta: Dict) -> List[Dict]:
        """
        Обработка таблиц в формате Markdown.
        Если таблица слишком длинная, она разбивается на части, сохраняя заголовок.
        """
        if self.count_tokens(text) <= self.table_limit:
            return [{"text": text, "meta": meta, "block_type": "table"}]

        rows = text.split("\n")
        if len(rows) < 2:
            return self._split_large_text_block(text, meta)

        header, separator = rows[0], rows[1]
        data_rows = rows[2:]
        res, current_block_rows = [], []
        header_token_count = self.count_tokens(header) + self.count_tokens(separator)
        current_block_token_count = 0

        for row in data_rows:
            row_tokens = self.count_tokens(row)

            if current_block_rows and header_token_count + current_block_token_count + row_tokens > self.chunk_tokens:
                block_text = "\n".join([header, separator] + current_block_rows)
                res.append({"text": block_text, "meta": meta, "block_type": "table_part"})

                overlap_rows = self._build_overlap_rows(current_block_rows, self.overlap_tokens) if self.overlap_tokens > 0 else []
                current_block_rows = overlap_rows
                current_block_token_count = sum(self.count_tokens(r) for r in current_block_rows)

            current_block_rows.append(row)
            current_block_token_count += row_tokens

        if current_block_rows:
            block_text = "\n".join([header, separator] + current_block_rows)
            res.append({"text": block_text, "meta": meta, "block_type": "table_part"})

        return res

    def split_document(self, sections: List[Dict]) -> List[Dict]:
        """
        Главная функция, которая "жадно" объединяет мелкие блоки в чанки оптимального размера.
        
        Алгоритм работы:
        1. Если весь документ меньше `doc_limit`, он возвращается как один чанк для максимального сохранения контекста.
        2. Специализированные блоки (таблицы, списки) обрабатываются своими функциями.
        3. Обычные текстовые блоки (параграфы, заголовки) накапливаются в `buffer`.
        4. Как только добавление нового блока в буфер превышает целевой размер чанка (`chunk_tokens`),
           содержимое буфера объединяется в один "композитный" чанк.
        5. Для обеспечения контекста сохраняется хвост предыдущего чанка нужной длины (по токенам), формируя "семантическое перекрытие".
        6. Очень большие блоки (> `section_limit`) обрабатываются отдельно функцией нарезки по предложениям.
        """
        total_text = "\n\n".join(sec["text"] for sec in sections if sec.get("text"))
        if self.count_tokens(total_text) <= self.doc_limit:
            logging.info(f"Документ достаточно мал ({self.count_tokens(total_text)} токенов), возвращается как единый чанк.")
            section_entries = [(idx, sec) for idx, sec in enumerate(sections) if sec.get("text")]
            combined_meta = self._build_combined_meta(section_entries, is_whole_doc=True)

            return [{"text": total_text, "meta": combined_meta, "block_type": "doc"}]

        chunks = []
        buffer: List[Tuple[int, Dict]] = []
        buffer_tokens = 0

        for idx, sec in enumerate(sections):
            sec_text = sec.get("text", "").strip()
            if not sec_text:
                continue
            
            sec_meta = sec.get("meta", {})
            sec_type = sec_meta.get("type", "paragraph")

            if sec_type in ["list", "list_item"]:
                chunks.extend(self._handle_list(sec_text, sec_meta))
                continue
            if sec_type == "table":
                chunks.extend(self._handle_table(sec_text, sec_meta))
                continue

            sec_tokens = self.count_tokens(sec_text)

            if sec_tokens > self.section_limit:
                if buffer:
                    chunk_text = "\n\n".join(b[1]['text'] for b in buffer)
                    combined_meta = self._build_combined_meta(buffer)
                    chunks.append({"text": chunk_text, "meta": combined_meta, "block_type": "composite_section"})
                    buffer = []

                chunks.extend(self._split_large_text_block(sec_text, sec_meta))
                continue

            buffer_tokens = self.count_tokens("\n\n".join(b[1]['text'] for b in buffer))
            if buffer_tokens > 0 and buffer_tokens + sec_tokens > self.chunk_tokens:
                chunk_text = "\n\n".join(b[1]['text'] for b in buffer)
                combined_meta = self._build_combined_meta(buffer)
                chunks.append({"text": chunk_text, "meta": combined_meta, "block_type": "composite_section"})

                buffer = self._build_text_overlap(buffer) if self.overlap_tokens > 0 else []

            buffer.append((idx, sec))
            
        if buffer:
            chunk_text = "\n\n".join(b[1]['text'] for b in buffer)
            combined_meta = self._build_combined_meta(buffer)
            chunks.append({"text": chunk_text, "meta": combined_meta, "block_type": "composite_section"})

        logging.info(f"Документ разбит на {len(chunks)} 'умных' объединенных чанков.")
        return chunks
