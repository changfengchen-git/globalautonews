"""
HTTP 抓取器 (支持静态和动态渲染)

核心类: Fetcher

公开方法:
    async def fetch(url: str, rendering: str = "static") -> FetchResult

FetchResult 数据类:
    url: str              # 最终URL（可能经过重定向）
    status_code: int      # HTTP 状态码
    html: str             # 页面 HTML 内容
    content_length: int   # 内容长度(字符数)
    response_time_ms: int # 响应时间(毫秒)
    encoding: str         # 检测到的编码
    error: str | None     # 错误信息（成功时为 None）

实现要求:

1. 使用 httpx.AsyncClient，启用 HTTP/2，复用连接池
2. User-Agent 轮换：从 config/settings.yaml 读取 UA 列表，每次请求随机选一个
3. 编码自动检测：
   - 优先使用 HTTP header 中的 charset
   - 其次使用 HTML <meta charset> 标签
   - 最后使用 charset-normalizer 自动检测
4. 重试机制：
   - 最多重试 2 次（共 3 次尝试）
   - 仅对 5xx 和超时进行重试
   - 4xx 不重试
   - 重试间隔 2 秒
5. 超时控制：
   - 静态模式：30 秒
   - 连接超时：10 秒
6. 全局单例 AsyncClient，在 Fetcher 初始化时创建，在 close() 时销毁
7. 跟随重定向（最多 5 次）
8. 请求头设置：
   - Accept: text/html,application/xhtml+xml
   - Accept-Language: en-US,en;q=0.9
   - Accept-Encoding: gzip, deflate, br
9. 错误处理：
   - 网络错误 → FetchResult(error="connection_error: ...")
   - 超时 → FetchResult(error="timeout")
   - HTTP 4xx/5xx → FetchResult(error="http_{status_code}")
   - 成功但内容为空 → FetchResult(error="empty_response")

10. Playwright 动态渲染支持：
    - 通过 PLAYWRIGHT_ENABLED 环境变量控制（默认 true）
    - 使用 asyncio.Semaphore(2) 限制最多 2 个并发浏览器页面
    - 全局维护一个 Browser 实例，懒加载
    - 当 rendering="dynamic" 且 Playwright 已启用 → 使用 Playwright
    - 当 rendering="dynamic" 但 Playwright 未启用 → 回退静态抓取 + 警告日志
"""
import time
import random
import logging
import re
import os
from dataclasses import dataclass
from typing import Optional, List
from urllib.parse import urlparse

import httpx
import yaml

logger = logging.getLogger("crawler.fetcher")

# Playwright support
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Dynamic rendering will not be available.")


@dataclass
class FetchResult:
    url: str
    status_code: int = 0
    html: str = ""
    content_length: int = 0
    response_time_ms: int = 0
    encoding: str = "utf-8"
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code == 200


class Fetcher:
    def __init__(self, settings_path: str = "/app/config/settings.yaml"):
        """
        初始化 Fetcher。
        - 加载 settings.yaml 中的 user_agents 列表
        - 创建 httpx.AsyncClient 实例
        - 初始化 Playwright（如果启用）
        """
        self.settings_path = settings_path
        self.user_agents: List[str] = []
        self.client: Optional[httpx.AsyncClient] = None
        
        # Playwright 相关
        self._playwright_enabled = os.getenv("PLAYWRIGHT_ENABLED", "true").lower() == "true"
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._pw_semaphore = None
        self._pw_initialized = False
        
        self._load_settings()
        self._create_client()
        
        # 如果 Playwright 启用，初始化 semaphore
        if self._playwright_enabled and PLAYWRIGHT_AVAILABLE:
            import asyncio
            self._pw_semaphore = asyncio.Semaphore(2)

    def _load_settings(self):
        """加载配置文件"""
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            crawler_config = config.get("crawler", {})
            self.user_agents = crawler_config.get("user_agents", [])
            
            # 默认 UA 列表
            if not self.user_agents:
                self.user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
                ]
            
            logger.info(f"Loaded {len(self.user_agents)} user agents")
            
        except Exception as e:
            logger.warning(f"Failed to load settings from {self.settings_path}: {e}")
            # 使用默认 UA
            self.user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            ]

    def _create_client(self):
        """创建 HTTP 客户端"""
        self.client = httpx.AsyncClient(
            http2=True,  # 启用 HTTP/2
            timeout=httpx.Timeout(
                connect=10.0,  # 连接超时 10 秒
                read=30.0,     # 读取超时 30 秒
                write=10.0,    # 写入超时 10 秒
                pool=30.0,     # 连接池超时 30 秒
            ),
            follow_redirects=True,  # 跟随重定向
            max_redirects=5,        # 最多 5 次重定向
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        )

    async def fetch(self, url: str, rendering: str = "static") -> FetchResult:
        """
        抓取指定 URL 的页面内容。
        
        参数:
            url: 目标 URL
            rendering: "static" 或 "dynamic"
        
        返回:
            FetchResult 对象
        """
        # 动态渲染模式
        if rendering == "dynamic":
            if self._playwright_enabled and PLAYWRIGHT_AVAILABLE:
                # 使用 Playwright 抓取
                try:
                    return await self._fetch_dynamic(url)
                except Exception as e:
                    logger.error(f"Playwright fetch failed for {url}: {e}, falling back to static")
                    # 降级为静态抓取
                    return await self._fetch_static_with_retry(url)
            else:
                # Playwright 未启用或不可用，回退到静态抓取
                logger.warning(f"Dynamic rendering requested for {url} but Playwright not available/enabled, falling back to static")
                return await self._fetch_static_with_retry(url)
        
        # 静态渲染模式
        return await self._fetch_static_with_retry(url)
    
    async def _fetch_static_with_retry(self, url: str) -> FetchResult:
        """静态抓取（带重试机制）"""
        # 重试机制：最多尝试 3 次
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                result = await self._fetch_once(url, attempt)
                
                # 如果成功，返回结果
                if result.error is None:
                    return result
                
                # 如果是 4xx 错误，不重试
                if result.status_code >= 400 and result.status_code < 500:
                    return result
                
                # 如果是超时或 5xx 错误，记录并可能重试
                last_error = result.error
                
                if attempt < max_attempts - 1:
                    logger.warning(f"Attempt {attempt + 1} failed for {url}: {result.error}, retrying...")
                    import asyncio
                    await asyncio.sleep(2)  # 重试间隔 2 秒
                    
            except Exception as e:
                last_error = f"unexpected_error: {str(e)}"
                logger.error(f"Unexpected error on attempt {attempt + 1} for {url}: {e}")
                
                if attempt < max_attempts - 1:
                    import asyncio
                    await asyncio.sleep(2)
        
        # 所有尝试都失败
        return FetchResult(
            url=url,
            error=last_error or "max_attempts_exceeded"
        )

    async def _fetch_once(self, url: str, attempt: int) -> FetchResult:
        """单次抓取尝试"""
        start_time = time.time()
        
        try:
            # 随机选择 User-Agent
            headers = {"User-Agent": self._get_random_ua()}
            
            # 发送请求
            response = await self.client.get(url, headers=headers)
            
            # 计算响应时间
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # 检测编码
            encoding = self._detect_encoding(response)
            
            # 解码内容
            try:
                html = response.content.decode(encoding)
            except UnicodeDecodeError:
                # 如果解码失败，尝试其他编码
                html = response.content.decode("utf-8", errors="replace")
                encoding = "utf-8"
            
            # 检查 HTTP 状态码
            if response.status_code >= 400:
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    html=html,
                    content_length=len(html),
                    response_time_ms=response_time_ms,
                    encoding=encoding,
                    error=f"http_{response.status_code}"
                )
            
            # 检查内容是否为空
            if not html.strip():
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    html="",
                    content_length=0,
                    response_time_ms=response_time_ms,
                    encoding=encoding,
                    error="empty_response"
                )
            
            # 成功
            return FetchResult(
                url=str(response.url),
                status_code=response.status_code,
                html=html,
                content_length=len(html),
                response_time_ms=response_time_ms,
                encoding=encoding,
                error=None
            )
            
        except httpx.TimeoutException:
            response_time_ms = int((time.time() - start_time) * 1000)
            return FetchResult(
                url=url,
                status_code=0,
                response_time_ms=response_time_ms,
                error="timeout"
            )
            
        except httpx.NetworkError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return FetchResult(
                url=url,
                status_code=0,
                response_time_ms=response_time_ms,
                error=f"connection_error: {str(e)}"
            )
            
        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            return FetchResult(
                url=url,
                status_code=0,
                response_time_ms=response_time_ms,
                error=f"unexpected_error: {str(e)}"
            )
    
    async def _init_playwright(self):
        """初始化 Playwright 浏览器实例（懒加载）"""
        if self._pw_initialized:
            return
        
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not available")
        
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ]
            )
            self._pw_initialized = True
            logger.info("Playwright browser initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {e}")
            raise
    
    async def _fetch_dynamic(self, url: str) -> FetchResult:
        """
        使用 Playwright 抓取动态渲染的页面。
        
        参数:
            url: 目标 URL
        
        返回:
            FetchResult 对象
        """
        import asyncio
        start_time = time.time()
        
        # 确保 Playwright 已初始化
        await self._init_playwright()
        
        async with self._pw_semaphore:
            context: Optional[BrowserContext] = None
            try:
                # 创建新的浏览器上下文
                context = await self._browser.new_context(
                    user_agent=self._get_random_ua(),
                    viewport={"width": 1280, "height": 800},
                    java_script_enabled=True,
                )
                
                page = await context.new_page()
                
                # 设置超时
                page.set_default_timeout(60000)  # 60 秒
                
                # 导航到页面
                response = await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # 获取页面内容
                html = await page.content()
                
                # 计算响应时间
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # 检查 HTTP 状态码
                status_code = response.status if response else 0
                
                if status_code >= 400:
                    return FetchResult(
                        url=url,
                        status_code=status_code,
                        html=html,
                        content_length=len(html),
                        response_time_ms=response_time_ms,
                        encoding="utf-8",
                        error=f"http_{status_code}"
                    )
                
                # 检查内容是否为空
                if not html.strip():
                    return FetchResult(
                        url=url,
                        status_code=status_code,
                        html="",
                        content_length=0,
                        response_time_ms=response_time_ms,
                        encoding="utf-8",
                        error="empty_response"
                    )
                
                # 成功
                return FetchResult(
                    url=url,
                    status_code=status_code,
                    html=html,
                    content_length=len(html),
                    response_time_ms=response_time_ms,
                    encoding="utf-8",
                    error=None
                )
                
            except Exception as e:
                response_time_ms = int((time.time() - start_time) * 1000)
                logger.error(f"Playwright error for {url}: {e}")
                return FetchResult(
                    url=url,
                    status_code=0,
                    response_time_ms=response_time_ms,
                    error=f"playwright_error: {str(e)}"
                )
            finally:
                # 确保关闭上下文
                if context:
                    await context.close()

    def _detect_encoding(self, response: httpx.Response) -> str:
        """
        检测响应编码：
        1. HTTP header charset
        2. HTML meta charset
        3. charset-normalizer 自动检测
        """
        # 1. 检查 HTTP header 中的 charset
        content_type = response.headers.get("content-type", "")
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
            if charset:
                return charset
        
        # 2. 检查 HTML meta charset
        try:
            # 只读取前 1024 字节来检测 meta 标签
            head = response.content[:1024].decode("latin-1", errors="ignore")
            
            # 查找 <meta charset="...">
            meta_match = re.search(r'<meta\s+charset=["\']?([^"\'>\s]+)', head, re.IGNORECASE)
            if meta_match:
                return meta_match.group(1)
            
            # 查找 <meta http-equiv="Content-Type" content="... charset=...">
            meta_match = re.search(r'<meta\s+http-equiv=["\']?Content-Type["\']?\s+content=["\']?[^"\']*charset=([^"\'>\s;]+)', head, re.IGNORECASE)
            if meta_match:
                return meta_match.group(1)
                
        except Exception:
            pass
        
        # 3. 使用 charset-normalizer 自动检测（如果可用）
        try:
            from charset_normalizer import from_bytes
            results = from_bytes(response.content)
            if results.best():
                return results.best().encoding
        except ImportError:
            # charset-normalizer 未安装，使用 chardet
            try:
                import chardet
                result = chardet.detect(response.content)
                if result["encoding"]:
                    return result["encoding"]
            except ImportError:
                pass
        
        # 默认返回 utf-8
        return "utf-8"

    def _get_random_ua(self) -> str:
        """随机返回一个 User-Agent"""
        return random.choice(self.user_agents)

    async def close(self):
        """关闭 HTTP 客户端连接池和 Playwright 浏览器"""
        # 关闭 HTTP 客户端
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("HTTP client closed")
        
        # 关闭 Playwright
        if self._browser:
            try:
                await self._browser.close()
                logger.info("Playwright browser closed")
            except Exception as e:
                logger.error(f"Error closing Playwright browser: {e}")
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
                logger.info("Playwright stopped")
            except Exception as e:
                logger.error(f"Error stopping Playwright: {e}")
            self._playwright = None
        
        self._pw_initialized = False
