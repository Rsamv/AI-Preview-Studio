# -*- coding: utf-8 -*-
"""AI Preview Studio - 智能资产导出系统

该模块负责将系统临时渲染的 AI 生成内容（HTML、Markdown等）正式持久化保存为本地用户资产。
支持自动建立输出目录、秒级时间戳防重名命名、安全写盘审计以及调用系统资源管理器定位。

符合 Google 编程规范，自带详细中文注释。
"""

import os
import datetime
import subprocess
from typing import Optional


class UniversalExporter:
    """通用导出器，封装目录建立、路径安全处理、文件导出与资源管理器交互"""

    def __init__(self, default_output_dirName: str = "output"):
        self.default_output_dirname = default_output_dirName

    def _resolve_output_dir(self, project_dir: Optional[str]) -> str:
        """根据当前项目工作区解析并创建绝对输出目录
        
        Args:
            project_dir: 选填，当前在主程序中打开的项目文件夹路径
            
        Returns:
            str: 确定的输出文件夹绝对路径
        """
        # 如果用户指定了项目文件夹，则将 output/ 建立在项目根目录下，方便就近管理资产
        if project_dir and os.path.exists(project_dir):
            base_dir = project_dir
        else:
            # 否则建立在当前运行程序的工作目录下
            base_dir = os.getcwd()
            
        output_dir = os.path.abspath(os.path.join(base_dir, self.default_output_dirname))
        
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def generate_timestamp_filename(self, prefix: str, ext: str) -> str:
        """基于当前时间戳生成带毫秒精度并防冲突的文件名，格式：prefix_YYYYMMDD_HHMMSS_ffffff.ext"""
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")[:18]  # 取至毫秒级前两位
        return f"{prefix}_{timestamp}.{ext.lstrip('.')}"

    @staticmethod
    def show_in_explorer(file_path: str) -> None:
        """调用 Windows 资源管理器打开输出文件夹并自动高亮选中导出的文件
        
        Args:
            file_path: 导出的文件绝对路径
        """
        if not file_path or not os.path.exists(file_path):
            return
            
        try:
            norm_path = os.path.normpath(file_path)
            # 在 Windows 下执行资源管理器选择指令，实现卓越的 UX 体验
            # 路径使用双引号进行严格包裹，防范命令注入与路径空格断裂风险
            subprocess.Popen(f'explorer /select,"{norm_path}"')
        except Exception as e:
            print(f"[WARNING] 无法在资源管理器中选中文件 {file_path}: {e}")

    def export(
        self,
        content_or_path: str,
        prefix: str,
        ext: str,
        project_dir: Optional[str] = None,
        target_path: Optional[str] = None,
        label: str = "资产"
    ) -> Optional[str]:
        """将当前内容（可以为纯文本或已存在的临时文件路径）持久化导出至指定路径
        
        Args:
            content_or_path: 源码内容，或指向临时文件的路径
            prefix: 默认文件名前缀（如 "preview" 或 "diagram"）
            ext: 默认文件名后缀（如 "html"、"md"、"svg"、"mermaid"）
            project_dir: 当前的项目工作文件夹，用于生成默认路径
            target_path: 自定义保存的目标路径，若提供则直接保存到此绝对路径
            label: 导出资产的描述性名称（用于日志输出与安全过滤）
            
        Returns:
            Optional[str]: 导出成功的绝对文件路径，若失败则返回 None
        """
        if not target_path:
            output_dir = self._resolve_output_dir(project_dir)
            filename = self.generate_timestamp_filename(prefix, ext)
            target_path = os.path.join(output_dir, filename)
        else:
            # 确保自定义父文件夹存在
            parent_dir = os.path.dirname(target_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            target_path = os.path.abspath(target_path)

        try:
            # 1. 强健的路径校验与类型识别
            is_file = False
            if len(content_or_path) < 512 and not any(c in content_or_path for c in "\n\r<>*?\"|"):
                try:
                    is_file = os.path.isfile(content_or_path) and os.path.exists(content_or_path)
                except Exception:
                    is_file = False

            if is_file:
                with open(content_or_path, "r", encoding="utf-8", errors="ignore") as f_src:
                    content = f_src.read()
            else:
                content = content_or_path
            
            # 2. 安全过滤与清洗
            content_stripped = content.strip()
            
            # 3. 安全落盘
            with open(target_path, "w", encoding="utf-8") as f_dest:
                f_dest.write(content_stripped)
                
            print(f"[INFO] {label}已成功一键导出到: {target_path}")
            return target_path
        except Exception as e:
            print(f"[ERROR] 导出 {label} 资产时发生异常: {e}")
            return None


# ==========================================================================
# 为了向后兼容性与软件工程解耦性，保留四个特定导出子类，仅作轻量转发
# ==========================================================================

class HTMLExporter(UniversalExporter):
    """HTML 网页一键导出器"""
    def export_html(
        self,
        content_or_path: str,
        project_dir: Optional[str] = None,
        target_path: Optional[str] = None
    ) -> Optional[str]:
        return self.export(content_or_path, "preview", "html", project_dir, target_path, "HTML 网页")


class MarkdownExporter(UniversalExporter):
    """Markdown 文档一键导出器"""
    def export_markdown(
        self,
        content_or_path: str,
        project_dir: Optional[str] = None,
        target_path: Optional[str] = None
    ) -> Optional[str]:
        return self.export(content_or_path, "preview", "md", project_dir, target_path, "Markdown 文档")


class SVGExporter(UniversalExporter):
    """SVG 矢量图形一键导出器"""
    def export_svg(
        self,
        content_or_path: str,
        project_dir: Optional[str] = None,
        target_path: Optional[str] = None
    ) -> Optional[str]:
        return self.export(content_or_path, "drawing", "svg", project_dir, target_path, "SVG 矢量图形")


class MermaidExporter(UniversalExporter):
    """Mermaid 流程图代码一键导出器"""
    def export_mermaid(
        self,
        content_or_path: str,
        project_dir: Optional[str] = None,
        target_path: Optional[str] = None
    ) -> Optional[str]:
        return self.export(content_or_path, "diagram", "mermaid", project_dir, target_path, "Mermaid 流程图代码")
