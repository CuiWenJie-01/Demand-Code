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
