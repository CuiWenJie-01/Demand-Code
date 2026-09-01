# M1：381 页正式退出验收

验收日期：2026-09-01。此记录仅覆盖 M1 引擎与命令行工作流；CER 桌面审校不属于日常转换路径。

## 验收输入

- 源文件：`D:\work\31.半月谈行测1000题下.pdf`
- 大小：156,234,759 bytes
- SHA-256：`87a6f8015987906bf690f3a5a0a2a0a660f762c63b69c8ca74cf970b3a19e1b0`
- 预检：381 页、PDF 1.6、未加密、`outlined`，全部页面走 OCR 路径。

该哈希与 2026-08-31 的完整历史作业相同，因而本次验收使用的是同一份原始 PDF，而非派生文件。

## 已通过门禁

1. `representative-regression --strict`：12/12 代表页通过，无待建页。
2. `representative-quality-gate --require-cer`：12/12 视觉回归通过；11 页有效文字 CER 均为 0，封面页按图像回退规则豁免。
3. 代表页资源可复现性：第 240、330、360、381 页原先指向已清理的临时裁图；已从同一源 PDF 的渲染检查点重建为 PageModel 同目录资源，并支持旧项目根目录相对资源与新同目录相对资源。

详细 JSON 工件位于 `runtime/m1-exit-20260901/representative-regression.json` 和 `runtime/m1-exit-20260901/representative-quality-gate-final.json`。

## 检查点恢复验证

本次新建作业 ID：`26e6bcfecd3e4a43be52e08e0d1693bd`。

- 在渲染阶段人为终止后，SQLite 保留了全部 381 页登记，其中 152 页为 `rendered`、229 页为 `pending`。
- 使用相同源文件、哈希和配置通过 `--resume-job` 恢复后，仅补渲染 229 个待处理页；前 152 页未被覆盖。
- 恢复后已形成全部 381 个 `rendered` 检查点，并进入 OCR 阶段。

初始与恢复日志分别为 `runtime/m1-exit-20260901/full-381-initial.stdout.log` 和 `runtime/m1-exit-20260901/full-381-resume.stdout.log`。

## 待完成的退出项

当前恢复作业仍在执行 OCR。仅当它完成并同时满足以下条件时，才能将 M1 标记为正式通过：

- 作业状态为 `completed`，无遗漏页和未处理错误；
- 输出单一 DOCX 与质量报告；
- 质量报告页数为 381，且与源 PDF 预检页数、作业检查点页数一致；
- 将最终输出路径、完成时间和上述统计补入本记录。
