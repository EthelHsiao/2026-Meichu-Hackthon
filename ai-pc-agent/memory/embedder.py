"""文字 -> 向量。存記憶和查詢都必須用同一個模型（config.EMBED_MODEL）。"""
from __future__ import annotations

import numpy as np


class Embedder:
    def __init__(self, model_name: str):
        self.name = model_name
        self._model = None  # 第一次 encode 才載入（bge-m3 約 2GB，載入要幾秒）

    def encode(self, texts: list[str]) -> np.ndarray:
        """回傳 shape (len(texts), dim) 的 float32 陣列，已 normalize（內積 = cosine）。"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.name)
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)
