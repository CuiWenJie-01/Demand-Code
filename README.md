# Demand-Code

本仓库收录了工作、学习和个人需求开发的各种工具程序与项目代码。

## 项目概览

| 项目名称 | 说明 | 技术栈 |
|---------|------|--------|
| [教辅](教辅/) | 教辅图书数据处理工具集，面向 LLM 训练数据的预处理、质检与格式化流水线 | Python |
| [EasyImages2.0-master](EasyImages2.0-master/) | 开源图床程序，支持多文件上传、无数据库部署 | PHP |
| [ChemicalApi](ChemicalApi/) | 化学品信息管理系统，支持查询、二维码生成与图片管理 | Java/Spring Boot |
| [csdn_downloader](csdn_downloader/) | CSDN 付费文章阅读器，支持多策略获取完整内容并保存为 Markdown | Python |

## 项目详情

### 教辅数据处理工具集

用于教辅图书数字化处理的 Python 工具链，涵盖 OCR 提单、QA 提取、数据过滤、质检上平台等完整工作流。

- **核心能力**: 图片 OCR 工单生成、问答对提取、学科规则过滤、数据去重优化
- **适用场景**: 大模型训练语料预处理、教辅内容结构化
- **详见**: [教辅/README.md](教辅/README.md)

### EasyImage 2.0 简单图床

一款基于 PHP 开发的开源图床，无需数据库即可部署，支持多格式链接输出与图片处理。

- **核心能力**: 多文件上传、水印/压缩/缩略图、API 接口、管理后台
- **适用场景**: 个人图床、临时图片托管、Markdown 写作配图
- **详见**: [EasyImages2.0-master/README.md](EasyImages2.0-master/README.md)

### ChemicalApi 化学品信息管理系统

基于 Spring Boot + Vue3 的化学品信息查询与管理系统，提供化学品数据的增删改查、分页展示、二维码生成等功能。

- **核心能力**: CAS 号/名称搜索、分页展示、二维码生成、分子结构图管理
- **适用场景**: 实验室化学品库存管理、化学品信息查询
- **详见**: [ChemicalApi/README.md](ChemicalApi/README.md)

### csdn_downloader CSDN 付费文章阅读器

支持通过多种接口获取 CSDN 文章完整内容（包括付费部分），并保存为 Markdown 格式。提供 PyQt6 桌面客户端、Flask Web 版和命令行版三种使用方式。

- **核心能力**: 多策略获取文章（Markdown API、文章详情 API、read 模式、页面抓取）、HTML 转 Markdown、代码块与图片保留
- **适用场景**: CSDN 文章离线阅读、付费内容获取、知识整理归档
- **详见**: [csdn_downloader/README.md](csdn_downloader/README.md)

## 仓库说明

- 部分项目包含大量原始数据文件（如教辅图片），已通过 `.gitignore` 排除，避免仓库体积过大
- 各子项目均有独立的 README 和 `.gitignore` 配置
- 代码按项目分类存放，方便独立维护与使用
