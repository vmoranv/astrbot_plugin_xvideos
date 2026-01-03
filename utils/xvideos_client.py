"""
XVideos API 客户端封装模块
"""
import asyncio
import aiohttp
from typing import Optional, Generator
from pathlib import Path
from astrbot.api import logger


class XVideosClient:
    """XVideos API 客户端封装"""
    
    BASE_URL = "https://www.xvideos.com"
    
    def __init__(self, proxy_url: Optional[str] = None):
        """
        初始化客户端
        
        Args:
            proxy_url: 代理地址，例如: http://127.0.0.1:7890
        """
        self.proxy_url = proxy_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
    
    async def initialize(self):
        """初始化HTTP会话"""
        if self.session is None:
            connector = aiohttp.TCPConnector(limit=10)
            timeout = aiohttp.ClientTimeout(total=30)
            
            kwargs = {
                'connector': connector,
                'timeout': timeout,
                'trust_env': True
            }
            
            if self.proxy_url:
                kwargs['proxy'] = self.proxy_url
            
            self.session = aiohttp.ClientSession(**kwargs)
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get_video_info(self, video_id: str) -> dict:
        """
        获取视频信息
        
        Args:
            video_id: 视频ID（可以带或不带点号前缀）
            
        Returns:
            视频信息字典
        """
        await self.initialize()
        
        # 处理视频ID：去掉可能存在的点号前缀
        # 正确的URL格式是 https://www.xvideos.com/video.hpltcdlece0
        original_video_id = video_id
        if video_id.startswith('.'):
            video_id = video_id[1:]  # 去掉点号
        
        # 构建正确的URL
        url = f"{self.BASE_URL}/video.{video_id}"
        
        logger.info(f"获取视频信息，原始ID: {original_video_id}, 处理后ID: {video_id}, URL: {url}")
        
        try:
            # 添加请求头，模拟浏览器访问
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with self.session.get(url, headers=headers) as response:
                logger.info(f"响应状态码: {response.status}")
                
                if response.status == 200:
                    html = await response.text()
                    logger.info(f"成功获取视频信息，HTML长度: {len(html)}")
                    
                    # 尝试使用 xvideos_api 库解析
                    try:
                        return await self._parse_with_xvideos_api(video_id, html, url)
                    except Exception as api_error:
                        logger.warning(f"xvideos_api 解析失败: {api_error}，尝试使用 BeautifulSoup 解析")
                        return await self._parse_video_info(html, url)
                        
                elif response.status == 404:
                    # 尝试其他可能的URL格式
                    logger.warning(f"404错误，尝试其他URL格式")
                    return await self._try_alternative_urls(original_video_id)
                else:
                    raise Exception(f"HTTP {response.status}: {url}")
                    
        except aiohttp.ClientError as e:
            logger.error(f"请求异常: {type(e).__name__}: {str(e)}")
            raise Exception(f"请求失败: {str(e)}, URL: {url}")
    
    async def _try_alternative_urls(self, video_id: str) -> dict:
        """
        尝试其他可能的URL格式
        
        Args:
            video_id: 原始视频ID
            
        Returns:
            视频信息字典
        """
        # 生成可能的URL格式
        possible_urls = []
        
        # 去掉点号
        clean_id = video_id[1:] if video_id.startswith('.') else video_id
        
        # 格式1: /video.hpltcdlece0 (点号在video后面)
        possible_urls.append(f"{self.BASE_URL}/video.{clean_id}")
        
        # 格式2: /video/.hpltcdlece0 (点号在斜杠后面)
        possible_urls.append(f"{self.BASE_URL}/video/.{clean_id}")
        
        # 格式3: /video/hpltcdlece0 (斜杠分隔)
        possible_urls.append(f"{self.BASE_URL}/video/{clean_id}")
        
        logger.info(f"尝试备选URL格式，共 {len(possible_urls)} 种")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        
        for idx, alt_url in enumerate(possible_urls, 1):
            try:
                logger.info(f"尝试备选URL {idx}/{len(possible_urls)}: {alt_url}")
                async with self.session.get(alt_url, headers=headers) as response:
                    logger.info(f"  响应状态码: {response.status}")
                    
                    if response.status == 200:
                        html = await response.text()
                        logger.info(f"  ✓ 成功！使用URL: {alt_url}")
                        return await self._parse_video_info(html, alt_url)
                    else:
                        logger.warning(f"  ✗ 失败: HTTP {response.status}")
                        
            except Exception as e:
                logger.warning(f"  ✗ 异常: {str(e)}")
                continue
        
        # 所有URL都失败了
        raise Exception(f"视频不存在或已被删除\n尝试的URL:\n" + "\n".join(possible_urls))
    
    async def _parse_with_xvideos_api(self, video_id: str, html: str, url: str) -> dict:
        """
        使用 xvideos_api 库解析视频信息
        
        Args:
            video_id: 视频ID
            html: HTML内容
            url: 视频URL
            
        Returns:
            视频信息字典
        """
        try:
            from xvideos_api import XVideosAPI
            api = XVideosAPI()
            
            # 使用API获取视频信息
            video_info = await api.get_video_info(video_id)
            
            # 添加URL字段
            video_info['url'] = url
            
            logger.info(f"使用 xvideos_api 成功解析视频信息")
            return video_info
            
        except ImportError:
            logger.warning("xvideos_api 库未安装，使用 BeautifulSoup 解析")
            raise
        except Exception as e:
            logger.warning(f"xvideos_api 解析失败: {e}")
            raise
    
    async def _parse_video_info(self, html: str, url: str) -> dict:
        """
        解析视频信息HTML
        
        Args:
            html: HTML内容
            url: 视频URL
            
        Returns:
            视频信息字典
        """
        # 简单的HTML解析，实际使用xvideos_api库会更准确
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        info = {
            'url': url,
            'title': '',
            'thumbnail': '',
            'duration': '',
            'views': '',
            'likes': '',
            'dislikes': '',
            'rating': '',
            'author': '',
            'tags': []
        }
        
        # 提取标题
        title_elem = soup.find('meta', property='og:title')
        if title_elem:
            info['title'] = title_elem.get('content', '')
        
        # 提取缩略图
        thumb_elem = soup.find('meta', property='og:image')
        if thumb_elem:
            info['thumbnail'] = thumb_elem.get('content', '')
        
        # 提取时长
        duration_elem = soup.find('span', class_='duration')
        if duration_elem:
            info['duration'] = duration_elem.text.strip()
        
        # 提取观看数
        views_elem = soup.find('span', class_='icon-f icf-eye')
        if views_elem and views_elem.next:
            info['views'] = views_elem.next.text.strip()
        
        # 提取点赞数
        likes_elem = soup.find('span', class_='rating-good-nbr')
        if likes_elem:
            info['likes'] = likes_elem.text.strip()
        
        # 提取不喜欢数
        dislikes_elem = soup.find('span', class_='rating-bad-nbr')
        if dislikes_elem:
            info['dislikes'] = dislikes_elem.text.strip()
        
        # 提取标签
        tag_elems = soup.find_all('a', class_='is-keyword btn btn-default')
        info['tags'] = [tag.text for tag in tag_elems]
        
        return info
    
    async def search_videos(self, query: str, max_results: int = 10) -> list:
        """
        搜索视频
        
        Args:
            query: 搜索关键词
            max_results: 最大结果数
            
        Returns:
            视频信息列表
        """
        await self.initialize()
        
        url = f"{self.BASE_URL}/?k={query}"
        
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                html = await response.text()
                
            return await self._parse_search_results(html, max_results)
            
        except aiohttp.ClientError as e:
            raise Exception(f"搜索失败: {str(e)}")
    
    async def _parse_search_results(self, html: str, max_results: int) -> list:
        """
        解析搜索结果HTML
        
        Args:
            html: HTML内容
            max_results: 最大结果数
            
        Returns:
            视频信息列表
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        
        results = []
        video_divs = soup.find_all('div', class_='thumb-block')[:max_results]
        
        for div in video_divs:
            video_info = {
                'id': '',
                'title': '',
                'thumbnail': '',
                'duration': '',
                'views': '',
                'rating': ''
            }
            
            # 提取视频ID和URL
            link_elem = div.find('a')
            if link_elem:
                href = link_elem.get('href', '')
                if '/video' in href:
                    # 提取视频ID（可能包含点号前缀）
                    video_id = href.split('/video')[-1].split('/')[0]
                    video_info['id'] = video_id
                    video_info['url'] = f"{self.BASE_URL}{href}"
                    
                    # 同时保存不带点号的ID，方便用户查询
                    if video_id.startswith('.'):
                        video_info['id_without_dot'] = video_id[1:]  # 去掉点号
                    else:
                        video_info['id_without_dot'] = video_id
            
            # 提取标题 - 尝试多种方式
            title = ''
            
            # 方法1: 从链接的 title 属性获取
            link_elem = div.find('a')
            if link_elem:
                title = link_elem.get('title', '')
            
            # 方法2: 从 p.title 的 title 属性获取
            if not title:
                title_elem = div.find('p', class_='title')
                if title_elem:
                    title = title_elem.get('title', '')
            
            # 方法3: 从 p.title 的文本内容获取
            if not title:
                title_elem = div.find('p', class_='title')
                if title_elem:
                    # 获取链接内的文本
                    link_in_title = title_elem.find('a')
                    if link_in_title:
                        title = link_in_title.text.strip()
            
            # 方法4: 直接从 p.title 获取文本
            if not title:
                title_elem = div.find('p', class_='title')
                if title_elem:
                    title = title_elem.get_text(strip=True)
            
            video_info['title'] = title
            
            # 提取缩略图
            img_elem = div.find('img')
            if img_elem:
                video_info['thumbnail'] = img_elem.get('data-src', '') or img_elem.get('src', '')
            
            # 提取时长
            duration_elem = div.find('span', class_='duration')
            if duration_elem:
                video_info['duration'] = duration_elem.text.strip()
            
            # 提取观看数
            views_elem = div.find('span', class_='bg')
            if views_elem:
                video_info['views'] = views_elem.text.strip()
            
            # 提取评分
            rating_elem = div.find('span', class_='rating')
            if rating_elem:
                video_info['rating'] = rating_elem.text.strip()
            
            if video_info['id']:
                results.append(video_info)
        
        return results
    
    async def download_thumbnail(self, thumbnail_url: str, save_path: str) -> str:
        """
        下载缩略图
        
        Args:
            thumbnail_url: 缩略图URL
            save_path: 保存路径
            
        Returns:
            保存的文件路径
        """
        await self.initialize()
        
        try:
            async with self.session.get(thumbnail_url) as response:
                response.raise_for_status()
                content = await response.read()
                
            # 确保目录存在
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path, 'wb') as f:
                f.write(content)
            
            return save_path
            
        except aiohttp.ClientError as e:
            raise Exception(f"下载缩略图失败: {str(e)}")
