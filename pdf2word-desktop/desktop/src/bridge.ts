import { invoke } from "@tauri-apps/api/core";

export type EngineStatus = {
  workerConfigured: boolean;
  message: string;
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
