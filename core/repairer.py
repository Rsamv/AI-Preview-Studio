# -*- coding: utf-8 -*-
"""AI Preview Studio - HTML 修复与补全模块

该模块负责对截断的、格式不完整的 HTML 代码进行修复和补全。
特别针对 AI 截断输出导致 style、script 或核心布局标签未闭合的问题，
采用基于标签栈和正则表达式的启发式补全算法。

符合 Google 编程规范。
"""

import re


def repair_html(html_content: str) -> str:
    """自动补全被截断的 HTML 标签，保证页面的渲染完整性
    
    Args:
        html_content: 原始(可能损坏的) HTML 代码字符串

    Returns:
        str: 修复补全后的 HTML 代码字符串
    """
    if not html_content.strip():
        return "<html><body><p>未检测到有效的 HTML 内容</p></body></html>"

    # 1. 优先修复关键标签 style 和 script
    # 如果 <style> 未闭合，则追加 </style>，否则后续内容会被浏览器解析为 CSS 样式文本
    last_style_open = html_content.rfind("<style")
    last_style_close = html_content.rfind("</style>")
    if last_style_open > last_style_close:
        html_content += "\n</style>"

    # 如果 <script> 未闭合，则追加 </script>，防止页面被识别为纯脚本
    last_script_open = html_content.rfind("<script")
    last_script_close = html_content.rfind("</script>")
    if last_script_open > last_script_close:
        html_content += "\n</script>"

    # 2. 基于标签栈对其他 HTML 容器标签进行匹配与补齐
    # 声明 HTML 规范中的自闭合(空)标签，这些标签不需要闭合
    void_tags = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"
    }

    # 正则表达式匹配所有的开始/结束标签，捕获标签名称
    # 排除注释以及其他特殊字符
    tag_regex = re.compile(r"</?([a-zA-Z0-9:-]+)(?:\s+[^>]*)?>")
    
    tag_stack = []

    # 遍历所有找到的标签
    for match in tag_regex.finditer(html_content):
        tag_text = match.group(0)
        tag_name = match.group(1).lower()

        # 过滤自闭合标签
        if tag_name in void_tags:
            continue

        if tag_text.startswith("</"):
            # 如果是闭合标签
            if tag_stack and tag_stack[-1] == tag_name:
                tag_stack.pop()
            elif tag_name in tag_stack:
                # 容错：如果当前闭合标签不在栈顶但存在于栈中，说明中间有漏掉的标签，强制回退栈
                while tag_stack and tag_stack[-1] != tag_name:
                    tag_stack.pop()
                if tag_stack:
                    tag_stack.pop()
        else:
            # 如果是开始标签，且没有以 '/>' (XML 风格) 结尾，则入栈
            if not tag_text.endswith("/>"):
                tag_stack.append(tag_name)

    # 3. 按出栈的相反顺序，在 HTML 末尾追加闭合标签
    for tag in reversed(tag_stack):
        html_content += f"\n</{tag}>"

    # 4. 补齐基本的结构性外层标签
    html_lower = html_content.lower()
    if "</body>" not in html_lower and "body" in html_lower:
        html_content += "\n</body>"
    if "</html>" not in html_lower:
        html_content += "\n</html>"

    return html_content
