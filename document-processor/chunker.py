# chunker.py
#
# Версия 3.6: Добавлено детальное комментирование алгоритмов.
# --------------------------------------------------------------------------

import hashlib
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
                 table_row_group_tokens: int = 0,
                 table_row_overlap: int = 0,
                 encoding: str = "cl100k_base"):
        
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.section_limit = section_limit # Жесткий лимит для одного блока
        self.doc_limit = doc_limit
        self.list_limit = list_limit
        self.table_limit = table_limit
        self.table_row_group_tokens = table_row_group_tokens
        self.table_row_overlap = table_row_overlap
        
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

        paragraphs = self._split_to_logical_blocks(text)

        chunks = []
        current_chunk_sentences: List[str] = []
        current_token_count = 0

        for paragraph in paragraphs:
            paragraph_sentences = self._split_to_sentences(paragraph)
            if not paragraph_sentences:
                continue

            paragraph_text = " ".join(paragraph_sentences)
            paragraph_tokens = self.count_tokens(paragraph_text)

            if paragraph_tokens > self.chunk_tokens:
                if current_chunk_sentences:
                    chunk_text = " ".join(current_chunk_sentences)
                    chunks.append({"text": chunk_text, "meta": meta, "block_type": "section_part"})
                    current_chunk_sentences, current_token_count = self._build_sentence_overlap(current_chunk_sentences)

                for sentence in paragraph_sentences:
                    sentence_token_count = self.count_tokens(sentence)

                    if current_chunk_sentences and current_token_count + sentence_token_count > self.chunk_tokens:
                        chunk_text = " ".join(current_chunk_sentences)
                        chunks.append({"text": chunk_text, "meta": meta, "block_type": "section_part"})
                        current_chunk_sentences, current_token_count = self._build_sentence_overlap(current_chunk_sentences)

                    current_chunk_sentences.append(sentence)
                    current_token_count += sentence_token_count

                continue

            if current_chunk_sentences and current_token_count + paragraph_tokens > self.chunk_tokens:
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append({"text": chunk_text, "meta": meta, "block_type": "section_part"})
                current_chunk_sentences, current_token_count = self._build_sentence_overlap(current_chunk_sentences)

            current_chunk_sentences.extend(paragraph_sentences)
            current_token_count += paragraph_tokens

        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append({"text": chunk_text, "meta": meta, "block_type": "section_part"})

        return chunks

    def _build_sentence_overlap(self, sentences: List[str]) -> Tuple[List[str], int]:
        if self.overlap_tokens <= 0:
            return [], 0

        overlap_sentences: List[str] = []
        overlap_token_count = 0

        for s in reversed(sentences):
            s_tokens = self.count_tokens(s)
            if overlap_sentences and overlap_token_count + s_tokens > self.overlap_tokens:
                break
            overlap_sentences.insert(0, s)
            overlap_token_count += s_tokens
            if overlap_token_count >= self.overlap_tokens:
                break

        return overlap_sentences, overlap_token_count

    def _split_to_logical_blocks(self, text: str) -> List[str]:
        lines = text.split("\n")
        blocks: List[str] = []
        current_block: List[str] = []

        bullet_pattern = re.compile(r"^\s*([-*+•·]|\d+[\.|\)])\s+")
        heading_pattern = re.compile(r"^\s{0,3}(#{1,6}\s+.+|.+?:)$")
        potential_list_context = False

        def flush_block():
            nonlocal potential_list_context
            if current_block:
                blocks.append(" ".join(line.strip() for line in current_block if line.strip()))
                current_block.clear()
            potential_list_context = False

        for line in lines:
            stripped = line.strip()

            if not stripped:
                flush_block()
                continue

            is_bullet = bool(bullet_pattern.match(stripped))
            is_heading = bool(heading_pattern.match(stripped))

            if is_bullet or is_heading:
                flush_block()
                current_block.append(stripped)
                flush_block()
                potential_list_context = is_heading and stripped.endswith(":")
                continue

            if potential_list_context and len(stripped.split()) <= 10:
                flush_block()
                blocks.append(stripped)
                continue

            current_block.append(stripped)

        flush_block()
        return [block for block in blocks if block]

    def _split_to_sentences(self, text: str) -> List[str]:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return []

        # Делим по завершенным предложениям, оставляя заглавные буквы как сигнал нового блока
        raw_sentences = re.split(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9])", normalized)
        sentences = [sent.strip() for sent in raw_sentences if sent.strip()]

        if not sentences:
            return [normalized]

        return sentences

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

    def _build_overlap_rows_by_tokens(self, rows: List[str], max_tokens: int) -> List[str]:
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

    def _build_table_overlap_rows(self, rows: List[str]) -> List[str]:
        if self.table_row_overlap > 0:
            return rows[-self.table_row_overlap:]
        if self.overlap_tokens > 0:
            return self._build_overlap_rows_by_tokens(rows, self.overlap_tokens)
        return []

    def _handle_table(self, text: str, meta: Dict) -> List[Dict]:
        """
        Обработка таблиц в формате Markdown.
        Если таблица слишком длинная, она разбивается на части, сохраняя заголовок.
        Поддерживается группировка строк по количеству токенов и отдельная настройка
        перекрытия по строкам для сохранения контекста.
        """
        rows = text.split("\n")
        if len(rows) < 2:
            return self._split_large_text_block(text, meta)

        header, separator = rows[0], rows[1]
        data_rows = rows[2:]
        header_token_count = self.count_tokens(header) + self.count_tokens(separator)
        total_tokens = self.count_tokens(text)

        meta_with_section = {**meta}
        table_section = meta_with_section.get("section") or meta_with_section.get("table_id") or meta_with_section.get("caption")
        if not table_section:
            digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:8]
            table_section = f"table_{digest}"
        meta_with_section["section"] = table_section

        row_group_limit = self.table_row_group_tokens or (self.chunk_tokens - header_token_count)
        if row_group_limit <= 0:
            row_group_limit = max(self.chunk_tokens, 1)

        effective_group_limit = min(row_group_limit, max(self.chunk_tokens - header_token_count, 1))

        if total_tokens <= self.table_limit and total_tokens <= header_token_count + effective_group_limit:
            return [{"text": text, "meta": meta_with_section, "block_type": "table"}]

        res, current_block_rows = [], []
        current_block_token_count = 0

        for row in data_rows:
            row_tokens = self.count_tokens(row)

            if current_block_rows and current_block_token_count + row_tokens > effective_group_limit:
                block_text = "\n".join([header, separator] + current_block_rows)
                res.append({"text": block_text, "meta": meta_with_section, "block_type": "table_part"})

                overlap_rows = self._build_table_overlap_rows(current_block_rows)
                current_block_rows = overlap_rows
                current_block_token_count = sum(self.count_tokens(r) for r in current_block_rows)

            current_block_rows.append(row)
            current_block_token_count += row_tokens

        if current_block_rows:
            block_text = "\n".join([header, separator] + current_block_rows)
            res.append({"text": block_text, "meta": meta_with_section, "block_type": "table_part"})

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
