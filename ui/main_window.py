# -*- coding: utf-8 -*-
"""AI Preview Studio - 主窗口界面

该模块实现了程序的主窗口，采用类似 qt5yolo-g 的微软亮色 Fluent 配色方案。
移除了所有按钮前的图形符号，功能选择类按钮统一放置在最上方，并新增了日志查看选项。
运行日志平时保持完全隐藏，不占用任何底部高度空间，仅在捕获到运行时 JavaScript 报错 (ERROR) 
或系统级错误时自动滑出/弹出。

符合 Google 编程规范，包含详细中文注释。
"""

import sys
import base64
import os
import re
import hashlib
import time
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QMenu, QTextEdit,
    QMessageBox, QApplication, QDialog, QRadioButton, QCheckBox
)
from PySide6.QtCore import Qt, QPoint, QFileSystemWatcher, QEventLoop, QTimer
from PySide6.QtGui import QAction, QActionGroup, QClipboard

from preview.webview import WebPreview
from core.server import LocalHttpServer
from core.repairer import repair_html
from core.exporter import HTMLExporter, MarkdownExporter, SVGExporter, MermaidExporter


class CloseConfirmDialog(QDialog):
    """自定义关闭确认与选项对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关闭选项")
        self.resize(320, 170)
        self.setModal(True)
        if parent and hasattr(parent, "windowIcon"):
            self.setWindowIcon(parent.windowIcon())
        
        # 从外部 QSS 文件加载高级扁平化样式表，样式与逻辑彻底分离
        if parent and hasattr(parent, "get_resource_path"):
            qss_path = parent.get_resource_path("ui/style.qss")
        else:
            qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.qss")
            
        try:
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
        except Exception as e:
            print(f"[ERROR] 无法为关闭选项对话框加载样式: {e}")


        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        label = QLabel("您希望如何处理关闭窗口操作？")
        layout.addWidget(label)

        self.radio_tray = QRadioButton("最小化到系统托盘 (继续在后台监听)")
        self.radio_tray.setObjectName("radio_tray")
        self.radio_tray.setChecked(True)
        
        self.radio_exit = QRadioButton("彻底退出程序")
        self.radio_exit.setObjectName("radio_exit")
        
        layout.addWidget(self.radio_tray)
        layout.addWidget(self.radio_exit)

        self.chk_remember = QCheckBox("记住我的选择，以后不再提示")
        layout.addWidget(self.chk_remember)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_ok = QPushButton("确定")
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("btn_cancel")
        
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)


class MainWindow(QMainWindow):
    """主应用窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("AI Preview Studio - V0.8")
        self.resize(1200, 850)

        # 1. 核心业务逻辑组件初始化
        self.server = LocalHttpServer()
        self.file_watcher = QFileSystemWatcher()
        self.clipboard = QApplication.clipboard()
        self.exporter = HTMLExporter()
        self.md_exporter = MarkdownExporter()
        self.svg_exporter = SVGExporter()
        self.mermaid_exporter = MermaidExporter()

        # 2. 状态控制变量与配置加载
        self.use_http = True            # 是否启用本地 HTTP 服务托管
        self.clipboard_monitor = True   # 是否开启剪贴板监听
        self.file_monitor = True        # 是否开启 file 变更自动刷新
        self.auto_repair = True          # 是否开启 HTML 自动修复与补全
        self.log_panel_auto_shown = False # 是否由于报错自动弹出了日志面板
        self.auto_raise = True            # 是否在监听到剪贴板HTML时自动弹窗置顶
        self.min_to_tray = True          # 是否在关闭窗口时最小化到系统托盘
        self.always_on_top = False       # 窗口是否保持置顶
        self.prompt_on_close = True      # 关闭窗口时是否弹出选择对话框
        self.current_content_type = "html" # 当前正在预览的内容类别 ("html" 或 "markdown")
        self.current_markdown_raw = ""     # 存放 Markdown 的原始未解析文本
        
        # 缓存系统初始默认窗口样式 Flags，防止后续修改 WindowStaysOnTopHint 时抹去原生关闭、最小化、最大化按钮
        self.default_flags = self.windowFlags()

        # 加载并设置窗口图标
        icon_path = self.get_resource_path("logo.ico")
        if os.path.exists(icon_path):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))

        # 加载持久化配置
        self.load_configuration()
        if self.always_on_top:
            self.setWindowFlags(self.default_flags | Qt.WindowType.WindowStaysOnTopHint)

        self.current_orig_file = ""     # 当前打开的原始文件路径
        self.current_rendered_file = "" # 当前正在渲染的文件路径（可能是修复后的临时文件）
        self.current_watched_dir = ""    # 当前正在监听的文件夹路径
        self.dir_files_snapshot = set()  # 当前监听文件夹的文件名快照
        self.temp_files = set()         # 跟踪创建的临时隐藏 file 路径，便于后续清理
        self.last_clip_hash = ""        # 防止同一次复制内容重复处理的哈希锁

        # 缓存文件夹定义与集中创建，消除 7 处重复创建逻辑
        self.cache_dir = os.path.join(os.getcwd(), ".preview_cache")
        os.makedirs(self.cache_dir, exist_ok=True)


        # 3. 初始化 UI 布局与样式
        self._init_ui()
        self._apply_qss()
        
        # 初始化系统托盘
        self._setup_system_tray()

        # 4. 建立信号与槽连接
        self.file_watcher.fileChanged.connect(self.on_file_changed)
        self.file_watcher.directoryChanged.connect(self.on_directory_changed)
        self.clipboard.dataChanged.connect(self.on_clipboard_changed)
        
        # 绑定 WebPreview 的自定义右键动作与强制渲染信号
        self.webview.force_markdown_signal.connect(self.load_markdown_from_clipboard)
        self.webview.force_html_signal.connect(self.load_html_from_clipboard)
        self.webview.force_svg_signal.connect(self.load_svg_from_clipboard)
        self.webview.force_mermaid_signal.connect(self.load_mermaid_from_clipboard)
        self.webview.export_preview_signal.connect(self.export_current_rendered)

        # 5. 初始隐藏日志面板
        self.log_panel.setVisible(False)

        self.log_message("系统初始化完毕，准备就绪。")

    def get_resource_path(self, relative_path: str) -> str:
        """获取资源文件的绝对路径，兼容开发环境与 PyInstaller 打包环境"""
        import sys
        if hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, relative_path)
        # 从 ui 目录下向上寻找两层到根目录
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

    def _init_ui(self) -> None:
        """构建主窗口界面组件"""
        # 主容器
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ==================== 1. 顶部紧凑功能栏 (TopCompactBar) ====================
        self.top_bar = QWidget()
        self.top_bar.setObjectName("top_bar")
        self.top_layout = QHBoxLayout(self.top_bar)
        self.top_layout.setContentsMargins(10, 0, 10, 0)
        self.top_layout.setSpacing(6)

        # 1.1 左侧功能选择区（按钮点击弹出下拉菜单）
        self.btn_file = QPushButton("文件")
        self.btn_file.setProperty("class", "top_btn")

        self.btn_server = QPushButton("服务")
        self.btn_server.setProperty("class", "top_btn")

        self.btn_monitor = QPushButton("监听")
        self.btn_monitor.setProperty("class", "top_btn")

        self.btn_repair = QPushButton("修复")
        self.btn_repair.setProperty("class", "top_btn")

        self.btn_log = QPushButton("日志")
        self.btn_log.setProperty("class", "top_btn")

        self.btn_settings = QPushButton("设置")
        self.btn_settings.setProperty("class", "top_btn")

        self.btn_export = QPushButton("导出网页")
        self.btn_export.setProperty("class", "export_btn")
        self.btn_export.setToolTip("一键将当前的网页预览保存为正式的项目资产文件 (Ctrl+S)")

        # 添加至布局
        self.top_layout.addWidget(self.btn_file)
        self.top_layout.addWidget(self.btn_server)
        self.top_layout.addWidget(self.btn_monitor)
        self.top_layout.addWidget(self.btn_repair)
        self.top_layout.addWidget(self.btn_log)
        self.top_layout.addWidget(self.btn_settings)
        self.top_layout.addWidget(self.btn_export)

        # 弹簧将状态信息推至右侧
        self.top_layout.addStretch()

        # 1.2 右侧状态显示区
        self.status_label = QLabel("模式: 本地托管 | 状态: 闲置")
        self.status_label.setObjectName("status_label")
        
        # 指示器灯，用于显示监听状态
        self.indicator = QLabel()
        self.indicator.setObjectName("indicator_active")
        self.indicator.setToolTip("后台自动监视器运行中")

        self.top_layout.addWidget(self.status_label)
        self.top_layout.addWidget(self.indicator)

        self.main_layout.addWidget(self.top_bar)

        # ==================== 2. 主页面渲染区 (WebView) ====================
        self.webview = WebPreview()
        self.main_layout.addWidget(self.webview, stretch=1)

        # ==================== 3. 底部日志控制台 (LogPanel) ====================
        # 默认不占任何物理空间（隐藏），除非报错或通过顶部“日志”菜单显示
        self.log_panel = QWidget()
        self.log_panel.setObjectName("log_panel")
        self.log_layout = QVBoxLayout(self.log_panel)
        self.log_layout.setContentsMargins(10, 5, 10, 5)
        self.log_layout.setSpacing(4)

        # 控制台顶栏（只放标题和关闭按钮，去掉多余占用）
        self.log_bar_header = QWidget()
        self.log_bar_header_layout = QHBoxLayout(self.log_bar_header)
        self.log_bar_header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_console_title = QLabel("运行日志与控制台")
        self.lbl_console_title.setObjectName("lbl_console_title")
        
        self.btn_close_log = QPushButton("✕")
        self.btn_close_log.setObjectName("btn_close_log")
        self.btn_close_log.clicked.connect(self.hide_log_panel)

        self.log_bar_header_layout.addWidget(self.lbl_console_title)
        self.log_bar_header_layout.addStretch()
        self.log_bar_header_layout.addWidget(self.btn_close_log)
        self.log_layout.addWidget(self.log_bar_header)

        # 日志只读文本框
        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("txt_log")
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(150)
        self.log_layout.addWidget(self.txt_log)

        self.main_layout.addWidget(self.log_panel)

        # 将 webview 的 JS 控制台信息输出导向到我们的日志槽函数中
        self.webview.page().console_message_signal.connect(self.log_web_console)

        # 延迟初始化下拉菜单绑定，确保所有 UI 小部件均已生成
        self._setup_file_menu()
        self._setup_server_menu()
        self._setup_monitor_menu()
        self._setup_repair_menu()
        self._setup_log_menu()
        self._setup_settings_menu()

        # 绑定导出按钮动作
        self.btn_export.clicked.connect(self.export_current_rendered)

    # ==================== 菜单配置辅助函数 ====================

    def _setup_file_menu(self) -> None:
        """配置“文件”选项的下拉菜单"""
        menu = QMenu(self)
        action_open_file = menu.addAction("打开 HTML 文件...")
        action_open_file.triggered.connect(self.open_file)
        
        action_open_dir = menu.addAction("打开项目文件夹...")
        action_open_dir.triggered.connect(self.open_dir)
        
        menu.addSeparator()
        action_clip_html = menu.addAction("从剪贴板加载并渲染为 HTML")
        action_clip_html.triggered.connect(self.load_html_from_clipboard)
        
        action_clip_md = menu.addAction("从剪贴板加载并渲染为 Markdown")
        action_clip_md.triggered.connect(self.load_markdown_from_clipboard)

        action_clip_svg = menu.addAction("从剪贴板加载并渲染为 SVG")
        action_clip_svg.triggered.connect(self.load_svg_from_clipboard)
        
        action_clip_mermaid = menu.addAction("从剪贴板加载并渲染为 Mermaid")
        action_clip_mermaid.triggered.connect(self.load_mermaid_from_clipboard)
        
        menu.addSeparator()
        action_export = menu.addAction("导出当前预览为资产")
        action_export.setShortcut("Ctrl+S")
        # 核心修复：注册快捷键上下文为窗口级别，并强制添加到主窗口中，防止因菜单未弹出或焦点在 WebView 而导致快捷键失效
        action_export.setShortcutContext(Qt.WindowShortcut)
        self.addAction(action_export)
        action_export.triggered.connect(self.export_current_rendered)

        menu.addSeparator()
        action_exit = menu.addAction("退出程序")
        action_exit.triggered.connect(self.close)

        self.btn_file.clicked.connect(lambda: self._show_popup_menu(self.btn_file, menu))

    def _setup_server_menu(self) -> None:
        """配置“服务”选项的下拉菜单"""
        menu = QMenu(self)
        group = QActionGroup(self)

        self.act_use_http = QAction("启用本地 HTTP 服务托管 (推荐)", menu, checkable=True, checked=True)
        self.act_use_file = QAction("使用默认 file:// 协议渲染", menu, checkable=True)

        group.addAction(self.act_use_http)
        group.addAction(self.act_use_file)
        menu.addAction(self.act_use_http)
        menu.addAction(self.act_use_file)

        self.act_use_http.triggered.connect(lambda: self.toggle_render_mode(True))
        self.act_use_file.triggered.connect(lambda: self.toggle_render_mode(False))

        self.btn_server.clicked.connect(lambda: self._show_popup_menu(self.btn_server, menu))

    def _setup_monitor_menu(self) -> None:
        """配置“监听”选项的下拉菜单"""
        menu = QMenu(self)

        self.act_clip_monitor = menu.addAction("监听剪贴板自动预览")
        self.act_clip_monitor.setCheckable(True)
        self.act_clip_monitor.setChecked(True)
        self.act_clip_monitor.triggered.connect(self.toggle_clipboard_monitor)

        self.act_file_monitor = menu.addAction("监听文件修改自动刷新")
        self.act_file_monitor.setCheckable(True)
        self.act_file_monitor.setChecked(True)
        self.act_file_monitor.triggered.connect(self.toggle_file_monitor)

        menu.addSeparator()
        self.act_auto_raise = menu.addAction("复制 HTML 时自动弹起窗口")
        self.act_auto_raise.setCheckable(True)
        self.act_auto_raise.setChecked(True)
        self.act_auto_raise.triggered.connect(self.toggle_auto_raise)

        self.btn_monitor.clicked.connect(lambda: self._show_popup_menu(self.btn_monitor, menu))

    def _setup_repair_menu(self) -> None:
        """配置“修复”选项的下拉菜单"""
        menu = QMenu(self)

        self.act_auto_repair = menu.addAction("启用 HTML 自动纠错与标签补全")
        self.act_auto_repair.setCheckable(True)
        self.act_auto_repair.setChecked(True)
        self.act_auto_repair.triggered.connect(self.toggle_auto_repair)

        menu.addSeparator()
        act_clean = menu.addAction("清理所有临时缓存文件")
        act_clean.triggered.connect(self.clear_all_temp_files)

        self.btn_repair.clicked.connect(lambda: self._show_popup_menu(self.btn_repair, menu))

    def _setup_log_menu(self) -> None:
        """配置“日志”选项的下拉菜单，用于控制日志面板的手动显示和隐藏"""
        menu = QMenu(self)

        self.act_show_log = menu.addAction("显示日志控制台")
        self.act_show_log.setCheckable(True)
        self.act_show_log.setChecked(False)
        self.act_show_log.triggered.connect(self.toggle_log_panel_action)

        menu.addSeparator()
        act_clear_log = menu.addAction("清空日志内容")
        act_clear_log.triggered.connect(self.txt_log.clear)

        self.btn_log.clicked.connect(lambda: self._show_popup_menu(self.btn_log, menu))

    def _show_popup_menu(self, button: QPushButton, menu: QMenu) -> None:
        """在按钮下方弹出展开菜单"""
        pos = button.mapToGlobal(QPoint(0, button.height()))
        menu.exec(pos)

    # ==================== 核心槽函数与业务逻辑 ====================

    def export_current_rendered(self) -> None:
        """一键将当前正在预览的资产导出，支持用户选择不同的格式和命名"""
        if self.current_content_type == "markdown":
            if not self.current_markdown_raw:
                QMessageBox.warning(self, "导出提示", "当前没有正在预览的 Markdown 资产，无法导出！")
                return
            
            default_dir = self.md_exporter._resolve_output_dir(self.current_watched_dir)
            default_filename = self.md_exporter.generate_timestamp_filename("preview", "md")
            default_filepath = os.path.join(default_dir, default_filename)
            
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出 Markdown 资产为...",
                default_filepath,
                "Markdown 文档 (*.md *.markdown);;所有文件 (*.*)"
            )
            if not save_path:
                self.log_message("用户取消了 Markdown 导出操作。")
                return
                
            self.log_message("正在处理一键导出 Markdown 资产...")
            exported_path = self.md_exporter.export_markdown(
                self.current_markdown_raw,
                self.current_watched_dir,
                target_path=save_path
            )
        elif self.current_content_type == "svg":
            if not self.current_markdown_raw:
                QMessageBox.warning(self, "导出提示", "当前没有正在预览的 SVG 资产，无法导出！")
                return
            
            default_dir = self.svg_exporter._resolve_output_dir(self.current_watched_dir)
            default_filename = self.svg_exporter.generate_timestamp_filename("drawing", "svg")
            default_filepath = os.path.join(default_dir, default_filename)
            
            save_path, selected_filter = QFileDialog.getSaveFileName(
                self,
                "导出 SVG 矢量图为...",
                default_filepath,
                "SVG 矢量图形 (*.svg);;JPEG 图片 (*.jpg);;PNG 图片 (*.png);;所有文件 (*.*)"
            )
            if not save_path:
                self.log_message("用户取消了 SVG 导出操作。")
                return
                
            self.log_message(f"正在处理一键导出 SVG 图形至 {save_path}...")
            ext = os.path.splitext(save_path)[1].lower()
            
            if ext == ".svg" or "SVG" in selected_filter:
                exported_path = self.svg_exporter.export_svg(
                    self.current_markdown_raw,
                    self.current_watched_dir,
                    target_path=save_path
                )
            elif ext in [".jpg", ".jpeg", ".png"] or "图片" in selected_filter:
                mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                img_bytes = self._retrieve_rasterized_image(mime_type)
                if img_bytes:
                    try:
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        exported_path = save_path
                    except Exception as e:
                        self.log_message(f"[ERROR] 写入图片文件失败: {e}")
                        exported_path = None
                else:
                    self.log_message("[ERROR] 无法从网页预览捕获高保真图像")
                    exported_path = None
            else:
                exported_path = None
        elif self.current_content_type == "mermaid":
            if not self.current_markdown_raw:
                QMessageBox.warning(self, "导出提示", "当前没有正在预览的 Mermaid 资产，无法导出！")
                return
            
            default_dir = self.mermaid_exporter._resolve_output_dir(self.current_watched_dir)
            default_filename = self.mermaid_exporter.generate_timestamp_filename("diagram", "mermaid")
            default_filepath = os.path.join(default_dir, default_filename)
            
            save_path, selected_filter = QFileDialog.getSaveFileName(
                self,
                "导出 Mermaid 流程图为...",
                default_filepath,
                "Mermaid 源码 (*.mermaid);;SVG 矢量图 (*.svg);;JPEG 图片 (*.jpg);;PNG 图片 (*.png);;所有文件 (*.*)"
            )
            if not save_path:
                self.log_message("用户取消了 Mermaid 导出操作。")
                return
                
            self.log_message(f"正在处理一键导出 Mermaid 流程图至 {save_path}...")
            ext = os.path.splitext(save_path)[1].lower()
            
            if ext in [".mermaid", ".mmd"] or "源码" in selected_filter:
                exported_path = self.mermaid_exporter.export_mermaid(
                    self.current_markdown_raw,
                    self.current_watched_dir,
                    target_path=save_path
                )
            else:
                # Retrieve raw SVG from WebEngineView
                loop = QEventLoop()
                raw_svg = ""
                def js_callback(result):
                    nonlocal raw_svg
                    raw_svg = result
                    loop.quit()
                
                self.webview.page().runJavaScript("window.rawSvg || '';", js_callback)
                QTimer.singleShot(2000, loop.quit)
                loop.exec()
                
                if not raw_svg:
                    self.log_message("[WARNING] 无法从网页预览中提取渲染后的 SVG 代码，将使用备用 Mermaid 源码导出。")
                    QMessageBox.warning(self, "导出警告", "未能从网页预览中捕获渲染图表，将默认导出为源码文件！")
                    if ext not in [".mermaid", ".mmd"]:
                        save_path += ".mermaid"
                    exported_path = self.mermaid_exporter.export_mermaid(
                        self.current_markdown_raw,
                        self.current_watched_dir,
                        target_path=save_path
                    )
                else:
                    if ext == ".svg" or "SVG" in selected_filter:
                        try:
                            if not raw_svg.startswith("<?xml"):
                                raw_svg = '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + raw_svg
                            with open(save_path, "w", encoding="utf-8") as f:
                                f.write(raw_svg)
                            exported_path = save_path
                        except Exception as e:
                            self.log_message(f"[ERROR] 写入 SVG 文件失败: {e}")
                            exported_path = None
                    elif ext in [".jpg", ".jpeg", ".png"] or "图片" in selected_filter:
                        mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                        img_bytes = self._retrieve_rasterized_image(mime_type)
                        if img_bytes:
                            try:
                                with open(save_path, "wb") as f:
                                    f.write(img_bytes)
                                exported_path = save_path
                            except Exception as e:
                                self.log_message(f"[ERROR] 写入图片文件失败: {e}")
                                exported_path = None
                        else:
                            self.log_message("[ERROR] 无法从网页预览捕获高保真图像")
                            exported_path = None
                    else:
                        exported_path = None
        else:
            if not self.current_rendered_file or not os.path.exists(self.current_rendered_file):
                self.log_message("[WARNING] 尝试导出空资产，已拦截。当前没有处于活动状态的 HTML 预览。")
                QMessageBox.warning(self, "导出提示", "当前没有正在预览的网页资产，无法导出！")
                return

            default_dir = self.exporter._resolve_output_dir(self.current_watched_dir)
            default_filename = self.exporter.generate_timestamp_filename("preview", "html")
            default_filepath = os.path.join(default_dir, default_filename)
            
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出网页资产为...",
                default_filepath,
                "网页文件 (*.html *.htm);;所有文件 (*.*)"
            )
            if not save_path:
                self.log_message("用户取消了 HTML 网页导出操作。")
                return

            self.log_message("正在处理一键导出网页资产...")
            exported_path = self.exporter.export_html(
                self.current_rendered_file,
                self.current_watched_dir,
                target_path=save_path
            )
        
        if exported_path:
            filename = os.path.basename(exported_path)
            self.log_message(f"资产已成功导出，物理路径: {exported_path}")
            
            self.status_label.setText(f"模式: 本地托管 | 状态: 资产已导出 ({filename})")
            
            QMessageBox.information(
                self, 
                "导出成功", 
                f"当前预览已成功导出为项目资产！\n\n文件名: {filename}\n保存路径: {os.path.dirname(exported_path)}\n\n将自动为您在资源管理器中打开并选中该文件。"
            )
            self.exporter.show_in_explorer(exported_path)
        else:
            self.log_message("[ERROR] 一键导出资产失败，请检查写入权限或目录有效性。")
            QMessageBox.critical(self, "导出错误", "导出资产时发生未知写入异常，请检查文件夹权限。")

    def _retrieve_rasterized_image(self, mime_type: str) -> bytes:
        """从 QWebEngineView 的 Canvas 异步转换为指定格式的图片字节流"""
        # 1. 触发前端 Canvas 渲染
        self.webview.page().runJavaScript(f"window.rasterizedData = ''; getSvgAsImageData('{mime_type}').then(data => window.rasterizedData = data).catch(err => window.rasterizedData = 'ERROR: ' + err);")
        
        # 2. 启动事件循环进行轮询
        loop = QEventLoop()
        result_data = ""
        start_time = time.time()
        
        def check_result(result):
            nonlocal result_data
            if result:
                result_data = result
                loop.quit()
                
        def poll():
            if time.time() - start_time > 3.0: # 3秒超时安全防线
                loop.quit()
                return
            self.webview.page().runJavaScript("window.rasterizedData || '';", check_result)
            
        timer = QTimer()
        timer.timeout.connect(poll)
        timer.start(50) # 每50毫秒轮询一次
        
        loop.exec()
        timer.stop()
        
        if not result_data or result_data.startswith("ERROR"):
            self.log_message(f"[ERROR] 网页光栅化图像失败: {result_data}")
            return b""
            
        if "," in result_data:
            _, encoded = result_data.split(",", 1)
            return base64.b64decode(encoded)
        return b""

    def open_file(self) -> None:
        """通过文件选择框加载本地 HTML / Markdown / SVG / Mermaid 文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择网页、文档、图形或图表文件",
            "",
            "所有支持的文件 (*.html *.htm *.md *.markdown *.svg *.mermaid *.mmd);;"
            "网页 (*.html *.htm);;"
            "Markdown (*.md *.markdown);;"
            "SVG 矢量图 (*.svg);;"
            "Mermaid 流程图 (*.mermaid *.mmd);;"
            "所有文件 (*.*)"
        )
        if file_path:
            self.load_html_document(file_path)

    def open_dir(self) -> None:
        """打开项目文件夹并自动尝试识别根目录下的 index.html，同时对文件夹目录实施动态监控"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if dir_path:
            dir_path = os.path.abspath(dir_path)
            
            # 清理先前的目录监听
            if self.current_watched_dir:
                try:
                    self.file_watcher.removePath(self.current_watched_dir)
                except:
                    pass
            
            # 设置当前监听目录与文件快照
            self.current_watched_dir = dir_path
            self.dir_files_snapshot = set(os.listdir(dir_path))
            
            # 将新文件夹加入监听
            if self.file_monitor:
                self.file_watcher.addPath(dir_path)
                
            index_path = os.path.join(dir_path, "index.html")
            if os.path.exists(index_path):
                self.log_message(f"成功打开文件夹: {dir_path}，自动定位到: index.html")
                self.load_html_document(index_path)
            else:
                candidate_files = [
                    f for f in os.listdir(dir_path) 
                    if f.lower().endswith(('.html', '.htm', '.md', '.markdown', '.svg', '.mermaid', '.mmd'))
                ]
                if candidate_files:
                    # 排序，HTML 优先
                    candidate_files.sort(key=lambda x: 0 if x.lower().endswith(('.html', '.htm')) else 1)
                    target_path = os.path.join(dir_path, candidate_files[0])
                    self.log_message(f"成功打开文件夹: {dir_path}，自动定位至: {candidate_files[0]}")
                    self.load_html_document(target_path)
                else:
                    self.log_message(f"[WARNING] 文件夹中未发现任何可预览页面: {dir_path}")
                    QMessageBox.information(self, "提示", "所选文件夹内没有找到任何 HTML、Markdown、SVG 或 Mermaid 文件")

    def load_document(self, file_path: str) -> None:
        """通用文档加载调度逻辑，支持 HTML/Markdown/SVG/Mermaid"""
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            self.log_message(f"[ERROR] 文件不存在: {file_path}")
            return

        # 1. 识别并标记当前预览资产类别
        ext = os.path.splitext(file_path.lower())[1]
        if ext in ('.md', '.markdown'):
            self.current_content_type = "markdown"
        elif ext == '.svg':
            self.current_content_type = "svg"
        elif ext in ('.mermaid', '.mmd'):
            self.current_content_type = "mermaid"
        else:
            self.current_content_type = "html"

        # 重置错误控制信号锁
        self.log_panel_auto_shown = False

        # 2. 接管并重建文件监控器
        if self.file_monitor:
            paths = self.file_watcher.files()
            if paths:
                self.file_watcher.removePaths(paths)
            self.file_watcher.addPath(file_path)

        self.current_orig_file = file_path

        # 3. HTML 资产渲染处理
        if self.current_content_type == "html":
            target_render_path = file_path
            # 执行自动纠错/完整性检查
            if self.auto_repair:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    repaired_content = repair_html(content)
                    
                    path_hash = hashlib.md5(file_path.encode("utf-8")).hexdigest()[:8]
                    temp_filename = f".temp_preview_{path_hash}.html"
                    temp_file_path = os.path.join(os.path.dirname(file_path), temp_filename)
                    
                    with open(temp_file_path, "w", encoding="utf-8") as f:
                        f.write(repaired_content)
                    
                    self.temp_files.add(temp_file_path)
                    target_render_path = temp_file_path
                    self.log_message(f"已启用 HTML 修复，生成缓存代理页: {temp_filename}")
                except Exception as e:
                    self.log_message(f"[WARNING] HTML 纠错自动补全失败: {e}，将直接加载原文件。")
                    target_render_path = file_path

            self.current_rendered_file = target_render_path

            # 4. 根据协议渲染 HTML 页面
            if self.use_http:
                web_dir = os.path.dirname(target_render_path)
                port = self.server.start(web_dir)
                filename = os.path.basename(target_render_path)
                url_str = f"http://127.0.0.1:{port}/{filename}"
                self.webview.load_url(url_str)
                self.status_label.setText(f"服务端口: {port} | 当前预览: {os.path.basename(file_path)}")
            else:
                self.webview.load_file(target_render_path)
                self.status_label.setText(f"本地渲染 | 当前预览: {os.path.basename(file_path)}")
        else:
            # 5. 其他文本类（Markdown/SVG/Mermaid）的提取与分发渲染
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                
                self.current_markdown_raw = text
                label = {"markdown": "Markdown 源码", "svg": "SVG 矢量图", "mermaid": "Mermaid 代码"}.get(self.current_content_type, self.current_content_type)
                self.log_message(f"已加载 {label}，字数: {len(text)}")
                
                if self.current_content_type == "markdown":
                    self.render_markdown_content(text)
                elif self.current_content_type == "svg":
                    self.render_svg_content(text)
                elif self.current_content_type == "mermaid":
                    self.render_mermaid_content(text)
            except Exception as e:
                self.log_message(f"[ERROR] 读取 {self.current_content_type} 文本失败: {e}")

    def load_html_document(self, file_path: str) -> None:
        """加载 HTML 文件的兼容接口"""
        self.load_document(file_path)

    def load_markdown_document(self, file_path: str) -> None:
        """加载 Markdown 文件的兼容接口"""
        self.load_document(file_path)

    def _read_template_file(self, filename: str) -> str:
        """从外部加载 HTML/JS 模板"""
        try:
            path = self.get_resource_path(os.path.join("templates", filename))
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            self.log_message(f"[ERROR] 无法读取模板文件 {filename}: {e}")
            return ""


    def render_svg_content(self, svg_text: str) -> None:
        """渲染 SVG 内容，展示高级设计师透明度网格背景"""
        svg_b64 = base64.b64encode(svg_text.encode('utf-8')).decode('utf-8')
        
        # 外部载入共享 JS 片段与 SVG 模版
        js_snippet = self._read_template_file("getSvgAsImageData.js")
        template = self._read_template_file("svg_preview.html")
        
        html_template = template.replace("{{svg_b64}}", svg_b64).replace("{{getSvgAsImageData}}", js_snippet)
        
        temp_svg_html = os.path.join(self.cache_dir, "svg_preview.html")
        
        try:
            with open(temp_svg_html, "w", encoding="utf-8") as f:
                f.write(html_template)
            
            self.temp_files.add(temp_svg_html)
            self.current_rendered_file = temp_svg_html
            
            if self.use_http:
                port = self.server.start(self.cache_dir)
                url_str = f"http://127.0.0.1:{port}/svg_preview.html"
                self.webview.load_url(url_str)
                self.status_label.setText(f"服务端口: {port} | 当前预览: SVG 矢量图形")
            else:
                self.webview.load_file(temp_svg_html)
                self.status_label.setText(f"本地渲染 | 当前预览: SVG 矢量图形")
        except Exception as e:
            self.log_message(f"[ERROR] 无法写入 SVG 渲染缓存: {e}")

    def render_mermaid_content(self, mermaid_code: str) -> None:
        """渲染 Mermaid 流程图，支持拖拽缩放控制"""
        clean_mermaid = mermaid_code.strip()
        match = re.search(r"```mermaid\s*\n([\s\S]*?)\n```", clean_mermaid, re.IGNORECASE)
        if match:
            clean_mermaid = match.group(1).strip()
            
        mermaid_b64 = base64.b64encode(clean_mermaid.encode('utf-8')).decode('utf-8')
        
        # 外部载入共享 JS 片段与 Mermaid 模版
        js_snippet = self._read_template_file("getSvgAsImageData.js")
        template = self._read_template_file("mermaid_preview.html")
        
        html_template = template.replace("{{mermaid_b64}}", mermaid_b64).replace("{{getSvgAsImageData}}", js_snippet)
        
        temp_mermaid_html = os.path.join(self.cache_dir, "mermaid_preview.html")
        
        try:
            with open(temp_mermaid_html, "w", encoding="utf-8") as f:
                f.write(html_template)
            
            self.temp_files.add(temp_mermaid_html)
            self.current_rendered_file = temp_mermaid_html
            
            if self.use_http:
                port = self.server.start(self.cache_dir)
                url_str = f"http://127.0.0.1:{port}/mermaid_preview.html"
                self.webview.load_url(url_str)
                self.status_label.setText(f"服务端口: {port} | 当前预览: Mermaid 流程图")
            else:
                self.webview.load_file(temp_mermaid_html)
                self.status_label.setText(f"本地渲染 | 当前预览: Mermaid 流程图")
        except Exception as e:
            self.log_message(f"[ERROR] 无法写入 Mermaid 渲染缓存: {e}")
    def reload_current_file(self) -> None:
        """重新载入当前正在预览的文件"""
        if self.current_orig_file and os.path.exists(self.current_orig_file):
            if self.current_content_type == "markdown":
                try:
                    with open(self.current_orig_file, "r", encoding="utf-8", errors="ignore") as f:
                        md_text = f.read()
                    self.current_markdown_raw = md_text
                    self.render_markdown_content(md_text)
                except Exception as e:
                    self.log_message(f"[ERROR] 重载 Markdown 失败: {e}")
            elif self.current_content_type == "svg":
                try:
                    with open(self.current_orig_file, "r", encoding="utf-8", errors="ignore") as f:
                        svg_text = f.read()
                    self.current_markdown_raw = svg_text
                    self.render_svg_content(svg_text)
                except Exception as e:
                    self.log_message(f"[ERROR] 重载 SVG 失败: {e}")
            elif self.current_content_type == "mermaid":
                try:
                    with open(self.current_orig_file, "r", encoding="utf-8", errors="ignore") as f:
                        mermaid_code = f.read()
                    self.current_markdown_raw = mermaid_code
                    self.render_mermaid_content(mermaid_code)
                except Exception as e:
                    self.log_message(f"[ERROR] 重载 Mermaid 失败: {e}")
            else:
                self.load_html_document(self.current_orig_file)

    # ==================== 监听事件回调槽函数 ====================

    def on_file_changed(self, path: str) -> None:
        """文件系统监听回调：若原文件被编辑器修改并保存，自动重载"""
        if not self.file_monitor:
            return
        self.log_message(f"检测到文件被外部修改: {path}，正在自动刷新预览...")
        self.reload_current_file()

    def on_directory_changed(self, dir_path: str) -> None:
        """项目目录监听回调：若目录下产生新 HTML，全自动拉起加载预览"""
        if not self.file_monitor or not self.current_watched_dir:
            return

        dir_path = os.path.abspath(dir_path)
        if not os.path.exists(dir_path):
            return

        try:
            # 1. 读取当前文件夹所有文件名
            current_files = set(os.listdir(dir_path))
            
            # 2. 对比快照，寻找新增的文件
            new_files = current_files - self.dir_files_snapshot
            
            # 3. 过滤出合法的 HTML/Markdown 页面，必须严格剔除以 .temp_preview_ 开头的隐藏自动修复代理文件
            new_docs = [
                f for f in new_files 
                if f.lower().endswith(('.html', '.htm', '.md', '.markdown')) and not f.startswith(".temp_preview_")
            ]
            
            # 4. 如果有新增文档
            if new_docs:
                # 按照修改时间进行排序，优先加载最新的
                new_doc_paths = [os.path.join(dir_path, f) for f in new_docs]
                new_doc_paths.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
                
                latest_new_doc = new_doc_paths[0]
                filename = os.path.basename(latest_new_doc)
                
                self.log_message(f"检测到工作目录下产生新文档文件: {filename}，正在自动加载预览...")
                self.load_html_document(latest_new_doc) # 它会自动分流到 md 或 html 加载器中
                
                if self.auto_raise:
                    self.raise_window_to_front()

            # 5. 无论如何更新快照，确保状态最新
            self.dir_files_snapshot = current_files
        except Exception as e:
            print(f"[ERROR] 目录监听匹配执行异常: {e}")

    def is_probable_markdown(self, text: str) -> bool:
        """启发式检测文本是否大概率是 Markdown 格式"""
        text_stripped = text.strip()
        if not text_stripped:
            return False
            
        # 如果包含 HTML 根标签，优先识别为 HTML，而非 Markdown
        text_lower = text_stripped.lower()
        if text_lower.startswith("<!doctype html") or text_lower.startswith("<html"):
            return False
            
        # 1. 强特征：检测 Markdown 标题 (如行首有 # 符号且后接空格)
        if re.search(r"(?m)^#{1,6}\s", text_stripped):
            return True
            
        # 2. 强特征：检测 Markdown 表格的分割线列结构 (如: | --- | 或 |:---|)
        if re.search(r"\|[\s]*:?-+:?[\s]*\|", text_stripped):
            return True
            
        # 3. 中特征：检测列表项 (如: - 或 * 或 + 或 1. 后接空格且处于行首)
        if re.search(r"(?m)^[\s]*[-*+]\s+", text_stripped) or re.search(r"(?m)^[\s]*\d+\.\s+", text_stripped):
            return True
            
        # 4. 中特征：检测引用块 (如: > 后接空格且处于行首)
        if re.search(r"(?m)^[\s]*>\s+", text_stripped):
            return True
            
        # 5. 辅助特征：拥有成对的围栏代码块
        if text_stripped.count("```") >= 2:
            return True
            
        # 6. 辅助特征：拥有成对的粗体/斜体样式标记
        if text_stripped.count("**") >= 2 or text_stripped.count("__") >= 2:
            return True
            
        # 7. 辅助特征：包含标准的 Markdown 链接语法 [text](url)
        if re.search(r"\[.+?\]\(.+?\)", text_stripped):
            return True
            
        # 8. 辅助特征：包含成对的行内代码标记
        if text_stripped.count("`") >= 2:
            return True
            
        return False

    def load_from_text(self, text: str, content_type: str) -> None:
        """从纯文本加载并根据格式类型分发渲染"""
        content_type = content_type.lower()
        suffix_map = {
            "markdown": "md",
            "html": "html",
            "svg": "svg",
            "mermaid": "mermaid"
        }
        suffix = suffix_map.get(content_type, "html")
        clip_file_path = os.path.join(self.cache_dir, f"clipboard_preview.{suffix}")
        
        try:
            if content_type == "html":
                text = repair_html(text)
                
            with open(clip_file_path, "w", encoding="utf-8") as f:
                f.write(text)
            
            self.temp_files.add(clip_file_path)
            self.current_orig_file = clip_file_path
            self.current_content_type = content_type
            self.current_markdown_raw = text
            
            label_map = {
                "markdown": "Markdown 内容",
                "html": "HTML 内容",
                "svg": "SVG 内容",
                "mermaid": "Mermaid 内容"
            }
            label = label_map.get(content_type, "文本内容")
            self.log_message(f"{label}已安全落盘至缓存目录。正在触发渲染模板呈现...")
            
            if content_type == "html":
                self.load_html_document(clip_file_path)
            elif content_type == "markdown":
                self.render_markdown_content(text)
            elif content_type == "svg":
                self.render_svg_content(text)
            elif content_type == "mermaid":
                self.render_mermaid_content(text)
                
            if self.auto_raise:
                self.raise_window_to_front()
        except Exception as e:
            self.log_message(f"[ERROR] 无法将 {content_type.upper()} 内容写入缓存: {e}")

    def load_from_clipboard(self, content_type: str) -> None:
        """从剪贴板强制提取指定内容格式载入"""
        text = self.clipboard.text().strip()
        if not text:
            QMessageBox.warning(self, "加载提示", "当前剪贴板为空，无法加载！")
            return
        
        label_map = {
            "markdown": "Markdown",
            "html": "HTML",
            "svg": "SVG",
            "mermaid": "Mermaid"
        }
        label = label_map.get(content_type.lower(), content_type.upper())
        self.log_message(f"手动触发：强制将剪贴板内容解析为 {label}...")
        self.load_from_text(text, content_type)

    def load_markdown_from_text(self, text: str) -> None:
        self.load_from_text(text, "markdown")

    def load_html_from_text(self, text: str) -> None:
        self.load_from_text(text, "html")

    def load_svg_from_text(self, text: str) -> None:
        self.load_from_text(text, "svg")

    def load_mermaid_from_text(self, text: str) -> None:
        self.load_from_text(text, "mermaid")

    def load_svg_from_clipboard(self) -> None:
        self.load_from_clipboard("svg")

    def load_mermaid_from_clipboard(self) -> None:
        self.load_from_clipboard("mermaid")

    def load_markdown_from_clipboard(self) -> None:
        self.load_from_clipboard("markdown")

    def load_html_from_clipboard(self) -> None:
        self.load_from_clipboard("html")

    def detect_content_type(self, text: str) -> str:
        """精确检测文本是 HTML、Markdown、SVG 还是 Mermaid
        
        Returns:
            "html", "markdown", "svg", "mermaid", or "unknown"
        """
        text_stripped = text.strip()
        if not text_stripped:
            return "unknown"
            
        text_lower = text_stripped.lower()
        
        # 1. SVG 强特征检测（以 <svg 开头，忽略 XML 声明与空白）
        if re.match(r"^\s*(?:<\?xml.*?\?>\s*)?(?:<!doctype svg.*?>\s*)?<svg", text_stripped, re.IGNORECASE):
            return "svg"
            
        # 2. Mermaid 特征检测
        if "```mermaid" in text_lower:
            return "mermaid"
        mermaid_keywords = (
            "graph", "flowchart", "sequencediagram", "classdiagram", "statediagram",
            "erdiagram", "journey", "gantt", "pie", "gitgraph", "mindmap", "timeline"
        )
        first_line = text_stripped.splitlines()[0].strip().lower() if text_stripped.splitlines() else ""
        first_line = first_line.lstrip("`").strip()
        if any(first_line.startswith(kw) for kw in mermaid_keywords):
            return "mermaid"
            
        # 3. 强网页特征检测 (以 <!doctype 或 <html 开头，或包含闭合 </html>/</body> 标签)
        if text_lower.startswith("<!doctype html") or text_lower.startswith("<html"):
            return "html"
        if "</html>" in text_lower or "</body>" in text_lower:
            return "html"
            
        # 4. 启发式 Markdown 特征检测 (若满足 Markdown 语法结构特征，优先识别为 MD)
        if self.is_probable_markdown(text_stripped):
            return "markdown"
            
        # 5. 弱网页特征检测 (仅在非 Markdown 情况下，判断是否包含成对的常见 HTML 标签)
        if (text_lower.count("<div") > 0 and text_lower.count("</div") > 0) or \
           (text_lower.count("<p") > 0 and text_lower.count("</p") > 0) or \
           (text_lower.count("<script") > 0 and text_lower.count("</script") > 0):
            return "html"
            
        return "unknown"

    def on_clipboard_changed(self) -> None:
        """剪贴板变更监听回调，增加安全长度审计与多阶段类型智能识别"""
        if not self.clipboard_monitor:
            return

        mime_data = self.clipboard.mimeData()

        # 1. 优先检测剪贴板是否包含 URL/文件路径列表 (如在资源管理器中直接复制文件)
        if mime_data.hasUrls():
            urls = mime_data.urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path and os.path.isfile(file_path) and os.path.exists(file_path):
                    if file_path.lower().endswith(('.html', '.htm', '.md', '.markdown', '.svg', '.mermaid', '.mmd')):
                        current_hash = hashlib.md5(file_path.encode("utf-8")).hexdigest()
                        if current_hash == self.last_clip_hash:
                            return
                        self.last_clip_hash = current_hash
                        
                        self.log_message(f"剪贴板中检测到复制的本地文件: {os.path.basename(file_path)}，正在自动加载渲染...")
                        self.load_html_document(file_path)
                        return

        text = self.clipboard.text().strip()
        if not text:
            return

        # 2. 其次检测剪贴板纯文本是否是合法的文件路径或 file:// 协议 URL
        file_path = text
        if file_path.startswith("file:///"):
            from PySide6.QtCore import QUrl
            file_path = QUrl(file_path).toLocalFile()
            
        # 清除两端多余的双引号（Windows 复制路径时可能带有双引号）
        file_path = file_path.strip('"\'')
        
        if os.path.isfile(file_path) and os.path.exists(file_path):
            if file_path.lower().endswith(('.html', '.htm', '.md', '.markdown', '.svg', '.mermaid', '.mmd')):
                current_hash = hashlib.md5(file_path.encode("utf-8")).hexdigest()
                if current_hash == self.last_clip_hash:
                    return
                self.last_clip_hash = current_hash
                
                self.log_message(f"剪贴板中检测到复制的文件路径文本: {os.path.basename(file_path)}，正在自动加载渲染...")
                self.load_html_document(file_path)
                return

        # 3. 文本长度安全防线
        if len(text) < 30:
            return
            
        if len(text) > 5 * 1024 * 1024:
            self.log_message("[WARNING] 剪贴板内容过长 (>5MB)，已忽略自动识别以防卡顿。")
            return

        # 4. 详细的决策输出：打印前 120 字以供直观调试
        clean_text_preview = text[:120].replace("\n", " ").replace("\r", "")
        self.log_message(f"[CLIPBOARD] 监听到变更文本 (共 {len(text)} 字): '{clean_text_preview}...'")

        # 5. 多阶段智能流分发并输出结果
        content_type = self.detect_content_type(text)
        self.log_message(f"[CLIPBOARD] 智能判定决策结果: {content_type.upper()}")

        if content_type == "unknown":
            return

        current_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        if current_hash == self.last_clip_hash:
            return
        self.last_clip_hash = current_hash

        label_map = {
            "markdown": "Markdown 富文本内容",
            "svg": "SVG 矢量图形内容",
            "mermaid": "Mermaid 流程图代码",
            "html": "HTML 网页代码"
        }
        label = label_map.get(content_type, "文本内容")
        self.log_message(f"剪贴板中检测到 {label}，开始进行自动解析捕获...")
        self.load_from_text(text, content_type)

    # ==================== 顶栏选项控制槽函数 ====================

    def toggle_render_mode(self, use_http: bool) -> None:
        """切换渲染协议模式"""
        self.use_http = use_http
        self.save_configuration()
        if use_http:
            self.log_message("已切换为: 本地 HTTP 服务托管模式")
        else:
            self.log_message("已切换为: file:// 协议渲染模式 (注意：部分高级 JS 模块将受限)")
            self.server.stop()
        self.reload_current_file()

    def toggle_clipboard_monitor(self, checked: bool) -> None:
        """开启或关闭剪贴板自动预览监视器"""
        self.clipboard_monitor = checked
        self.act_tray_clip.setChecked(checked)
        self.save_configuration()
        if checked:
            self.log_message("剪贴板自动识别监视器: 开启")
            self.indicator.setObjectName("indicator_active")
        else:
            self.log_message("剪贴板自动识别监视器: 关闭")
            self.indicator.setObjectName("indicator_inactive")
        self.indicator.style().unpolish(self.indicator)
        self.indicator.style().polish(self.indicator)

    def toggle_file_monitor(self, checked: bool) -> None:
        """开启或关闭文件自动刷新监视器"""
        self.file_monitor = checked
        self.save_configuration()
        if checked:
            self.log_message("文件修改自动重载监视器: 开启")
            if self.current_orig_file:
                self.file_watcher.addPath(self.current_orig_file)
            if self.current_watched_dir:
                self.file_watcher.addPath(self.current_watched_dir)
        else:
            self.log_message("文件修改自动重载监视器: 关闭")
            paths = self.file_watcher.files()
            if paths:
                self.file_watcher.removePaths(paths)

    def toggle_auto_raise(self, checked: bool) -> None:
        """开启或关闭复制 HTML 时自动弹窗置顶"""
        self.auto_raise = checked
        self.save_configuration()
        if checked:
            self.log_message("复制 HTML 自动弹窗置顶: 开启")
        else:
            self.log_message("复制 HTML 自动弹窗置顶: 关闭")

    def raise_window_to_front(self) -> None:
        """将窗口强行拉回并激活到前台，支持从最小化状态唤起"""
        # 1. 恢复正常大小（如果最小化）
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()

        # 2. 通过临时设置 WindowStaysOnTopHint 并显式调用 raise_ & activateWindow 唤醒前台焦点
        self.setWindowFlags(self.default_flags | Qt.WindowType.WindowStaysOnTopHint)
        self.show()
        
        # 3. 立即恢复默认的 flags
        if not self.always_on_top:
            self.setWindowFlags(self.default_flags)
            self.show()
        
        # 4. 再次确保激活
        self.raise_()
        self.activateWindow()

    def toggle_auto_repair(self, checked: bool) -> None:
        """切换 HTML 自动修复/纠错模式"""
        self.auto_repair = checked
        self.save_configuration()
        if checked:
            self.log_message("HTML 自动纠错与标签补全: 启用")
        else:
            self.log_message("HTML 自动纠错与标签补全: 禁用")
        self.reload_current_file()

    def clear_all_temp_files(self) -> None:
        """物理清除生命周期中产生的所有临时隐藏预览缓存文件"""
        count = 0
        for file_path in list(self.temp_files):
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    count += 1
                except Exception as e:
                    self.log_message(f"[WARNING] 清理缓存文件失败 {file_path}: {e}")
        self.temp_files.clear()
        
        if os.path.exists(self.cache_dir):
            for f in os.listdir(self.cache_dir):
                f_path = os.path.join(self.cache_dir, f)
                try:
                    os.remove(f_path)
                    count += 1
                except:
                    pass
        self.log_message(f"已清理所有缓存和残留文件，共释放 {count} 个临时页面。")

    # ==================== 日志控制台与报错处理 ====================

    def toggle_log_panel_action(self, checked: bool) -> None:
        """从顶栏日志菜单手动切换显示日志控制台"""
        self.log_panel.setVisible(checked)
        if checked:
            self.log_panel_auto_shown = True
        else:
            self.log_panel_auto_shown = False

    def hide_log_panel(self) -> None:
        """隐藏日志控制台"""
        self.log_panel.setVisible(False)
        self.act_show_log.setChecked(False)
        self.log_panel_auto_shown = False

    def _trigger_auto_show_log(self) -> None:
        """智能机制：报错时自动非阻塞弹出控制台，限制重绘频次"""
        if not self.log_panel.isVisible():
            self.log_panel.setVisible(True)
            self.act_show_log.setChecked(True)
            self.log_panel_auto_shown = True

    def log_message(self, message: str) -> None:
        """向日志终端追加日志信息，超过行数进行剪裁防止内存积压"""
        try:
            # 检查 txt_log 是否已被垃圾回收以防止 C++ 析构异常
            if hasattr(self, "txt_log") and self.txt_log:
                if self.txt_log.document().blockCount() > 800:
                    self.txt_log.clear()
                    self.txt_log.append(">> [SYSTEM] 运行日志超出上限，已自动清空历史数据。")

                self.txt_log.append(f">> {message}")
                self.txt_log.moveCursor(self.txt_log.textCursor().MoveOperation.End)
        except RuntimeError:
            # 捕获 C++ 对象已被 Qt 注销销毁的异常，不做任何处理直接静默
            pass

        print(f"[Log] {message}")

        # 如果系统遇到 ERROR，且当前界面仍存活，则自动弹出控制台提醒
        if "[ERROR]" in message:
            try:
                self._trigger_auto_show_log()
            except:
                pass

    def log_web_console(self, level: int, message: str, line_number: int, source_id: str) -> None:
        """接管并格式化输出 JavaScript 的控制台错误"""
        level_map = {
            0: "[Web-INFO]",
            1: "[Web-WARN]",
            2: "[Web-ERROR]"
        }
        level_str = level_map.get(level, "[Web-LOG]")
        filename = os.path.basename(source_id) if source_id else "inline"
        
        log_content = f"{level_str} ({filename}:{line_number}): {message}"
        self.log_message(log_content)

        # 核心智能点：如果网页 JS 发生运行时错误 (level == 2 为 ERROR)，自动弹出日志区
        if level == 2:
            self._trigger_auto_show_log()

    def changeEvent(self, event) -> None:
        """监听窗口最小化事件，根据设置将其直接隐藏到系统托盘"""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                if self.min_to_tray:
                    self.hide()
                    if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
                        from PySide6.QtWidgets import QSystemTrayIcon
                        self.tray_icon.showMessage(
                            "AI Preview Studio",
                            "已最小化到系统托盘，继续在后台运行。",
                            QSystemTrayIcon.MessageIcon.Information,
                            1500
                        )
                    event.ignore()
                    return
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        """重写关闭窗口事件，根据设置隐藏到系统托盘或执行安全退出"""
        if getattr(self, "_force_exit", False):
            # 外部强制退出
            self._perform_exit(event)
            return

        if self.prompt_on_close:
            # 弹出自定义选择对话框
            self.raise_()
            self.activateWindow()
            QApplication.beep()
            
            dialog = CloseConfirmDialog(self)
            if self.min_to_tray:
                dialog.radio_tray.setChecked(True)
            else:
                dialog.radio_exit.setChecked(True)
                
            if dialog.exec() == QDialog.DialogCode.Accepted:
                remember = dialog.chk_remember.isChecked()
                to_tray = dialog.radio_tray.isChecked()
                
                if remember:
                    self.prompt_on_close = False
                    self.min_to_tray = to_tray
                    # 更新菜单中的状态
                    if hasattr(self, "act_prompt_on_close"):
                        self.act_prompt_on_close.setChecked(False)
                    if hasattr(self, "act_min_to_tray"):
                        self.act_min_to_tray.setChecked(to_tray)
                    self.save_configuration()
                else:
                    # 不记住选择时，仅更新临时操作模式
                    self.min_to_tray = to_tray
                
                if to_tray:
                    self._minimize_to_tray(event)
                else:
                    self._perform_exit(event)
            else:
                event.ignore()
        else:
            # 不弹出确认提示，直接按已有的记住选项处理
            if self.min_to_tray:
                self._minimize_to_tray(event)
            else:
                self._perform_exit(event)

    def _minimize_to_tray(self, event) -> None:
        """最小化到托盘的具体实现，隐藏窗口（不显示在任务栏）"""
        self.hide()
        self.tray_icon.showMessage(
            "AI Preview Studio",
            "已最小化到系统托盘，将在后台持续监听剪贴板。",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        event.ignore()

    def _perform_exit(self, event) -> None:
        """退出程序，回收资源"""
        print("[Log] 程序正在退出，开始回收系统资源并清理临时文件...")
        self.server.stop()
        self.clear_all_temp_files()
        event.accept()
        QApplication.quit()  # 确保在 setQuitOnLastWindowClosed(False) 下能正常结束事件循环退出

    def _setup_system_tray(self) -> None:
        """设置系统托盘图标与上下文菜单"""
        from PySide6.QtWidgets import QSystemTrayIcon, QStyle
        from PySide6.QtGui import QIcon
        
        self.tray_icon = QSystemTrayIcon(self)
        
        # 优先载入我们自定义的 logo.ico 图标，如果不存在则退回原生计算机图标
        icon_path = self.get_resource_path("logo.ico")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        
        # 创建托盘菜单
        tray_menu = QMenu(self)
        
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self.show_and_raise)
        tray_menu.addAction(act_show)
        
        self.act_tray_clip = QAction("监听剪贴板", self, checkable=True)
        self.act_tray_clip.setChecked(self.clipboard_monitor)
        self.act_tray_clip.triggered.connect(self.toggle_clipboard_from_tray)
        tray_menu.addAction(self.act_tray_clip)
        
        tray_menu.addSeparator()
        
        act_exit = QAction("安全退出", self)
        act_exit.triggered.connect(self.force_exit_app)
        tray_menu.addAction(act_exit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()
        
    def show_and_raise(self) -> None:
        """显示并激活主窗口，将其置顶弹起"""
        self.showNormal()  # 确保恢复正常窗口状态（防止在最小化状态下被隐藏）
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_clipboard_from_tray(self, checked: bool) -> None:
        """从托盘菜单快速切换剪贴板监听器"""
        self.clipboard_monitor = checked
        self.act_clip_monitor.setChecked(checked)
        self.act_tray_clip.setChecked(checked)
        self.save_configuration()
        self.log_message(f"已从系统托盘{'开启' if checked else '关闭'}剪贴板自动监视")
        
    def force_exit_app(self) -> None:
        """彻底安全关闭软件"""
        self._force_exit = True
        self.close()

    def on_tray_icon_activated(self, reason) -> None:
        """点击托盘图标激活主窗口"""
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_and_raise()

    def load_configuration(self) -> None:
        """从本地存储读取配置参数"""
        import json
        config_path = os.path.join(os.getcwd(), ".preview_cache", "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.use_http = cfg.get("use_http", True)
                self.clipboard_monitor = cfg.get("clipboard_monitor", True)
                self.file_monitor = cfg.get("file_monitor", True)
                self.auto_repair = cfg.get("auto_repair", True)
                self.auto_raise = cfg.get("auto_raise", True)
                self.min_to_tray = cfg.get("min_to_tray", True)
                self.always_on_top = cfg.get("always_on_top", False)
                self.prompt_on_close = cfg.get("prompt_on_close", True)
            except Exception as e:
                print(f"[Warning] 加载配置文件失败: {e}")

    def save_configuration(self) -> None:
        """保存配置参数至本地存储"""
        import json
        config_path = os.path.join(os.getcwd(), ".preview_cache", "config.json")
        cfg = {
            "use_http": self.use_http,
            "clipboard_monitor": self.clipboard_monitor,
            "file_monitor": self.file_monitor,
            "auto_repair": self.auto_repair,
            "auto_raise": self.auto_raise,
            "min_to_tray": self.min_to_tray,
            "always_on_top": self.always_on_top,
            "prompt_on_close": self.prompt_on_close
        }
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Warning] 保存配置文件失败: {e}")

    def _setup_settings_menu(self) -> None:
        """配置“设置”选项的下拉菜单，用于系统级参数配置"""
        menu = QMenu(self)

        self.act_autostart = menu.addAction("开机自动启动")
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(self.load_autostart_state())
        self.act_autostart.triggered.connect(self.toggle_autostart)

        self.act_prompt_on_close = menu.addAction("关闭窗口时弹出确认与选项")
        self.act_prompt_on_close.setCheckable(True)
        self.act_prompt_on_close.setChecked(self.prompt_on_close)
        self.act_prompt_on_close.triggered.connect(self.toggle_prompt_on_close)

        self.act_min_to_tray = menu.addAction("关闭窗口时最小化到系统托盘")
        self.act_min_to_tray.setCheckable(True)
        self.act_min_to_tray.setChecked(self.min_to_tray)
        self.act_min_to_tray.triggered.connect(self.toggle_min_to_tray)

        self.act_always_on_top = menu.addAction("保持窗口置顶")
        self.act_always_on_top.setCheckable(True)
        self.act_always_on_top.setChecked(self.always_on_top)
        self.act_always_on_top.triggered.connect(self.toggle_always_on_top)

        self.btn_settings.clicked.connect(lambda: self._show_popup_menu(self.btn_settings, menu))

    def toggle_prompt_on_close(self, checked: bool) -> None:
        """切换关闭时是否确认提示"""
        self.prompt_on_close = checked
        self.save_configuration()
        self.log_message(f"关闭窗口确认提示已{'开启' if checked else '关闭'}")

    def toggle_always_on_top(self, checked: bool) -> None:
        """切换窗口置顶状态"""
        self.always_on_top = checked
        self.save_configuration()
        if checked:
            self.setWindowFlags(self.default_flags | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.default_flags)
        self.show()
        self.log_message(f"窗口置顶已{'开启' if checked else '关闭'}")

    def toggle_min_to_tray(self, checked: bool) -> None:
        """切换关闭时是否最小化到系统托盘"""
        self.min_to_tray = checked
        self.save_configuration()
        self.log_message(f"关闭窗口最小化到托盘已{'开启' if checked else '关闭'}")

    def toggle_autostart(self, checked: bool) -> None:
        """切换开机自启动"""
        self.set_autostart_registry(checked)
        self.save_configuration()
        self.log_message(f"开机自启动已{'开启' if checked else '关闭'}")

    def load_autostart_state(self) -> bool:
        """自启动注册表状态读取"""
        from PySide6.QtCore import QSettings
        settings = QSettings("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", QSettings.NativeFormat)
        return settings.contains("AIPreviewStudio")

    def set_autostart_registry(self, enable: bool) -> None:
        """配置 Windows 开机自启注册表"""
        from PySide6.QtCore import QSettings
        import sys
        
        settings = QSettings("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", QSettings.NativeFormat)
        app_name = "AIPreviewStudio"
        
        if enable:
            if sys.executable.endswith(".exe") and "python" not in os.path.basename(sys.executable).lower():
                app_path = f'"{os.path.abspath(sys.executable)}"'
            else:
                app_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            settings.setValue(app_name, app_path)
        else:
            settings.remove(app_name)

    # ==================== 微软 Fluent Light 主题 QSS ====================

    def _apply_qss(self) -> None:
        """注入高级别 Fluent 浅色扁平化 QSS 样式表，从外部 qss 文件读取以实现样式与逻辑分离"""
        try:
            qss_path = self.get_resource_path(os.path.join("ui", "style.qss"))
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    qss = f.read()
                self.setStyleSheet(qss)
            else:
                self.log_message(f"[WARNING] 样式表文件不存在: {qss_path}")
        except Exception as e:
            self.log_message(f"[ERROR] 载入 QSS 样式表失败: {e}")