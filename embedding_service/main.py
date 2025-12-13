# main.py
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import List, Union
import logging
import time
import uuid
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer
from .model_manager import ModelManager, RAW_TRANSFORMERS_MODELS, _GPU_AVAILABLE

logger = logging.getLogger(__name__)

app = FastAPI(title="Сервис для создания эмбеддингов", description="Унифицированный сервис для получения эмбеддингов в Docker.", version="1.0.0")

# --- Pydantic модели для валидации данных ---

class EmbeddingRequest(BaseModel):
    model: str = Field(..., description="Имя модели с Hugging Face")
    input: Union[str, List[str]] = Field(..., description="Текст или список текстов")

class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int

class Usage(BaseModel):
    prompt_tokens: int
    total_tokens: int

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: Usage

# --- Вспомогательная функция ---

def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

# --- Инициализация менеджеров моделей ---

cpu_model_manager = ModelManager(preferred_device="cpu")
gpu_model_manager = ModelManager(preferred_device="gpu")

# --- События жизненного цикла приложения ---

@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...")
    cpu_model_manager.start_cleanup_thread()
    gpu_model_manager.start_cleanup_thread()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown...")
    cpu_model_manager.stop_cleanup_thread()
    gpu_model_manager.stop_cleanup_thread()

# --- Основная логика обработки ---

def _create_embeddings_sync(texts: List[str], model_mgr: ModelManager, request_model: str, request_id: str, request_type: str):
    """Синхронная функция для выполнения ресурсоемких вычислений в отдельном потоке."""
    try:
        loaded_model = model_mgr.get_model(model_name=request_model, request_id=request_id)
        effective_device = model_mgr.device
        
        if request_model in RAW_TRANSFORMERS_MODELS:
            model, tokenizer = loaded_model
            encoded_input = tokenizer(texts, padding=True, truncation=True, return_tensors='pt').to(effective_device)
            with torch.no_grad():
                model_output = model(**encoded_input)
            sentence_embeddings = mean_pooling(model_output, encoded_input['attention_mask'])
            normalized_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)
            embeddings = normalized_embeddings.tolist()
            total_tokens = sum(len(tokenizer(t, add_special_tokens=False)['input_ids']) for t in texts)
        else:
            sbert_model: SentenceTransformer = loaded_model
            embeddings = sbert_model.encode(texts, normalize_embeddings=True).tolist()
            total_tokens = sum(len(sbert_model.tokenizer(t, add_special_tokens=False)['input_ids']) for t in texts)

        return embeddings, total_tokens, None
    except Exception as e:
        logger.error(f"[{request_id}-{request_type.upper()}] Internal processing error: {e}", exc_info=True)
        return None, None, "Internal server error during embedding creation."


async def _process_embeddings_request(request: EmbeddingRequest, model_mgr: ModelManager, request_type: str) -> EmbeddingResponse:
    """Асинхронная обертка, которая вызывает синхронный код в пуле потоков."""
    request_id = str(uuid.uuid4())[:8]
    texts = [request.input] if isinstance(request.input, str) else request.input
    if not texts or not all(isinstance(t, str) for t in texts):
        raise HTTPException(status_code=400, detail="Input must be a non-empty string or a list of non-empty strings.")

    logger.info(f"[{request_id}-{request_type.upper()}] Received request for model '{request.model}'. Offloading to thread pool.")
    
    start_time = time.perf_counter()
    embeddings, total_tokens, error = await run_in_threadpool(
        _create_embeddings_sync, texts, model_mgr, request.model, request_id, request_type
    )
    
    if error:
        raise HTTPException(status_code=500, detail=error)

    duration = time.perf_counter() - start_time
    logger.info(f"[{request_id}-{request_type.upper()}] Request processed in {duration:.4f} seconds.")

    embedding_data = [EmbeddingData(embedding=emb, index=i) for i, emb in enumerate(embeddings)]
    return EmbeddingResponse(
        data=embedding_data,
        model=request.model,
        usage=Usage(prompt_tokens=total_tokens, total_tokens=total_tokens)
    )

# --- API Эндпоинты ---

@app.post("/v1/embeddings/cpu", response_model=EmbeddingResponse, tags=["Embeddings"])
async def create_cpu_embeddings(request: EmbeddingRequest):
    return await _process_embeddings_request(request, cpu_model_manager, "cpu")

@app.post("/v1/embeddings/gpu", response_model=EmbeddingResponse, tags=["Embeddings"])
async def create_gpu_embeddings(request: EmbeddingRequest):
    return await _process_embeddings_request(request, gpu_model_manager, "gpu")

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "cpu_manager_info": {
            "effective_device": str(cpu_model_manager.device),
            "cached_models_count": len(cpu_model_manager.cache)
        },
        "gpu_manager_info": {
            "effective_device": str(gpu_model_manager.device),
            "gpu_library_available": _GPU_AVAILABLE,
            "cached_models_count": len(gpu_model_manager.cache)
        }
    }