import { ChangeEvent, useEffect, useRef, useState } from "react";
import { EngineStatus, getEngineStatus, isTauriRuntime } from "./bridge";

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

export function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dpi, setDpi] = useState(300);
  const [engine, setEngine] = useState<EngineStatus>({ workerConfigured: false, message: "正在检查转换引擎…" });

  useEffect(() => {
    getEngineStatus().then(setEngine).catch((reason: unknown) => {
      setEngine({ workerConfigured: false, message: `引擎检查失败：${String(reason)}` });
    });
  }, []);

  const desktopReady = isTauriRuntime() && engine.workerConfigured;

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0] ?? null);
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">SOURCE-FIRST LOCAL CONVERSION</p>
          <h1>PDF2Word Desktop</h1>
          <p className="subtitle">准确优先、正文可编辑、复杂区域源图回退</p>
        </div>
        <span className={desktopReady ? "status status-ready" : "status"}>{desktopReady ? "引擎就绪" : "开发模式"}</span>
      </header>
      <section className="card import-card">
        <div>
          <h2>选择 PDF</h2>
          <p>文件仅在本机处理。正式入口只会调用源文档直跑管线，不读取旧任务 OCR 或 PageModel。</p>
        </div>
        <button type="button" className="primary-button" onClick={() => inputRef.current?.click()}>选择文件</button>
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={onFileChange} hidden />
        {selectedFile && <div className="file-summary"><strong>{selectedFile.name}</strong><span>{formatBytes(selectedFile.size)}</span></div>}
      </section>
      <section className="settings-grid">
        <label className="card setting">
          <span>源页渲染 DPI</span>
          <select value={dpi} onChange={(event) => setDpi(Number(event.target.value))}>
            <option value={200}>200 DPI（快速检查）</option>
            <option value={300}>300 DPI（推荐）</option>
          </select>
        </label>
      </section>
      <section className="card engine-card">
        <h2>转换引擎</h2>
        <p>{engine.message}</p>
        <ul>
          <li>兼容 GPU 可用时强制优先使用 GPU；CPU 回退必须记录原因。</li>
          <li>普通正文使用原生 Word 段落，公式和不可靠复杂区域局部截图。</li>
          <li>381 页全书入口将在当前源文档直跑链路完成后接入。</li>
        </ul>
      </section>
      <footer className="action-bar">
        <div><strong>{selectedFile ? "已选择文件，等待全书入口接入" : "请选择一个 PDF"}</strong><span>源文档直跑 · {dpi} DPI</span></div>
        <button type="button" className="primary-button" disabled title="全书 source-first 管线尚未接入桌面端">开始转换</button>
      </footer>
    </main>
  );
}
