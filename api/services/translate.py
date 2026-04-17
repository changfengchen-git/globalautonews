"""
按需翻译服务

支持 DeepL API 和 Google Translate 两种翻译引擎。
"""

import os
import logging
from typing import Optional, Dict, Tuple
from enum import Enum

logger = logging.getLogger("api.services.translate")


class TranslationEngine(str, Enum):
    DEEPL = "deepl"
    GOOGLE = "google"
    MOCK = "mock"


class TranslationService:
    """翻译服务"""

    def __init__(self):
        """初始化翻译服务"""
        self.deepl_api_key = os.getenv("DEEPL_API_KEY")
        self.deepl_api_url = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
        
        # 确定使用的引擎
        if self.deepl_api_key:
            self.engine = TranslationEngine.DEEPL
            logger.info("Using DeepL API for translation")
        else:
            self.engine = TranslationEngine.GOOGLE
            logger.info("Using Google Translate for translation")

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        翻译文本。

        参数:
            text: 要翻译的文本
            target_language: 目标语言代码 (en, zh, ja, ko, de, fr, es)
            source_language: 源语言代码（可选，自动检测）

        返回:
            (translated_text, detected_source_language)
        """
        if not text or not text.strip():
            return "", ""

        try:
            if self.engine == TranslationEngine.DEEPL:
                return await self._translate_deepl(text, target_language, source_language)
            else:
                return await self._translate_google(text, target_language, source_language)

        except Exception as e:
            logger.error(f"Translation error: {e}")
            # 返回原文
            return text, source_language or "unknown"

    async def _translate_deepl(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> Tuple[str, str]:
        """使用 DeepL API 翻译"""
        import httpx

        # DeepL 语言代码映射
        deepl_target = self._to_deepl_language(target_language)
        
        data = {
            "text": [text[:5000]],  # DeepL 限制
            "target_lang": deepl_target,
        }
        
        if source_language:
            data["source_lang"] = self._to_deepl_language(source_language)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.deepl_api_url,
                params={"auth_key": self.deepl_api_key},
                data=data,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise Exception(f"DeepL API error: {response.status_code}")

            result = response.json()
            
            if not result.get("translations"):
                raise Exception("No translations returned from DeepL")

            translation = result["translations"][0]
            translated_text = translation["text"]
            detected_lang = translation.get("detected_source_language", "unknown")

            return translated_text, detected_lang

    async def _translate_google(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> Tuple[str, str]:
        """使用 Google Translate（免费）"""
        try:
            from googletrans import Translator
            
            translator = Translator()
            
            # 翻译
            result = translator.translate(
                text[:5000],  # 限制长度
                dest=target_language,
                src=source_language or 'auto'
            )
            
            return result.text, result.src

        except ImportError:
            # googletrans 未安装，使用 mock
            logger.warning("googletrans not installed, using mock translation")
            return self._mock_translate(text, target_language)

    def _mock_translate(self, text: str, target_language: str) -> Tuple[str, str]:
        """模拟翻译（用于测试）"""
        # 简单的前缀标记
        prefixes = {
            "zh": "[中文翻译] ",
            "en": "[English] ",
            "ja": "[日本語] ",
            "ko": "[한국어] ",
            "de": "[Deutsch] ",
            "fr": "[Français] ",
            "es": "[Español] ",
        }
        
        prefix = prefixes.get(target_language, f"[{target_language}] ")
        return prefix + text[:500], "auto"

    def _to_deepl_language(self, lang: str) -> str:
        """转换为 DeepL 语言代码"""
        mapping = {
            "en": "EN",
            "zh": "ZH",
            "ja": "JA",
            "ko": "KO",
            "de": "DE",
            "fr": "FR",
            "es": "ES",
            "it": "IT",
            "pt": "PT",
            "ru": "RU",
        }
        return mapping.get(lang.lower(), lang.upper())

    def is_available(self) -> bool:
        """检查翻译服务是否可用"""
        return True  # 总是可用（有 mock fallback）

    def get_engine(self) -> str:
        """获取当前使用的引擎"""
        return self.engine.value


# 全局单例
_translation_service: Optional[TranslationService] = None


def get_translation_service() -> TranslationService:
    """获取全局翻译服务单例"""
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
