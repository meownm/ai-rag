# model_manager.py
import time
import threading
import logging
from typing import Dict, Any
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer
import torch

# Проверяем доступность CUDA API (работает и для NVIDIA, и для AMD ROCm)
_GPU_AVAILABLE = torch.cuda.is_available()

logger = logging.getLogger(__name__)

# Списки специальных моделей
TRUSTED_MODELS = {"ai-sage/Giga-Embeddings-instruct"}
RAW_TRANSFORMERS_MODELS = {"ai-sage/Giga-Embeddings-instruct"}

class ModelCacheEntry:
    """Запись в кэше, содержащая саму модель и метаданные."""
    def __init__(self, model_name: str, device: str):
        self.model_name = model_name
        self.device = device
        self.model: Any = None
        self.last_accessed: float = time.time()
        self.lock = threading.Lock()

class ModelManager:
    """Управляет жизненным циклом моделей: загрузка, кэширование, выгрузка."""
    def __init__(self, preferred_device: str, unload_timeout_seconds: int = 1800):
        self.preferred_device = preferred_device
        self.unload_timeout = unload_timeout_seconds
        self.cache: Dict[str, ModelCacheEntry] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._stop_event = threading.Event()

        # Логика выбора устройства для контейнера
        if self.preferred_device == "gpu" and _GPU_AVAILABLE:
            self.device = "cuda:0"
            try:
                gpu_name = torch.cuda.get_device_name(0)
            except Exception:
                gpu_name = "N/A"
            logger.info(f"[Startup-GPU] Manager will use device: {self.device} ({gpu_name})")
        else:
            self.device = "cpu"
            if self.preferred_device == "gpu":
                logger.warning("[Startup-GPU] CUDA/ROCm not available. Falling back to CPU for GPU queue.")
            else:
                logger.info("[Startup-CPU] Manager will use device: CPU")

    def get_model(self, model_name: str, request_id: str = "N/A") -> Any:
        """Получает модель из кэша или загружает ее, если она отсутствует."""
        with self._lock:
            if model_name not in self.cache:
                logger.info(f"[{request_id}-{self.preferred_device.upper()}] Model '{model_name}' not in cache. Creating new entry.")
                self.cache[model_name] = ModelCacheEntry(model_name, self.device)
        
        entry = self.cache[model_name]
        if entry.model is not None:
            logger.info(f"[{request_id}-{self.preferred_device.upper()}] Cache hit for model '{model_name}'.")
            entry.last_accessed = time.time()
            return entry.model

        # Блокировка на уровне конкретной модели, чтобы избежать двойной загрузки
        with entry.lock:
            # Повторная проверка, так как модель могла быть загружена, пока поток ждал блокировки
            if entry.model is not None:
                return entry.model
            
            start_time = time.perf_counter()
            try:
                if model_name in RAW_TRANSFORMERS_MODELS:
                    logger.info(f"[{request_id}-{self.preferred_device.upper()}] Loading model '{model_name}' via 'transformers' on {self.device}...")
                    trust_code = model_name in TRUSTED_MODELS
                    tokenizer = AutoTokenizer.from_pretrained(model_name)
                    model = AutoModel.from_pretrained(model_name, trust_remote_code=trust_code)
                    model.to(self.device)
                    model.eval()
                    entry.model = (model, tokenizer)
                else:
                    logger.info(f"[{request_id}-{self.preferred_device.upper()}] Loading model '{model_name}' via 'sentence-transformers' on {self.device}...")
                    model_kwargs = {'trust_remote_code': True} if model_name in TRUSTED_MODELS else {}
                    sbert_model = SentenceTransformer(model_name, device=self.device, **model_kwargs)
                    entry.model = sbert_model
                
                duration = time.perf_counter() - start_time
                logger.info(f"[{request_id}-{self.preferred_device.upper()}] Model '{model_name}' loaded in {duration:.2f} seconds on {self.device}.")
            except Exception as e:
                # В случае ошибки удаляем запись из кэша, чтобы можно было попробовать снова
                with self._lock:
                    if model_name in self.cache:
                        del self.cache[model_name]
                logger.error(f"[{request_id}-{self.preferred_device.upper()}] Failed to load model '{model_name}' on {self.device}: {e}", exc_info=True)
                raise
        
        entry.last_accessed = time.time()
        return entry.model

    def _cleanup_worker(self):
        """Фоновый поток, который периодически проверяет кэш и выгружает старые модели."""
        logger.info(f"[Cleanup-{self.preferred_device.upper()}] Cache cleanup thread started for {self.device}.")
        while not self._stop_event.is_set():
            self._stop_event.wait(60)
            now = time.time()
            models_to_unload = [
                name for name, entry in self.cache.items()
                if entry.model is not None and (now - entry.last_accessed) > self.unload_timeout
            ]

            if models_to_unload:
                with self._lock:
                    for model_name in models_to_unload:
                        # Убедимся, что модель все еще существует, прежде чем удалять
                        if model_name in self.cache:
                            entry = self.cache[model_name]
                            idle_time = now - entry.last_accessed
                            logger.warning(f"[Cleanup-{self.preferred_device.upper()}] Unloading model '{model_name}' due to inactivity ({idle_time:.0f}s) from {self.device}.")
                            del self.cache[model_name]
                            # Очищаем VRAM, если использовался GPU
                            if self.device.startswith("cuda"):
                                torch.cuda.empty_cache()

    def start_cleanup_thread(self):
        """Запускает фоновый поток очистки."""
        self._cleanup_thread.start()

    def stop_cleanup_thread(self):
        """Останавливает фоновый поток очистки."""
        logger.info(f"[Shutdown-{self.preferred_device.upper()}] Stopping cache cleanup thread for {self.device}.")
        self._stop_event.set()
        self._cleanup_thread.join()```