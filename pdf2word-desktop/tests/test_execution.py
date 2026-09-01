from __future__ import annotations

import unittest
from unittest.mock import patch

from pdf2word_engine.execution import NvidiaGpu, resolve_ocr_execution_profile
from pdf2word_engine.ocr import FocusedOcrPipelineCache


class ExecutionProfileTests(unittest.TestCase):
    def test_explicit_cpu_never_probes_gpu(self) -> None:
        profile = resolve_ocr_execution_profile(
            "cpu",
            cpu_threads=6,
            paddle_cuda_available=lambda: (_ for _ in ()).throw(AssertionError("不应探测 GPU")),
        )

        self.assertEqual(profile.device, "cpu")
        self.assertEqual(profile.paddle_options(), {"device": "cpu", "cpu_threads": 6})

    def test_auto_uses_gpu_when_runtime_and_vram_are_ready(self) -> None:
        gpu = NvidiaGpu(0, "NVIDIA GeForce GTX 1660 SUPER", 6144, 3000)
        profile = resolve_ocr_execution_profile(
            "auto",
            paddle_cuda_available=lambda: (True, "ready"),
            nvidia_gpu_query=lambda: [gpu],
            hpi_available=lambda: True,
        )

        self.assertEqual(profile.device, "gpu:0")
        self.assertTrue(profile.enable_hpi)
        self.assertEqual(profile.gpu, gpu)

    def test_auto_keeps_busy_gpu_with_conservative_execution(self) -> None:
        gpu = NvidiaGpu(0, "NVIDIA GPU", 6144, 1024)
        profile = resolve_ocr_execution_profile(
            "auto",
            cpu_threads=4,
            paddle_cuda_available=lambda: (True, "ready"),
            nvidia_gpu_query=lambda: [gpu],
        )

        self.assertEqual(profile.device, "gpu:0")
        self.assertIn("串行/低批次", profile.reason)

    def test_production_gpu_preference_overrides_explicit_cpu_when_gpu_is_usable(self) -> None:
        gpu = NvidiaGpu(0, "NVIDIA GPU", 6144, 4096)
        profile = resolve_ocr_execution_profile(
            "cpu",
            cpu_threads=4,
            enforce_gpu_preference=True,
            paddle_cuda_available=lambda: (True, "ready"),
            nvidia_gpu_query=lambda: [gpu],
        )

        self.assertEqual(profile.device, "gpu:0")
        self.assertIn("未采用显式 CPU 请求", profile.reason)

    def test_requested_gpu_falls_back_when_cpu_runtime_is_installed(self) -> None:
        profile = resolve_ocr_execution_profile(
            "gpu",
            cpu_threads=4,
            paddle_cuda_available=lambda: (False, "当前 PaddlePaddle 是 CPU 运行时。"),
        )

        self.assertEqual(profile.device, "cpu")
        self.assertTrue(profile.fallback_from_gpu)


class FocusedPipelineCacheTests(unittest.TestCase):
    def test_constructs_lightweight_model_once(self) -> None:
        cache = FocusedOcrPipelineCache(device="cpu", cpu_threads=4)
        pipeline = object()
        with patch("pdf2word_engine.ocr._focused_text_ocr_pipeline", return_value=pipeline) as create:
            self.assertIs(cache.get(), pipeline)
            self.assertIs(cache.get(), pipeline)

        create.assert_called_once_with(device="cpu", cpu_threads=4)
