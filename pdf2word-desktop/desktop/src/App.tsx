import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  CerCatalog,
  CerPreparedPage,
  CerReviewSegment,
  EngineStatus,
  chooseCerManifest,
  chooseCerSourcePdf,
  getCerCatalog,
  getEngineStatus,
  isTauriRuntime,
  prepareCerReview,
  saveCerReview,
} from "./bridge";

function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

export function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dpi, setDpi] = useState(200);
  const [engine, setEngine] = useState<EngineStatus>({ workerConfigured: false, message: "正在检查转换引擎…" });
  const [screen, setScreen] = useState<"convert" | "cer">("convert");
  const [manifestPath, setManifestPath] = useState<string | null>(null);
  const [sourcePdfPath, setSourcePdfPath] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<CerCatalog | null>(null);
  const [prepared, setPrepared] = useState<CerPreparedPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEngineStatus().then(setEngine).catch((reason: unknown) => {
      setEngine({ workerConfigured: false, message: `引擎检查失败：${String(reason)}` });
    });
  }, []);

  function chooseFile() { inputRef.current?.click(); }
  function onFileChange(event: ChangeEvent<HTMLInputElement>) { setSelectedFile(event.target.files?.[0] ?? null); }
  const desktopReady = isTauriRuntime() && engine.workerConfigured;

  async function pickManifest() {
    setError(null); setNotice(null);
    try {
      const path = await chooseCerManifest();
      if (!path) return;
      setLoading(true);
      const next = await getCerCatalog(path);
      setManifestPath(path); setCatalog(next); setPrepared(null);
    } catch (reason) { setError(String(reason)); } finally { setLoading(false); }
  }

  async function pickSourcePdf() {
    setError(null); setNotice(null);
    try {
      const path = await chooseCerSourcePdf();
      if (path) setSourcePdfPath(path);
    } catch (reason) { setError(String(reason)); }
  }

  async function openReview(pageNumber: number) {
    if (!manifestPath || !sourcePdfPath) { setError("请先选择代表页清单和源 PDF。"); return; }
    setLoading(true); setError(null); setNotice(null);
    try { setPrepared(await prepareCerReview(manifestPath, sourcePdfPath, pageNumber)); }
    catch (reason) { setError(String(reason)); }
    finally { setLoading(false); }
  }

  function updateReference(index: number, referenceText: string) {
    setPrepared((current) => {
      if (!current) return current;
      const segments = current.review.segments.map((segment, position) => position === index ? { ...segment, reference_text: referenceText } : segment);
      return { ...current, review: { ...current.review, segments } };
    });
  }

  async function confirmPage() {
    if (!manifestPath || !prepared) return;
    setSaving(true); setError(null); setNotice(null);
    try {
      const result = await saveCerReview(manifestPath, prepared.page.page_number, prepared.review.segments);
      setNotice(`第 ${prepared.page.page_number} 页已整页确认并写入 ${result.annotation_path}`);
      setCatalog(await getCerCatalog(manifestPath));
    } catch (reason) { setError(String(reason)); }
    finally { setSaving(false); }
  }

  if (screen === "cer") {
    return <CerReviewScreen
      engine={engine} manifestPath={manifestPath} sourcePdfPath={sourcePdfPath} catalog={catalog} prepared={prepared}
      loading={loading} saving={saving} notice={notice} error={error}
      onBack={() => setScreen("convert")} onPickManifest={pickManifest} onPickSource={pickSourcePdf}
      onOpenPage={openReview} onUpdateReference={updateReference} onConfirm={confirmPage}
    />;
  }

  return (
    <main className="app-shell">
      <header className="app-header"><div><p className="eyebrow">LOCAL PDF CONVERSION</p><h1>PDF2Word Desktop</h1><p className="subtitle">面向大文件和复杂版式的本地 Word 转换</p></div><span className={desktopReady ? "status status-ready" : "status"}>{desktopReady ? "引擎就绪" : "开发模式"}</span></header>
      <section className="card import-card"><div><h2>选择 PDF</h2><p>文件仅在本机处理。预检会自动识别扫描件、文字轮廓和普通文字 PDF。</p></div><button type="button" className="primary-button" onClick={chooseFile}>选择文件</button><input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={onFileChange} hidden />{selectedFile && <div className="file-summary"><strong>{selectedFile.name}</strong><span>{formatBytes(selectedFile.size)}</span></div>}</section>
      <section className="settings-grid"><label className="card setting"><span>OCR 识别 DPI</span><select value={dpi} onChange={(event) => setDpi(Number(event.target.value))}><option value={144}>144 DPI（较小文件）</option><option value={200}>200 DPI（推荐）</option><option value={300}>300 DPI（最高保真）</option></select></label></section>
      <section className="card engine-card"><h2>转换引擎</h2><p>{engine.message}</p><ul><li>仅生成可编辑 Word：需要 PaddleOCR PP-StructureV3 模型包。</li><li>大文件任务：逐页检查点、暂停恢复和失败重试。</li></ul></section>
      <section className="card cer-entry"><div><p className="eyebrow">BASELINE LIBRARY</p><h2>CER 代表页审校</h2><p>只用于建立或扩充基准库；不会进入日常 PDF 转换流程。应用内按页确认并直接写入标注。</p></div><button type="button" className="secondary-button" onClick={() => setScreen("cer")}>打开 CER 审校</button></section>
      <footer className="action-bar"><div><strong>{selectedFile ? "已选择文件，等待预检" : "请选择一个 PDF"}</strong><span>可编辑 Word · {dpi} DPI</span></div><button type="button" className="primary-button" disabled={!desktopReady || !selectedFile} title={desktopReady ? "开始转换" : "Tauri sidecar 尚未打包"}>开始转换</button></footer>
    </main>
  );
}

type CerScreenProps = {
  engine: EngineStatus; manifestPath: string | null; sourcePdfPath: string | null; catalog: CerCatalog | null; prepared: CerPreparedPage | null;
  loading: boolean; saving: boolean; notice: string | null; error: string | null;
  onBack: () => void; onPickManifest: () => void; onPickSource: () => void; onOpenPage: (page: number) => void;
  onUpdateReference: (index: number, value: string) => void; onConfirm: () => void;
};

function CerReviewScreen(props: CerScreenProps) {
  const { catalog, prepared } = props;
  const progress = catalog ? `${catalog.completed_page_count} / ${catalog.selected_page_count}` : "0 / 12";
  const dimensions = useMemo(() => {
    if (!prepared) return { width: 1, height: 1 };
    const boxes = prepared.review.segments.map((segment) => segment.bbox);
    return {
      width: prepared.annotation_image_width_px || Math.max(1, ...boxes.map((bbox) => bbox[2])),
      height: prepared.annotation_image_height_px || Math.max(1, ...boxes.map((bbox) => bbox[3])),
    };
  }, [prepared]);
  const flagged = prepared?.review.segments.filter((segment) => segment.review_flags.length > 0) ?? [];
  const canReview = Boolean(props.manifestPath && props.sourcePdfPath && props.engine.workerConfigured);

  return <main className="cer-shell">
    <header className="cer-header"><div><button type="button" className="text-button" onClick={props.onBack}>← 返回转换</button><p className="eyebrow">BASELINE LIBRARY · HUMAN REVIEW</p><h1>CER 代表页审校</h1><p className="subtitle">整页确认后直接更新对应 <code>cer_annotations/page-xxxx.json</code>，不下载、不手动替换。</p></div><div className="progress-chip"><strong>{progress}</strong><span>页已完成</span></div></header>
    <section className="card cer-setup"><div className="path-choice"><span>代表页清单</span><strong>{props.manifestPath ? basename(props.manifestPath) : "尚未选择"}</strong></div><button type="button" className="secondary-button" onClick={props.onPickManifest} disabled={!props.engine.workerConfigured}>选择清单</button><div className="path-choice"><span>源 PDF</span><strong>{props.sourcePdfPath ? basename(props.sourcePdfPath) : "尚未选择"}</strong></div><button type="button" className="secondary-button" onClick={props.onPickSource} disabled={!props.engine.workerConfigured}>选择源 PDF</button></section>
    {!props.engine.workerConfigured && <p className="inline-message error">{props.engine.message} CER 审校会在打包 sidecar 后启用。</p>}
    {props.error && <p className="inline-message error">{props.error}</p>}
    {props.notice && <p className="inline-message success">{props.notice}</p>}
    <section className="cer-layout">
      <aside className="card page-list"><div className="list-heading"><h2>代表页</h2><span>{catalog?.selected_page_count ?? 12} 页</span></div>{catalog ? catalog.pages.map((page) => <button key={page.page_number} type="button" className={`page-item ${prepared?.page.page_number === page.page_number ? "active" : ""}`} onClick={() => props.onOpenPage(page.page_number)} disabled={!canReview || props.loading}><span className={page.completed ? "check complete" : "check"}>{page.completed ? "✓" : "·"}</span><span><strong>第 {page.page_number} 页</strong><small>{page.description}</small><em>{page.coverage.join(" · ")}</em></span></button>) : <p className="empty-state">选择代表页清单后，显示 12 页进度；以后新增页或异常页只需更新清单，再审校该页。</p>}</aside>
      <section className="review-workspace">{props.loading && <div className="card loading-card">正在准备源页与 OCR 草稿…</div>}{!props.loading && !prepared && <div className="card empty-review"><h2>开始整页审校</h2><p>选择清单和源 PDF，然后从左侧打开一页。红框表示低置信度、双 OCR 差异或疑似断行。</p></div>}{prepared && !props.loading && <><div className="review-title"><div><h2>第 {prepared.page.page_number} 页</h2><p>{prepared.page.description}</p></div><div className="badges"><span>{prepared.review.segments.length} 个可编辑块</span><span className={flagged.length ? "flag" : ""}>{flagged.length} 个需关注</span></div></div><div className="review-columns"><section className="card image-panel"><h2>原始页面</h2><div className="source-frame"><img src={prepared.source_image_data_url} alt={`源 PDF 第 ${prepared.page.page_number} 页`} />{flagged.map((segment) => <span key={segment.block_id} title={segment.review_flags.join("，")} className="source-highlight" style={{ left: `${segment.bbox[0] / dimensions.width * 100}%`, top: `${segment.bbox[1] / dimensions.height * 100}%`, width: `${(segment.bbox[2] - segment.bbox[0]) / dimensions.width * 100}%`, height: `${(segment.bbox[3] - segment.bbox[1]) / dimensions.height * 100}%` }} />)}</div><p className="image-caption">红框与右侧标红文本一一对应；框仅提示需要优先核对的位置。</p></section><section className="card transcript-panel"><h2>预填 OCR 与人工真值</h2><p>{prepared.review.instructions}</p><div className="segment-list">{prepared.review.segments.map((segment, index) => <ReviewSegment key={segment.block_id} segment={segment} onChange={(value) => props.onUpdateReference(index, value)} />)}</div></section></div><footer className="confirm-bar"><span>确认即写入当前清单登记的标注路径。</span><button type="button" className="primary-button" onClick={props.onConfirm} disabled={props.saving}>{props.saving ? "正在写入…" : "确认整页并写入标注"}</button></footer></>}</section>
    </section>
  </main>;
}

function ReviewSegment({ segment, onChange }: { segment: CerReviewSegment; onChange: (value: string) => void }) {
  const flagged = segment.review_flags.length > 0;
  return <article className={`review-segment ${flagged ? "attention" : ""}`}><div className="segment-meta"><span>#{segment.ordinal} · {segment.semantic_role || "text"}</span><span>{segment.review_flags.map((flag) => <em key={flag}>{flag}</em>)}</span></div><textarea value={segment.reference_text} onChange={(event) => onChange(event.target.value)} aria-label={`第 ${segment.ordinal} 段人工确认文本`} />{segment.independent_ocr_text && flagged && <p className="secondary-ocr">独立 OCR：{segment.independent_ocr_text}</p>}</article>;
}
