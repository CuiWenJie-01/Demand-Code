"""JSON Lines sidecar protocol for the future Tauri desktop host."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .ocr import paddleocr_capability
from .execution import resolve_ocr_execution_profile
from .pipeline import convert_pdf
from .preflight import inspect_pdf
from .representative import (
    cer_review_catalog,
    load_representative_manifest,
    prepare_cer_review_page,
    save_cer_review_page,
)


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
    if command == "convert":
        result = convert_pdf(
            Path(request["source"]),
            output_dir=Path(request["output_dir"]),
            workspace_root=Path(request["workspace_root"]),
            dpi=int(request.get("dpi", 200)),
            page_range=request.get("page_range"),
            resume_job_id=request.get("resume_job_id"),
            ocr_device=str(request.get("ocr_device", "auto")),
            cpu_threads=int(request["cpu_threads"]) if request.get("cpu_threads") is not None else None,
            progress=lambda payload: _event(request_id, payload),
        )
        _send({"protocol_version": 1, "request_id": request_id, "ok": True, "result": result.to_dict()})
        return
    if command == "cer_review_catalog":
        manifest_path = Path(request["manifest"])
        manifest = load_representative_manifest(manifest_path)
        _send(
            {
                "protocol_version": 1,
                "request_id": request_id,
                "ok": True,
                "result": cer_review_catalog(manifest, manifest_path),
            }
        )
        return
    if command == "cer_review_prepare":
        manifest = load_representative_manifest(Path(request["manifest"]))
        result = prepare_cer_review_page(
            manifest,
            page_number=int(request["page_number"]),
            source_pdf=Path(request["source_pdf"]),
            independent_ocr_path=Path(request["independent_ocr"]) if request.get("independent_ocr") else None,
            dpi=int(request.get("dpi", 144)),
            low_confidence_threshold=float(request.get("low_confidence_threshold", 0.90)),
        )
        _send({"protocol_version": 1, "request_id": request_id, "ok": True, "result": result})
        return
    if command == "cer_review_save":
        manifest = load_representative_manifest(Path(request["manifest"]))
        raw_segments = request.get("segments")
        if raw_segments is not None and not isinstance(raw_segments, list):
            raise ValueError("segments 必须是数组。")
        output = save_cer_review_page(
            manifest,
            page_number=int(request["page_number"]),
            segments=raw_segments,
        )
        _send(
            {
                "protocol_version": 1,
                "request_id": request_id,
                "ok": True,
                "result": {"annotation_path": str(output)},
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
