#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scrapling 抓取引擎封装

使用 Scrapling 的 Fetcher (基于 curl_cffi) 发起 HTTP 请求:
- impersonate='chrome': 模拟真实 Chrome 浏览器的 TLS 指纹，降低被 CSDN 风控拦截的概率
- stealthy_headers: 自动生成与真实浏览器一致的请求头
- 支持通过 cookie.txt / 环境变量 CSDN_COOKIE 注入登录态（获取付费全文）
"""

import os
from pathlib import Path

from scrapling.fetchers import Fetcher
from playwright.sync_api import sync_playwright


def load_csdn_cookie() -> str:
    """加载 CSDN 登录 Cookie，用于获取付费全文

    优先级: 环境变量 CSDN_COOKIE > 程序同目录 cookie.txt
    """
    cookie = os.environ.get("CSDN_COOKIE", "").strip()
    if not cookie:
        cookie_file = Path(__file__).resolve().with_name("cookie.txt")
        if cookie_file.exists():
            cookie = cookie_file.read_text(encoding="utf-8").strip()
    return cookie


class ScraplingFetchEngine:
    """基于 Scrapling Fetcher 的 HTTP 抓取引擎"""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.cookie = load_csdn_cookie()

    def _build_headers(self, extra: dict | None = None) -> dict:
        """构造请求头: 登录 Cookie + 调用方指定的附加头

        其余浏览器请求头由 stealthy_headers 自动生成，
        extra 中的同名头会覆盖自动生成的头。
        """
        headers = {}
        if self.cookie:
            headers["Cookie"] = self.cookie
        if extra:
            headers.update(extra)
        return headers

    def get(self, url: str, headers: dict | None = None):
        """发起 GET 请求，返回 Scrapling Response 对象；失败返回 None

        Response 常用属性: status / body(bytes) / encoding / headers / json()
        """
        try:
            return Fetcher.get(
                url,
                impersonate="chrome",
                stealthy_headers=True,
                headers=self._build_headers(headers),
                timeout=self.timeout,
            )
        except Exception:
            return None

    def dynamic_get(self, url: str, timeout: int = 30) -> str | None:
        """使用 Playwright (Chromium) 动态渲染页面，返回完整 HTML

        适用于:
        - 需要绕过 Cloudflare 等反爬保护的页面
        - 内容由 JavaScript 动态加载的页面
        - CSDN 文库专栏页面（需要 JS 渲染才能获取完整 INITIAL_STATE）

        内部使用 Playwright 的无头 Chromium 浏览器，
        等待网络空闲后返回最终渲染的 HTML。
        """
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                )
                if self.cookie:
                    context.add_cookies([
                        {
                            "name": c.split("=", 1)[0].strip(),
                            "value": c.split("=", 1)[1].strip(),
                            "domain": ".csdn.net",
                            "path": "/",
                        }
                        for c in self.cookie.split(";")
                        if "=" in c
                    ])
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                html = page.content()
                browser.close()
                return html
        except Exception:
            return None

    @staticmethod
    def get_text(page) -> str:
        """将 Response 响应体解码为文本"""
        if page is None:
            return ""
        body = page.body
        if not body:
            return ""
        encoding = getattr(page, "encoding", None) or "utf-8"
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            return body.decode("utf-8", errors="replace")
