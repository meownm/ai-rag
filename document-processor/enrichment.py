# enrichment.py
#
# Версия 3.9: Добавлена поддержка vLLM. Приоритет запросов управляется через .env.
# --------------------------------------------------------------------------

import os
import json
import requests
import re
import logging
import time
from typing import Dict, Any, List
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from clients import DatabaseClient

# --- ИЗМЕНЕНИЕ: Явная конфигурация провайдера и параметров LLM из .env ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower() # 'ollama', 'openai', или 'vllm'
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3")
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "300"))
# --- ИЗМЕНЕНИЕ: Параметр приоритета, специфичный для vLLM ---
VLLM_REQUEST_PRIORITY = os.getenv("VLLM_REQUEST_PRIORITY", "low").lower() # 'high', 'medium', или 'low'

def _get_llm_config() -> (str, str):
    """Определяет эндпоинт и тип API на основе LLM_PROVIDER."""
    base_url = LLM_API_BASE.rstrip('/')
    if LLM_PROVIDER == 'ollama':
        return f"{base_url}/api/generate", "ollama"
    # --- ИЗМЕНЕНИЕ: vLLM использует тот же API, что и OpenAI ---
    elif LLM_PROVIDER in ['openai', 'vllm']:
        return f"{base_url}/v1/chat/completions", "openai"
    else:
        # Это исключение будет поймано при старте приложения, но для безопасности оставим
        raise ValueError(f"Неизвестный LLM_PROVIDER: '{LLM_PROVIDER}'. Допустимые значения: 'ollama', 'openai', 'vllm'.")

LLM_ENDPOINT, LLM_API_TYPE = _get_llm_config()

METADATA_SYSTEM_PROMPT_RU = "Ты — высокоточный API для извлечения информации. Твой ответ ДОЛЖЕН быть ТОЛЬКО валидным JSON-объектом внутри тегов `<json_output>`. Ты НИКОГДА не пишешь объяснений или другого текста вне JSON-структуры."
METADATA_USER_PROMPT_RU = """Сначала пошагово подумай внутри блока `<thinking>`. Проанализируй предоставленный фрагмент документа, определи основную тему, ключевые термины и именованные сущности.

Затем, на основе своих рассуждений, сгенерируй JSON-объект с ключами `summary`, `keywords` и `entities`.
- `summary` должно быть кратким резюме из 1-2 предложений.
- `keywords` должен быть массивом важных терминов.
- `entities` должен быть объектом, где ключи — это типы сущностей на английском языке (например, `PERSON`, `ORGANIZATION`), а значения — массивы извлеченных наименований.
- Все **значения** в JSON ДОЛЖНЫ быть на языке оригинала документа.
- В конце, помести итоговый JSON-объект внутрь тегов `<json_output>`.

Фрагмент документа:
---
{text_block}
---
"""

RELATIONS_SYSTEM_PROMPT_RU = "Ты — высокоточный API для извлечения графа знаний. Твой ответ ДОЛЖЕН быть ТОЛЬКО валидным JSON-массивом внутри тегов `<json_output>`. Ты НИКОГДА не пишешь объяснений."
RELATIONS_USER_PROMPT_RU = """Сначала пошагово подумай внутри блока `<thinking>`. Проанализируй текст, чтобы выявить отдельные сущности и отношения между ними.

Затем, на основе своих рассуждений, извлеки отношения для графа знаний. Верни JSON-массив объектов, где каждый объект имеет ключи `subject`, `subject_type`, `relation`, `object` и `object_type`.

ВАЖНЫЕ ИНСТРУКЦИИ:
1. Все значения для ключей `subject`, `relation`, `object` ДОЛЖНЫ быть на языке оригинала.
2. Значения для `subject_type` и `object_type` ДОЛЖНЫ быть из этого списка: `PERSON`, `ORGANIZATION`, `LOCATION`, `DATE`, `PRODUCT`, `EVENT`, `CONCEPT`. По умолчанию используй `ENTITY`.
3. Значение `relation` должно быть краткой глагольной фразой в ВЕРХНЕМ РЕГИСТРЕ (например, `ОСНОВАЛ`).
4. Если отношения не найдены, верни пустой массив `[]`.
5. В конце, помести итоговый JSON-массив внутрь тегов `<json_output>`.

Текст для анализа:
---
{text_block}
---
"""

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _make_llm_request(payload: dict, timeout: int) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    logging.debug(f"Отправка запроса в LLM: {LLM_ENDPOINT} с payload: {json.dumps(payload, ensure_ascii=False)}")
    response = requests.post(LLM_ENDPOINT, json=payload, timeout=timeout, headers=headers)
    response.raise_for_status()
    return response

def _extract_and_parse_json(text: str) -> Dict | List:
    match = re.search(r'<json_output>(.*?)</json_output>', text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logging.error(f"Найдены <json_output>, но содержимое не валидно: {e}.")
            return {"error": f"Invalid JSON in <json_output>: {e}", "raw_content": json_str}

    logging.warning("Теги <json_output> не найдены. Используется fallback-поиск.")
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        json_str = match.group(0).strip()
        try:
            decoder = json.JSONDecoder(strict=False)
            obj, _ = decoder.raw_decode(json_str)
            return obj
        except json.JSONDecodeError as e:
             logging.error(f"Fallback не смог распарсить JSON: {e}.")
             return {"error": f"Fallback failed to parse JSON: {e}", "raw_response": text}

    logging.error(f"В ответе LLM не найден JSON.")
    return {"error": "No JSON found in response"}

def _execute_llm_call(system_prompt: str, user_prompt: str, request_type: str, db: "DatabaseClient", context: dict, timeout: int) -> Dict | List:
    log_data = {
        "start_time": datetime.utcnow(), "end_time": None, "duration": None,
        "is_success": False, "request_type": request_type, "model_name": LLM_MODEL,
        "prompt": user_prompt, "raw_response": None, "error_message": None,
        "prompt_tokens": None, "completion_tokens": None, **context
    }

    if LLM_API_TYPE == "openai":
        payload = {"model": LLM_MODEL, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.0, "stream": False}
        
        # --- ИЗМЕНЕНИЕ: Добавляем поле priority, если провайдер - vLLM ---
        if LLM_PROVIDER == 'vllm':
            payload['priority'] = VLLM_REQUEST_PRIORITY
            log_data['request_type'] = f"{request_type}_vllm_{VLLM_REQUEST_PRIORITY}"
            
    else: # ollama
        payload = {"model": LLM_MODEL, "system": system_prompt, "prompt": user_prompt, "stream": False, "options": {"temperature": 0.0}}
    
    try:
        response = _make_llm_request(payload, timeout=timeout)
        response_data = response.json()
        log_data["is_success"] = True

        if LLM_API_TYPE == "openai":
            raw_response = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response_data.get("usage", {})
            log_data["prompt_tokens"] = usage.get("prompt_tokens")
            log_data["completion_tokens"] = usage.get("completion_tokens")
        else: # ollama
            raw_response = response_data.get("response", "")
        
        log_data["raw_response"] = raw_response
        if not raw_response.strip():
            raise RuntimeError("LLM returned an empty response string")
        
        return _extract_and_parse_json(raw_response)
        
    except Exception as e:
        log_data["is_success"] = False
        log_data["error_message"] = f"{type(e).__name__}: {str(e)}"
        raise
    finally:
        log_data["end_time"] = datetime.utcnow()
        log_data["duration"] = (log_data["end_time"] - log_data["start_time"]).total_seconds()
        db.log_llm_request(log_data)

def extract_metadata_with_llm(text_block: str, db: "DatabaseClient", context: dict) -> Dict[str, Any]:
    user_prompt = METADATA_USER_PROMPT_RU.format(text_block=text_block)
    try:
        parsed_json = _execute_llm_call(
            METADATA_SYSTEM_PROMPT_RU, user_prompt, 
            "metadata_extraction", db, context, 
            timeout=LLM_REQUEST_TIMEOUT
        )
        if isinstance(parsed_json, dict) and 'error' not in parsed_json:
            return parsed_json
        else:
            return {"error": "Parsed JSON is missing or contains an error", "raw_response": str(parsed_json)}
    except Exception as e:
        return {"error": str(e)}

def extract_relations_with_llm(text_block: str, db: "DatabaseClient", context: dict) -> list:
    ALLOWED_NODE_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "DATE", "PRODUCT", "EVENT", "CONCEPT", "ENTITY"}
    user_prompt = RELATIONS_USER_PROMPT_RU.format(text_block=text_block)

    try:
        parsed_json = _execute_llm_call(
            RELATIONS_SYSTEM_PROMPT_RU, user_prompt, 
            "relation_extraction", db, context, 
            timeout=LLM_REQUEST_TIMEOUT
        )
        
        if not isinstance(parsed_json, list):
            return []

        sanitized_relations = []
        required_keys = ['subject', 'subject_type', 'relation', 'object', 'object_type']

        for item in parsed_json:
            if not isinstance(item, dict) or not all(k in item for k in required_keys):
                continue

            s_type = str(item.get('subject_type', 'ENTITY')).upper()
            o_type = str(item.get('object_type', 'ENTITY')).upper()
            
            item['subject_type'] = s_type if s_type in ALLOWED_NODE_TYPES else 'ENTITY'
            item['object_type'] = o_type if o_type in ALLOWED_NODE_TYPES else 'ENTITY'
            
            sanitized_relations.append(item)

        return sanitized_relations
        
    except Exception:
        return []