#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSDN 付费文章阅读器 (命令行版)
支持通过多种接口获取 CSDN 文章完整内容（包括付费部分）
保存为 Markdown 格式，保留图片、代码块、数学公式等排版
用法: python csdn_reader.py
"""

import os
import sys

from reader import CsdnArticleReader


def main():
    print("=" * 50)
    print("   CSDN 付费文章阅读器 (Python 版)")
    print("=" * 50)
    print("提示: 输入 CSDN 文章 URL 即可获取完整内容")
    print("支持格式: https://blog.csdn.net/用户名/article/details/文章ID")
    print("          https://wenku.csdn.net/column/文档ID (CSDN 文库)")
    print("付费全文: 浏览器登录 CSDN 后，将 Cookie 保存到程序同目录 cookie.txt")
    print("          或设置环境变量 CSDN_COOKIE")
    print("输入 exit 退出程序")
    print("=" * 50)

    reader = CsdnArticleReader()
    save_dir = os.path.join(os.path.expanduser("~"), "Downloads", "CSDN_Articles")

    while True:
        url = input("\n请输入 CSDN 文章 URL: ").strip()

        if url.lower() == "exit":
            print("程序已退出")
            sys.exit(0)

        if not url:
            continue

        print(f"[*] 正在获取文章 ...")
        try:
            result = reader.read_article(url, save_dir)
            if result.get("success"):
                print(f"[OK] {result.get('message', '文章获取成功')}")
                if result.get("title"):
                    print(f"     标题: {result['title']}")
                if result.get("filepath"):
                    print(f"     文件: {result['filepath']}")
            else:
                print(f"[FAIL] {result.get('message', '获取失败')}")
        except Exception as e:
            print(f"[FAIL] 处理失败: {e}")


if __name__ == "__main__":
    main()
