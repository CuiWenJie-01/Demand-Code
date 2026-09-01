# M0 技术验证记录

> 日期：2026-08-26（路线调整后更新）  
> 状态：仅可编辑 Word 路线；已完成代表页的 OCR、行级绝对定位重建、Microsoft Word 实机渲染验证；CER 人工标注尚待完成

## 已实现

- 只读 PDF 预检：页数、文件大小、加密、元数据、字体资源、XObject、抽样文字和页面尺寸。
- 路由分类：born-digital、scanned、outlined、mixed、encrypted、damaged。
- PDFium 按页渲染：不一次性把整份 PDF 放入内存。
- SQLite 任务工作区：页级 `pending/rendered` 状态、源文件哈希和转换配置。
- 文字 PDF 的基础可编辑 DOCX：仅面向已有可靠文字层的 MVP 路径。
- JSON Lines worker：为后续 Tauri sidecar 提供 `ping`、`preflight`、`convert` 协议，错误也会关联原 `request_id`。
- PaddleOCR PageModel 适配：将 PP-StructureV3 的版面 JSON 标准化为版本化页面块模型；正文使用行级 `rec_texts + rec_boxes` 坐标重建，缺少可靠坐标的区域会明确拒绝进入可编辑重建。
- 可编辑质量报告：OCR 路线会随 DOCX 生成不含 OCR 正文的 JSON 报告，列出逐页可编辑块、局部图像回退块与告警。

## 自动测试

使用当前 Python 运行时执行 `unittest`：

| 测试 | 结果 |
| --- | --- |
| 文字 PDF 预检分类 | 通过 |
| 页码范围解析与错误处理 | 通过 |
| 文字 PDF 可编辑 DOCX | 通过 |
| 任务工作区重新打开及不存在任务保护 | 通过 |
| PaddleOCR 结果到 PageModel 的字段映射及异常区域保护 | 通过 |
| PageModel 坐标、可编辑文本框与局部图片回退 DOCX | 通过 |
| 行级 OCR 坐标替换自动换行正文块 | 通过 |
| 旧 PageModel 缓存从原始 Paddle JSON 无 OCR 重建 | 通过 |

结果：16/16 通过。

## 真实样例验证

输入样例：

```text
D:\work\31.半月谈行测1000题下.pdf
```

预检结果：

| 项目 | 结果 |
| --- | --- |
| 大小 | 156,234,759 字节 |
| 页数 | 381 |
| 分类 | `outlined` |
| 具有字体资源的页数 | 0 |
| 具有 XObject 的页数 | 381 |
| 抽样可提取字符数 | 0 |

第 10 页和第 300 页已完成逐页渲染验证。此前用于验证大文件分页渲染的页图 DOCX 路线已根据产品决策移除，不再是项目功能或验收目标。大文件处理的任务工作区、逐页渲染和页面检查点基础设施会保留给 OCR 与可编辑重建使用。

## OCR / PageModel 样页验证

使用第 10 页渲染图（1032 × 1458 px）验证 PP-StructureV3 CPU 路径。首次模型准备下载约 1.0 GiB 的 PP-StructureV3 相关模型；不把它们放入代码仓库，正式桌面端将由模型管理器安装到用户数据目录。

| 项目 | 结果 |
| --- | --- |
| Paddle 运行时 | `paddlepaddle==3.2.2` |
| OCR/版面组件 | `paddleocr==3.7.0`、`paddlex[ocr]==3.7.2` |
| 真实推理 | 成功，约 91 秒（首次该进程加载模型及 CPU 推理） |
| 原始结果 | 56,344 字节 JSON，位于该页工作区 |
| 标准化 PageModel | 44 个定位块（36 个行级正文块、合计 38 个可编辑文本块、6 个局部图像回退块） |
| 发现的块类型 | `header`、`text_line`、`paragraph_title`、`number`、`image`、`aside_text` |

PP-StructureV3 3.7 的原始数据位于顶层 `res.parsing_res_list`，适配器已兼容该形状和旧版顶层形状。对于没有有效边界框的区域，适配器会记录警告并排除出可编辑重建，避免位置不确定的 OCR 文本污染输出。

已验证的页级工件：

```text
runtime/jobs/7692f85f062948d987c1f5c1a31528bd/pages/0010/paddle-raw.json
runtime/jobs/7692f85f062948d987c1f5c1a31528bd/pages/0010/page-model.json
```

注意：这项验证确认了 OCR 与版面块提取，不等同于已通过 CER 人工标注评测，也不等同于高保真可编辑 DOCX 已完成。

## 定位式可编辑 DOCX 样页验证

第 10 页已通过正式引擎入口执行端到端路线：PDFium 渲染 → PP-StructureV3 → `PageModel`/局部图像缓存 → 定位式可编辑 DOCX。输出包含 44 个版面块：题干、选项、解析和正文按 OCR 行坐标写入可编辑 Word 文本框；6 个页眉、装饰标签和图像类区域作为局部 PNG 回退。恢复已有任务时，旧版 PageModel 会从已保存的原始 Paddle JSON 重建，不会为此重复 OCR。

```text
outputs/m1-pipeline-page10/31.半月谈行测1000题下-可编辑版.docx
```

该文档已经使用 LibreOffice 转为 PDF/PNG 并人工检查渲染页：页面坐标、页眉、粉色标签和复杂区回退均可见，题干、选项与解析正文均可编辑。行级模型避免了长 OCR 段落由 Word 自动换行而导致的末行裁切。不同渲染器的 CJK 字体度量仍可能产生少量宽度差异；M1 后续将以代表页差异报告继续收敛。

同一输出目录还会生成 `31.半月谈行测1000题下-质量报告.json`；第 10 页报告记录 `editable_text_blocks=38`、`fallback_blocks=6`，不保存题目正文，便于桌面端展示质量告警而不重复保存文本内容。

第 300 页另行通过同一正式入口验证，覆盖图文混排页面：21 个行级正文块及另外 2 个定位文本块写入可编辑文本框，柱状图和装饰标签等 10 个复杂区域按块回退为 PNG。LibreOffice 渲染后，图表位置与正文阅读顺序可见；数学算式仍以 OCR 文本近似，属于后续公式结构化重建的验证项。

同一次样页推理还生成了 Paddle 原生 Word 对照文件：

```text
outputs/m0-paddle-native/render.docx
```

该文档为 42,048 字节，包含 15 个非空段落和 2 个内联图。它确认了 OCR 结果可被 Paddle 的内容恢复路径导出为 DOCX，但尚未在 Word/LibreOffice 中再渲染，因此仅作为未来绝对定位可编辑 DOCX 的内容恢复对照。

## 桌面端验证

- React/Vite 前端依赖已安装，`pnpm build` 成功。
- Tauri Rust 源码和配置已创建。
- 当前开发机可以找到 `rustc` 和 `cargo`，但执行 `cargo check` 时被 Windows 应用程序控制策略拦截：`os error 4551`。
- 阻塞点是 Cargo 为依赖编译产生的 build script 可执行文件，尚未进入项目 Rust 源码的编译错误检查阶段。
- 在允许开发工作区执行 Cargo 构建脚本后，应先重新运行 `cargo check`，再冻结 Python worker 并执行 `pnpm tauri build`。

## Microsoft Word 代表页实机验证（2026-08-31）

已使用安装在 `C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE` 的 Microsoft Word，以 COM 只读打开 DOCX、导出 PDF、关闭文档与 Word 进程。固定 12 页（1、10、40、80、120、160、200、240、300、330、360、381）均成功导出，且每份 PDF 的实际页数均为 1/1。

导出的 PDF 与 144 DPI 页面图保存在 `runtime/word-render/representative-pages/`。逐页目视复核结果为通过：题图、表格、图表、竖排栏、页码、粉色提示标签及末页留白均未出现裁剪、重叠或连锁分页。Word 的像素基线须与 LibreOffice 基线分离维护，不能直接套用 LibreOffice 的 SSIM/MAE 阈值。

## 尚未完成的 M0 验证

1. 尚未完成代表页 CER 的人工逐字标注与正式报告；模板已生成在 `tests/fixtures/cer_annotations/`。
2. WPS 兼容性验收需独立于 Word 进行；本机 WPS 未注册可用 COM 自动化接口，因此需以实际 GUI 打开、导出、页数与视觉复核执行，不能以 Word 结果替代。
3. 已建立项目隔离的 PaddleOCR CPU 验证环境并下载模型；PaddlePaddle 3.3.1 的 oneDNN/PIR 缺陷可稳定复现，已在隔离环境降为 3.2.2 后继续真实样页推理。主转换引擎已接入 OCR 可编辑 Word 输出。上游记录：[Paddle #77340](https://github.com/PaddlePaddle/Paddle/issues/77340)。
4. Tauri 编译因本机应用程序控制策略被拦截，尚未生成或验证 `.exe` 安装包。

## 下一阶段

1. 完成 PP-StructureV3 代表页推理，固化原始结果与 PageModel 样本。
2. 针对固定代表页测量 OCR 字符准确率、表格、公式和阅读顺序。
4. 接入可用的 Word/LibreOffice 渲染器，建立视觉回归与 SSIM 阈值。
5. 完成页面级恢复入口，并将引擎接到 Tauri 桌面端。
