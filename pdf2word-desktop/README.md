# PDF2Word Desktop

本仓库实现 [PROJECT_PLAN.md](PROJECT_PLAN.md) 中的 PDF2Word Desktop 开发基线。

当前阶段是 M0/M1：可运行的本地转换引擎，包含 PDF 预检、分类、分页渲染、SQLite 检查点、保真版 DOCX 导出、基础文字 PDF 可编辑导出，以及可供 Tauri 调用的 JSON Lines worker。

针对文字转轮廓和扫描 PDF，项目已完成 PP-StructureV3 的真实样页版面/OCR 到 `PageModel` 的适配验证；高保真可编辑 Word 的绝对定位 renderer 仍在实现，当前不会把 OCR 结果伪装为最终可编辑成品。

## 快速开始

使用 Python 3.11 或更高版本安装项目：

```powershell
python -m pip install -e .
```

只读预检：

```powershell
pdf2word-engine preflight "D:\\work\\31.半月谈行测1000题下.pdf"
```

生成保真版 DOCX：

```powershell
pdf2word-engine convert "D:\\work\\31.半月谈行测1000题下.pdf" `
  --output-dir ".\\outputs" `
  --mode visual `
  --dpi 200
```

在目前未安装 OCR 模型的环境中，`editable` 模式仅支持有可靠文字层的 PDF。对于扫描件和文字转轮廓的 PDF，程序会明确报告需要安装 OCR 引擎，避免输出伪造的可编辑文本。

## 目录

```text
src/pdf2word_engine/  Python 引擎与 sidecar 协议
tests/                自动测试
PROJECT_PLAN.md       产品与架构基线
```

## 状态

- [x] M0 子阶段：预检、渲染、381 页保真 DOCX 技术验证
- [x] M1 子阶段：任务工作区、SQLite 页面检查点、断点恢复入口和 CLI 基础
- [x] PaddleOCR PP-StructureV3 PageModel JSON 适配（真实样页识别与可编辑 Word renderer 仍在验证）
- [ ] 高保真可编辑 Word renderer
- [x] Tauri Windows 桌面端前端与 Rust 源码骨架（Cargo 构建受本机策略阻塞）
- [ ] NSIS 安装包与离线模型包
