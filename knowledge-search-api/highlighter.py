# highlighter.py
#
# Финальная, исправленная версия. Устранен IndentationError.
# --------------------------------------------------------------------------
import re
from difflib import SequenceMatcher
from typing import List, Dict

from sentence_transformers import SentenceTransformer, util

from schemas import RetrievedChunk, HighlightedCitation

def _split_into_sentences(text: str) -> List[str]:
    """
    Простой, но эффективный сплиттер текста на предложения с помощью регулярного выражения.
    """
    # Этот regex разбивает по точкам, восклицательным и вопросительным знакам,
    # за которыми следует пробел или конец строки. Он также пытается сохранить разделитель.
    sentences = re.split(r'(?<=[.?!])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def verify_and_highlight_citations(
    answer_text: str,
    source_chunks: List[RetrievedChunk],
    embedding_model: SentenceTransformer,
    similarity_threshold: float = 0.7
) -> tuple[str, List[HighlightedCitation]]:
    """
    Верифицирует цитаты в ответе, удаляет недостоверные,
    подсвечивает достоверные и возвращает очищенный текст и цитаты.
    """
    source_map: Dict[int, RetrievedChunk] = {chunk.source_id: chunk for chunk in source_chunks}
    highlighted_texts: Dict[int, str] = {chunk.source_id: chunk.text for chunk in source_chunks}
    
    # Извлекаем все предложения и их цитаты из ответа
    # Regex, который находит предложение (до точки/вопроса/воскл. знака) вместе с его цитатой в конце
    pattern = re.compile(r'([^.?!]+[.?!])\s*(\[(\d+(?:,\s*\d+)*)\])')
    
    matches = pattern.findall(answer_text)
    
    verified_answer_text = answer_text
    
    for sentence, full_citation_marker, citation_ids_str in matches:
        sentence = sentence.strip()
        source_ids = [int(sid.strip()) for sid in citation_ids_str.split(',')]
        
        is_verified = False
        for source_id in set(source_ids): # Используем set для уникальности
            if source_id not in source_map:
                continue

            chunk_text = source_map[source_id].text
            
            # Верификация: вычисляем семантическую схожесть
            try:
                sentence_embedding = embedding_model.encode(sentence)
                chunk_embedding = embedding_model.encode(chunk_text)
                similarity = util.cos_sim(sentence_embedding, chunk_embedding).item()
            except Exception as e:
                print(f"Warning: Could not compute similarity for verification. Error: {e}")
                similarity = 0.0 # Считаем, что верификация не пройдена

            if similarity >= similarity_threshold:
                is_verified = True
                
                # Подсветка: ищем наиболее похожее место в чанке
                matcher = SequenceMatcher(None, sentence, chunk_text, autojunk=False)
                match = matcher.find_longest_match(0, len(sentence), 0, len(chunk_text))
                
                if match.size > 0:
                    start, end = match.b, match.b + match.size
                    original_substring = chunk_text[start:end]
                    
                    if f"<highlight>{original_substring}</highlight>" not in highlighted_texts[source_id]:
                        highlighted_texts[source_id] = highlighted_texts[source_id].replace(
                            original_substring, f"<highlight>{original_substring}</highlight>", 1
                        )
                # Если хотя бы один источник подтвердил цитату, считаем ее верной
                break 

        # Если ни один из перечисленных источников не подтвердил цитату, удаляем ее
        if not is_verified:
            verified_answer_text = verified_answer_text.replace(full_citation_marker, "")

    # Формируем финальный список цитат
    final_citations = [
        HighlightedCitation(
            highlighted_text=highlighted_texts.get(chunk.source_id, chunk.text),
            **chunk.dict(exclude={"metadata"}) # metadata не нужна в финальном ответе
        ) for chunk in source_chunks
    ]
        
    return verified_answer_text.strip(), final_citations