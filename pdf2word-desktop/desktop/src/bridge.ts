import { invoke } from "@tauri-apps/api/core";

export type EngineStatus = {
  workerConfigured: boolean;
  message: string;
};

export type CerCatalogPage = {
  page_number: number;
  coverage: string[];
  description: string;
  completed: boolean;
  excluded_from_cer: boolean;
  annotation_path: string | null;
};

export type CerCatalog = {
  manifest_path: string;
  selected_page_count: number;
  completed_page_count: number;
  pages: CerCatalogPage[];
};

export type CerReviewSegment = {
  ordinal: number;
  block_id: string;
  semantic_role: string;
  bbox: [number, number, number, number];
  confidence: number | null;
  production_ocr_text: string;
  independent_ocr_text: string | null;
  review_flags: string[];
  reference_text: string;
};

export type CerReview = {
  page_number: number;
  instructions: string;
  segments: CerReviewSegment[];
  unmatched_independent_block_ids: string[];
};

export type CerPreparedPage = {
  page: { page_number: number; description: string; coverage: string[]; annotation_path: string | null };
  review: CerReview;
  source_image_data_url: string;
  annotation_image_width_px: number | null;
  annotation_image_height_px: number | null;
};

export function isTauriRuntime(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

export async function getEngineStatus(): Promise<EngineStatus> {
  if (!isTauriRuntime()) {
    return {
      workerConfigured: false,
      message: "浏览器预览模式：Python 转换引擎仅能在 Tauri 桌面端运行。"
    };
  }
  return invoke<EngineStatus>("engine_status");
}

function requireTauri(): void {
  if (!isTauriRuntime()) throw new Error("CER 审校只能在 PDF2Word 桌面端运行。");
}

export async function chooseCerSourcePdf(): Promise<string | null> {
  requireTauri();
  return invoke<string | null>("choose_cer_source_pdf");
}

export async function chooseCerManifest(): Promise<string | null> {
  requireTauri();
  return invoke<string | null>("choose_cer_manifest");
}

export async function getCerCatalog(manifest: string): Promise<CerCatalog> {
  requireTauri();
  return invoke<CerCatalog>("cer_review_catalog", { manifest });
}

export async function prepareCerReview(manifest: string, sourcePdf: string, pageNumber: number): Promise<CerPreparedPage> {
  requireTauri();
  return invoke<CerPreparedPage>("cer_review_prepare", { manifest, sourcePdf, pageNumber });
}

export async function saveCerReview(manifest: string, pageNumber: number, segments: CerReviewSegment[]): Promise<{ annotation_path: string }> {
  requireTauri();
  return invoke<{ annotation_path: string }>("cer_review_save", { manifest, pageNumber, segments });
}
