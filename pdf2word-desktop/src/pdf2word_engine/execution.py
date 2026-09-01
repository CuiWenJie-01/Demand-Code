"""Runtime hardware selection for the OCR worker.

The conversion format must not depend on the selected processor: a checkpoint
created by the CPU worker can therefore be resumed by a GPU worker (and vice
versa).  This module keeps the execution decision separate from that durable
conversion configuration.
"""

from __future__ import annotations

import importlib.util
import os
import site
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


_MINIMUM_GPU_TOTAL_MB = 4 * 1024
_MINIMUM_GPU_FREE_MB = 2 * 1024
_DLL_DIRECTORY_HANDLES: list[object] = []
_CONFIGURED_DLL_DIRECTORIES: set[str] = set()


@dataclass(frozen=True, slots=True)
class NvidiaGpu:
    index: int
    name: str
    total_memory_mb: int | None
    free_memory_mb: int | None


@dataclass(frozen=True, slots=True)
class OcrExecutionProfile:
    """One conservative, observable OCR execution decision."""

    requested_device: str
    device: str
    cpu_threads: int | None
    enable_hpi: bool
    reason: str
    gpu: NvidiaGpu | None = None
    fallback_from_gpu: bool = False

    @property
    def uses_gpu(self) -> bool:
        return self.device.startswith("gpu")

    def paddle_options(self) -> dict[str, object]:
        options: dict[str, object] = {"device": self.device}
        if self.uses_gpu:
            # PP-StructureV3 documents this flag as its supported high-performance
            # inference switch.  TensorRT is deliberately not enabled here: it
            # needs a separate compatibility and accuracy qualification.
            options["enable_hpi"] = self.enable_hpi
        elif self.cpu_threads is not None:
            options["cpu_threads"] = self.cpu_threads
        return options

    def focused_paddle_options(self) -> dict[str, object]:
        """Options shared by the lightweight, cropped-text OCR model."""

        options: dict[str, object] = {"device": self.device}
        if not self.uses_gpu and self.cpu_threads is not None:
            options["cpu_threads"] = self.cpu_threads
        return options

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_device": self.requested_device,
            "device": self.device,
            "cpu_threads": self.cpu_threads,
            "enable_hpi": self.enable_hpi,
            "reason": self.reason,
            "fallback_from_gpu": self.fallback_from_gpu,
            "gpu": None
            if self.gpu is None
            else {
                "index": self.gpu.index,
                "name": self.gpu.name,
                "total_memory_mb": self.gpu.total_memory_mb,
                "free_memory_mb": self.gpu.free_memory_mb,
            },
        }


def _recommended_cpu_threads() -> int:
    # Leave room for the desktop UI, renderer and Word writer.  This is a
    # practical ceiling for a 6C/12T, 16 GiB-class machine and scales down on
    # smaller devices.
    logical_cores = os.cpu_count() or 4
    return max(2, min(8, logical_cores - 2))


def _paddle_cuda_available() -> tuple[bool, str]:
    if importlib.util.find_spec("paddle") is None:
        return False, "未安装 PaddlePaddle GPU 运行时。"
    try:
        _configure_nvidia_dll_search_path()
        import paddle  # type: ignore[import-not-found]

        if not paddle.device.is_compiled_with_cuda():
            return False, "当前 PaddlePaddle 是 CPU 运行时。"
        count = int(paddle.device.cuda.device_count())
        if count < 1:
            return False, "PaddlePaddle 未检测到可用的 NVIDIA GPU。"
    except Exception as exc:
        return False, f"GPU 运行时自检失败：{exc}"
    return True, "PaddlePaddle CUDA 运行时可用。"


def _configure_nvidia_dll_search_path() -> None:
    """Expose pip-installed CUDA DLLs to Paddle on Windows.

    NVIDIA's pip packages place DLLs under ``site-packages/nvidia/*/bin``.
    They are not reliably inherited by a frozen sidecar, so configure the
    process before importing Paddle.  The operation is harmless on CPU-only
    machines and on non-Windows systems.
    """

    if os.name != "nt":
        return
    bin_directories: list[Path] = []
    for packages_path in site.getsitepackages():
        nvidia_root = Path(packages_path) / "nvidia"
        if nvidia_root.is_dir():
            bin_directories.extend(path for path in nvidia_root.glob("*/bin") if path.is_dir())
    if not bin_directories:
        return
    current_path = os.environ.get("PATH", "")
    added = [str(path) for path in bin_directories if str(path) not in current_path.split(os.pathsep)]
    if added:
        os.environ["PATH"] = os.pathsep.join([*added, current_path])
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if callable(add_dll_directory):
        for directory in bin_directories:
            directory_text = str(directory)
            if directory_text not in _CONFIGURED_DLL_DIRECTORIES:
                _DLL_DIRECTORY_HANDLES.append(add_dll_directory(directory_text))
                _CONFIGURED_DLL_DIRECTORIES.add(directory_text)


def _as_memory(value: str) -> int | None:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def _query_nvidia_gpus() -> list[NvidiaGpu]:
    """Best-effort VRAM check; the Paddle probe remains the source of truth."""

    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    gpus: list[NvidiaGpu] = []
    for index, line in enumerate(completed.stdout.splitlines()):
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3:
            continue
        gpus.append(NvidiaGpu(index, fields[0], _as_memory(fields[1]), _as_memory(fields[2])))
    return gpus


def _hpi_available() -> bool:
    """PP-StructureV3's HPI backend additionally requires ultra-infer."""

    return importlib.util.find_spec("ultra_infer") is not None


def resolve_ocr_execution_profile(
    requested_device: str | None = "auto",
    *,
    cpu_threads: int | None = None,
    enforce_gpu_preference: bool = False,
    paddle_cuda_available: Callable[[], tuple[bool, str]] = _paddle_cuda_available,
    nvidia_gpu_query: Callable[[], list[NvidiaGpu]] = _query_nvidia_gpus,
    hpi_available: Callable[[], bool] = _hpi_available,
) -> OcrExecutionProfile:
    """Pick an observable OCR device profile.

    Production conversion passes ``enforce_gpu_preference=True``: an explicit
    CPU request then remains only a fallback hint and cannot bypass a usable
    NVIDIA GPU.  Low free VRAM selects conservative GPU execution rather than
    silently abandoning acceleration; the caller may serialize pages or lower
    batches before an audited CPU fallback.
    """

    request = (requested_device or "auto").strip().lower()
    if request not in {"auto", "cpu", "gpu"}:
        raise ValueError("ocr_device 只能是 auto、cpu 或 gpu。")
    threads = cpu_threads if cpu_threads is not None else _recommended_cpu_threads()
    if threads < 1:
        raise ValueError("cpu_threads 必须大于 0。")
    if request == "cpu" and not enforce_gpu_preference:
        return OcrExecutionProfile(request, "cpu", threads, False, "用户指定使用 CPU。")

    cuda_ready, cuda_reason = paddle_cuda_available()
    gpus = nvidia_gpu_query() if cuda_ready else []
    gpu = gpus[0] if gpus else None
    gpu_usable = cuda_ready and (
        gpu is None
        or (
            (gpu.total_memory_mb is None or gpu.total_memory_mb >= _MINIMUM_GPU_TOTAL_MB)
        )
    )
    if gpu_usable:
        hpi_enabled = hpi_available()
        reason = "GPU 优先策略选择 NVIDIA GPU OCR。"
        if request == "cpu":
            reason += "检测到可用 GPU，未采用显式 CPU 请求。"
        if gpu is not None and gpu.free_memory_mb is not None and gpu.free_memory_mb < _MINIMUM_GPU_FREE_MB:
            reason += f"当前空闲显存 {gpu.free_memory_mb} MiB，将采用串行/低批次执行。"
        if not hpi_enabled:
            reason += "未安装 ultra-infer，使用 Paddle 原生 GPU 推理。"
        return OcrExecutionProfile(request, "gpu:0", None, hpi_enabled, reason, gpu)

    if gpu is not None and gpu.total_memory_mb is not None and gpu.total_memory_mb < _MINIMUM_GPU_TOTAL_MB:
        reason = f"GPU 总显存仅 {gpu.total_memory_mb} MiB，低于安全阈值；改用 CPU。"
    else:
        reason = f"{cuda_reason} 改用 CPU。"
    return OcrExecutionProfile(request, "cpu", threads, False, reason, gpu, fallback_from_gpu=request == "gpu")


def is_recoverable_gpu_error(error: BaseException) -> bool:
    """Return whether rerunning the pending pages on CPU is safe and useful."""

    message = str(error).lower()
    markers = ("cuda", "cudnn", "cublas", "gpu", "out of memory", "memory allocation")
    return any(marker in message for marker in markers)
