# CSDN 付费文章阅读器

支持通过多种策略获取 CSDN 文章完整内容（包括付费部分），并保存为 Markdown 格式，保留图片、代码块、表格等排版。

## 功能特性

- **多策略获取**：自动尝试 4 种获取策略，确保最大程度获取文章内容
  1. Markdown API（优先）— 直接获取文章 Markdown 源码
  2. 文章详情 API — 获取 HTML 内容并转换
  3. read.csdn.net — 通过阅读模式获取
  4. 直接页面抓取 — 兜底策略
- **多客户端支持**：提供命令行、Web 网页、PyQt6 桌面客户端三种使用方式
- **多语言实现**：Python 版本 + Java/Spring Boot 版本
- **内容转换**：HTML 转 Markdown，保留代码块高亮、图片链接、表格、引用等格式
- **智能保存**：自动清理文件名，保存为 `.md` 文件，可用 VS Code / Typora 打开

## 项目结构

```
csdn_downloader/
├── app.py                          # Flask Web 服务端
├── csdn_reader.py                  # Python 命令行版本
├── gui.py                          # PyQt6 桌面客户端
├── requirements.txt                # Python 依赖
├── pom.xml                         # Java Maven 配置
├── templates/
│   └── index.html                  # Web 前端页面
└── src/com/csdndownload/
    ├── DownloadApplication.java    # Java Spring Boot 入口
    ├── service/
    │   ├── CsdnArticleService.java
    │   └── impl/CsdnArticleServiceImpl.java
    └── utils/                      # 工具类
```

## 安装依赖

### Python 版本

```bash
pip install -r requirements.txt
```

依赖：
- `requests` — HTTP 请求
- `beautifulsoup4` — HTML 解析
- `flask` — Web 服务端
- `PyQt6` — 桌面 GUI

### Java 版本

```bash
mvn clean install
```

## 使用方法

### 1. 命令行版本（Python）

```bash
python csdn_reader.py
```

输入 CSDN 文章 URL，程序自动获取并保存为 Markdown 文件。

### 2. Web 版本

```bash
python app.py
```

打开浏览器访问 `http://localhost:5000`，支持文章预览和下载保存。

### 3. 桌面客户端（PyQt6）

```bash
python gui.py
```

提供图形化界面，支持文件夹选择、文章预览、下载保存。

### 4. Java 命令行版本

```bash
mvn spring-boot:run
```

### 支持的 URL 格式

```
https://blog.csdn.net/用户名/article/details/文章ID
```

## 技术实现

### 多策略降级机制

程序按优先级依次尝试以下策略，任一成功即返回：

| 策略 | 说明 | 优势 |
|------|------|------|
| Markdown API | 调用 CSDN 编辑器 API | 直接获取 MD 源码，格式最完整 |
| 文章详情 API | 调用文章详情接口 | 获取 HTML 内容，信息较全 |
| 阅读模式 | 访问 read.csdn.net | 针对付费文章的阅读页面 |
| 页面抓取 | 直接请求文章页面 | 兜底策略，兼容性好 |

### HTML 转 Markdown

- 递归遍历 DOM 树，将 HTML 元素映射为 Markdown 语法
- 支持：标题、段落、代码块、表格、列表、引用、图片、链接、粗体/斜体
- 自动补全相对路径为绝对路径

## 免责声明

本项目仅供学习和技术研究使用，请勿用于侵犯他人权益或违反 CSDN 平台规则。获取的文章内容请遵守原作者的版权协议。

## License

MIT
