from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pdf2word_engine.quality import compare_rasters


class QualityTests(unittest.TestCase):
    def test_identical_images_have_perfect_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "page.png"
            Image.new("L", (32, 32), color=180).save(path)
            result = compare_rasters(path, path)

        self.assertTrue(result.same_dimensions)
        self.assertEqual(result.ssim, 1.0)
        self.assertEqual(result.mean_absolute_error, 0.0)

    def test_different_images_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            left = Path(temp) / "left.png"
            right = Path(temp) / "right.png"
            Image.new("L", (32, 32), color=0).save(left)
            Image.new("L", (32, 32), color=255).save(right)
            result = compare_rasters(left, right)

        self.assertLess(result.ssim, 0.1)
        self.assertGreater(result.mean_absolute_error, 200)
