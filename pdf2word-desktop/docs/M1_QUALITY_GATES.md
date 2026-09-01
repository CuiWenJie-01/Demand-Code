# M1 质量门禁

代表页清单固定为 12 页。`representative-regression --strict` 验证每页都具有 PageModel 与 DOCX 工件，并检查定位文本框、可编辑竖排栏/页码色条及 Office 兼容渲染后的单页分页。

`representative-quality-gate` 不读取已有 DOCX 作为候选输出：它从登记的 PageModel 重新生成 DOCX，使用指定渲染器输出 144 DPI PNG，再与清单中的人工批准视觉快照比较 SSIM 和 MAE。清单中记录每页阈值；第 200 页为 Word/LibreOffice 字体度量差异较大的已批准例外，其余页使用通用阈值。

CER 是代表页基准的研发验收工具，不是每次转换的人工步骤。正常转换只执行预检、OCR、Word 生成和自动质量检查；只有建立或扩充页面类型基准时，才运行人工审校。

使用 `cer-review` 生成的浏览器页面按页而非按块确认：左侧为源 PDF 原图，右侧为预填生产 OCR；双 OCR 不一致、低置信度和疑似断行会高亮。审校者修正文字后一次确认整页，下载的 UTF-8 JSON 才能作为 CER 标注。预填 OCR 只是编辑草稿，`page_confirmed: true` 是人工已通读确认的必要记录。

```powershell
pdf2word-engine cer-review .\tests\fixtures\representative_pages.json `
  --source-pdf D:\work\source.pdf --output-dir .\runtime\cer-review
```

确认后的 CER 标注格式如下。`reference_text` 由人工确认，禁止把未确认的 OCR 草稿当作真值；每个片段仍保留独立 `block_id`，以便定位错误和计算 CER。

```json
{
  "schema_version": 2,
  "workflow": "page_review",
  "page_number": 10,
  "page_confirmed": true,
  "segments": [
    {"block_id": "line-1", "reference_text": "人工逐字转写内容"},
    {"block_id": "line-2", "reference_text": "下一行人工转写内容"}
  ]
}
```

若页面完全由图片回退构成、没有可编辑 OCR 文本，可登记 `exclude_from_cer: true` 与明确的 `exclusion_reason`；该页从 CER 分母排除，不能伪造 0% CER。

执行 `representative-quality-gate --require-cer` 时，任一页缺少标注、未整页确认或超出该页 `maximum_cer` 即失败。当前验收阈值为 0.5%，但只有在 12 页独立人工标注完整后，才可宣称 CER 已通过。

长期基准库按页面类型积累：普通题目、图表资料分析、表格公式、几何图、竖排栏/水印、封面目录末页和低清异常页。相近的新书仅自动转换和抽检；出版社/版式变化时补充约 5–12 个代表页；自动门禁标红时仅审校异常页。

最终 Microsoft Word 门禁使用 `word-render-regression`。它经 Word COM 以只读方式打开 DOCX、导出 PDF、验证页数，并始终关闭 Word 与文档；运行机器必须预先安装 Microsoft Word 和项目 `word-render` 可选依赖。该门禁不能由 LibreOffice 结果替代。

WPS 是单独的兼容性目标，不能替代 Microsoft Word。本机 WPS 未注册可调用的 COM 自动化接口，因此现阶段按实际 GUI 流程打开 DOCX、导出 PDF、验证页数并逐页目视复核；通过后应保存独立的 WPS PDF/截图和验收记录，不能混用 Word 或 LibreOffice 的像素阈值。
