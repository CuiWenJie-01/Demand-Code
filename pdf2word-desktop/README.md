# PDF2Word Desktop

本仓库正在实现“源文档驱动、准确优先、正文可编辑”的复杂中文 PDF 转 Word 管线。当前基准源文档为 `D:\work\31.半月谈行测1000题下.pdf`，详细约束见：

- `PROJECT_PLAN.md`：产品、架构与里程碑总方案；
- `docs/SOURCE_FIRST_EDITABLE_HYBRID_REBUILD.md`：本书专项实施基线；
- `docs/M1_QUALITY_GATES.md`：当前质量门禁。

当前有效链路从源 PDF 和空任务目录开始，优先使用 GPU 重新渲染、清理水印并 OCR；普通正文写为原生 Word 段落，复杂公式、Logo、艺术字和不可靠局部使用无水印源图截图。历史 12 页 PageModel/CER/视觉金标及缓存重建入口已经移除，不能再把人工修好的中间结果当作端到端输入。

## 当前状态

- 物理页 7、8、9、10、21、23 的第二轮 6 页 source-first 候选样本已通过自动静态检查和 LibreOffice 完整渲染目检；
- 候选样本运行在 GPU，普通正文使用原生 Word 段落，整页截图为 0；
- 381 页正式 source-first 转换入口尚未实现，因此旧 `convert` 命令和桌面端“开始转换”入口不对外开放；
- 旧任务目录和过期输出不作为代码、测试或恢复点。

## 开发命令

安装 Python 3.11 或更高版本：

```powershell
python -m pip install -e .
```

只读预检：

```powershell
pdf2word-engine preflight "D:\work\31.半月谈行测1000题下.pdf"
```

从空工作区生成当前 6 页样本：

```powershell
pdf2word-engine source-first-pilot "D:\work\31.半月谈行测1000题下.pdf" `
  --output-dir ".\outputs\source-first-editable-v2-next" `
  --workspace-dir ".\runtime\source-first-editable-v2-next" `
  --dpi 300 --ocr-device auto
```

检查 DOCX 的可编辑结构，可选使用 LibreOffice 渲染并验证页数：

```powershell
pdf2word-engine docx-check ".\outputs\candidate.docx" `
  --minimum-editable-characters 100 `
  --render-output-dir ".\runtime\docx-check" --expected-pages 6
```

Microsoft Word 实机门禁：

```powershell
pdf2word-engine word-render-check ".\outputs\candidate.docx" `
  --output-pdf ".\runtime\word-check\candidate.pdf" --expected-pages 6
```

## 目录

```text
src/pdf2word_engine/  Python 引擎与 sidecar 协议
tests/                自动测试
desktop/              Tauri/React 桌面壳
docs/                 专项方案和质量门禁
PROJECT_PLAN.md       产品与架构基线
```
