use serde::Serialize;
use serde_json::{json, Value};
use std::{
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};
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
        .ok_or_else(|| format!("未找到 CER/转换 sidecar（期望 {}）。", file_name))
}

fn run_worker(app: &tauri::AppHandle, request: Value) -> Result<Value, String> {
    let request_id = request
        .get("request_id")
        .and_then(Value::as_str)
        .ok_or_else(|| "sidecar 请求缺少 request_id。".to_string())?
        .to_owned();
    let mut child = Command::new(worker_path(app)?)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("无法启动 PDF2Word sidecar：{error}"))?;
    let input = format!(
        "{}\n",
        serde_json::to_string(&request)
            .map_err(|error| format!("无法编码 sidecar 请求：{error}"))?
    );
    child
        .stdin
        .take()
        .ok_or_else(|| "无法写入 PDF2Word sidecar。".to_string())?
        .write_all(input.as_bytes())
        .map_err(|error| format!("写入 PDF2Word sidecar 失败：{error}"))?;
    let output = child
        .wait_with_output()
        .map_err(|error| format!("等待 PDF2Word sidecar 失败：{error}"))?;
    let stdout = String::from_utf8(output.stdout)
        .map_err(|error| format!("sidecar 输出不是 UTF-8：{error}"))?;
    let response = stdout
        .lines()
        .filter_map(|line| serde_json::from_str::<Value>(line).ok())
        .find(|payload| {
            payload.get("request_id").and_then(Value::as_str) == Some(request_id.as_str())
                && payload.get("event").is_none()
        })
        .ok_or_else(|| {
            format!(
                "PDF2Word sidecar 没有返回有效结果。{}",
                String::from_utf8_lossy(&output.stderr)
            )
        })?;
    if response.get("ok").and_then(Value::as_bool) != Some(true) {
        return Err(response
            .get("error")
            .and_then(|error| error.get("message"))
            .and_then(Value::as_str)
            .unwrap_or("CER sidecar 请求失败。")
            .to_owned());
    }
    response
        .get("result")
        .cloned()
        .ok_or_else(|| "CER sidecar 响应缺少 result。".to_string())
}

#[tauri::command]
fn engine_status(app: tauri::AppHandle) -> EngineStatus {
    match worker_path(&app) {
        Ok(_) => EngineStatus {
            worker_configured: true,
            message: "桌面端 CER 审校与转换 sidecar 已就绪。".to_string(),
        },
        Err(message) => EngineStatus {
            worker_configured: false,
            message,
        },
    }
}

#[tauri::command]
fn choose_cer_source_pdf() -> Option<String> {
    rfd::FileDialog::new()
        .add_filter("PDF 文件", &["pdf"])
        .pick_file()
        .map(|path| path.to_string_lossy().to_string())
}

#[tauri::command]
fn choose_cer_manifest() -> Option<String> {
    rfd::FileDialog::new()
        .add_filter("代表页清单", &["json"])
        .pick_file()
        .map(|path| path.to_string_lossy().to_string())
}

#[tauri::command]
fn cer_review_catalog(app: tauri::AppHandle, manifest: String) -> Result<Value, String> {
    run_worker(
        &app,
        json!({"request_id": "desktop-cer-catalog", "command": "cer_review_catalog", "manifest": manifest}),
    )
}

#[tauri::command]
fn cer_review_prepare(
    app: tauri::AppHandle,
    manifest: String,
    source_pdf: String,
    page_number: u32,
) -> Result<Value, String> {
    run_worker(
        &app,
        json!({"request_id": "desktop-cer-prepare", "command": "cer_review_prepare", "manifest": manifest, "source_pdf": source_pdf, "page_number": page_number, "dpi": 144}),
    )
}

#[tauri::command]
fn cer_review_save(
    app: tauri::AppHandle,
    manifest: String,
    page_number: u32,
    segments: Option<Vec<Value>>,
) -> Result<Value, String> {
    run_worker(
        &app,
        json!({"request_id": "desktop-cer-save", "command": "cer_review_save", "manifest": manifest, "page_number": page_number, "segments": segments}),
    )
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            engine_status,
            choose_cer_source_pdf,
            choose_cer_manifest,
            cer_review_catalog,
            cer_review_prepare,
            cer_review_save
        ])
        .run(tauri::generate_context!())
        .expect("启动 PDF2Word Desktop 失败");
}
