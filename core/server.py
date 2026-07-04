# -*- coding: utf-8 -*-
"""AI Preview Studio - 本地轻量级 HTTP 服务模块

该模块用于在本地后台启动一个简易的 HTTP 服务，支持 CORS 跨域请求，并具备防路径穿越的安全防护，
用以解决本地 file:// 协议下无法加载现代 JS 模块 (ES Module) 和部分外部 CDN 资源的问题。

符合 Google 编程规范。
"""

import os
import socket
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer


class CORSHTTPRequestHandler(SimpleHTTPRequestHandler):
    """支持跨域资源共享(CORS)的 HTTP 请求处理器"""

    def end_headers(self) -> None:
        """添加 CORS 响应头，允许跨域访问"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "X-Requested-With, Content-Type"
        )
        super().end_headers()

    def translate_path(self, path: str) -> str:
        """将请求 URL 路径翻译为本地文件系统路径，包含路径穿越安全审计"""
        # 调用父类方法获取默认的工作目录相对路径
        default_path = super().translate_path(path)
        
        # 获取与当前工作目录的相对关系，重新映射到指定的 web 根目录
        rel_path = os.path.relpath(default_path, os.getcwd())
        target_path = os.path.join(self.server.web_root, rel_path)
        
        # 安全审计：防范路径穿越漏洞 (Path Traversal)
        abs_target_path = os.path.abspath(target_path)
        abs_web_root = os.path.abspath(self.server.web_root)
        
        # 如果解析后的绝对路径不以 web_root 开始，说明存在越界访问风险，强制重定向到根目录
        if not abs_target_path.startswith(abs_web_root):
            return abs_web_root
            
        return abs_target_path

    def log_message(self, format: str, *args) -> None:
        """静默处理请求日志，避免控制台输出过多垃圾信息"""
        pass


class LocalHttpServer:
    """本地 HTTP 服务器管理器"""

    def __init__(self):
        self.server = None
        self.port = 0
        self.thread = None
        self.web_root = ""

    def start(self, web_root: str) -> int:
        """在后台线程中启动本地 HTTP 服务器
        
        Args:
            web_root: 托管的本地目录绝对路径

        Returns:
            int: 分配的本地随机端口号
        """
        # 如果已经存在服务，先将其关闭
        if self.server:
            self.stop()
            
        self.web_root = os.path.abspath(web_root)
        
        # 动态获取一个本地空闲的随机端口
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_socket.bind(("127.0.0.1", 0))
        self.port = temp_socket.getsockname()[1]
        temp_socket.close()
        
        # 动态创建包含 web_root 上下文的 HTTPServer 类
        class CustomServer(HTTPServer):
            web_root = self.web_root
            
        def run_server():
            try:
                # 仅绑定至 127.0.0.1 (本地环回)，防止外部网络访问，确保本地安全性
                self.server = CustomServer(("127.0.0.1", self.port), CORSHTTPRequestHandler)
                self.server.serve_forever()
            except Exception as e:
                print(f"[ERROR] 本地 HTTP 服务器运行异常: {e}")

        # 启动后台守护线程
        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        print(f"[INFO] 本地 HTTP 服务器已启动，监听端口: {self.port}，托管目录: {self.web_root}")
        return self.port

    def stop(self) -> None:
        """关闭本地 HTTP 服务器，释放线程和端口"""
        if self.server:
            srv = self.server
            self.server = None
            
            def async_shutdown():
                try:
                    srv.shutdown()
                    srv.server_close()
                except Exception as e:
                    print(f"[WARNING] 关闭 HTTP 服务器时发生异常: {e}")
                    
            # 必须使用异步线程执行 shutdown，否则如果前端有持久化链接(Keep-Alive)，会死锁主线程导致程序卡死
            threading.Thread(target=async_shutdown, daemon=True).start()
            
        if self.thread:
            # 既然是守护线程(daemon=True)，不需要 join 阻塞主线程退出，让其随进程生命周期消亡即可
            self.thread = None
            
        self.port = 0
        print("[INFO] 本地 HTTP 服务器已停止")
