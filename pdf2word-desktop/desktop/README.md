# Tauri Desktop Shell

此目录是 Windows 桌面端源码。前端使用 React/Vite，`src-tauri` 使用 Tauri 2。

当前已实现可运行的界面骨架、文件选择、模式与 DPI 设置，以及 Rust ↔ 前端的 `engine_status` 调用。转换按钮会在 Python sidecar 未打包时保持禁用，避免给用户造成“已开始转换”的错误印象。

## 后续接入顺序

1. 安装 Rust/Cargo 和 Windows C++ Build Tools。
2. 使用 Nuitka/PyInstaller 将 `pdf2word_engine.worker` 冻结为 Windows sidecar。
3. 将 sidecar 放置为 `src-tauri/binaries/pdf2word-worker-x86_64-pc-windows-msvc.exe`。
4. 在 `tauri.conf.json` 配置 `bundle.externalBin`，并通过 `tauri-plugin-shell` 启动 worker。
5. 将 JSON Lines 的 `preflight`、`convert`、暂停、继续和取消事件映射到 UI。
6. 使用 `pnpm tauri build` 生成 NSIS `setup.exe`。

当前开发机已检测到 Rust/Cargo，React/Vite 前端也已通过生产构建；但 `cargo check` 被 Windows 应用程序控制策略拦截（`os error 4551`），因此尚未生成 `.exe`。解除该策略后应先运行 `cargo check`，再继续 sidecar 打包和 `pnpm tauri build`。
