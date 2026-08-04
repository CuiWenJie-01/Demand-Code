#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSDN 付费文章阅读器 - PyQt6 桌面客户端
支持系统文件夹选择器、文章预览、Markdown 保存
"""

import os
import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
    QMessageBox, QProgressBar, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from reader import CsdnArticleReader


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
