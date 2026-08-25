from __future__ import annotations

import unittest

from pdf2word_engine.models import PageSize, PdfKind
from pdf2word_engine.ocr import page_model_from_paddle_result


class PaddleResultAdapterTests(unittest.TestCase):
    def test_maps_documented_paddle_region_fields(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {
                        "block_id": 7,
                        "block_label": "text",
                        "block_bbox": [10, 20, 110, 60],
                        "block_order": 2,
                        "block_content": "行测题目",
                        "score": 0.96,
                    }
                ]
            },
            page_index=4,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertEqual(model.page_index, 4)
        self.assertEqual(len(model.blocks), 1)
        self.assertEqual(model.blocks[0].block_id, "7")
        self.assertEqual(model.blocks[0].text, "行测题目")
        self.assertEqual(model.blocks[0].bbox, (10.0, 20.0, 110.0, 60.0))
        self.assertEqual(model.blocks[0].reading_order, 2)
        self.assertAlmostEqual(model.blocks[0].confidence or 0, 0.96)
        self.assertEqual(model.to_dict()["source_type"], "outlined")

    def test_discards_unpositioned_regions_with_warning(self) -> None:
        model = page_model_from_paddle_result(
            {"parsing_res_list": [{"block_label": "text", "block_content": "无法定位"}]},
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.SCANNED,
        )

        self.assertEqual(model.blocks, [])
        self.assertTrue(model.warnings)

    def test_accepts_paddle_37_nested_result_shape(self) -> None:
        model = page_model_from_paddle_result(
            {
                "res": {
                    "parsing_res_list": [
                        {
                            "block_label": "header",
                            "block_bbox": [8, 12, 88, 30],
                            "block_content": "页眉",
                            "block_order": None,
                        }
                    ]
                }
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertEqual(model.blocks[0].text, "页眉")
        self.assertEqual(model.blocks[0].reading_order, 0)
