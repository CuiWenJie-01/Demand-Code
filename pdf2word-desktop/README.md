# PDF2Word Desktop

本仓库实现 [PROJECT_PLAN.md](PROJECT_PLAN.md) 中的 PDF2Word Desktop 开发基线。

当前阶段是 M1 后段的“版式收敛与回归基准建立”：可运行的本地转换引擎已经具备 PDF 预检、分类、OCR 页渲染、SQLite 检查点、定位式可编辑 DOCX 与 JSON Lines worker；M2 桌面应用尚未开始交付。

针对文字转轮廓和扫描 PDF，项目已完成 PP-StructureV3 的真实样页版面/OCR 到 `PageModel` 的适配，并接入定位式可编辑 Word renderer：正文、选项和解析按行级 OCR 坐标写入可编辑文本框；页眉、装饰标签、图表、公式等复杂区域按块裁图回退。OCR 输出同时生成不含题目正文的质量报告。大文件整本质量验证仍在继续。

第 10 页最终单页 DOCX 是首个黄金视觉回归样页。其规则以 `cn_exam_question_v1` 版式档案固化：题号仅加粗、题干/解析右边界对齐、答案独立可编辑、右侧栏和页码色条可编辑且不跨页。可用下列命令在 Office 兼容渲染器上运行完整门禁：

```powershell
pdf2word-engine visual-regression ".\runtime\qa-page10-final-one-page\page-model.json" `
  ".\runtime\qa-page10-final-one-page\第10页-全部修复且不分页.docx"
```

固定代表页集位于 `tests/fixtures/representative_pages.json`，当前选择 12 页，覆盖封面、普通题目、公式、表格、图表、水印、几何图和末页。第 10、40、80、120、160、200、300 页已建立可执行基线；第 160 页覆盖浅灰中央水印与可编辑正文的叠放，第 200 页覆盖谈徽标图形保真、标签和星级可编辑、题干括号对齐及低置信度竖排侧栏回退。其余页面会显示为 `pending`，直至建立工件。使用 `--strict` 可作为 M1 退出门禁：

```powershell
pdf2word-engine representative-regression ".\tests\fixtures\representative_pages.json" `
  --renderer "D:\software\LibreOffice\program\soffice.com"
```

严格回归之后，以相同 PageModel 重新生成 DOCX 并对比已批准视觉快照；加上 `--require-cer` 会要求每页都已由人工确认，不能将 OCR 文本自身作为参照：

```powershell
pdf2word-engine representative-quality-gate ".\tests\fixtures\representative_pages.json" `
  --renderer "D:\software\LibreOffice\program\soffice.com" --require-cer
```

CER 是研发验收和基准扩充工具，不会进入正常 PDF 转换流程。桌面端的“CER 代表页审校”已接入同一套基准库：选择代表页清单和源 PDF，应用会显示 12 页进度、原图、预填 OCR 及差异高亮；一次整页确认后由 sidecar 直接原子写入清单登记的 `cer_annotations/page-xxxx.json`，无需浏览器下载或手动替换。以后只补充异常页或新页面类型时，扩充清单后选择该页即可。

命令行 `cer-review` 仍保留给 CI/离线排查使用：

```powershell
pdf2word-engine cer-review ".\tests\fixtures\representative_pages.json" `
  --source-pdf "D:\work\31.半月谈行测1000题下.pdf" `
  --output-dir ".\runtime\cer-review"
```

最终 Windows 验收应在安装了 Microsoft Word 与 `pywin32` 的机器运行：

```powershell
pdf2word-engine word-render-regression .\runtime\qa-page10-final-one-page\page-model-源PDF对照修复-v3.json `
  .\runtime\qa-page10-final-one-page\第10页-源PDF对照修复-v3.docx `
  --output-pdf .\runtime\word-render\page-0010.pdf
```

对整个代表页集运行 Microsoft Word 实机分页验证：

```powershell
pdf2word-engine representative-word-regression .\tests\fixtures\representative_pages.json `
  --output-dir .\runtime\word-render\representative-pages
```

## 快速开始

使用 Python 3.11 或更高版本安装项目：

```powershell
python -m pip install -e .
```

只读预检：

```powershell
pdf2word-engine preflight "D:\\work\\31.半月谈行测1000题下.pdf"
```

生成可编辑 DOCX：

```powershell
pdf2word-engine convert "D:\\work\\31.半月谈行测1000题下.pdf" `
  --output-dir ".\\outputs" `
  --dpi 200
```

在未安装 OCR 模型的环境中，转换仅支持有可靠文字层的 PDF。对于扫描件和文字转轮廓的 PDF，程序会明确报告需要 OCR 引擎，避免输出伪造的可编辑文本。

## 目录

```text
src/pdf2word_engine/  Python 引擎与 sidecar 协议
tests/                自动测试
PROJECT_PLAN.md       产品与架构基线
```

## 状态

- [x] M0 子阶段：预检、OCR 页渲染、381 页大文件资源验证
- [x] M1 子阶段：任务工作区、SQLite 页面检查点、断点恢复入口和 CLI 基础
- [x] PaddleOCR PP-StructureV3 PageModel JSON 适配（含行级可编辑正文重建）
- [x] PageModel 定位式可编辑 Word renderer（第 10 页真实样例通过 LibreOffice 渲染验证）
- [x] `cn_exam_question_v1` 通用题目页规则与第 10 页结构/分页视觉回归门禁
- [ ] 代表页集的 OCR 准确率、表格/公式与多页回归验证
- [x] Tauri Windows 桌面端前端与 Rust 源码骨架（Cargo 构建受本机策略阻塞）
- [ ] NSIS 安装包与离线模型包
