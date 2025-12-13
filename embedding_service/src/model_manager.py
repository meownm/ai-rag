# src/model_manager.py
import time
import threading
import logging
from typing import Dict, Any, Union
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer
import torch

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

# --- СПИСКИ СПЕЦИАЛЬНЫХ МОДЕЛЕЙ ---
TRUSTED_MODELS = {
    "ai-sage/Giga-Embeddings-instruct",
}
# Модели, которые нужно загружать напрямую через transformers, минуя SentenceTransformer
RAW_TRANSFORMERS_MODELS = {
    "ai-sage/Giga-Embeddings-instruct",
}
# ------------------------------------

class ModelCacheEntry:
    def __init__(self, model_name: str, device: str):
        self.model_name = model_name
        self.device = device
        self.model: Any = None # Может быть SentenceTransformer или (AutoModel, AutoTokenizer)
        self.last_accessed: float = time.time()
        self.lock = threading.Lock()

class ModelManager:
    def __init__(self, unload_timeout_seconds: int = 1800):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[Startup] Сервис будет использовать устройство: {self.device.upper()}")
        self.cache: Dict[str, ModelCacheEntry] = {}
        self.unload_timeout = unload_timeout_seconds
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._stop_event = threading.Event()

    def get_model(self, model_name: str, request_id: str = "N/A") -> Any:
        with self._lock:
            if model_name not in self.cache:
                logger.info(f"[{request_id}] Модель '{model_name}' не в кэше. Создание новой записи.")
                self.cache[model_name] = ModelCacheEntry(model_name, self.device)
        
        entry = self.cache[model_name]
        if entry.model is not None:
            logger.info(f"[{request_id}] Cache hit для модели '{model_name}'.")
            entry.last_accessed = time.time()
            return entry.model

        with entry.lock:
            if entry.model is None:
                start_time = time.perf_counter()
                try:
                    # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: ВЫБИРАЕМ СПОСОБ ЗАГРУЗКИ ---
                    if model_name in RAW_TRANSFORMERS_MODELS:
                        logger.info(f"[{request_id}] Загрузка модели '{model_name}' через 'transformers'...")
                        trust_code = model_name in TRUSTED_MODELS
                        if trust_code:
                            logger.warning(f"[{request_id}] Модель '{model_name}' требует trust_remote_code=True.")
                        
                        tokenizer = AutoTokenizer.from_pretrained(model_name)
                        model = AutoModel.from_pretrained(model_name, trust_remote_code=trust_code)
                        model.to(self.device)
                        model.eval()
                        entry.model = (model, tokenizer) # Сохраняем как кортеж
                    else:
                        logger.info(f"[{request_id}] Загрузка модели '{model_name}' через 'sentence-transformers'...")
                        model_kwargs = {}
                        if model_name in TRUSTED_MODELS:
                            logger.warning(f"[{request_id}] Модель '{model_name}' требует trust_remote_code=True.")
                            model_kwargs['trust_remote_code'] = True
                        
                        sbert_model = SentenceTransformer(model_name, device=self.device, **model_kwargs)
                        entry.model = sbert_model
                    # --------------------------------------------------------
                    duration = time.perf_counter() - start_time
                    logger.info(f"[{request_id}] Модель '{model_name}' успешно загружена за {duration:.2f} секунд.")
                except Exception as e:
                    with self._lock:
                        if model_name in self.cache: del self.cache[model_name]
                    logger.error(f"[{request_id}] Ошибка при загрузке модели '{model_name}': {e}", exc_info=True)
                    raise
        
        entry.last_accessed = time.time()
        return entry.model

    # ... (остальной код ModelManager остается без изменений) ...
    def _cleanup_worker(self):
        logger.info("[Cleanup] Фоновый поток очистки кэша запущен.")
        while not self._stop_event.is_set():
            self._stop_event.wait(60)
            logger.info("[Cleanup] Проверка кэша на наличие неактивных моделей...")
            now = time.time()
            models_to_unload = []
            with self._lock:
                if not self.cache:
                    logger.info("[Cleanup] Кэш пуст. Пропускаем проверку.")
                    continue
                for model_name, entry in list(self.cache.items()):
                    if entry.model is not None:
                        idle_time = now - entry.last_accessed
                        if idle_time > self.unload_timeout:
                            models_to_unload.append((model_name, idle_time))
                if models_to_unload:
                    for model_name, idle_time in models_to_unload:
                        logger.warning(f"[Cleanup] Модель '{model_name}' неактивна {idle_time:.0f}с. Выгрузка из памяти.")
                        del self.cache[model_name]
                        if self.device == "cuda":
                            torch.cuda.empty_cache()
                else:
                    logger.info("[Cleanup] Не найдено неактивных моделей для выгрузки.")

    def start_cleanup_thread(self): self._cleanup_thread.start()
    def stop_cleanup_thread(self):
        logger.info("[Shutdown] Остановка фонового потока очистки кэша моделей.")
        self._stop_event.set()
        self._cleanup_thread.join()

model_manager = ModelManager(unload_timeout_seconds=1800)