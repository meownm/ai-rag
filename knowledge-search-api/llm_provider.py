import os
import requests
import json
from typing import List, Dict, Generator

def generate_answer(
    query: str,
    context: str,
    history_str: str,
    max_tokens: int
) -> str | None:
    """
    Формирует финальный промпт и генерирует полный ответ с помощью Ollama.
    """
    system_prompt = """
    Ты — умный и вежливый ассистент для ответа на вопросы по базе знаний.
    Твоя задача — дать исчерпывающий ответ на вопрос пользователя, основываясь ИСКЛЮЧИТЕЛЬНО на предоставленном контексте.
    - Отвечай на языке вопроса пользователя.
    - Твой ответ должен быть отформатирован в Markdown (используй списки, жирный шрифт и т.д. для лучшей читаемости).
    - Когда используешь информацию из контекста, ОБЯЗАТЕЛЬНО указывай номер источника в квадратных скобках в конце предложения, например: [1] или [2, 3].
    - Если в контексте нет информации для ответа, вежливо сообщи об этом. Не придумывай информацию.
    """
    
    user_prompt = f"""
    Используй следующий контекст и историю диалога для ответа на вопрос.

    {history_str}

    <context>
    {context}
    </context>

    Вопрос: {query}
    """
    
    try:
        response = requests.post(
            os.getenv("OLLAMA_URL"),
            json={
                "model": os.getenv("OLLAMA_MODEL"),
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.1
                }
            },
            timeout=300
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"LLM Generation Error: {e}")
        return None

def generate_answer_stream(
    query: str,
    context: str,
    history_str: str,
    max_tokens: int
) -> Generator[str, None, None]:
    """
    Формирует промпт и генерирует ответ от Ollama в потоковом режиме,
    возвращая токены по мере их поступления.
    """
    system_prompt = """
    Ты — умный и вежливый ассистент для ответа на вопросы по базе знаний.
    Твоя задача — дать исчерпывающий ответ на вопрос пользователя, основываясь ИСКЛЮЧИТЕЛЬНО на предоставленном контексте.
    - Отвечай на языке вопроса пользователя.
    - Твой ответ должен быть отформатирован в Markdown (используй списки, жирный шрифт и т.д. для лучшей читаемости).
    - Когда используешь информацию из контекста, ОБЯЗАТЕЛЬНО указывай номер источника в квадратных скобках в конце предложения, например: [1] или [2, 3].
    - Если в контексте нет информации для ответа, вежливо сообщи об этом. Не придумывай информацию.
    """
    
    user_prompt = f"""
    Используй следующий контекст и историю диалога для ответа на вопрос.

    {history_str}

    <context>
    {context}
    </context>

    Вопрос: {query}
    """
    
    try:
        response = requests.post(
            os.getenv("OLLAMA_URL"),
            json={
                "model": os.getenv("OLLAMA_MODEL"),
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": True,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.1
                }
            },
            stream=True,
            timeout=300
        )
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line)
                content = chunk.get("response", "")
                yield content
                if chunk.get("done"):
                    break

    except Exception as e:
        print(f"LLM Stream Generation Error: {e}")
        # В случае ошибки генератор просто прекратит свою работу, и поток закроется.