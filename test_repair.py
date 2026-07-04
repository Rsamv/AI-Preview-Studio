# -*- coding: utf-8 -*-
"""AI Preview Studio - HTML 修复算法验证脚本

该脚本用于对 D:\\aimg\\AISTUDIO\\HTML 目录下的测试用例进行修复测试。
它会读取原文件，通过 core/repairer 模块进行自动修复，并将修复前后的结构差异输出打印，
以验证是否成功闭合了被截断的 HTML 标签（如 style, script 等），彻底解决只渲染一部分或无法渲染的问题。

符合 Google 编程规范，包含详细中文注释。
"""

import os
import sys

# 将当前目录加入 Python 搜索路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.repairer import repair_html


def test_html_repair():
    """测试并展示 HTML 修复逻辑"""
    test_dir = r"D:\aimg\AISTUDIO\HTML"
    
    if not os.path.exists(test_dir):
        print(f"[ERROR] 测试目录不存在: {test_dir}")
        return

    print("=" * 60)
    print("           HTML 修复算法兼容性验证测试")
    print("=" * 60)

    html_files = [f for f in os.listdir(test_dir) if f.lower().endswith(('.html', '.htm'))]

    if not html_files:
        print("[WARNING] 未在测试目录下发现任何 HTML 文件。")
        return

    for file_name in html_files:
        file_path = os.path.join(test_dir, file_name)
        file_size = os.path.getsize(file_path)
        
        print(f"\n-> 正在测试文件: {file_name} ({file_size} 字节)")

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                original_content = f.read()

            # 调用修复算法
            repaired_content = repair_html(original_content)

            # 统计未闭合标签修复差异
            orig_lines = original_content.splitlines()
            repaired_lines = repaired_content.splitlines()
            added_lines_count = len(repaired_lines) - len(orig_lines)

            print(f"  - 原始行数: {len(orig_lines)}")
            print(f"  - 修复后行数: {len(repaired_lines)}")
            print(f"  - 追加闭合标签行数: {added_lines_count}")

            # 如果有追加的内容，打印出末尾追加的几行，以便我们观察补全的标签
            if added_lines_count > 0:
                print("  - 追加的闭合标签明细:")
                # 打印出最后追加的部分
                repaired_tail = repaired_content[len(original_content):].strip()
                for line in repaired_tail.splitlines():
                    print(f"    └─ [追加] {line}")
            else:
                print("  - 该 HTML 格式完整，无需补全闭合标签。")

            # 验证关键的 style 和 script 闭合情况
            style_closed = repaired_content.count("<style") == repaired_content.count("</style>")
            script_closed = repaired_content.count("<script") == repaired_content.count("</script>")
            
            print(f"  - <style> 标签是否闭合: {style_closed} (开:{repaired_content.count('<style')}, 闭:{repaired_content.count('</style>')})")
            print(f"  - <script> 标签是否闭合: {script_closed} (开:{repaired_content.count('<script')}, 闭:{repaired_content.count('</script>')})")

        except Exception as e:
            print(f"  - [FAIL] 修复过程中发生异常: {e}")

    print("\n" + "=" * 60)
    print("                  测试执行完毕")
    print("=" * 60)


if __name__ == "__main__":
    test_html_repair()
