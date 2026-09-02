# Tauri Desktop Shell

此目录是 Windows 桌面端源码。前端使用 React/Vite，`src-tauri` 使用 Tauri 2。

桌面端当前只保留与产品主线一致的界面骨架和 `engine_status` 检查。过期 CER 审校界面、文件选择命令和 sidecar 协议已经删除，因为它们依赖过期 PageModel 与人工金标，不属于当前 source-first 端到端链路。

“开始转换”按钮保持禁用，直到由预检读取实际页数 `N` 的任意页数 source-first 管线具备以下条件后再接入：

1. 从源 PDF 和经过完整指纹校验的任务上下文开始；
2. GPU 可用时优先使用 GPU，CPU 回退有完整原因记录；
3. 普通正文使用原生 Word 段落，复杂区域局部源图回退；
4. 同一任务断点恢复校验源哈希、代码、模型和参数；
5. 静态质量、可编辑覆盖率、渲染页数和动态抽样门禁完整通过。

全书入口、任务指纹、动态首批页、分批停止、全量自动检查和最终状态的具体实现以 `../docs/FULL_BOOK_DYNAMIC_QUALITY_GATE.md` 为准。

## 后续接入顺序

1. 完成并验证任意页数 source-first Python 入口，并以当前 `N = 381` 的大型基准验收；
2. 将 `preflight`、正式转换、暂停、继续和取消协议接回 worker 与 UI；
3. 使用 `scripts/build-sidecar.ps1` 冻结 Windows sidecar；
4. 运行 `pnpm build`、`cargo check` 与 `pnpm tauri build`；
5. 在干净 Windows 10/11 环境验证 Word、LibreOffice 与 WPS 兼容性。
