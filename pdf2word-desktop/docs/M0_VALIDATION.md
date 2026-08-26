# M0 技术验证记录

> 日期：2026-08-26（路线调整后更新）  
> 状态：仅可编辑 Word 路线；OCR、Word 实际渲染对比和绝对定位重建待继续验证

## 已实现

- 只读 PDF 预检：页数、文件大小、加密、元数据、字体资源、XObject、抽样文字和页面尺寸。
- 路由分类：born-digital、scanned、outlined、mixed、encrypted、damaged。
- PDFium 按页渲染：不一次性把整份 PDF 放入内存。
- SQLite 任务工作区：页级 `pending/rendered` 状态、源文件哈希和转换配置。
- 文字 PDF 的基础可编辑 DOCX：仅面向已有可靠文字层的 MVP 路径。
- JSON Lines worker：为后续 Tauri sidecar 提供 `ping`、`preflight`、`convert` 协议，错误也会关联原 `request_id`。
- PaddleOCR PageModel 适配：将 PP-StructureV3 的版面 JSON 标准化为版本化页面块模型；缺少可靠坐标的区域会明确拒绝进入可编辑重建。

## 自动测试

使用当前 Python 运行时执行 `unittest`：

| 测试 | 结果 |
| --- | --- |
| 文字 PDF 预检分类 | 通过 |
| 页码范围解析与错误处理 | 通过 |
| 文字 PDF 可编辑 DOCX | 通过 |
| 任务工作区重新打开及不存在任务保护 | 通过 |
| PaddleOCR 结果到 PageModel 的字段映射及异常区域保护 | 通过 |

结果：11/11 通过。

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
| 标准化 PageModel | 19 个定位块、9,754 字节 JSON |
| 发现的块类型 | `header`、`text`、`paragraph_title`、`number`、`image`、`aside_text` |

PP-StructureV3 3.7 的原始数据位于顶层 `res.parsing_res_list`，适配器已兼容该形状和旧版顶层形状。对于没有有效边界框的区域，适配器会记录警告并排除出可编辑重建，避免位置不确定的 OCR 文本污染输出。

已验证的页级工件：

```text
runtime/jobs/7692f85f062948d987c1f5c1a31528bd/pages/0010/paddle-raw.json
runtime/jobs/7692f85f062948d987c1f5c1a31528bd/pages/0010/page-model.json
```

注意：这项验证确认了 OCR 与版面块提取，不等同于已通过 CER 人工标注评测，也不等同于高保真可编辑 DOCX 已完成。

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

## 尚未完成的 M0 验证

1. 当前环境未检测到 Microsoft Word 或 LibreOffice，尚未对可编辑 DOCX 再渲染为 PDF/PNG 并计算版式差异。
2. 已建立项目隔离的 PaddleOCR CPU 验证环境并下载模型；PaddlePaddle 3.3.1 的 oneDNN/PIR 缺陷可稳定复现，已在隔离环境降为 3.2.2 后继续真实样页推理。主转换引擎尚未把 OCR 自动接入可编辑 Word 输出，因而不会伪造文字。上游记录：[Paddle #77340](https://github.com/PaddlePaddle/Paddle/issues/77340)。
3. 尚未验证公式、图表、竖排文字和水印的 OCR/绝对定位 Word 重建效果。
4. Tauri 编译因本机应用程序控制策略被拦截，尚未生成或验证 `.exe` 安装包。

## 下一阶段

1. 完成 PP-StructureV3 代表页推理，固化原始结果与 PageModel 样本。
2. 针对固定代表页测量 OCR 字符准确率、表格、公式和阅读顺序。
4. 接入可用的 Word/LibreOffice 渲染器，建立视觉回归与 SSIM 阈值。
5. 完成页面级恢复入口，并将引擎接到 Tauri 桌面端。
