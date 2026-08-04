#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSDN 付费文章阅读器 - 共享核心模块

支持通过多种接口获取 CSDN 文章完整内容（包括付费部分），
保存为 Markdown 格式，保留图片、代码块、数学公式等排版。

抓取层基于 Scrapling Fetcher（真实 Chrome TLS 指纹，见 fetch_engine.py），
供 app.py (Web)、csdn_reader.py (命令行)、gui.py (桌面端) 共用。
"""

import os
import re
import json
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString

from fetch_engine import ScraplingFetchEngine


class CsdnArticleReader:
    """CSDN 文章阅读器核心类"""

    def __init__(self):
        self.engine = ScraplingFetchEngine(timeout=15)

    def read_article(self, article_url: str, save_dir: str) -> dict:
        """读取文章并保存，返回结果信息"""
        # CSDN 文库链接走专门的解析逻辑
        if self._is_wenku_url(article_url):
            return self._read_wenku_article(article_url, save_dir)

        article_id = self._extract_article_id(article_url)
        if not article_id:
            return {"success": False, "message": "无法解析文章ID，请检查 URL 格式"}

        # 策略1: Markdown API
        md_content = self._fetch_md_from_api(article_id)
        if md_content:
            title = self._fetch_title(article_url, article_id)
            filepath = self._save_as_markdown(title, md_content, article_id, article_url, save_dir, is_md=True)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        # 策略2: 文章详情 API
        html_content = self._fetch_html_from_api(article_id)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            filepath = self._save_as_markdown(title, md, article_id, article_url, save_dir, is_md=False)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        # 策略3: read.csdn.net
        html_content = self._fetch_from_read_page(article_id)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            filepath = self._save_as_markdown(title, md, article_id, article_url, save_dir, is_md=False)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        # 策略4: 直接抓取页面
        html_content = self._fetch_from_page(article_url)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            filepath = self._save_as_markdown(title, md, article_id, article_url, save_dir, is_md=False)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        return {"success": False, "message": "未能获取到文章内容，可能文章不存在或已被删除/加密"}

    def preview_article(self, article_url: str) -> dict:
        """预览文章内容，不保存文件"""
        # CSDN 文库链接走专门的解析逻辑
        if self._is_wenku_url(article_url):
            doc_id = self._extract_wenku_id(article_url)
            info = self._fetch_wenku_article(article_url)
            if not info or not info["content"]:
                return {"success": False, "message": "未能获取到文库文章内容"}
            if info["is_md"]:
                md = info["content"]
            else:
                md = self._html_to_markdown(info["content"], article_url)
            result = {
                "success": True,
                "title": info["title"] or f"CSDN文库_{doc_id}",
                "content": md,
                "source": "wenku_page",
            }
            if not info["is_full"]:
                result["message"] = self._wenku_partial_hint(info)
            return result

        article_id = self._extract_article_id(article_url)
        if not article_id:
            return {"success": False, "message": "无法解析文章ID"}

        md_content = self._fetch_md_from_api(article_id)
        if md_content:
            title = self._fetch_title(article_url, article_id)
            return {"success": True, "title": title, "content": md_content, "source": "markdown_api"}

        html_content = self._fetch_html_from_api(article_id)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            return {"success": True, "title": title, "content": md, "source": "html_api"}

        html_content = self._fetch_from_read_page(article_id)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            return {"success": True, "title": title, "content": md, "source": "read_page"}

        html_content = self._fetch_from_page(article_url)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            return {"success": True, "title": title, "content": md, "source": "direct_page"}

        return {"success": False, "message": "未能获取到文章内容"}

    def _extract_article_id(self, url: str) -> str | None:
        match = re.search(r"/details/(\d+)", url)
        return match.group(1) if match else None

    def _is_wenku_url(self, url: str) -> bool:
        """判断是否为 CSDN 文库链接 (wenku.csdn.net)"""
        try:
            return urlparse(url).netloc.endswith("wenku.csdn.net")
        except Exception:
            return False

    def _extract_wenku_id(self, url: str) -> str:
        """从文库 URL 路径中提取文档 ID"""
        parts = [p for p in urlparse(url).path.split("/") if p]
        return parts[-1] if parts else "unknown"

    def _fetch_wenku_article(self, article_url: str) -> dict | None:
        """抓取 CSDN 文库页面，返回 {"title", "content", "is_md", "is_full"}

        文库页面有风控，使用 Scrapling Fetcher 模拟真实 Chrome TLS 指纹，
        并带完整浏览器请求头才能拿到 200 响应。
        全文受登录态控制: 登录 VIP 账号后，服务端会在
        __INITIAL_STATE__.pageData.detailInfo.viewContent 中返回完整 Markdown；
        未登录/非 VIP 时该字段只有预览部分 (isShowAll=False)。
        """
        headers = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Referer": "https://wenku.csdn.net/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        page = self.engine.get(article_url, headers=headers)
        if page is None or page.status != 200:
            return None
        html = self.engine.get_text(page)

        # 优先解析 SSR 状态数据 (viewContent 已是 Markdown 格式)
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*)", html, re.S)
        if m:
            try:
                state, _ = json.JSONDecoder().raw_decode(m.group(1))
                page_data = state.get("pageData", {}) or {}
                detail = page_data.get("detailInfo", {}) or {}
                user_info = page_data.get("curUserInfo", {}) or {}
                content = detail.get("viewContent") or ""
                if len(content) > 100:
                    return {
                        "title": detail.get("title"),
                        "content": content,
                        "is_md": True,
                        "is_full": bool(detail.get("isShowAll")),
                        "is_vip": bool(user_info.get("isVip")),
                        "login_user": user_info.get("userName") or "",
                    }
            except Exception:
                pass

        # 兜底: 从 DOM 中提取正文 HTML
        soup = BeautifulSoup(html, "html.parser")

        title = None
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True).replace("- CSDN文库", "").strip()

        selectors = [
            "div#copyRef.content-view",
            "div.markdown_views",
            "div.htmledit_views",
            "div.article-box div.cont",
            "div#chatgpt-article-detail",
        ]
        for sel in selectors:
            div = soup.select_one(sel)
            if div and len(div.get_text(strip=True)) > 100:
                return {"title": title, "content": str(div), "is_md": False, "is_full": False}
        return None

    def _read_wenku_article(self, article_url: str, save_dir: str) -> dict:
        """读取 CSDN 文库文章并保存"""
        doc_id = self._extract_wenku_id(article_url)
        info = self._fetch_wenku_article(article_url)
        if not info or not info["content"]:
            return {"success": False, "message": "未能获取到文库文章内容，可能文档不存在、需要会员权限或被风控拦截"}

        title = info["title"] or f"CSDN文库_{doc_id}"
        if info["is_md"]:
            md = info["content"]
        else:
            md = self._html_to_markdown(info["content"], article_url)
        filepath = self._save_as_markdown(title, md, doc_id, article_url, save_dir, is_md=info["is_md"])

        message = "文章获取成功"
        if not info["is_full"]:
            message += f"（{self._wenku_partial_hint(info)}）"
        return {"success": True, "message": message, "filepath": filepath, "title": title}

    def _wenku_partial_hint(self, info: dict) -> str:
        """文库仅返回预览部分时，根据登录态给出针对性提示"""
        login_user = info.get("login_user", "")
        if login_user:
            if info.get("is_vip"):
                return f"Cookie 已识别为用户 {login_user}，但未返回全文，该账号可能无此文档权限"
            return f"Cookie 已识别为用户 {login_user}，但该账号不是 VIP，无法获取全文"
        if self.engine.cookie:
            return "仅预览部分；Cookie 已发送但未被识别，可能已过期，请重新从浏览器复制完整 Cookie"
        return "仅预览部分；完整全文需登录 VIP 账号（将 Cookie 保存到程序同目录 cookie.txt 或设置环境变量 CSDN_COOKIE）"

    def _fetch_md_from_api(self, article_id: str) -> str | None:
        """通过 CSDN 编辑器 API 获取 Markdown 源码"""
        api_url = f"https://blog-console-api.csdn.net/v1/editor/getArticle?id={article_id}"
        page = self.engine.get(api_url, headers={"Accept": "application/json, text/plain, */*"})
        if page is None or page.status != 200:
            return None
        try:
            data = page.json()
        except Exception:
            return None
        md = (data.get("data") or {}).get("markdowncontent")
        if md and md != "null":
            return md
        return None

    def _fetch_html_from_api(self, article_id: str) -> str | None:
        """通过 CSDN 文章详情 API 获取 HTML"""
        api_url = f"https://blog.csdn.net/phoenix/web/v1/article?id={article_id}"
        page = self.engine.get(api_url, headers={"Accept": "application/json, text/plain, */*"})
        if page is None or page.status != 200:
            return None
        try:
            data = page.json()
        except Exception:
            return None
        content = (data.get("data") or {}).get("content")
        if content:
            return content
        return None

    def _fetch_from_read_page(self, article_id: str) -> str | None:
        """通过 read.csdn.net 阅读模式获取 HTML"""
        read_url = f"https://read.csdn.net/article/details/{article_id}"
        page = self.engine.get(read_url)
        if page is None or page.status != 200:
            return None
        soup = BeautifulSoup(self.engine.get_text(page), "html.parser")
        content_div = soup.select_one("div.article_content") or soup.select_one("div#content_views")
        if content_div:
            return str(content_div)
        return None

    def _fetch_from_page(self, article_url: str) -> str | None:
        """直接抓取文章页面 HTML"""
        page = self.engine.get(article_url)
        if page is None or page.status != 200:
            return None
        soup = BeautifulSoup(self.engine.get_text(page), "html.parser")
        selectors = ["div.article_content", "div#content_views", "article.article"]
        for sel in selectors:
            div = soup.select_one(sel)
            if div:
                return str(div)
        return None

    def _fetch_title(self, article_url: str, article_id: str) -> str:
        """获取文章标题"""
        page = self.engine.get(article_url)
        if page is not None and page.status == 200:
            soup = BeautifulSoup(self.engine.get_text(page), "html.parser")
            h1 = soup.select_one("h1.title-article")
            if h1:
                return h1.get_text(strip=True)
            title_tag = soup.find("title")
            if title_tag:
                return title_tag.get_text(strip=True).replace("_CSDN博客", "").strip()
        return f"CSDN文章_{article_id}"

    def _save_as_markdown(self, title: str, content: str, article_id: str, article_url: str, save_dir: str, is_md: bool) -> str:
        """保存为 Markdown 文件，返回文件绝对路径"""
        os.makedirs(save_dir, exist_ok=True)
        safe_title = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "_", title)[:50]
        filename = f"{safe_title}_{article_id}.md"
        filepath = os.path.join(save_dir, filename)

        content = re.sub(r"\n{3,}", "\n\n", content)

        md_lines = [
            f"# {title}",
            "",
            f"> 原文链接: [{article_url}]({article_url})",
            f"> 文章ID: {article_id}",
            "",
            "---",
            "",
            content.strip(),
            "",
        ]

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return os.path.abspath(filepath)

    def _html_to_markdown(self, html_content: str, base_url: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        return self._convert_element_to_md(soup, base_url)

    def _convert_element_to_md(self, element, base_url: str) -> str:
        if isinstance(element, NavigableString):
            return str(element)

        parts = []
        tag_name = element.name
        if tag_name is None:
            return ""

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            prefix = "#" * level + " "
            inner = self._concat_children(element, base_url)
            parts.append(f"\n{prefix}{inner.strip()}\n")
        elif tag_name == "p":
            inner = self._concat_children(element, base_url)
            parts.append(f"\n{inner}\n")
        elif tag_name in ("br",):
            parts.append("\n")
        elif tag_name == "img":
            src = element.get("src", "")
            alt = element.get("alt", "")
            if src and not src.startswith(("http://", "https://", "data:")):
                src = urljoin(base_url, src)
            parts.append(f"\n![{alt}]({src})\n")
        elif tag_name == "a":
            href = element.get("href", "")
            inner = self._concat_children(element, base_url)
            if href:
                if not href.startswith(("http://", "https://")):
                    href = urljoin(base_url, href)
                parts.append(f"[{inner}]({href})")
            else:
                parts.append(inner)
        elif tag_name in ("strong", "b"):
            inner = self._concat_children(element, base_url)
            parts.append(f"**{inner.strip()}**")
        elif tag_name in ("em", "i"):
            inner = self._concat_children(element, base_url)
            parts.append(f"*{inner.strip()}*")
        elif tag_name == "code":
            inner = self._concat_children(element, base_url)
            parts.append(f"`{inner}`")
        elif tag_name == "pre":
            code = element.find("code")
            if code:
                lang = ""
                classes = code.get("class", [])
                for cls in classes:
                    if cls.startswith("language-"):
                        lang = cls.replace("language-", "")
                        break
                inner = code.get_text()
                parts.append(f"\n```{lang}\n{inner}\n```\n")
            else:
                inner = element.get_text()
                parts.append(f"\n```\n{inner}\n```\n")
        elif tag_name in ("ul", "ol"):
            is_ordered = tag_name == "ol"
            start = int(element.get("start", 1))
            for idx, li in enumerate(element.find_all("li", recursive=False)):
                inner = self._concat_children(li, base_url)
                if is_ordered:
                    parts.append(f"{start + idx}. {inner.strip()}\n")
                else:
                    parts.append(f"- {inner.strip()}\n")
            parts.append("\n")
        elif tag_name == "blockquote":
            inner = self._concat_children(element, base_url)
            lines = inner.strip().split("\n")
            quoted = "\n".join(f"> {line}" for line in lines if line.strip())
            parts.append(f"\n{quoted}\n")
        elif tag_name == "table":
            parts.append(self._convert_table_to_md(element, base_url))
        elif tag_name in ("div", "span", "section", "article"):
            for child in element.children:
                parts.append(self._convert_element_to_md(child, base_url))
        elif tag_name in ("script", "style", "noscript", "iframe", "svg"):
            pass
        else:
            for child in element.children:
                parts.append(self._convert_element_to_md(child, base_url))

        return "".join(parts)

    def _concat_children(self, element, base_url: str) -> str:
        result = []
        for child in element.children:
            result.append(self._convert_element_to_md(child, base_url))
        return "".join(result)

    def _convert_table_to_md(self, table, base_url: str) -> str:
        rows = []
        headers = []
        thead = table.find("thead")
        if thead:
            for th in thead.find_all("th"):
                headers.append(self._concat_children(th, base_url).strip() or " ")
        tbody = table.find("tbody") or table
        for tr in tbody.find_all("tr"):
            row = []
            for td in tr.find_all(("td", "th")):
                row.append(self._concat_children(td, base_url).strip() or " ")
            if row:
                rows.append(row)
        if not rows:
            return ""
        if not headers and rows:
            headers = rows[0]
            rows = rows[1:]
        if not headers:
            return ""
        md_lines = []
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            while len(row) < len(headers):
                row.append(" ")
            md_lines.append("| " + " | ".join(row[:len(headers)]) + " |")
        return "\n" + "\n".join(md_lines) + "\n"
