# -*- coding: utf-8 -*-
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def test_detection():
    # 初始化 QApplication 以便实例化 MainWindow
    app = QApplication(sys.argv)
    window = MainWindow()

    # 测试用例定义
    cases = [
        # 1. SVG
        ("""<svg width="100" height="100">
  <circle cx="50" cy="50" r="40" stroke="green" stroke-width="4" fill="yellow" />
</svg>""", "svg"),
        
        ("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns="http://www.w3.org/2000/svg">
</svg>""", "svg"),

        # 2. Mermaid
        ("```mermaid\ngraph TD\nA[Christmas] -->|Get money| B(Go shopping)\n```", "mermaid"),
        ("graph TD\nA --> B", "mermaid"),
        ("flowchart LR\nA --> B", "mermaid"),

        # 3. HTML
        ("<!DOCTYPE html><html><body><h1>Hello</h1></body></html>", "html"),
        ("<div><p>Test</p></div>", "html"),

        # 4. Markdown
        ("# Title\n- Item 1\n- Item 2", "markdown"),
        ("## Header 2\n\nSome text with **bold**.", "markdown"),
        ("| Col 1 | Col 2 |\n|---|---|\n| A | B |", "markdown")
    ]

    print("开始进行智能检测模块单元测试...")
    passed = 0
    for i, (text, expected) in enumerate(cases):
        detected = window.detect_content_type(text)
        if detected == expected:
            print(f"[PASS] Case {i+1}: 期望 {expected}, 实际检测为 {detected}")
            passed += 1
        else:
            print(f"[FAIL] Case {i+1}: 期望 {expected}, 实际检测为 {detected}")
            print(f"输入内容首部 preview: {text[:100]!r}")
            
    print(f"\n测试完成：通过 {passed}/{len(cases)}")
    sys.exit(0 if passed == len(cases) else 1)

if __name__ == "__main__":
    test_detection()
