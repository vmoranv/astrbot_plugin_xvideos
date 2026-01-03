"""
缓存管理模块
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timedelta


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str, ttl: int = 3600):
        """
        初始化缓存管理器
        
        Args:
            cache_dir: 缓存目录
            ttl: 缓存过期时间（秒）
        """
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self.lock = asyncio.Lock()
        
        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_key(self, key: str) -> str:
        """
        生成缓存键的文件名
        
        Args:
            key: 缓存键
            
        Returns:
            缓存文件名
        """
        # 使用MD5哈希作为文件名
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_cache_path(self, key: str) -> Path:
        """
        获取缓存文件路径
        
        Args:
            key: 缓存键
            
        Returns:
            缓存文件路径
        """
        cache_key = self._get_cache_key(key)
        return self.cache_dir / f"{cache_key}.json"
    
    def _is_expired(self, cache_path: Path) -> bool:
        """
        检查缓存是否过期
        
        Args:
            cache_path: 缓存文件路径
            
        Returns:
            是否过期
        """
        if not cache_path.exists():
            return True
        
        # 获取文件修改时间
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        expiry_time = mtime + timedelta(seconds=self.ttl)
        
        return datetime.now() > expiry_time
    
    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或过期则返回None
        """
        async with self.lock:
            cache_path = self._get_cache_path(key)
            
            if self._is_expired(cache_path):
                # 缓存过期，删除文件
                if cache_path.exists():
                    cache_path.unlink()
                return None
            
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('value')
            except (json.JSONDecodeError, IOError):
                return None
    
    async def set(self, key: str, value: Any) -> None:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        async with self.lock:
            cache_path = self._get_cache_path(key)
            
            data = {
                'key': key,
                'value': value,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def delete(self, key: str) -> None:
        """
        删除缓存
        
        Args:
            key: 缓存键
        """
        async with self.lock:
            cache_path = self._get_cache_path(key)
            if cache_path.exists():
                cache_path.unlink()
    
    async def clear(self) -> None:
        """清空所有缓存"""
        async with self.lock:
            for cache_file in self.cache_dir.glob('*.json'):
                cache_file.unlink()
    
    async def cleanup_expired(self) -> int:
        """
        清理过期缓存
        
        Returns:
            清理的文件数量
        """
        async with self.lock:
            count = 0
            for cache_file in self.cache_dir.glob('*.json'):
                if self._is_expired(cache_file):
                    cache_file.unlink()
                    count += 1
            return count
    
    def set_ttl(self, ttl: int) -> None:
        """
        设置缓存过期时间
        
        Args:
            ttl: 缓存过期时间（秒）
        """
        self.ttl = ttl
