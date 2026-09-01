# Tauri Desktop Shell

此目录是 Windows 桌面端源码。前端使用 React/Vite，`src-tauri` 使用 Tauri 2。

当前已实现可运行的界面骨架、文件选择、模式与 DPI 设置，以及 Rust ↔ 前端的 `engine_status` 调用。转换按钮会在 Python sidecar 未打包时保持禁用，避免给用户造成“已开始转换”的错误印象。

此外，桌面端已提供独立的 **CER 代表页审校** 入口，不进入日常 PDF 转换流程：

1. 选择代表页清单（现有基准库为 `tests/fixtures/representative_pages.json`）和源 PDF；
2. 应用显示 12 页完成进度，按需只渲染并打开一张代表页；
3. 左侧显示源页原图及差异/低置信度/疑似断行红框，右侧预填生产 OCR；
4. 点击一次“确认整页并写入标注”，sidecar 会校验当前 PageModel 的 block ID，并原子写入该清单登记的 `cer_annotations/page-xxxx.json`；
5. 后续新增异常页或版式类型时，只需扩充清单并重新选择它，不必重审已完成页面。

CER 调用通过 JSON Lines worker 的 `cer_review_catalog`、`cer_review_prepare` 与 `cer_review_save` 命令完成。sidecar 未打包时该入口明确禁用；不会回退为浏览器下载或手动覆盖 JSON 的流程。

## 后续接入顺序

1. 安装 Rust/Cargo 和 Windows C++ Build Tools。
2. 使用 `powershell -ExecutionPolicy Bypass -File .\scripts\build-sidecar.ps1` 将 `pdf2word_worker.py` 冻结为 Windows sidecar（需要 `.venv-ocr` 已安装 PyInstaller 与 OCR 依赖）。
3. 将 sidecar 放置为 `src-tauri/binaries/pdf2word-worker-x86_64-pc-windows-msvc.exe`。
4. `tauri.conf.json` 已配置 `bundle.externalBin`；桌面端会直接启动 worker 并通过标准输入输出交换一次请求/响应。
5. 将 JSON Lines 的 `preflight`、`convert`、暂停、继续和取消事件映射到 UI。
6. 使用 `pnpm tauri build` 生成 NSIS `setup.exe`。

当前开发机已检测到 Rust/Cargo，React/Vite 前端也已通过生产构建；但 `cargo check` 被 Windows 应用程序控制策略拦截（`os error 4551`），因此尚未生成 `.exe`。解除该策略后应先运行 `cargo check`，再继续 sidecar 打包和 `pnpm tauri build`。
