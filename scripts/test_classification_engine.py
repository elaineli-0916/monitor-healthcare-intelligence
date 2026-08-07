#!/usr/bin/env python3
"""Offline tests for the three-stage dashboard classifier."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from classification_engine import (
    DEFAULT_MODEL_PATH,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_SILVER_PATH,
    ClassificationEngine,
)


SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_ROOT = DEFAULT_RUNTIME_ROOT


class ContractAndRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ClassificationEngine(
            enable_semantic=False,
            enable_llm=False,
        )

    def test_contract_has_expected_taxonomy(self) -> None:
        summary = self.engine.contract_summary()
        self.assertEqual(summary["schema_version"], "1.0")
        self.assertEqual(summary["parents"], 4)
        self.assertEqual(summary["children"], 25)
        self.assertGreater(summary["rules"], 40)

    def test_explicit_nucleic_drug_uses_rule_layer(self) -> None:
        result = self.engine.classify("siRNA降脂药III期达到主要终点")
        self.assertEqual(
            result.level_2_category,
            "1.2 生物药（抗体/蛋白/核酸/ADC/XDC偶联药物）",
        )
        self.assertEqual(result.classification_method, "rule")

    def test_adc_rule_is_part_of_biologic_drug_category(self) -> None:
        result = self.engine.classify(
            "ADC药王Enhertu半年销售近30亿美元",
            "摘要同时提到小分子药物研发。",
        )
        self.assertEqual(
            result.level_2_category,
            "1.2 生物药（抗体/蛋白/核酸/ADC/XDC偶联药物）",
        )
        self.assertEqual(result.classification_method, "rule")

    def test_cxo_moved_under_innovative_drugs(self) -> None:
        result = self.engine.classify("CDMO企业扩建生产基地")
        self.assertEqual(result.level_1_category, "1. 创新药")
        self.assertEqual(result.level_2_category, "1.4 医药CXO（CRO/CDMO/CSO）")
        self.assertEqual(result.classification_method, "rule")

    def test_synthetic_biology_category_is_available(self) -> None:
        result = self.engine.classify("合成生物学平台完成新一轮融资")
        self.assertEqual(result.level_2_category, "1.6 合成生物学")
        self.assertEqual(result.classification_method, "rule")

    def test_sleep_and_hearing_are_separate_categories(self) -> None:
        sleep = self.engine.classify("睡眠健康管理平台发布新产品")
        hearing = self.engine.classify("助听器企业完成渠道扩张")
        self.assertEqual(sleep.level_2_category, "4.8 睡眠")
        self.assertEqual(hearing.level_2_category, "4.7 听力")
        self.assertEqual(sleep.classification_method, "rule")
        self.assertEqual(hearing.classification_method, "rule")

    def test_parent_rule_is_not_overridden_by_summary_keyword(self) -> None:
        result = self.engine.classify(
            "11家创新药公司完成新一轮融资",
            "其中包含重组融合蛋白和治疗性疫苗管线。",
        )
        self.assertEqual(result.level_2_category, "1. 创新药")

    def test_conflicting_title_rules_do_not_use_first_match(self) -> None:
        result = self.engine.classify_rule("CAR-T与mRNA联合治疗研究", "")
        self.assertIsNone(result)

    def test_explicit_veterinary_news_stays_in_open_set(self) -> None:
        result = self.engine.classify("宠物兽药公司宣布新产品获批")
        self.assertEqual(result.level_2_category, "其他/综合")
        self.assertEqual(result.classification_method, "rule")

    def test_source_placeholder_stays_in_open_set(self) -> None:
        result = self.engine.classify(
            "[澳大利亚] TGA 批准决定",
            "官方页面可访问，内容需人工审阅或后续解析。",
        )
        self.assertEqual(result.level_2_category, "其他/综合")
        self.assertEqual(result.classification_model_revision, "placeholder-policy:1.0")


class LlmFallbackTests(unittest.TestCase):
    def test_valid_injected_llm_result_is_accepted(self) -> None:
        engine = ClassificationEngine(
            enable_semantic=False,
            llm_classifier=lambda payload: {
                "level_2_category": "3.1 专科医院/连锁诊所",
                "confidence": 0.82,
                "reason": "新闻核心是专科诊疗网络扩张。",
                "_model": "test-llm",
            },
        )
        result = engine.classify("某医疗机构宣布新业务")
        self.assertEqual(result.classification_method, "llm")
        self.assertEqual(result.level_1_category, "3. 医疗服务")
        self.assertEqual(result.classification_model_revision, "test-llm")

    def test_invalid_llm_label_falls_back_to_other(self) -> None:
        engine = ClassificationEngine(
            enable_semantic=False,
            llm_classifier=lambda payload: {
                "level_2_category": "不存在的类别",
                "confidence": 1,
                "reason": "非法输出",
            },
        )
        result = engine.classify("无法判断的边界新闻")
        self.assertEqual(result.level_2_category, "其他/综合")
        self.assertEqual(result.classification_method, "other")


@unittest.skipUnless(
    DEFAULT_MODEL_PATH.exists() and DEFAULT_SILVER_PATH.exists(),
    "external SentenceTransformer model or silver labels are unavailable",
)
class SilverAndSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = ClassificationEngine(enable_llm=False)

    def test_silver_dataset_has_approved_shape(self) -> None:
        rows = [
            json.loads(line)
            for line in (
                RUNTIME_ROOT / "classification" / "silver_labels.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 120)
        self.assertEqual(sum(row["split"] == "calibration" for row in rows), 80)
        self.assertEqual(sum(row["split"] == "test" for row in rows), 40)
        self.assertTrue(all(row["label_source"] == "llm_silver" for row in rows))

    def test_model_loads_fully_offline(self) -> None:
        status = self.engine.model_status()
        self.assertTrue(status["ready"], status["error"])
        self.assertEqual(status["silver_rows"], 120)

    def test_policy_article_stays_in_open_set(self) -> None:
        result = self.engine.classify("国家医保局发布第十二批集采规则")
        self.assertEqual(result.level_1_category, "其他/综合")

    def test_semantic_layer_keeps_ambiguous_cross_modality_at_parent(self) -> None:
        result = self.engine.classify("CAR-T与mRNA联合治疗研究")
        self.assertEqual(result.level_2_category, "1.3 细胞与基因治疗（CGT）")
        self.assertEqual(result.classification_method, "semantic")


if __name__ == "__main__":
    unittest.main()
