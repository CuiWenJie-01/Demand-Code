use serde::Serialize;
use std::path::PathBuf;
use tauri::Manager;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineStatus {
    worker_configured: bool,
    message: String,
}

fn worker_file_name() -> String {
    format!(
        "pdf2word-worker-{}-pc-windows-msvc.exe",
        std::env::consts::ARCH
    )
}

fn worker_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let file_name = worker_file_name();
    let mut candidates = vec![PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("binaries")
        .join(&file_name)];
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("binaries").join(&file_name));
        candidates.push(resource_dir.join(&file_name));
    }
    if let Ok(executable_dir) = app.path().executable_dir() {
        candidates.push(executable_dir.join(&file_name));
    }
    candidates
        .into_iter()
        .find(|path| path.is_file())
        .ok_or_else(|| format!("未找到转换 sidecar（期望 {}）。", file_name))
}

#[tauri::command]
fn engine_status(app: tauri::AppHandle) -> EngineStatus {
    match worker_path(&app) {
        Ok(_) => EngineStatus {
            worker_configured: true,
            message: "桌面端 source-first 转换 sidecar 已就绪。".to_string(),
        },
        Err(message) => EngineStatus {
            worker_configured: false,
            message,
        },
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![engine_status])
        .run(tauri::generate_context!())
        .expect("启动 PDF2Word Desktop 失败");
}
