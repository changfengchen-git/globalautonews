"""
嵌入向量生成器

支持双模式：
1. local: 使用 sentence-transformers 加载本地模型
2. api: 调用 OpenAI Embeddings API（或兼容接口）

支持 MRL (Matryoshka Representation Learning) 维度裁剪，默认输出 256 维。
"""

import os
import logging
from typing import List, Optional, Union
import numpy as np

logger = logging.getLogger("crawler.embeddings")

# 尝试导入 sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available. Local embedding mode will not work.")

# 尝试导入 openai
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai not available. API embedding mode will not work.")


class EmbeddingGenerator:
    """嵌入向量生成器"""

    def __init__(
        self,
        mode: Optional[str] = None,
        model_name: str = "google/embedding-gemma-3-308m",
        dimensions: int = 256,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        """
        初始化嵌入生成器。

        参数:
            mode: "local" 或 "api"，默认从环境变量 EMBEDDING_MODE 读取
            model_name: 模型名称
            dimensions: 输出维度（MRL 裁剪）
            api_key: API 密钥（API 模式）
            api_base: API 基础 URL（API 模式）
        """
        self.mode = mode or os.getenv("EMBEDDING_MODE", "local")
        self.model_name = model_name
        self.dimensions = dimensions
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("OPENAI_API_BASE")

        self._model = None
        self._initialized = False

        logger.info(f"EmbeddingGenerator initialized: mode={self.mode}, model={self.model_name}, dims={self.dimensions}")

    def _init_local_model(self):
        """初始化本地模型"""
        if self._initialized:
            return

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise RuntimeError("sentence-transformers is not available")

        try:
            logger.info(f"Loading local model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            self._initialized = True
            logger.info("Local model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")
            raise

    def generate(self, texts: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        生成嵌入向量。

        参数:
            texts: 单个文本或文本列表

        返回:
            嵌入向量或向量列表
        """
        if isinstance(texts, str):
            texts = [texts]
            single_input = True
        else:
            single_input = False

        if self.mode == "local":
            embeddings = self._generate_local(texts)
        elif self.mode == "api":
            embeddings = self._generate_api(texts)
        else:
            raise ValueError(f"Unknown embedding mode: {self.mode}")

        # MRL 维度裁剪
        if embeddings and len(embeddings[0]) > self.dimensions:
            embeddings = [emb[:self.dimensions] for emb in embeddings]

        if single_input:
            return embeddings[0]
        return embeddings

    def _generate_local(self, texts: List[str]) -> List[np.ndarray]:
        """使用本地模型生成嵌入"""
        self._init_local_model()

        try:
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return list(embeddings)
        except Exception as e:
            logger.error(f"Local embedding generation failed: {e}")
            raise

    def _generate_api(self, texts: List[str]) -> List[np.ndarray]:
        """使用 API 生成嵌入"""
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai is not available")

        if not self.api_key:
            raise ValueError("API key is required for API mode")

        try:
            # 配置 openai 客户端
            client_kwargs = {"api_key": self.api_key}
            if self.api_base:
                client_kwargs["base_url"] = self.api_base

            client = openai.OpenAI(**client_kwargs)

            # 调用 API
            response = client.embeddings.create(
                model=self.model_name,
                input=texts,
                dimensions=self.dimensions,  # 如果 API 支持
            )

            embeddings = []
            for item in response.data:
                embeddings.append(np.array(item.embedding, dtype=np.float32))

            return embeddings

        except Exception as e:
            logger.error(f"API embedding generation failed: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """获取嵌入向量维度"""
        return self.dimensions

    def is_available(self) -> bool:
        """检查当前模式是否可用"""
        if self.mode == "local":
            return SENTENCE_TRANSFORMERS_AVAILABLE
        elif self.mode == "api":
            return OPENAI_AVAILABLE and bool(self.api_key)
        return False

    def compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        计算两个嵌入向量的余弦相似度。

        参数:
            emb1: 嵌入向量 1
            emb2: 嵌入向量 2

        返回:
            余弦相似度 (0.0 - 1.0)
        """
        # 归一化
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # 余弦相似度
        similarity = np.dot(emb1, emb2) / (norm1 * norm2)
        return float(similarity)


# 全局单例
_embedding_generator: Optional[EmbeddingGenerator] = None


def get_embedding_generator() -> EmbeddingGenerator:
    """获取全局嵌入生成器单例"""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator
