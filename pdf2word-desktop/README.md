# PDF2Word Desktop

本仓库正在实现“源文档驱动、准确优先、正文可编辑”的复杂中文 PDF 转 Word 管线。当前基准源文档为 `D:\work\31.半月谈行测1000题下.pdf`，详细约束见：

- `PROJECT_PLAN.md`：产品、架构与里程碑总方案；
- `docs/SOURCE_FIRST_EDITABLE_HYBRID_REBUILD.md`：本书专项实施基线；
- `docs/M1_QUALITY_GATES.md`：当前质量门禁。

当前有效链路从源 PDF 和空任务目录开始，优先使用 GPU 重新渲染、清理水印并 OCR；题干、选项、答案、解析、提示、分数和公式全部写为可编辑 Word 内容，图片只保留 Logo、艺术字、“谈+标签”组合标识、侧栏、艺术页码和真实图形。历史 12 页 PageModel/CER/视觉金标及缓存重建入口已经移除，不能再把人工修好的中间结果当作端到端输入。

## 当前状态

- run8 虽通过旧自动门禁，但经用户对照源文档后判定不通过；该结论已作废；
- 物理页 7、8、9、10、21、23 的“正文零图片”当前候选已通过 91 项自动测试、6 页完整渲染和 Microsoft Word 实机导出逐页目检，正在等待用户复核；
- 当前候选从空任务目录在 `gpu:0` 重新 OCR，无 CPU 回退；正文图片块、公式图片回退、异常重叠和整页截图均为 0，平均可编辑字符覆盖率为 99.53%；
- 27 个紧凑分数已写为 Word 原生 OMML 上下式并保持可编辑；46 个“谈指数/谈解析/谈答案/谈提示”使用源页组合标识图并与后续可编辑正文行内绑定；
- 候选目录使用固定的 `outputs/source-first-editable-v2-current` 与 `runtime/source-first-editable-v2-current`；失败任务自动清理暂存目录，成功任务才替换上一版当前候选；
- 用户确认 6 页候选前，不启动新的长期 12 页回归基线或 381 页正式任务；
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

生成当前 6 页样本：

```powershell
pdf2word-engine source-first-pilot "D:\work\31.半月谈行测1000题下.pdf" `
  --dpi 300 --ocr-device auto
```

命令在唯一的隐藏暂存目录中全新渲染和 OCR。失败时自动删除本次暂存目录并保留上一版当前候选；完整成功后才替换上述两个 `current` 目录。若 Word/WPS 仍打开当前候选，命令会在 OCR 前根据锁文件立即失败，避免白跑。通常不再传入带 `run8/run9/...` 编号的目录。

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
