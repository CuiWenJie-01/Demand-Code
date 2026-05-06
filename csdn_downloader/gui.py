#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSDN 付费文章阅读器 - PyQt6 桌面客户端
支持系统文件夹选择器、文章预览、Markdown 保存
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QMessageBox, QProgressBar, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
import requests
from bs4 import BeautifulSoup, NavigableString


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

    def read_article(self, article_url: str, save_dir: str) -> dict:
        article_id = self._extract_article_id(article_url)
        if not article_id:
            return {"success": False, "message": "无法解析文章ID，请检查 URL 格式"}

        md_content = self._fetch_md_from_api(article_id)
        if md_content:
            title = self._fetch_title(article_url, article_id)
            filepath = self._save_as_markdown(title, md_content, article_id, article_url, save_dir, is_md=True)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        html_content = self._fetch_html_from_api(article_id)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            filepath = self._save_as_markdown(title, md, article_id, article_url, save_dir, is_md=False)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        html_content = self._fetch_from_read_page(article_id)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            filepath = self._save_as_markdown(title, md, article_id, article_url, save_dir, is_md=False)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        html_content = self._fetch_from_page(article_url)
        if html_content:
            title = self._fetch_title(article_url, article_id)
            md = self._html_to_markdown(html_content, article_url)
            filepath = self._save_as_markdown(title, md, article_id, article_url, save_dir, is_md=False)
            return {"success": True, "message": "文章获取成功", "filepath": filepath, "title": title}

        return {"success": False, "message": "未能获取到文章内容，可能文章不存在或已被删除/加密"}

    def preview_article(self, article_url: str) -> dict:
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


class WorkerThread(QThread):
    """后台工作线程，避免阻塞 UI"""
    finished = pyqtSignal(dict)

    def __init__(self, reader: CsdnArticleReader, url: str, save_dir: str = "", mode: str = "download"):
        super().__init__()
        self.reader = reader
        self.url = url
        self.save_dir = save_dir
        self.mode = mode

    def run(self):
        try:
            if self.mode == "preview":
                result = self.reader.preview_article(self.url)
            else:
                result = self.reader.read_article(self.url, self.save_dir)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({"success": False, "message": str(e)})


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.reader = CsdnArticleReader()
        self.worker = None
        self.default_save_dir = os.path.join(os.path.expanduser("~"), "Downloads", "CSDN_Articles")
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("CSDN 付费文章阅读器")
        self.setMinimumSize(900, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title_label = QLabel("CSDN 付费文章阅读器")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        subtitle = QLabel("输入文章 URL，一键获取完整内容并保存为 Markdown")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 10px;")
        main_layout.addWidget(subtitle)

        # 输入区域
        input_group = QGroupBox("文章信息")
        input_layout = QVBoxLayout(input_group)

        # URL 输入
        url_layout = QHBoxLayout()
        url_label = QLabel("文章链接:")
        url_label.setFixedWidth(70)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://blog.csdn.net/用户名/article/details/文章ID")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        input_layout.addLayout(url_layout)

        # 保存路径
        path_layout = QHBoxLayout()
        path_label = QLabel("保存路径:")
        path_label.setFixedWidth(70)
        self.path_input = QLineEdit()
        self.path_input.setText(self.default_save_dir)
        self.path_input.setReadOnly(True)
        self.path_btn = QPushButton("选择文件夹")
        self.path_btn.setFixedWidth(100)
        self.path_btn.clicked.connect(self.select_folder)
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.path_btn)
        input_layout.addLayout(path_layout)

        main_layout.addWidget(input_group)

        # 按钮区域
        btn_layout = QHBoxLayout()
        self.preview_btn = QPushButton("预览文章")
        self.preview_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #5a6fd6, stop:1 #6a4190); }
            QPushButton:disabled { background: #ccc; }
        """)
        self.preview_btn.clicked.connect(self.preview_article)

        self.download_btn = QPushButton("下载保存")
        self.download_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #11998e, stop:1 #38ef7d);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0d8579, stop:1 #2dd46a); }
            QPushButton:disabled { background: #ccc; }
        """)
        self.download_btn.clicked.connect(self.download_article)

        btn_layout.addWidget(self.preview_btn)
        btn_layout.addWidget(self.download_btn)
        main_layout.addLayout(btn_layout)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximum(0)
        self.progress.setMinimum(0)
        self.progress.hide()
        main_layout.addWidget(self.progress)

        # 状态标签
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #666; font-size: 13px;")
        main_layout.addWidget(self.status_label)

        # 预览区域
        preview_group = QGroupBox("文章预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("点击「预览文章」按钮，在此处查看文章内容...")
        preview_font = QFont("Microsoft YaHei", 11)
        self.preview_text.setFont(preview_font)
        preview_layout.addWidget(self.preview_text)
        main_layout.addWidget(preview_group)

        # 提示信息
        tips = QLabel(
            "使用提示: 1) 支持 CSDN 文章链接格式  2) 程序会自动尝试多种方式获取付费内容  "
            "3) 保存为 Markdown 格式，可用 VS Code / Typora 打开  4) 图片链接会保留，联网时可正常显示"
        )
        tips.setWordWrap(True)
        tips.setStyleSheet("color: #999; font-size: 12px; padding: 8px; background: #f5f5f5; border-radius: 6px;")
        main_layout.addWidget(tips)

        main_layout.setStretchFactor(preview_group, 1)

    def select_folder(self):
        """弹出系统文件夹选择器"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择保存文件夹",
            self.path_input.text() or self.default_save_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self.path_input.setText(folder)

    def set_buttons_enabled(self, enabled: bool):
        self.preview_btn.setEnabled(enabled)
        self.download_btn.setEnabled(enabled)

    def preview_article(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入文章 URL")
            return

        self.set_buttons_enabled(False)
        self.progress.show()
        self.status_label.setText("正在获取文章，请稍候...")
        self.preview_text.clear()

        self.worker = WorkerThread(self.reader, url, mode="preview")
        self.worker.finished.connect(self.on_preview_finished)
        self.worker.start()

    def on_preview_finished(self, result: dict):
        self.progress.hide()
        self.set_buttons_enabled(True)

        if result.get("success"):
            self.status_label.setText(f"预览成功 | 来源: {result.get('source', 'unknown')}")
            self.preview_text.setPlainText(result.get("content", ""))
        else:
            self.status_label.setText(f"预览失败: {result.get('message', '')}")
            QMessageBox.critical(self, "错误", result.get("message", "未知错误"))

    def download_article(self):
        url = self.url_input.text().strip()
        save_dir = self.path_input.text().strip()

        if not url:
            QMessageBox.warning(self, "提示", "请输入文章 URL")
            return

        self.set_buttons_enabled(False)
        self.progress.show()
        self.status_label.setText("正在下载文章，请稍候...")

        self.worker = WorkerThread(self.reader, url, save_dir=save_dir, mode="download")
        self.worker.finished.connect(self.on_download_finished)
        self.worker.start()

    def on_download_finished(self, result: dict):
        self.progress.hide()
        self.set_buttons_enabled(True)

        if result.get("success"):
            self.status_label.setText(f"下载成功 | 保存至: {result.get('filepath', '')}")
            QMessageBox.information(
                self, "成功",
                f"文章已保存:\n{result.get('filepath', '')}"
            )
        else:
            self.status_label.setText(f"下载失败: {result.get('message', '')}")
            QMessageBox.critical(self, "错误", result.get("message", "未知错误"))


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()