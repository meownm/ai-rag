# context_builder.py
from typing import List, Dict, Optional
import tiktoken

from schemas import InternalChunk

TOKENIZER = tiktoken.get_encoding("cl100k_base")
MAX_CONTEXT_TOKENS = 60000

def count_tokens(text: str) -> int:
    return len(TOKENIZER.encode(text, disallowed_special=()))

def build_context(
    final_chunks: List[InternalChunk],
    conversation_history: List[Dict],
    graph_context_str: Optional[str] = None
) -> Dict:
    context_parts = []
    total_tokens = 0
    history_str = ""

    # 1. Обработка истории диалога
    history_token_limit = int(MAX_CONTEXT_TOKENS * 0.4)
    for turn in reversed(conversation_history):
        turn_text = f"Пользователь: {turn['query']}\nАссистент: {turn['answer']}\n\n"
        turn_tokens = count_tokens(turn_text)
        if total_tokens + turn_tokens <= history_token_limit:
            history_str = turn_text + history_str
            total_tokens += turn_tokens
        else:
            break
            
    if history_str:
        context_parts.append(f"<history>\n{history_str.strip()}\n</history>")

    remaining_tokens = MAX_CONTEXT_TOKENS - total_tokens
    chunks_token_limit = int(remaining_tokens * 0.7)
    graph_token_limit = int(remaining_tokens * 0.2)
    enrichment_token_limit = int(remaining_tokens * 0.1)
    
    # 2. Добавляем граф-контекст
    graph_used = False
    if graph_context_str:
        graph_tokens = count_tokens(graph_context_str)
        if graph_tokens <= graph_token_limit:
            context_parts.append(f"<graph_context>\n{graph_context_str.strip()}\n</graph_context>")
            total_tokens += graph_tokens
            graph_used = True

    # 3. Добавляем Enrichment
    enrichment_used = False
    enrichment_context = ""
    unique_summaries = set()
    unique_keywords = set()
    for chunk in final_chunks: # Теперь используем final_chunks
        if chunk.metadata and "llm_enrichment" in chunk.metadata:
            enrichment = chunk.metadata["llm_enrichment"]
            if "summary" in enrichment and enrichment["summary"] not in unique_summaries:
                unique_summaries.add(enrichment["summary"])
            if "keywords" in enrichment and isinstance(enrichment["keywords"], list):
                unique_keywords.update(enrichment["keywords"])
    
    if unique_summaries:
        enrichment_context += "Key Summaries:\n" + "\n".join(f"- {s}" for s in unique_summaries) + "\n\n"
    if unique_keywords:
        enrichment_context += "Key Terms:\n" + ", ".join(unique_keywords)

    if enrichment_context:
        enrichment_tokens = count_tokens(enrichment_context)
        if (total_tokens + enrichment_tokens <= MAX_CONTEXT_TOKENS) and (enrichment_tokens <= enrichment_token_limit):
            context_parts.append(f"<enrichment>\n{enrichment_context.strip()}\n</enrichment>")
            total_tokens += enrichment_tokens
            enrichment_used = True

    # 4. Добавляем реконструированные чанки
    chunks_context = ""
    used_chunks_count = 0
    
    for chunk in final_chunks:
        block_text_with_source = f"[Источник {chunk.source_id}: {chunk.filename}]\n{chunk.text}\n\n"
        block_tokens = count_tokens(block_text_with_source)
        
        if (total_tokens + block_tokens <= MAX_CONTEXT_TOKENS) and \
           (count_tokens(chunks_context) + block_tokens <= chunks_token_limit):
            chunks_context += block_text_with_source
            total_tokens += block_tokens
            used_chunks_count += 1
        else:
            break
            
    if chunks_context:
        context_parts.append(f"<chunks>\n{chunks_context.strip()}\n</chunks>")

    return {
        "context_str": "\n\n".join(context_parts),
        "history_str": f"<history>\n{history_str.strip()}\n</history>" if history_str else "",
        "used_chunks": used_chunks_count,
        "used_tokens": total_tokens,
        "graph_used": graph_used,
        "enrichment_used": enrichment_used
    }