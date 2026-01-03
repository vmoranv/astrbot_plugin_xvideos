"""
AstrBot XVideos 插件
提供视频搜索、视频信息查询等功能
"""
import os
import sys
import asyncio
from pathlib import Path
from typing import Optional

from astrbot.api import star
from astrbot.api.star import Context
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# 添加当前目录到 Python 路径，以便导入 utils 模块
_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from utils.xvideos_client import XVideosClient
from utils.image_processor import ImageProcessor
from utils.cache_manager import CacheManager


class Main(star.Star):
    """XVideos 插件主类"""
    
    # 硬编码的URL前缀
    VIDEO_URL_PREFIX = "https://www.xvideos.com/video"
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        
        # 获取插件数据目录
        data_path = get_astrbot_data_path()
        self.plugin_data_dir = Path(os.path.join(data_path, "plugin_data", "astrbot_plugin_xvideos"))
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存目录
        self.cache_dir = self.plugin_data_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        # 临时文件目录
        self.temp_dir = self.plugin_data_dir / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        
        # 初始化组件
        self.client: Optional[XVideosClient] = None
        self.image_processor: Optional[ImageProcessor] = None
        self.cache_manager: Optional[CacheManager] = None
        
        # 上一次发送的文件路径（用于清理）
        self.last_sent_files = []
        
        logger.info("XVideos 插件初始化完成")
    
    async def initialize(self):
        """插件初始化"""
        # 获取配置
        config = self.context.get_config(umo=None)
        
        proxy_url = config.get("proxy_url", "")
        blur_level = config.get("blur_level", 50)
        cache_enabled = config.get("cache_enabled", True)
        cache_ttl = config.get("cache_ttl", 3600)
        
        # 初始化客户端
        self.client = XVideosClient(proxy_url=proxy_url if proxy_url else None)
        
        # 初始化图片处理器
        self.image_processor = ImageProcessor(blur_level=blur_level)
        
        # 初始化缓存管理器
        if cache_enabled:
            self.cache_manager = CacheManager(str(self.cache_dir), ttl=cache_ttl)
        
        logger.info("XVideos 插件已激活")
    
    async def terminate(self):
        """插件终止清理"""
        # 关闭客户端
        if self.client:
            await self.client.close()
        
        # 清理临时文件
        await self._cleanup_temp_files()
        
        logger.info("XVideos 插件已停用")
    
    async def _cleanup_temp_files(self):
        """清理临时文件"""
        for file_path in self.last_sent_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"已清理临时文件: {file_path}")
            except Exception as e:
                logger.warning(f"清理文件失败 {file_path}: {e}")
        
        self.last_sent_files.clear()
    
    async def _cleanup_before_send(self):
        """发送前清理上一次的缓存文件"""
        await self._cleanup_temp_files()
    
    async def _get_video_url(self, video_id: str) -> str:
        """
        获取视频完整URL
        
        Args:
            video_id: 视频ID
            
        Returns:
            完整的视频URL
        """
        return f"{self.VIDEO_URL_PREFIX}{video_id}"
    
    async def _format_video_info(self, video_info: dict) -> str:
        """
        格式化视频信息
        
        Args:
            video_info: 视频信息字典
            
        Returns:
            格式化后的文本
        """
        lines = [
            f"📹 标题: {video_info.get('title', '未知')}",
            f"⏱️ 时长: {video_info.get('duration', '未知')}",
            f"👁️ 观看: {video_info.get('views', '未知')}",
            f"👍 点赞: {video_info.get('likes', '未知')}",
            f"👎 踩: {video_info.get('dislikes', '未知')}",
        ]
        
        if video_info.get('tags'):
            tags_str = ', '.join(video_info['tags'][:10])  # 最多显示10个标签
            lines.append(f"🏷️ 标签: {tags_str}")
        
        return '\n'.join(lines)
    
    async def _download_and_process_thumbnail(self, thumbnail_url: str) -> Optional[str]:
        """
        下载并处理缩略图
        
        Args:
            thumbnail_url: 缩略图URL
            
        Returns:
            处理后的图片路径
        """
        try:
            # 生成临时文件名
            import hashlib
            file_hash = hashlib.md5(thumbnail_url.encode()).hexdigest()[:16]
            temp_path = str(self.temp_dir / f"thumb_{file_hash}.jpg")
            
            # 下载缩略图
            downloaded_path = await self.client.download_thumbnail(thumbnail_url, temp_path)
            
            # 应用打码处理
            processed_path = await self.image_processor.process_image(downloaded_path)
            
            # 记录文件以便后续清理
            self.last_sent_files.append(processed_path)
            
            return processed_path
            
        except Exception as e:
            logger.error(f"处理缩略图失败: {e}")
            return None
    
    @filter.command("xv_search")
    async def search_videos(self, event: AstrMessageEvent, query: str = ""):
        """
        搜索视频
        
        用法: /xv_search <关键词>
        """
        # 清理上一次的缓存文件
        await self._cleanup_before_send()
        
        # 检查搜索关键词
        if not query:
            yield event.plain_result("用法: /xv_search <关键词>\u200E")
            return
        
        # 获取配置
        config = self.context.get_config(umo=event.unified_msg_origin)
        max_results = config.get("max_results", 10)
        
        try:
            # 检查缓存
            cache_key = f"search:{query}:{max_results}"
            if self.cache_manager:
                cached_results = await self.cache_manager.get(cache_key)
                if cached_results:
                    logger.info(f"使用缓存搜索结果: {query}")
                    results = cached_results
                else:
                    # 执行搜索
                    results = await self.client.search_videos(query, max_results)
                    await self.cache_manager.set(cache_key, results)
            else:
                results = await self.client.search_videos(query, max_results)
            
            if not results:
                yield event.plain_result(f"未找到与 '{query}' 相关的视频\u200E")
                return
            
            # 构建消息链
            chain = []
            
            # 添加标题
            chain.append(Comp.Plain(f"🔍 搜索结果: {query}\n找到 {len(results)} 个结果:\u200E\n"))
            
            # 为每个视频添加封面图和详细信息
            for i, video in enumerate(results[:5], 1):  # 最多显示5个结果
                video_id = video.get('id', '')
                video_id_display = video.get('id_without_dot', video_id)  # 使用不带点号的ID显示
                title = video.get('title', '未知')
                duration = video.get('duration', '未知')
                views = video.get('views', '未知')
                thumbnail_url = video.get('thumbnail', '')
                
                # 先添加封面图（如果有）
                if thumbnail_url:
                    try:
                        processed_thumb = await self._download_and_process_thumbnail(thumbnail_url)
                        if processed_thumb:
                            chain.append(Comp.Image.fromFileSystem(processed_thumb))
                    except Exception as e:
                        logger.warning(f"处理缩略图失败: {e}")
                
                # 添加视频信息文本（使用不带点号的ID）
                info_text = f"\n{i}. {title}\n   ID: {video_id_display} | 时长: {duration} | 观看: {views}\u200E"
                chain.append(Comp.Plain(info_text))
            
            # 添加提示信息
            chain.append(Comp.Plain(f"\n💡 使用 /xv_info <ID> 查看详情\u200E"))
            
            # 一次性发送整个消息链
            yield event.chain_result(chain)
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            yield event.plain_result(f"搜索失败: {str(e)}\u200E")
    
    @filter.command("xv_info")
    async def get_video_info(self, event: AstrMessageEvent, video_id: str = ""):
        """
        获取视频详细信息
        
        用法: /xv_info <视频ID>
        """
        # 清理上一次的缓存文件
        await self._cleanup_before_send()
        
        # 检查视频ID
        if not video_id:
            yield event.plain_result("用法: /xv_info <视频ID>\u200E")
            return
        
        try:
            # 处理视频ID：去掉可能存在的点号前缀
            # 正确的URL格式是 https://www.xvideos.com/video.hpltcdlece0
            if video_id.startswith('.'):
                video_id = video_id[1:]  # 去掉点号
            
            # 检查缓存
            cache_key = f"video:{video_id}"
            if self.cache_manager:
                cached_info = await self.cache_manager.get(cache_key)
                if cached_info:
                    logger.info(f"使用缓存视频信息: {video_id}")
                    video_info = cached_info
                else:
                    # 获取视频信息
                    video_info = await self.client.get_video_info(video_id)
                    await self.cache_manager.set(cache_key, video_info)
            else:
                video_info = await self.client.get_video_info(video_id)
            
            # 构建消息链
            chain = []
            
            # 添加文本信息
            info_text = await self._format_video_info(video_info)
            chain.append(Comp.Plain(info_text + "\u200E"))
            
            # 添加缩略图
            thumbnail_url = video_info.get('thumbnail', '')
            if thumbnail_url:
                processed_thumb = await self._download_and_process_thumbnail(thumbnail_url)
                if processed_thumb:
                    chain.append(Comp.Image.fromFileSystem(processed_thumb))
            
            # 一次性发送整个消息链
            yield event.chain_result(chain)
            
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            yield event.plain_result(f"获取视频信息失败: {str(e)}\u200E")
