# -*- coding: utf-8 -*-
"""AI Preview Studio - 自定义网页预览组件

该模块扩展了 QWebEngineView，通过自定义 QWebEnginePage 捕获 JavaScript 运行时的
控制台输出日志，并提供相应的 Qt 信号进行广播；同时进行了安全和兼容性相关的 Web 属性配置。
此外，自定义了右键上下文菜单，扩展了强制渲染剪贴板内容与一键导出的快捷菜单项。

符合 Google 编程规范，包含详细中文注释。
"""

import os
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtCore import QUrl, Signal, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget


class CustomWebPage(QWebEnginePage):
    """自定义网页视图页面类，用于捕获和转发控制台消息"""

    # 定义 Qt 信号，参数类型分别为：日志级别(int)、日志内容(str)、行号(int)、源文件名(str)
    console_message_signal = Signal(int, str, int, str)

    def javaScriptConsoleMessage(
        self, level: int, message: str, line_number: int, source_id: str
    ) -> None:
        """重写 C++ 虚函数以接管控制台消息，并以 Qt 信号形式发射出去"""
        self.console_message_signal.emit(level, message, line_number, source_id)


class WebPreview(QWebEngineView):
    """自定义网页预览组件，基于 QWebEngineView 进行了兼容性增强与右键菜单自定义"""

    # 自定义右键菜单广播信号
    force_markdown_signal = Signal()
    force_html_signal = Signal()
    force_svg_signal = Signal()
    force_mermaid_signal = Signal()
    export_preview_signal = Signal()

    def __init__(self):
        super().__init__()

        # 使用自定义的 Page 类，接管控制台消息机制
        self.custom_page = CustomWebPage(self)
        self.setPage(self.custom_page)

        self._init_settings()

        # 内部默认连接至控制台打印（作备份或常规终端日志）
        self.custom_page.console_message_signal.connect(self._on_console_message)

        # 核心拦截设计：安装事件过滤器，拦截并接管当前视图以及其所有子控件的按键事件
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def _init_settings(self) -> None:
        """初始化 WebEngine 配置以获得最大的渲染兼容性"""
        settings = self.settings()

        # 启用 JavaScript 交互
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        # 允许脚本弹出窗口
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True
        )
        # 允许本地加载的 HTML 跨域请求远程资源 (如引用 unpkg 等外部 CDN 资源)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        # 允许本地加载的 HTML 读取其他本地文件
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        # 允许运行混合内容 (HTTP 与 HTTPS 内容混合渲染)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True
        )
        # 启用本地持久化存储的支持 (一些复杂的 HTML 渲染需要 LocalStorage)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, True
        )

    def load_file(self, file_path: str) -> None:
        """以本地 file:// 协议直接加载 HTML 文件
        
        Args:
            file_path: 本地 HTML 文件的绝对路径
        """
        file_path = os.path.abspath(file_path)
        url = QUrl.fromLocalFile(file_path)
        self.load(url)
        print(f"[INFO] 正在以 file:// 协议加载: {file_path}")

    def load_url(self, url_str: str) -> None:
        """以本地 HTTP 协议加载 URL
        
        Args:
            url_str: 本地托管的 HTTP 网页链接
        """
        url = QUrl(url_str)
        self.load(url)
        print(f"[INFO] 正在以 http:// 协议加载: {url_str}")

    def contextMenuEvent(self, event) -> None:
        """重写右键上下文菜单事件，保留网页默认选项并追加快捷渲染和导出入口"""
        # 1. 动态生成系统的标准上下文菜单（保留原生复制、粘贴、检查元素等动作）
        menu = self.createStandardContextMenu()
        
        # 2. 追加分割线与自定义开发调试资产工具
        menu.addSeparator()
        
        action_clip_md = QAction("强制解析剪贴板为 Markdown 渲染", menu)
        action_clip_md.triggered.connect(self.force_markdown_signal.emit)
        menu.addAction(action_clip_md)
        
        action_clip_html = QAction("强制解析剪贴板为 HTML 渲染", menu)
        action_clip_html.triggered.connect(self.force_html_signal.emit)
        menu.addAction(action_clip_html)
        
        action_clip_svg = QAction("强制解析剪贴板为 SVG 渲染", menu)
        action_clip_svg.triggered.connect(self.force_svg_signal.emit)
        menu.addAction(action_clip_svg)
        
        action_clip_mermaid = QAction("强制解析剪贴板为 Mermaid 渲染", menu)
        action_clip_mermaid.triggered.connect(self.force_mermaid_signal.emit)
        menu.addAction(action_clip_mermaid)
        
        menu.addSeparator()
        
        action_export = QAction("一键导出当前预览资产 (Ctrl+S)", menu)
        action_export.triggered.connect(self.export_preview_signal.emit)
        menu.addAction(action_export)
        
        # 3. 在触发位置执行菜单
        menu.exec(event.globalPos())

    def eventFilter(self, watched, event) -> bool:
        """事件过滤器：在按键事件到达底层 Chromium 渲染内核之前进行截获"""
        if event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Save):
                # 标记事件已被接受，阻止事件进一步传递给 Chromium 渲染线程
                event.accept()
                # 广播自定义导出信号，由 MainWindow 执行资产一键另存为
                self.export_preview_signal.emit()
                return True
        return super().eventFilter(watched, event)

    def childEvent(self, event) -> None:
        """动态子控件监听：在 Chromium 的渲染子窗口等组件生成时，立刻为其挂载过滤器"""
        if event.type() == QEvent.Type.ChildAdded:
            child = event.child()
            if child and child.isWidgetType():
                child.installEventFilter(self)
        super().childEvent(event)

    def focusInEvent(self, event) -> None:
        """当视图重新获得输入焦点时，强制使 focusProxy 挂载过滤器"""
        proxy = self.focusProxy()
        if proxy:
            proxy.installEventFilter(self)
        super().focusInEvent(event)

    def _on_console_message(
        self, level: int, message: str, line_number: int, source_id: str
    ) -> None:
        """格式化输出 HTML 内部 JavaScript 的控制台报错日志"""
        level_map = {0: "INFO", 1: "WARNING", 2: "ERROR"}
        level_str = level_map.get(level, "LOG")
        print(
            f"[WebConsole - {level_str}] 文件: {source_id} (第 {line_number} 行): {message}"
        )