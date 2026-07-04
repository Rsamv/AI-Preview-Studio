# -*- coding: utf-8 -*-
"""AI Preview Studio - 一键打包发布脚本

该脚本会自动检查并安装 PyInstaller，并将主程序打包成单文件、无黑框控制台的独立 Windows 运行程序。
"""

import os
import sys
import subprocess

def run_build():
    print("==================================================")
    print("          AI Preview Studio 一键打包系统           ")
    print("==================================================")
    
    # 1. 检查并安装 PyInstaller
    try:
        import PyInstaller
        print("[INFO] PyInstaller 已安装，准备开始打包。")
    except ImportError:
        print("[INFO] 未检测到 PyInstaller，正在为您安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("[INFO] PyInstaller 安装成功！")
        except Exception as e:
            print(f"[ERROR] 安装 PyInstaller 失败: {e}")
            sys.exit(1)

    # 2. 准备打包参数
    # --noconsole: 不显示控制台窗口
    # --onedir: 打包为独立目录（包含 exe 与动态链接库及资源文件夹，启动非常快）
    # --clean: 清理缓存
    # --name: 指定可执行文件名
    dist_name = "AI-Preview-Studio"
    
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onedir",
        "--noconsole",
        "--add-data=logo.ico;.",
        "--icon=logo.ico",
        f"--name={dist_name}",
        "main.py"
    ]

    print(f"[INFO] 正在执行打包命令: {' '.join(cmd)}")
    
    try:
        subprocess.check_call(cmd)
        print("\n==================================================")
        print("打包圆满成功！")
        print(f"可执行主程序目录: {os.path.abspath(os.path.join('dist', dist_name))}")
        print(f"可执行文件路径: {os.path.abspath(os.path.join('dist', dist_name, dist_name + '.exe'))}")
        print("==================================================")
    except Exception as e:
        print(f"\n[ERROR] 打包过程中出现异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_build()
