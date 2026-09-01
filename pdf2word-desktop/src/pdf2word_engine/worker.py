"""JSON Lines sidecar protocol for the future Tauri desktop host."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .execution import resolve_ocr_execution_profile
from .ocr import paddleocr_capability
from .pipeline import create_source_first_pilot
from .preflight import inspect_pdf


def _send(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _event(request_id: str, payload: dict[str, object]) -> None:
    _send({"protocol_version": 1, "request_id": request_id, "event": payload})


def _handle(request: dict[str, Any]) -> None:
    request_id = str(request.get("request_id", ""))
    command = request.get("command")
    if not request_id:
        raise ValueError("request_id 不能为空。")
    if command == "preflight":
        report = inspect_pdf(Path(request["source"]))
        _send({"protocol_version": 1, "request_id": request_id, "ok": True, "result": report.to_dict(include_page_sizes=False)})
        return
    if command == "source_first_pilot":
        docx, quality_report, manifest = create_source_first_pilot(
            Path(request["source"]),
            output_dir=Path(request["output_dir"]),
            workspace_dir=Path(request["workspace_dir"]),
            dpi=int(request.get("dpi", 300)),
            ocr_device=str(request.get("ocr_device", "auto")),
            cpu_threads=int(request["cpu_threads"]) if request.get("cpu_threads") is not None else None,
            progress=lambda payload: _event(request_id, payload),
        )
        _send(
            {
                "protocol_version": 1,
                "request_id": request_id,
                "ok": True,
                "result": {
                    "docx": str(docx),
                    "quality_report": str(quality_report),
                    "manifest": str(manifest),
                },
            }
        )
        return
    if command == "ping":
        capability = paddleocr_capability()
        execution_profile = resolve_ocr_execution_profile("auto")
        _send(
            {
                "protocol_version": 1,
                "request_id": request_id,
                "ok": True,
                "result": {
                    "status": "ready",
                    "ocr": {"available": capability.available, "engine": capability.engine, "reason": capability.reason},
                    "recommended_execution_profile": execution_profile.to_dict(),
                },
            }
        )
        return
    raise ValueError(f"不支持的命令：{command}")


def main() -> int:
    for line in sys.stdin:
        request_id = ""
        try:
            request = json.loads(line)
            request_id = str(request.get("request_id", ""))
            _handle(request)
        except Exception as exc:
            _send(
                {
                    "protocol_version": 1,
                    "request_id": request_id,
                    "ok": False,
                    "error": {"code": type(exc).__name__, "message": str(exc)},
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
