import { ChangeEvent, useEffect, useRef, useState } from "react";
import { EngineStatus, getEngineStatus, isTauriRuntime } from "./bridge";

type ConversionMode = "visual" | "editable" | "both";

const modeLabels: Record<ConversionMode, string> = {
  visual: "极致还原版",
  editable: "高保真可编辑版",
  both: "同时生成两种版本"
};

export function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ConversionMode>("both");
  const [dpi, setDpi] = useState(200);
  const [engine, setEngine] = useState<EngineStatus>({ workerConfigured: false, message: "正在检查转换引擎…" });

  useEffect(() => {
    getEngineStatus().then(setEngine).catch((error: unknown) => {
      setEngine({ workerConfigured: false, message: `引擎检查失败：${String(error)}` });
    });
  }, []);

  function chooseFile() {
    inputRef.current?.click();
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
  }

  const desktopReady = isTauriRuntime() && engine.workerConfigured;

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">LOCAL PDF CONVERSION</p>
          <h1>PDF2Word Desktop</h1>
          <p className="subtitle">面向大文件和复杂版式的本地 Word 转换</p>
        </div>
        <span className={desktopReady ? "status status-ready" : "status"}>{desktopReady ? "引擎就绪" : "开发模式"}</span>
      </header>

      <section className="card import-card">
        <div>
          <h2>选择 PDF</h2>
          <p>文件仅在本机处理。预检会自动识别扫描件、文字轮廓和普通文字 PDF。</p>
        </div>
        <button type="button" className="primary-button" onClick={chooseFile}>选择文件</button>
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={onFileChange} hidden />
        {selectedFile && (
          <div className="file-summary">
            <strong>{selectedFile.name}</strong>
            <span>{formatBytes(selectedFile.size)}</span>
          </div>
        )}
      </section>

      <section className="settings-grid">
        <label className="card setting">
          <span>导出模式</span>
          <select value={mode} onChange={(event) => setMode(event.target.value as ConversionMode)}>
            {(Object.keys(modeLabels) as ConversionMode[]).map((key) => <option key={key} value={key}>{modeLabels[key]}</option>)}
          </select>
        </label>
        <label className="card setting">
          <span>保真渲染 DPI</span>
          <select value={dpi} onChange={(event) => setDpi(Number(event.target.value))}>
            <option value={144}>144 DPI（较小文件）</option>
            <option value={200}>200 DPI（推荐）</option>
            <option value={300}>300 DPI（最高保真）</option>
          </select>
        </label>
      </section>

      <section className="card engine-card">
        <h2>转换引擎</h2>
        <p>{engine.message}</p>
        <ul>
          <li>保真模式：逐页 PDFium 渲染，无损嵌入 Word。</li>
          <li>可编辑模式：需要 PaddleOCR PP-StructureV3 模型包。</li>
          <li>大文件任务：逐页检查点、暂停恢复和失败重试。</li>
        </ul>
      </section>

      <footer className="action-bar">
        <div>
          <strong>{selectedFile ? "已选择文件，等待预检" : "请选择一个 PDF"}</strong>
          <span>当前模式：{modeLabels[mode]} · {dpi} DPI</span>
        </div>
        <button type="button" className="primary-button" disabled={!desktopReady || !selectedFile} title={desktopReady ? "开始转换" : "Tauri sidecar 尚未打包"}>
          开始转换
        </button>
      </footer>
    </main>
  );
}
