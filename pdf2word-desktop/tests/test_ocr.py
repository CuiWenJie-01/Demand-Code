from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pdf2word_engine.layout_profiles import CN_EXAM_QUESTION_V1
from pdf2word_engine.models import PageBlock, PageModel, PageSize, PdfKind
from pdf2word_engine.ocr import (
    materialize_visual_fallbacks,
    merge_semantic_callout_lines,
    page_model_from_paddle_result,
)


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

    def test_uses_line_level_ocr_for_text_layout_regions(self) -> None:
        model = page_model_from_paddle_result(
            {
                "res": {
                    "parsing_res_list": [
                        {"block_id": "body", "block_label": "text", "block_bbox": [0, 0, 100, 100], "block_content": "段落"},
                        {"block_id": "title", "block_label": "paragraph_title", "block_bbox": [0, 110, 100, 130], "block_content": "标题"},
                    ],
                    "overall_ocr_res": {
                        "rec_texts": ["第一行", "第二行", "标题"],
                        "rec_boxes": [[1, 10, 90, 25], [1, 40, 90, 55], [1, 112, 90, 126]],
                        "rec_scores": [0.9, 0.8, 0.99],
                    },
                }
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertEqual([block.text for block in model.blocks], ["第一行", "第二行", "标题"])
        self.assertEqual([block.block_type for block in model.blocks], ["text_line", "text_line", "paragraph_title"])

    def test_preserves_question_accent_answer_blank_and_talk_callouts(self) -> None:
        model = page_model_from_paddle_result(
            {
                "res": {
                    "parsing_res_list": [
                        {"block_id": "question", "block_label": "text", "block_bbox": [100, 100, 900, 220], "block_content": "题目"},
                        {"block_id": "analysis", "block_label": "text", "block_bbox": [100, 300, 900, 460], "block_content": "谈解析正文"},
                        {"block_id": "answer", "block_label": "paragraph_title", "block_bbox": [150, 500, 360, 550], "block_content": "谈答案A"},
                        {"block_id": "hint", "block_label": "text", "block_bbox": [100, 600, 900, 680], "block_content": "提示正文"},
                        {"block_id": "index", "block_label": "paragraph_title", "block_bbox": [200, 720, 700, 740], "block_content": "指数"},
                        {"block_id": "second-analysis-line", "block_label": "text", "block_bbox": [100, 770, 900, 850], "block_content": "第二行解析"},
                    ],
                    "overall_ocr_res": {
                        "rec_texts": [
                            "7.（2018年国考）题干",
                            "(",
                            "）",
                            "谈",
                            "解析正文",
                            "谈答案A",
                            "S",
                            "提示正文",
                            "第二行解析",
                        ],
                        "rec_boxes": [
                            [110, 110, 700, 130],
                            [820, 190, 840, 210],
                            [870, 190, 890, 210],
                            [150, 290, 195, 340],
                            [200, 310, 850, 330],
                            [150, 505, 300, 535],
                            [165, 592, 185, 608],
                            [100, 640, 800, 660],
                            [100, 790, 800, 810],
                        ],
                    },
                    "semantic_line_ocr": [
                        {"layout_block_id": "hint", "text": "本题考查的是数字计算", "bbox": [280, 605, 700, 630], "score": 0.99},
                        {"layout_block_id": "second-analysis-line", "text": "根据题意可知", "bbox": [270, 760, 700, 785], "score": 0.99},
                    ],
                }
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        by_text = {block.text: block for block in model.blocks if block.text}
        self.assertEqual(by_text["7.（2018年国考）题干"].style["semantic_role"], "question_heading")
        self.assertEqual(by_text["7.（2018年国考）题干"].style["accent_length"], len("7.（2018年国考）"))
        self.assertEqual(by_text["7.（2018年国考）题干"].style["bold_prefix_length"], 2)
        self.assertTrue(by_text["7.（2018年国考）题干"].style["justify_to_bbox"])
        self.assertEqual(by_text["（"].style["semantic_role"], "answer_blank")
        self.assertEqual(by_text["）"].style["semantic_role"], "answer_blank")
        self.assertEqual(by_text["正文"].style["semantic_role"], "callout_body")
        self.assertTrue(by_text["正文"].style["justify_to_bbox"])
        self.assertEqual(by_text["A"].style["semantic_role"], "callout_answer")
        answer_block = by_text["A"]
        answer_tag = next(block for block in model.blocks if block.block_id.startswith("answer-talk-badge"))
        self.assertEqual(answer_block.bbox[1] - answer_tag.bbox[1], 12)
        self.assertEqual(answer_tag.bbox[2] - answer_tag.bbox[0], CN_EXAM_QUESTION_V1.talk_badge_width_px)
        self.assertEqual(by_text["本题考查的是数字计算"].style["source"], "focused PaddleOCR line")
        self.assertEqual(by_text["根据题意可知"].style["source"], "focused PaddleOCR line")
        self.assertTrue(by_text["根据题意可知"].style["justify_to_bbox"])
        editable_labels = [block for block in model.blocks if block.style.get("semantic_role") == "callout_label"]
        self.assertGreaterEqual(len(editable_labels), 2)

    def test_restores_missing_second_answer_parenthesis(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "question", "block_label": "text", "block_bbox": [100, 100, 900, 220], "block_content": "题目"}
                ],
                "overall_ocr_res": {"rec_texts": ["题干", "("], "rec_boxes": [[110, 110, 700, 130], [820, 190, 840, 210]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        parentheses = [block for block in model.blocks if block.style.get("semantic_role") == "answer_blank"]
        self.assertEqual([block.text for block in parentheses], ["（", "）"])
        self.assertEqual(parentheses[1].bbox[0] - parentheses[0].bbox[0], 54)

    def test_drops_empty_line_when_callout_tag_consumes_its_source_box(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "callout", "block_label": "text", "block_bbox": [100, 300, 300, 360], "block_content": "谈解析"}
                ],
                "overall_ocr_res": {
                    "rec_texts": ["谈", "解析"],
                    "rec_boxes": [[100, 290, 150, 340], [160, 310, 200, 330]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertFalse(any(not block.text for block in model.blocks if block.block_type == "text_line"))
        self.assertFalse(any(block.bbox[2] <= block.bbox[0] for block in model.blocks))

    def test_fragmented_formula_is_collapsed_to_one_image_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            Image.new("RGB", (1000, 1400), color="white").save(image)
            model = PageModel(
                4,
                0,
                PageSize(500, 700),
                PdfKind.OUTLINED,
                blocks=[
                    PageBlock("numerator", "text_line", (800, 900, 870, 920), 1, 1, text="26962.20"),
                    PageBlock("operator", "text_line", (875, 905, 895, 920), 2, 2, text="≈"),
                    PageBlock("denominator", "text_line", (900, 910, 960, 930), 3, 3, text="1.133"),
                    PageBlock("body", "text_line", (100, 940, 700, 960), 4, 4, text="普通正文"),
                ],
            )
            materialize_visual_fallbacks(model, image, root / "regions")

        self.assertEqual([block.block_id for block in model.blocks if block.block_type == "formula"], ["formula-fallback-1"])
        self.assertTrue(next(block for block in model.blocks if block.block_type == "formula").asset_path)
        self.assertEqual(next(block for block in model.blocks if block.block_id == "body").text, "普通正文")

    def test_combines_talk_hint_image_with_pink_label_and_leaves_body_editable(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "hint-icon", "block_label": "image", "block_bbox": [100, 100, 142, 138], "block_content": ""},
                    {"block_id": "hint", "block_label": "text", "block_bbox": [145, 110, 400, 130], "block_content": "提示正文"},
                ],
                "overall_ocr_res": {"rec_texts": ["提示正文"], "rec_boxes": [[145, 110, 400, 130]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        tag = next(block for block in model.blocks if block.text == "提示")
        body = next(block for block in model.blocks if block.block_id == "hint-line-1")
        self.assertEqual(body.text, "正文")
        self.assertEqual(tag.bbox[2] - tag.bbox[0], CN_EXAM_QUESTION_V1.callout_label_width_px)
        self.assertGreaterEqual(body.bbox[0], tag.bbox[2])

    def test_combines_standalone_talk_label_and_styles_following_body(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "badge", "block_label": "image", "block_bbox": [100, 100, 150, 150], "block_content": "谈"},
                    {"block_id": "hint", "block_label": "text", "block_bbox": [150, 100, 900, 180], "block_content": "提示正文"},
                ],
                "overall_ocr_res": {
                    "rec_texts": ["提示", "正文内容"],
                    "rec_boxes": [[160, 110, 220, 132], [270, 112, 820, 135]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        tag = next(block for block in model.blocks if block.text == "提示")
        body = next(block for block in model.blocks if block.text == "正文内容")
        self.assertEqual(tag.style["semantic_role"], "callout_label")
        self.assertGreater(body.bbox[0], tag.bbox[2])
        self.assertEqual(body.style["semantic_role"], "callout_body")
        self.assertTrue(body.style["justify_to_bbox"])
        self.assertEqual(body.style["semantic_role"], "callout_body")

    def test_combines_talk_answer_image_with_editable_answer_value(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "answer-icon", "block_label": "image", "block_bbox": [100, 100, 142, 138], "block_content": ""},
                    {"block_id": "answer", "block_label": "text", "block_bbox": [145, 110, 260, 135], "block_content": "答案D"},
                ],
                "overall_ocr_res": {"rec_texts": ["答案D"], "rec_boxes": [[145, 110, 260, 135]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        tag = next(block for block in model.blocks if block.text == "答案")
        answer = next(block for block in model.blocks if block.text == "D")
        self.assertEqual(answer.style["semantic_role"], "callout_answer")
        self.assertGreaterEqual(answer.bbox[0], tag.bbox[2])

    def test_repairs_badge_with_trailing_ocr_artifact_and_misread_answer_label(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "answer-icon", "block_label": "image", "block_bbox": [100, 100, 158, 150], "block_content": "谈I"},
                    {"block_id": "answer", "block_label": "paragraph_title", "block_bbox": [165, 112, 245, 140], "block_content": "名B"},
                ],
                "overall_ocr_res": {"rec_texts": ["谈", "B"], "rec_boxes": [[101, 101, 158, 150], [220, 115, 242, 138]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertFalse(any(block.text == "谈I" for block in model.blocks))
        tag = next(block for block in model.blocks if block.text == "答案")
        answer = next(block for block in model.blocks if block.text == "B")
        self.assertEqual(answer.style["semantic_role"], "callout_answer")
        self.assertGreaterEqual(answer.bbox[0], tag.bbox[2])

    def test_marks_solution_before_talk_answer_as_right_aligned(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "solution", "block_label": "text", "block_bbox": [100, 100, 900, 170], "block_content": "解析说明"},
                    {"block_id": "answer", "block_label": "paragraph_title", "block_bbox": [100, 180, 240, 220], "block_content": "谈答案D"},
                ],
                "overall_ocr_res": {"rec_texts": ["解析说明第一行内容足够长一些", "C项当选", "谈答案D"], "rec_boxes": [[100, 105, 900, 125], [100, 140, 180, 160], [100, 180, 240, 220]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        solution = next(block for block in model.blocks if block.block_id == "solution-line-1")
        self.assertEqual(solution.style["semantic_role"], "solution_body")
        self.assertTrue(solution.style["justify_to_bbox"])
        short_solution = next(block for block in model.blocks if block.text == "C项当选")
        self.assertGreaterEqual(short_solution.bbox[2] - short_solution.bbox[0], 128)
        self.assertEqual(short_solution.style["semantic_role"], "solution_short_body")
        self.assertNotIn("justify_to_bbox", short_solution.style)

    def test_splits_inline_talk_answer_into_image_tag_and_editable_value(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "answer", "block_label": "text", "block_bbox": [100, 100, 280, 145], "block_content": "谈答案B"}
                ],
                "overall_ocr_res": {"rec_texts": ["谈答案B"], "rec_boxes": [[100, 100, 280, 145]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        tag = next(block for block in model.blocks if block.text == "答案")
        answer = next(block for block in model.blocks if block.text == "B")
        self.assertEqual(answer.style["semantic_role"], "callout_answer")
        self.assertGreaterEqual(answer.bbox[0], tag.bbox[2])

    def test_recovers_missing_prompt_after_inline_talk_answer(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "answer", "block_label": "text", "block_bbox": [100, 100, 240, 140], "block_content": "谈答案B"},
                    {"block_id": "hint", "block_label": "text", "block_bbox": [100, 170, 850, 240], "block_content": "提示正文"},
                ],
                "overall_ocr_res": {"rec_texts": ["谈答案B", "正文"], "rec_boxes": [[100, 100, 240, 140], [160, 200, 600, 220]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        prompt_tag = next(block for block in model.blocks if block.block_id.startswith("hint-missing-talk-callout"))
        self.assertEqual(prompt_tag.block_type, "talk_badge_image")
        self.assertIn("recovery_crop_bbox", prompt_tag.style)
        self.assertEqual(prompt_tag.bbox[2] - prompt_tag.bbox[0], CN_EXAM_QUESTION_V1.talk_badge_width_px)

    def test_splits_single_ocr_parenthesis_pair_without_adding_a_second_pair(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "question", "block_label": "text", "block_bbox": [100, 100, 900, 180], "block_content": "16.题目"}
                ],
                "overall_ocr_res": {
                    "rec_texts": ["16.题目", "( )"],
                    "rec_boxes": [[100, 100, 800, 120], [824, 140, 900, 160]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        parentheses = [block for block in model.blocks if block.style.get("semantic_role") == "answer_blank"]
        self.assertEqual([block.text for block in parentheses], ["（", "）"])

    def test_recovers_missing_prompt_after_paragraph_title_answer(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "answer", "block_label": "paragraph_title", "block_bbox": [100, 100, 240, 140], "block_content": "谈答案D"},
                    {"block_id": "hint", "block_label": "text", "block_bbox": [100, 165, 850, 230], "block_content": "走过的路程相同"},
                ],
                "overall_ocr_res": {"rec_texts": ["谈答案D", "走过的路程相同"], "rec_boxes": [[100, 100, 240, 140], [160, 200, 600, 220]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        prompt_tag = next(block for block in model.blocks if block.block_id.startswith("hint-missing-talk-callout"))
        self.assertEqual(prompt_tag.block_type, "talk_badge_image")
        self.assertEqual(prompt_tag.style["layout_block_id"], "hint")

    def test_recovers_missing_prompt_after_standalone_answer_value(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "answer", "block_label": "paragraph_title", "block_bbox": [100, 100, 220, 140], "block_content": "D"},
                    {"block_id": "hint", "block_label": "text", "block_bbox": [100, 165, 850, 230], "block_content": "进而计算概率"},
                ],
                "overall_ocr_res": {"rec_texts": ["D", "进而计算概率"], "rec_boxes": [[100, 100, 220, 140], [160, 200, 600, 220]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        prompt_tag = next(block for block in model.blocks if block.block_id.startswith("hint-missing-talk-callout"))
        self.assertEqual(prompt_tag.block_type, "talk_badge_image")
        self.assertEqual(prompt_tag.style["layout_block_id"], "hint")

    def test_keeps_recovered_analysis_label_in_image_tag(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "index", "block_label": "paragraph_title", "block_bbox": [160, 100, 500, 130], "block_content": "5\n易考指数"},
                    {"block_id": "analysis", "block_label": "text", "block_bbox": [120, 165, 900, 240], "block_content": "解析正文"},
                ],
                "overall_ocr_res": {"rec_texts": ["正文"], "rec_boxes": [[220, 200, 800, 220]]},
                "semantic_line_ocr": [
                    {"layout_block_id": "analysis", "text": "解析 根据题意", "bbox": [220, 170, 800, 190], "score": 0.99}
                ],
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        analysis = next(block for block in model.blocks if block.text == "根据题意")
        tag = next(block for block in model.blocks if block.block_type == "talk_badge_image")
        self.assertGreater(analysis.bbox[0], tag.bbox[2])

    def test_rebuilds_talk_tag_when_only_pink_label_is_recognised(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "hint", "block_label": "text", "block_bbox": [160, 200, 900, 260], "block_content": "提示正文"}
                ],
                "overall_ocr_res": {"rec_texts": ["提示正文"], "rec_boxes": [[215, 205, 800, 228]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        tag = next(block for block in model.blocks if block.text == "提示")
        body = next(block for block in model.blocks if block.text == "正文")
        self.assertEqual(body.text, "正文")
        self.assertGreaterEqual(body.bbox[0], tag.bbox[2])

    def test_gives_short_callout_continuation_enough_horizontal_room(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "hint", "block_label": "text", "block_bbox": [100, 200, 900, 300], "block_content": "提示正文"}
                ],
                "overall_ocr_res": {
                    "rec_texts": ["谈", "提示正文", "洞察力。"],
                    "rec_boxes": [[100, 190, 150, 240], [160, 205, 850, 228], [100, 250, 165, 270]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        continuation = next(block for block in model.blocks if block.text == "洞察力。")
        self.assertGreaterEqual(continuation.bbox[2] - continuation.bbox[0], 100)
        self.assertTrue(continuation.style["justify_to_bbox"])

    def test_merges_adjacent_long_line_fragments_before_word_rendering(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "analysis", "block_label": "text", "block_bbox": [100, 200, 900, 300], "block_content": "解析正文"}
                ],
                "overall_ocr_res": {
                    "rec_texts": ["谈", "解析这是一段已经识别的长句，", "排除", "A", "、B三项。"],
                    "rec_boxes": [
                        [100, 190, 150, 240],
                        [160, 205, 600, 228],
                        [604, 205, 645, 228],
                        [648, 202, 670, 232],
                        [672, 205, 760, 228],
                    ],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        merged = next(block for block in model.blocks if block.block_id.endswith("merged-fragments"))
        self.assertEqual(merged.text, "这是一段已经识别的长句，排除A、B三项。")
        self.assertGreaterEqual(merged.bbox[2] - merged.bbox[0], 550)
        self.assertEqual(merged.style["merged_prefix_text"], "这是一段已经识别的长句，")

    def test_restores_missing_option_figure_strip_above_a_to_d(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (1000, 1400), color="white")
            source.putpixel((250, 180), (0, 0, 0))
            source.save(image)
            model = PageModel(
                4,
                0,
                PageSize(500, 700),
                PdfKind.OUTLINED,
                blocks=[
                    PageBlock("a", "text_line", (490, 275, 510, 295), 1, 1, text="A"),
                    PageBlock("b", "text_line", (585, 275, 605, 295), 2, 2, text="B"),
                    PageBlock("c", "text_line", (680, 275, 700, 295), 3, 3, text="C"),
                    PageBlock("d", "text_line", (775, 275, 795, 295), 4, 4, text="D"),
                ],
            )
            materialize_visual_fallbacks(model, image, root / "regions")

            strip = next(block for block in model.blocks if block.block_id == "option-figure-strip-1")
            self.assertTrue(strip.asset_path)
            with Image.open(strip.asset_path) as crop:
                self.assertEqual(crop.getpixel((0, 20)), (0, 0, 0))
            self.assertTrue(next(block for block in model.blocks if block.block_id == "option-figure-net-bottom-rule-1").asset_path)

    def test_marks_table_intro_as_right_aligned_editable_prose(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "table", "block_label": "table", "block_bbox": [100, 100, 900, 220], "block_content": "<table/>"},
                    {"block_id": "intro", "block_label": "text", "block_bbox": [100, 230, 900, 310], "block_content": "表格下说明"},
                ],
                "overall_ocr_res": {"rec_texts": ["表格下说明"], "rec_boxes": [[100, 240, 900, 260]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        intro = next(block for block in model.blocks if block.block_id == "intro-line-1")
        self.assertEqual(intro.style["semantic_role"], "table_intro_body")
        self.assertTrue(intro.style["justify_to_bbox"])

    def test_restores_both_answer_parentheses_when_numbered_question_has_none(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [{"block_id": "question", "block_label": "text", "block_bbox": [100, 100, 900, 250], "block_content": "13.题目"}],
                "overall_ocr_res": {"rec_texts": ["13.题目"], "rec_boxes": [[100, 100, 880, 120]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        blanks = [block for block in model.blocks if block.style.get("semantic_role") == "answer_blank"]
        self.assertEqual([block.text for block in blanks], ["（", "）"])
        self.assertEqual(blanks[1].bbox[0] - blanks[0].bbox[0], CN_EXAM_QUESTION_V1.answer_pair_gap_px)
        self.assertNotIn("accent_length", blanks[0].style)
        self.assertNotIn("bold_prefix_length", blanks[0].style)

    def test_does_not_duplicate_answer_pair_when_a_neighboring_layout_has_it(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "heading", "block_label": "text", "block_bbox": [100, 100, 600, 150], "block_content": "12.题干"},
                    {"block_id": "answer", "block_label": "text", "block_bbox": [820, 100, 920, 150], "block_content": "（ ）"},
                ],
                "overall_ocr_res": {
                    "rec_texts": ["12.题干", "( )"],
                    "rec_boxes": [[100, 110, 520, 135], [840, 110, 900, 135]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        blanks = [block for block in model.blocks if block.style.get("semantic_role") == "answer_blank"]
        self.assertEqual([block.text for block in blanks], ["（", "）"])

    def test_aligns_a_missing_question_blank_to_the_previous_question(self) -> None:
        model = page_model_from_paddle_result(
            {
                "width": 1000,
                "parsing_res_list": [
                    {"block_id": "q1", "block_label": "text", "block_bbox": [100, 100, 500, 140], "block_content": "11.题干"},
                    {"block_id": "a1", "block_label": "text", "block_bbox": [800, 100, 900, 140], "block_content": "（ ）"},
                    {"block_id": "q2", "block_label": "text", "block_bbox": [100, 300, 500, 340], "block_content": "12.题干"},
                ],
                "overall_ocr_res": {
                    "rec_texts": ["11.题干", "( )", "12.题干"],
                    "rec_boxes": [[100, 105, 450, 135], [820, 105, 890, 135], [100, 305, 450, 335]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        blanks = [block for block in model.blocks if block.style.get("semantic_role") == "answer_blank"]
        self.assertEqual(len(blanks), 4)
        self.assertEqual(blanks[2].bbox[0], 820)

    def test_recovers_analysis_badge_and_editable_label_after_an_index_row(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "index", "block_label": "text", "block_bbox": [150, 100, 800, 130], "block_content": "易错指数"},
                    {"block_id": "index-badge", "block_label": "image", "block_bbox": [100, 90, 150, 140], "block_content": "谈"},
                    {"block_id": "analysis", "block_label": "text", "block_bbox": [100, 165, 900, 240], "block_content": "正文"},
                ],
                "overall_ocr_res": {
                    "rec_texts": ["易错指数★★★☆☆", "易考指数★★★★☆", "分析正文"],
                    "rec_boxes": [[260, 105, 470, 128], [520, 105, 740, 128], [180, 200, 800, 225]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        badge = next(block for block in model.blocks if block.block_id.startswith("analysis-missing-talk-callout"))
        label = next(block for block in model.blocks if block.text == "解析")
        self.assertEqual(badge.block_type, "talk_badge_image")
        self.assertEqual(label.style["semantic_role"], "callout_label")
        self.assertGreaterEqual(badge.style["recovery_crop_bbox"][0], label.bbox[2])

    def test_rebuilds_talk_index_title_as_editable_text(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "badge", "block_label": "image", "block_bbox": [100, 100, 150, 150], "block_content": "谈"},
                    {"block_id": "index", "block_label": "paragraph_title", "block_bbox": [150, 100, 800, 150], "block_content": "谈易错指数"},
                ],
                "overall_ocr_res": {
                    "rec_texts": ["谈", "易错指数⭐⭐☆☆", "易考指数⭐⭐⭐⭐☆"],
                    "rec_boxes": [[100, 100, 150, 150], [280, 110, 470, 135], [520, 110, 740, 135]],
                },
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        badge = next(block for block in model.blocks if block.block_id == "badge")
        self.assertEqual(badge.block_type, "talk_badge_image")
        self.assertIsNone(badge.text)
        text = {block.text for block in model.blocks if block.block_type == "text_line"}
        self.assertIn("指数", text)
        self.assertIn("易错指数★★☆☆☆", text)
        self.assertIn("易考指数★★★★☆", text)

    def test_table_fallback_keeps_bottom_border_pixel(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (12, 12), color="white")
            # The outer rule sits two pixels below the OCR box, which mirrors
            # PP-Structure's common text-baseline table measurement.
            source.putpixel((6, 8), (0, 0, 0))
            source.save(image)
            model = PageModel(
                4,
                0,
                PageSize(500, 700),
                PdfKind.OUTLINED,
                blocks=[PageBlock("table", "table", (2, 2, 6, 6), 1, 1, text="<table/>")],
            )
            materialize_visual_fallbacks(model, image, root / "regions")
            with Image.open(next((root / "regions").glob("table.png"))) as crop:
                self.assertEqual(crop.getpixel((4, 6)), (0, 0, 0))
            self.assertEqual(model.blocks[0].bbox[3], 9)

    def test_classifies_editable_rating_stars_from_source_ink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (300, 200), color="white")
            for index in range(5):
                left = 40 + index * 29
                size = 10 if index < 3 else 3
                for x in range(left + 5, left + 5 + size):
                    for y in range(55, 55 + size):
                        source.putpixel((x, y), (239, 22, 139))
            source.save(image)
            model = PageModel(
                4,
                0,
                PageSize(300, 200),
                PdfKind.OUTLINED,
                blocks=[
                    PageBlock(
                        "rating",
                        "text_line",
                        (40, 50, 185, 75),
                        1,
                        1,
                        text="易错指数★★★★★",
                        style={"semantic_role": "callout_index"},
                    )
                ],
            )

            materialize_visual_fallbacks(model, image, root / "regions")

            self.assertEqual(model.blocks[0].text, "易错指数★★★☆☆")

    def test_talk_callout_fallback_keeps_right_and_bottom_antialiasing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (12, 12), color="white")
            source.putpixel((6, 6), (255, 0, 128))
            source.save(image)
            model = PageModel(
                4,
                0,
                PageSize(500, 700),
                PdfKind.OUTLINED,
                blocks=[PageBlock("hint", "talk_badge_image", (2, 2, 6, 6), 1, 1)],
            )
            materialize_visual_fallbacks(model, image, root / "regions")
            with Image.open(next((root / "regions").glob("hint.png"))) as crop:
                self.assertEqual(crop.getpixel((4, 4)), (255, 0, 128))
            self.assertEqual(model.blocks[0].bbox, (2, 2, 8.0, 8.0))

    def test_does_not_restore_large_neutral_gray_central_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (1000, 1400), color="white")
            # This pale, neutral rectangle stands in for the large low-contrast
            # diagonal mark omitted by the layout detector.
            for x in range(300, 720):
                for y in range(560, 920):
                    source.putpixel((x, y), (230, 230, 231))
            source.save(image)
            model = PageModel(
                4,
                0,
                PageSize(500, 700),
                PdfKind.OUTLINED,
                blocks=[PageBlock("body", "text_line", (100, 600, 800, 630), 1, 1, text="可编辑正文")],
            )

            materialize_visual_fallbacks(model, image, root / "regions")

            self.assertFalse(any(block.block_type == "watermark" for block in model.blocks))
            self.assertFalse((root / "regions" / "source-watermark.png").exists())

    def test_ignores_small_neutral_gray_marks_when_detecting_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (1000, 1400), color="white")
            for x in range(400, 480):
                for y in range(600, 680):
                    source.putpixel((x, y), (230, 230, 231))
            source.save(image)
            model = PageModel(4, 0, PageSize(500, 700), PdfKind.OUTLINED)

            materialize_visual_fallbacks(model, image, root / "regions")

            self.assertFalse(any(block.block_type == "watermark" for block in model.blocks))

    def test_falls_back_to_source_image_for_unreadable_vertical_sidebar(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "page.png"
            source = Image.new("RGB", (1000, 1400), color="white")
            source.putpixel((970, 1210), (255, 0, 128))
            source.save(image)
            model = PageModel(
                4,
                0,
                PageSize(500, 700),
                PdfKind.OUTLINED,
                blocks=[
                    PageBlock("chapter", "aside_text", (940, 1200, 965, 1340), 10, 10, text=""),
                    PageBlock("partial", "text_line", (970, 1200, 990, 1230), 11, 11, text="第"),
                    PageBlock("page", "number", (950, 1360, 990, 1380), 12, 12, text="1151"),
                ],
            )

            materialize_visual_fallbacks(model, image, root / "regions")

            fallback = next(block for block in model.blocks if block.block_id == "unreadable-sidebar")
            self.assertTrue(fallback.asset_path)
            self.assertFalse(any(block.block_id in {"chapter", "partial", "page"} for block in model.blocks))
            with Image.open(fallback.asset_path) as asset:
                self.assertEqual(asset.getpixel((85, 30)), (255, 0, 128))

    def test_merges_new_callout_recovery_without_losing_cached_lines(self) -> None:
        cached = [{"layout_block_id": "hint-1", "text": "第一行", "bbox": [1, 2, 3, 4], "score": 0.9}]
        retried = [
            {"layout_block_id": "hint-1", "text": "第一行", "bbox": [1, 2, 3, 4], "score": 0.99},
            {"layout_block_id": "hint-2", "text": "新恢复首行", "bbox": [5, 6, 7, 8], "score": 0.98},
        ]

        merged = merge_semantic_callout_lines(cached, retried)

        self.assertEqual([line["text"] for line in merged], ["第一行", "新恢复首行"])

    def test_bare_question_number_uses_pink_bold_question_prefix(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [{"block_id": "question", "block_label": "text", "block_bbox": [100, 100, 900, 140], "block_content": "4.题目"}],
                "overall_ocr_res": {"rec_texts": ["4.2016年全年铁路货物"], "rec_boxes": [[100, 100, 900, 120]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        block = model.blocks[0]
        self.assertEqual(block.style["semantic_role"], "question_heading")
        self.assertEqual(block.style["accent_length"], 2)
        self.assertEqual(block.style["bold_prefix_length"], 2)

    def test_long_decimal_at_line_start_is_not_a_question_number(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [{"block_id": "body", "block_label": "text", "block_bbox": [100, 100, 900, 140], "block_content": "数值"}],
                "overall_ocr_res": {"rec_texts": ["26962.20亿吨公里"], "rec_boxes": [[100, 100, 900, 120]]},
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertNotEqual(model.blocks[0].style.get("semantic_role"), "question_heading")

    def test_builds_vertical_chapter_sidebar_as_editable_components(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "chapter", "block_label": "aside_text", "block_bbox": [996, 1219, 1017, 1349], "block_content": "第一章解题方法"},
                    {"block_id": "page", "block_label": "number", "block_bbox": [979, 1387, 1016, 1403], "block_content": "005"},
                ]
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertEqual([block.block_type for block in model.blocks], ["sidebar_vertical_text", "sidebar_page_number", "sidebar_accent_rule"])
        self.assertEqual(model.blocks[0].text, "第一章解题方法")
        self.assertEqual(model.blocks[1].text, "005")
        self.assertEqual(model.blocks[1].bbox, (979.0, 1385.0, 1036.0, 1408.0))
        self.assertEqual(model.blocks[2].bbox, (1021.0, 1384.0, 1024.0, 1409.0))

    def test_discards_spurious_fourth_digit_in_three_digit_sidebar_page_number(self) -> None:
        model = page_model_from_paddle_result(
            {
                "parsing_res_list": [
                    {"block_id": "chapter", "block_label": "aside_text", "block_bbox": [996, 1219, 1017, 1349], "block_content": "第一章图形推理"},
                    {"block_id": "page", "block_label": "number", "block_bbox": [979, 1387, 1016, 1403], "block_content": "1151"},
                ]
            },
            page_index=0,
            size=PageSize(595, 842),
            source_type=PdfKind.OUTLINED,
        )

        self.assertEqual(next(block for block in model.blocks if block.block_type == "sidebar_page_number").text, "115")
