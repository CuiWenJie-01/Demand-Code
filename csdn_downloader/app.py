#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSDN 付费文章阅读器 - Web 版
Flask 后端 + 前端页面
"""

import os
import tkinter as tk
from tkinter import filedialog

from flask import Flask, render_template, request, jsonify

from reader import CsdnArticleReader

app = Flask(__name__)

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
