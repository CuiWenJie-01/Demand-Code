#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSDN 付费文章阅读器 - Web 版
Flask 后端 + 前端页面
"""

import os
import re
import json
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from urllib.parse import urljoin, urlparse
from threading import Thread

from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup, NavigableString

app = Flask(__name__)


class CsdnArticleReader:
    """CSDN 文章阅读器核心类"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.timeout = 15
        self._load_cookie()

    def _load_cookie(self):
        """加载 CSDN 登录 Cookie，用于获取付费全文

        优先级: 环境变量 CSDN_COOKIE > 程序同目录 cookie.txt
        """
        cookie = os.environ.get("CSDN_COOKIE", "").strip()
        if not cookie:
            cookie_file = Path(__file__).resolve().with_name("cookie.txt")
            if cookie_file.exists():
                cookie = cookie_file.read_text(encoding="utf-8").strip()
        if cookie:
            self.session.headers["Cookie"] = cookie

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
                result["message"] = "仅预览部分；完整全文需登录 VIP 账号（cookie.txt 或环境变量 CSDN_COOKIE）"
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

        文库页面有风控，需要带完整浏览器请求头才能拿到 200 响应。
        全文受登录态控制: 登录 VIP 账号后，服务端会在
        __INITIAL_STATE__.pageData.detailInfo.viewContent 中返回完整 Markdown；
        未登录/非 VIP 时该字段只有预览部分 (isShowAll=False)。
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/139.0.0.0 Safari/537.36"
            ),
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
        try:
            resp = self.session.get(article_url, timeout=self.timeout, headers=headers)
            if resp.status_code != 200:
                return None
            html = resp.text

            # 优先解析 SSR 状态数据 (viewContent 已是 Markdown 格式)
            m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*)", html, re.S)
            if m:
                try:
                    state, _ = json.JSONDecoder().raw_decode(m.group(1))
                    detail = state.get("pageData", {}).get("detailInfo", {}) or {}
                    content = detail.get("viewContent") or ""
                    if len(content) > 100:
                        return {
                            "title": detail.get("title"),
                            "content": content,
                            "is_md": True,
                            "is_full": bool(detail.get("isShowAll")),
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
        except Exception:
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
            message += "（仅预览部分；完整全文需登录 VIP 账号，将 Cookie 保存到程序同目录 cookie.txt 或设置环境变量 CSDN_COOKIE）"
        return {"success": True, "message": message, "filepath": filepath, "title": title}

    def _fetch_md_from_api(self, article_id: str) -> str | None:
        api_url = f"https://blog-console-api.csdn.net/v1/editor/getArticle?id={article_id}"
        try:
            resp = self.session.get(api_url, timeout=self.timeout)
            data = resp.json()
            if data.get("data", {}).get("markdowncontent"):
                md = data["data"]["markdowncontent"]
                if md and md != "null":
                    return md
        except Exception:
            pass
        return None

    def _fetch_html_from_api(self, article_id: str) -> str | None:
        api_url = f"https://blog.csdn.net/phoenix/web/v1/article?id={article_id}"
        try:
            resp = self.session.get(api_url, timeout=self.timeout)
            data = resp.json()
            if data.get("data", {}).get("content"):
                return data["data"]["content"]
        except Exception:
            pass
        return None

    def _fetch_from_read_page(self, article_id: str) -> str | None:
        read_url = f"https://read.csdn.net/article/details/{article_id}"
        try:
            resp = self.session.get(read_url, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, "html.parser")
            content_div = soup.select_one("div.article_content") or soup.select_one("div#content_views")
            if content_div:
                return str(content_div)
        except Exception:
            pass
        return None

    def _fetch_from_page(self, article_url: str) -> str | None:
        try:
            resp = self.session.get(article_url, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, "html.parser")
            selectors = ["div.article_content", "div#content_views", "article.article"]
            for sel in selectors:
                div = soup.select_one(sel)
                if div:
                    return str(div)
        except Exception:
            pass
        return None

    def _fetch_title(self, article_url: str, article_id: str) -> str:
        try:
            resp = self.session.get(article_url, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, "html.parser")
            h1 = soup.select_one("h1.title-article")
            if h1:
                return h1.get_text(strip=True)
            title_tag = soup.find("title")
            if title_tag:
                return title_tag.get_text(strip=True).replace("_CSDN博客", "").strip()
        except Exception:
            pass
        return f"CSDN文章_{article_id}"

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


reader = CsdnArticleReader()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    save_dir = data.get("save_dir", "").strip()

    if not url:
        return jsonify({"success": False, "message": "请输入文章 URL"})

    if not save_dir:
        save_dir = os.path.join(os.path.expanduser("~"), "Downloads", "CSDN_Articles")

    # 处理 Windows 路径
    save_dir = os.path.normpath(save_dir)

    try:
        result = reader.read_article(url, save_dir)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"处理失败: {str(e)}"})


@app.route("/api/preview", methods=["POST"])
def api_preview():
    data = request.get_json() or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"success": False, "message": "请输入文章 URL"})

    try:
        result = reader.preview_article(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"预览失败: {str(e)}"})


@app.route("/api/select_folder", methods=["GET"])
def api_select_folder():
    """弹出系统文件夹选择器，返回选中的路径"""
    selected_path = {"path": ""}

    def open_dialog():
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="选择保存文件夹")
        root.destroy()
        if folder:
            selected_path["path"] = os.path.normpath(folder)

    # 在主线程中运行 tkinter 对话框
    open_dialog()
    return jsonify({"success": bool(selected_path["path"]), "path": selected_path["path"]})


@app.route("/api/default_path", methods=["GET"])
def api_default_path():
    """获取默认保存路径"""
    default = os.path.join(os.path.expanduser("~"), "Downloads", "CSDN_Articles")
    return jsonify({"path": os.path.normpath(default)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
