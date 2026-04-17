#!/usr/bin/env python3
"""
导入站点脚本

从 sites 目录下的文件导入汽车新闻站点到数据库。
支持格式：
1. 完整 URL（如 https://www.example.com/news）
2. 域名（如 example.com）

用法：
    python scripts/import_sites.py [文件路径]
"""

import sys
import re
import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
from typing import List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    # 如果没有 dotenv，手动解析 .env 文件
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from sqlalchemy import select, exists
from shared.database import get_engine, get_session
from shared.models import Source


# 国家代码映射（域名后缀 -> 国家代码）
COUNTRY_MAP = {
    # 通用
    'com': 'US', 'net': 'US', 'org': 'US', 'io': 'US',
    # 国家代码
    'cn': 'CN', 'jp': 'JP', 'kr': 'KR', 'de': 'DE', 'fr': 'FR',
    'uk': 'GB', 'co.uk': 'GB', 'it': 'IT', 'es': 'ES', 'nl': 'NL',
    'br': 'BR', 'mx': 'MX', 'ar': 'AR', 'cl': 'CL', 'co': 'CO',
    'ru': 'RU', 'pl': 'PL', 'se': 'SE', 'no': 'NO', 'dk': 'DK',
    'fi': 'FI', 'th': 'TH', 'vn': 'VN', 'id': 'ID', 'my': 'MY',
    'sg': 'SG', 'ph': 'PH', 'in': 'IN', 'au': 'AU', 'nz': 'NZ',
    'ca': 'CA', 'hk': 'HK', 'tw': 'TW', 'pk': 'PK', 'ae': 'AE',
    'sa': 'SA', 'tr': 'TR', 'il': 'IL', 'eg': 'EG', 'za': 'ZA',
    'ng': 'NG', 'ke': 'KE', 'ua': 'UA', 'cz': 'CZ', 'at': 'AT',
    'ch': 'CH', 'be': 'BE', 'pt': 'PT', 'ro': 'RO', 'hu': 'HU',
}

# 语言映射（域名关键词 -> 语言代码）
LANGUAGE_MAP = {
    # 语言关键词
    'cn': 'zh', 'tw': 'zh', 'hongkong': 'zh',
    'jp': 'ja', 'japan': 'ja',
    'kr': 'ko', 'korea': 'ko',
    'de': 'de', 'german': 'de',
    'fr': 'fr', 'french': 'fr',
    'es': 'es', 'spanish': 'es',
    'pt': 'pt', 'portuguese': 'pt',
    'ru': 'ru', 'russian': 'ru',
    'it': 'it', 'italian': 'it',
    'th': 'th', 'thai': 'th',
    'vn': 'vn', 'vietnam': 'vn',
    'id': 'id', 'indonesia': 'id',
    'ar': 'ar', 'arabic': 'ar',
    'hi': 'hi', 'hindi': 'hi',
}

# 常见汽车关键词（用于识别汽车站点）
AUTO_KEYWORDS = [
    'auto', 'car', 'motor', 'vehicle', 'ev', 'electric',
    'automobile', 'automotive', 'otomotif', 'voiture',
    'carro', 'coche', 'wagen', 'racing', 'f1', 'formula',
    'drive', 'speed', 'turbo', 'engine', 'wheel', 'tire',
]


def parse_sites_file(file_path: str) -> List[dict]:
    """
    解析站点文件，返回站点信息列表。
    
    支持格式：
    - 完整 URL: https://www.example.com/news
    - 域名: example.com
    """
    sites = []
    seen_domains = set()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#') or line.startswith('是否'):
                continue
            
            # 清理行尾空格和特殊字符
            line = line.rstrip(' \t\n\r')
            
            # 解析 URL 或域名
            url = None
            domain = None
            
            if line.startswith('http://') or line.startswith('https://'):
                # 完整 URL
                url = line
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc
                except:
                    continue
            elif re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line):
                # 域名
                domain = line
                url = f"https://{domain}"
            else:
                continue
            
            # 清理域名
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # 去重
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            
            # 检测国家和语言
            country = detect_country(domain, url)
            language = detect_language(domain, url)
            
            # 检测是否是汽车相关站点
            if not is_automotive_site(domain, url):
                # 非汽车站点，跳过或标记
                pass
            
            sites.append({
                'domain': domain,
                'url': url,
                'country': country,
                'language': language,
            })
    
    return sites


def detect_country(domain: str, url: str) -> str:
    """检测站点所属国家"""
    # 检查国家代码域名
    for suffix, country in COUNTRY_MAP.items():
        if domain.endswith(f'.{suffix}'):
            return country
    
    # 检查 URL 中的路径关键词
    url_lower = url.lower()
    country_hints = {
        '/hk/': 'HK', '/tw/': 'TW', '/cn/': 'CN', '/jp/': 'JP',
        '/kr/': 'KR', '/de/': 'DE', '/fr/': 'FR', '/es/': 'ES',
        '/it/': 'IT', '/br/': 'BR', '/mx/': 'MX', '/in/': 'IN',
        '/au/': 'AU', '/uk/': 'GB', '/ru/': 'RU', '/th/': 'TH',
        '/vn/': 'VN', '/id/': 'ID', '/my/': 'MY', '/ph/': 'PH',
    }
    
    for hint, country in country_hints.items():
        if hint in url_lower:
            return country
    
    # 默认美国
    return 'US'


def detect_language(domain: str, url: str) -> str:
    """检测站点语言"""
    # 检查域名中的语言关键词
    domain_lower = domain.lower()
    url_lower = url.lower()
    
    for keyword, lang in LANGUAGE_MAP.items():
        if keyword in domain_lower or keyword in url_lower:
            return lang
    
    # 检查 URL 路径中的语言标识
    lang_hints = {
        '/zh/': 'zh', '/ja/': 'ja', '/ko/': 'ko',
        '/de/': 'de', '/fr/': 'fr', '/es/': 'es',
        '/pt/': 'pt', '/ru/': 'ru', '/ar/': 'ar',
        '/hi/': 'hi', '/th/': 'th', '/vi/': 'vi',
    }
    
    for hint, lang in lang_hints.items():
        if hint in url_lower:
            return lang
    
    # 默认英语
    return 'en'


def is_automotive_site(domain: str, url: str) -> bool:
    """判断是否是汽车相关站点"""
    combined = f"{domain} {url}".lower()
    
    for keyword in AUTO_KEYWORDS:
        if keyword in combined:
            return True
    
    return False


def generate_site_name(domain: str) -> str:
    """根据域名生成站点名称"""
    # 移除 www. 前缀
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # 提取主域名（移除 TLD）
    parts = domain.split('.')
    if len(parts) > 2:
        # 子域名，取第二级
        name = parts[-3] if len(parts) == 3 else parts[-2]
    else:
        name = parts[0]
    
    # 首字母大写
    return name.capitalize()


async def import_sites(file_path: str, dry_run: bool = False):
    """导入站点到数据库"""
    print(f"解析文件: {file_path}")
    sites = parse_sites_file(file_path)
    print(f"找到 {len(sites)} 个唯一站点")
    
    if dry_run:
        print("\n=== 预览模式（不写入数据库）===")
        for i, site in enumerate(sites[:20], 1):
            print(f"{i}. {site['domain']} ({site['country']}, {site['language']})")
        if len(sites) > 20:
            print(f"... 还有 {len(sites) - 20} 个站点")
        return
    
    # 连接数据库
    engine = get_engine()
    
    imported = 0
    skipped = 0
    errors = 0
    
    async with get_session(engine) as session:
        for site in sites:
            try:
                # 检查是否已存在
                result = await session.execute(
                    select(exists().where(Source.domain == site['domain']))
                )
                exists_result = result.scalar()
                
                if exists_result:
                    skipped += 1
                    continue
                
                # 创建新站点
                source = Source(
                    name=generate_site_name(site['domain']),
                    domain=site['domain'],
                    url=site['url'],
                    country=site['country'],
                    language=site['language'],
                    region=get_region(site['country']),
                    tier=1,
                    rendering='static',
                    has_rss=False,
                    priority='medium',
                    status='active',
                    crawl_interval_minutes=240,
                    next_crawl_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                )
                
                session.add(source)
                imported += 1
                
                if imported % 10 == 0:
                    print(f"已导入 {imported} 个站点...")
                    await session.flush()
                    
            except Exception as e:
                errors += 1
                print(f"错误: {site['domain']} - {e}")
        
        # 提交事务
        await session.commit()
    
    print(f"\n导入完成:")
    print(f"  - 新增: {imported}")
    print(f"  - 跳过（已存在）: {skipped}")
    print(f"  - 错误: {errors}")


def get_region(country: str) -> str:
    """根据国家代码获取地区"""
    region_map = {
        # 亚洲
        'CN': 'Asia', 'JP': 'Asia', 'KR': 'Asia', 'IN': 'Asia',
        'TH': 'Asia', 'VN': 'Asia', 'ID': 'Asia', 'MY': 'Asia',
        'SG': 'Asia', 'PH': 'Asia', 'HK': 'Asia', 'TW': 'Asia',
        'PK': 'Asia', 'AE': 'Asia', 'SA': 'Asia',
        # 欧洲
        'DE': 'Europe', 'FR': 'Europe', 'GB': 'Europe', 'IT': 'Europe',
        'ES': 'Europe', 'NL': 'Europe', 'SE': 'Europe', 'NO': 'Europe',
        'DK': 'Europe', 'FI': 'Europe', 'PL': 'Europe', 'RU': 'Europe',
        'CZ': 'Europe', 'AT': 'Europe', 'CH': 'Europe', 'BE': 'Europe',
        'PT': 'Europe', 'RO': 'Europe', 'HU': 'Europe', 'UA': 'Europe',
        # 北美
        'US': 'North America', 'CA': 'North America', 'MX': 'North America',
        # 南美
        'BR': 'South America', 'AR': 'South America', 'CL': 'South America',
        'CO': 'South America',
        # 大洋洲
        'AU': 'Oceania', 'NZ': 'Oceania',
        # 非洲/中东
        'ZA': 'Africa', 'NG': 'Africa', 'KE': 'Africa',
        'IL': 'Middle East', 'EG': 'Africa', 'TR': 'Europe',
    }
    return region_map.get(country, 'Other')


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='导入汽车新闻站点')
    parser.add_argument('file', nargs='?', default='sites/sites0415', help='站点文件路径')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不写入数据库')
    
    args = parser.parse_args()
    
    file_path = Path(__file__).parent.parent / args.file
    
    if not file_path.exists():
        print(f"文件不存在: {file_path}")
        sys.exit(1)
    
    asyncio.run(import_sites(str(file_path), dry_run=args.dry_run))
