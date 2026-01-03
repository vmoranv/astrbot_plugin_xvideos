"""
图片处理模块 - 用于封面图片打码处理
"""
import os
from PIL import Image, ImageFilter
from typing import Optional
from pathlib import Path


class ImageProcessor:
    """图片处理器，用于对封面图片进行打码处理"""
    
    def __init__(self, blur_level: int = 50):
        """
        初始化图片处理器
        
        Args:
            blur_level: 打码程度 (0-100)，0为不打码，100为完全模糊
        """
        self.blur_level = max(0, min(100, blur_level))
    
    async def process_image(self, image_path: str, output_path: Optional[str] = None) -> str:
        """
        处理图片，应用模糊效果
        
        Args:
            image_path: 输入图片路径
            output_path: 输出图片路径，如果为None则覆盖原文件
            
        Returns:
            处理后的图片路径
        """
        if self.blur_level == 0:
            # 不需要打码，直接返回原路径
            return image_path
        
        try:
            # 打开图片
            img = Image.open(image_path)
            
            # 计算模糊半径 (0-100 映射到 0-50)
            blur_radius = int(self.blur_level / 2)
            
            # 应用高斯模糊
            blurred_img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            # 确定输出路径
            if output_path is None:
                output_path = image_path
            
            # 保存处理后的图片
            blurred_img.save(output_path, quality=95)
            
            return output_path
            
        except Exception as e:
            raise Exception(f"图片处理失败: {str(e)}")
    
    async def process_image_from_bytes(self, image_bytes: bytes, output_path: str) -> str:
        """
        从字节数据处理图片
        
        Args:
            image_bytes: 图片字节数据
            output_path: 输出图片路径
            
        Returns:
            处理后的图片路径
        """
        if self.blur_level == 0:
            # 不需要打码，直接保存
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            return output_path
        
        try:
            # 从字节数据打开图片
            img = Image.open(image_bytes)
            
            # 计算模糊半径
            blur_radius = int(self.blur_level / 2)
            
            # 应用高斯模糊
            blurred_img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            # 保存处理后的图片
            blurred_img.save(output_path, quality=95)
            
            return output_path
            
        except Exception as e:
            raise Exception(f"图片处理失败: {str(e)}")
    
    def set_blur_level(self, blur_level: int):
        """
        设置打码程度
        
        Args:
            blur_level: 打码程度 (0-100)
        """
        self.blur_level = max(0, min(100, blur_level))
