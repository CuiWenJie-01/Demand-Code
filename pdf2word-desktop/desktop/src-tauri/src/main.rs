use serde::Serialize;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineStatus {
    worker_configured: bool,
    message: String,
}

#[tauri::command]
fn engine_status() -> EngineStatus {
    EngineStatus {
        worker_configured: false,
        message: "桌面壳已启动；等待打包 Python sidecar 和 PaddleOCR 模型包。".to_string(),
    }
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![engine_status])
        .run(tauri::generate_context!())
        .expect("启动 PDF2Word Desktop 失败");
}
