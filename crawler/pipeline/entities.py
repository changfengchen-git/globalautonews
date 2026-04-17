"""
实体提取器

从文章标题和正文中提取汽车相关实体（品牌、车型、组织名）。

功能:
1. 加载品牌词典 (config/entities/brands.yaml)
2. 加载车型词典 (config/entities/models.yaml)
3. 从文本中提取实体
4. 支持多语言匹配
"""

import logging
import re
from typing import List, Set, Dict, Optional, Tuple
from pathlib import Path

import yaml

logger = logging.getLogger("crawler.entities")


class EntityExtractor:
    """实体提取器"""

    def __init__(
        self,
        brands_path: str = "config/entities/brands.yaml",
        models_path: str = "config/entities/models.yaml"
    ):
        """
        初始化实体提取器。

        参数:
            brands_path: 品牌词典路径
            models_path: 车型词典路径
        """
        self.brands: Dict[str, List[str]] = {}
        self.models: Dict[str, List[str]] = {}
        self.brand_patterns: List[Tuple[str, str]] = []  # (pattern, brand_name)
        self.model_patterns: List[Tuple[str, str]] = []  # (pattern, model_name)

        self._load_dictionaries(brands_path, models_path)
        self._compile_patterns()

    def _load_dictionaries(self, brands_path: str, models_path: str):
        """加载品牌和车型词典"""
        try:
            # 加载品牌词典
            with open(brands_path, "r", encoding="utf-8") as f:
                self.brands = yaml.safe_load(f) or {}
            logger.info(f"Loaded {len(self.brands)} brands")

            # 加载车型词典
            with open(models_path, "r", encoding="utf-8") as f:
                self.models = yaml.safe_load(f) or {}
            logger.info(f"Loaded {len(self.models)} models")

        except FileNotFoundError as e:
            logger.error(f"Dictionary file not found: {e}")
            self.brands = {}
            self.models = {}
        except Exception as e:
            logger.error(f"Error loading dictionaries: {e}")
            self.brands = {}
            self.models = {}

    def _compile_patterns(self):
        """编译正则表达式模式"""
        # 品牌模式
        for brand_name, aliases in self.brands.items():
            # 主名称
            self.brand_patterns.append((self._escape_pattern(brand_name), brand_name))
            # 别名
            for alias in aliases:
                if alias:
                    self.brand_patterns.append((self._escape_pattern(alias), brand_name))

        # 车型模式
        for model_name, aliases in self.models.items():
            # 主名称
            self.model_patterns.append((self._escape_pattern(model_name), model_name))
            # 别名
            for alias in aliases:
                if alias:
                    self.model_patterns.append((self._escape_pattern(alias), model_name))

        # 按长度排序（优先匹配较长的名称）
        self.brand_patterns.sort(key=lambda x: len(x[0]), reverse=True)
        self.model_patterns.sort(key=lambda x: len(x[0]), reverse=True)

        logger.debug(f"Compiled {len(self.brand_patterns)} brand patterns and {len(self.model_patterns)} model patterns")

    def _escape_pattern(self, text: str) -> str:
        """转义正则表达式特殊字符"""
        return re.escape(text)

    def extract(
        self,
        text: str,
        title: str = "",
        max_content_length: int = 200
    ) -> Dict[str, List[str]]:
        """
        从文本中提取实体。

        参数:
            text: 正文内容
            title: 标题
            max_content_length: 正文最大处理长度（字符数）

        返回:
            包含 brands 和 models 的字典
        """
        # 合并标题和正文前部分内容
        combined_text = title + " " + text[:max_content_length]

        # 提取品牌
        brands = self._extract_brands(combined_text)

        # 提取车型
        models = self._extract_models(combined_text)

        return {
            "brands": list(brands),
            "models": list(models)
        }

    def _extract_brands(self, text: str) -> Set[str]:
        """从文本中提取品牌"""
        brands = set()
        text_upper = text.upper()

        for pattern, brand_name in self.brand_patterns:
            # 使用不区分大小写的匹配
            if re.search(pattern, text, re.IGNORECASE):
                brands.add(brand_name)

        return brands

    def _extract_models(self, text: str) -> Set[str]:
        """从文本中提取车型"""
        models = set()

        for pattern, model_name in self.model_patterns:
            # 使用不区分大小写的匹配
            if re.search(pattern, text, re.IGNORECASE):
                models.add(model_name)

        return models

    def extract_brands_only(self, text: str, title: str = "") -> List[str]:
        """仅提取品牌"""
        result = self.extract(text, title)
        return result["brands"]

    def extract_models_only(self, text: str, title: str = "") -> List[str]:
        """仅提取车型"""
        result = self.extract(text, title)
        return result["models"]

    def has_brand(self, text: str, brand_name: str) -> bool:
        """检查文本是否包含指定品牌"""
        brands = self.extract_brands_only(text)
        return brand_name in brands

    def has_model(self, text: str, model_name: str) -> bool:
        """检查文本是否包含指定车型"""
        models = self.extract_models_only(text)
        return model_name in models

    def get_brand_count(self) -> int:
        """获取品牌数量"""
        return len(self.brands)

    def get_model_count(self) -> int:
        """获取车型数量"""
        return len(self.models)

    def get_all_brands(self) -> List[str]:
        """获取所有品牌名称"""
        return list(self.brands.keys())

    def get_all_models(self) -> List[str]:
        """获取所有车型名称"""
        return list(self.models.keys())


# 全局单例
_entity_extractor: Optional[EntityExtractor] = None


def get_entity_extractor() -> EntityExtractor:
    """获取全局实体提取器单例"""
    global _entity_extractor
    if _entity_extractor is None:
        _entity_extractor = EntityExtractor()
    return _entity_extractor
