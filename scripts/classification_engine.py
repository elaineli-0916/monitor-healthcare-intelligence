#!/usr/bin/env python3
"""Auditable three-stage classifier for the healthcare dashboard."""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = SKILL_ROOT.parents[1]
DEFAULT_RUNTIME_ROOT = Path(
    os.environ.get(
        "HEALTHCARE_RUNTIME_ROOT",
        str(PROJECT_ROOT.parent / "healthcare-intelligence-runtime"),
    )
).expanduser()
DEFAULT_CONTRACT_PATH = SKILL_ROOT / "references" / "dashboard-categories.json"
DEFAULT_MODEL_PATH = (
    DEFAULT_RUNTIME_ROOT / "models" / "paraphrase-multilingual-MiniLM-L12-v2"
)
DEFAULT_SILVER_PATH = (
    DEFAULT_RUNTIME_ROOT / "classification" / "silver_labels.jsonl"
)
DEFAULT_ENV_PATH = DEFAULT_RUNTIME_ROOT / ".env"
PLACEHOLDER_SUMMARY_MARKER = "内容需人工审阅或后续解析"


@dataclass(frozen=True)
class ClassificationResult:
    level_1_category: str
    level_2_category: str
    classification_method: str
    classification_confidence: float
    classification_reason: str
    classification_schema_version: str
    classification_model_revision: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def article_text(title: str, summary: str, tags: list[str] | None = None) -> str:
    normalized_title = clean_text(title)
    parts = [f"标题：{normalized_title}", f"核心主题：{normalized_title}"]
    if clean_text(summary):
        parts.append(f"摘要：{clean_text(summary)[:600]}")
    if tags:
        normalized_tags = [clean_text(tag) for tag in tags if clean_text(tag)]
        if normalized_tags:
            parts.append("标签：" + "、".join(normalized_tags))
    return " ".join(parts)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


class ClassificationEngine:
    def __init__(
        self,
        contract_path: Path | None = None,
        model_path: Path | None = None,
        silver_path: Path | None = None,
        env_path: Path | None = None,
        *,
        enable_semantic: bool = True,
        enable_llm: bool = True,
        llm_classifier: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.contract_path = Path(
            os.environ.get(
                "HEALTHCARE_CLASSIFICATION_CONTRACT",
                str(contract_path or DEFAULT_CONTRACT_PATH),
            )
        )
        self.model_path = Path(
            os.environ.get(
                "HEALTHCARE_ST_MODEL_PATH",
                str(model_path or DEFAULT_MODEL_PATH),
            )
        )
        self.silver_path = Path(
            os.environ.get(
                "HEALTHCARE_SILVER_LABELS",
                str(silver_path or DEFAULT_SILVER_PATH),
            )
        )
        self.env_path = Path(
            os.environ.get(
                "HEALTHCARE_LLM_ENV",
                str(env_path or DEFAULT_ENV_PATH),
            )
        )
        self.enable_semantic = enable_semantic
        self.enable_llm = enable_llm
        self.llm_classifier = llm_classifier
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        self.schema_version = str(self.contract["schema_version"])
        self.other_label = str(self.contract["other_label"])
        self.model_config = self.contract["model"]
        self.model_revision = str(self.model_config["revision"])
        self.parent_definitions: dict[str, str] = {}
        self.parent_children: dict[str, list[str]] = {}
        self.label_parent: dict[str, str] = {self.other_label: self.other_label}
        self.label_definitions: dict[str, str] = {
            self.other_label: "超出四个医疗健康赛道边界或信息不足"
        }
        self.parent_prototypes: dict[str, list[str]] = {}
        self.child_prototypes: dict[str, list[str]] = {}
        self.compiled_rules: list[tuple[str, str, re.Pattern[str]]] = []
        self._prepare_contract()
        self.allowed_labels = set(self.label_parent)
        self.silver_rows = load_jsonl(self.silver_path)
        self._model: Any | None = None
        self._model_error = ""
        self._parent_vectors: dict[str, Any] = {}
        self._child_vectors: dict[str, Any] = {}
        self._silver_vectors: Any | None = None
        self._silver_vector_rows: list[dict[str, Any]] = []
        self._semantic_ready = False

    def _prepare_contract(self) -> None:
        for parent in self.contract["parents"]:
            parent_label = str(parent["label"])
            self.parent_definitions[parent_label] = str(parent["definition"])
            self.parent_children[parent_label] = []
            self.label_parent[parent_label] = parent_label
            self.label_definitions[parent_label] = str(parent["definition"])
            self.parent_prototypes[parent_label] = [
                str(value) for value in parent["prototypes"]
            ]
            for pattern in parent.get("rules", []):
                self.compiled_rules.append(
                    (
                        parent_label,
                        str(pattern),
                        re.compile(str(pattern), re.IGNORECASE),
                    )
                )
            for child in parent["children"]:
                label = str(child["label"])
                self.parent_children[parent_label].append(label)
                self.label_parent[label] = parent_label
                self.label_definitions[label] = str(child["definition"])
                self.child_prototypes[label] = [
                    str(value) for value in child["prototypes"]
                ]
                for pattern in child.get("rules", []):
                    self.compiled_rules.append(
                        (
                            label,
                            str(pattern),
                            re.compile(str(pattern), re.IGNORECASE),
                        )
                    )
        self.parent_prototypes[self.other_label] = [
            str(value) for value in self.contract["other_prototypes"]
        ]
        for pattern in self.contract.get("other_rules", []):
            self.compiled_rules.append(
                (
                    self.other_label,
                    str(pattern),
                    re.compile(str(pattern), re.IGNORECASE),
                )
            )

    def contract_summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parents": len(self.parent_definitions),
            "children": sum(len(values) for values in self.parent_children.values()),
            "rules": len(self.compiled_rules),
            "allowed_labels": len(self.allowed_labels),
        }

    def _result(
        self,
        label: str,
        method: str,
        confidence: float,
        reason: str,
        model_revision: str,
    ) -> ClassificationResult:
        if label not in self.allowed_labels:
            label = self.other_label
            method = "other"
            confidence = 0.0
            reason = "分类器返回了分类契约之外的标签。"
        return ClassificationResult(
            level_1_category=self.label_parent[label],
            level_2_category=label,
            classification_method=method,
            classification_confidence=round(
                min(1.0, max(0.0, float(confidence))), 4
            ),
            classification_reason=clean_text(reason)[:500],
            classification_schema_version=self.schema_version,
            classification_model_revision=model_revision,
        )

    def classify_rule(
        self, title: str, summary: str, tags: list[str] | None = None
    ) -> ClassificationResult | None:
        parent_labels = set(self.parent_definitions)

        def collect(
            text: str, *, include_parent_rules: bool = True
        ) -> dict[str, list[str]]:
            found: dict[str, list[str]] = {}
            for label, pattern_text, pattern in self.compiled_rules:
                if not include_parent_rules and label in parent_labels:
                    continue
                match = pattern.search(text)
                if match:
                    evidence = clean_text(match.group(0)) or pattern_text
                    found.setdefault(label, []).append(evidence)
            return found

        title_matches = collect(clean_text(title))
        if len(title_matches) > 1:
            return None
        if title_matches:
            title_label = next(iter(title_matches))
            matches = title_matches
        elif clean_text(summary):
            # Title yielded no match: try summary as a lower-confidence fallback.
            summary_matches = collect(clean_text(summary))
            if len(summary_matches) == 1:
                label, evidence = next(iter(summary_matches.items()))
                return self._result(
                    label,
                    "rule",
                    0.85,
                    f"摘要规则命中：{'、'.join(evidence[:3])}",
                    f"rules:{self.schema_version}",
                )
            else:
                matches = {}
        else:
            # High-precision rules are title-first. A child term that appears only
            # in a long summary is too easy to treat as the article's core topic.
            matches = {}
        if len(matches) != 1:
            return None
        label, evidence = next(iter(matches.items()))
        return self._result(
            label,
            "rule",
            0.99,
            f"高精度规则命中：{'、'.join(evidence[:3])}",
            f"rules:{self.schema_version}",
        )

    def _ensure_semantic(self) -> bool:
        if self._semantic_ready:
            return True
        if self._model_error or not self.enable_semantic:
            return False
        if not self.model_path.exists():
            self._model_error = f"local model not found: {self.model_path}"
            return False
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer

            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            self._model = SentenceTransformer(
                str(self.model_path), local_files_only=True
            )
            calibration = [
                row
                for row in self.silver_rows
                if row.get("split") == "calibration"
                and float(row.get("confidence", 0)) >= 0.6
            ]
            for parent, prototypes in self.parent_prototypes.items():
                documents = list(prototypes)
                documents.extend(
                    article_text(
                        str(row.get("title", "")),
                        str(row.get("summary", "")),
                    )
                    for row in calibration
                    if row.get("level_1_category") == parent
                )
                self._parent_vectors[parent] = self._centroid(documents, np)
            for label, prototypes in self.child_prototypes.items():
                documents = list(prototypes)
                documents.extend(
                    article_text(
                        str(row.get("title", "")),
                        str(row.get("summary", "")),
                    )
                    for row in calibration
                    if row.get("level_2_category") == label
                )
                self._child_vectors[label] = self._centroid(documents, np)
            self._silver_vector_rows = calibration
            if calibration:
                self._silver_vectors = self._model.encode(
                    [
                        article_text(
                            str(row.get("title", "")),
                            str(row.get("summary", "")),
                        )
                        for row in calibration
                    ],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            self._semantic_ready = True
            return True
        except Exception as exc:
            self._model_error = f"{type(exc).__name__}: {exc}"
            return False

    def _centroid(self, documents: list[str], np: Any) -> Any:
        assert self._model is not None
        vectors = self._model.encode(
            documents,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        centroid = vectors.mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        return centroid / norm if norm else centroid

    @staticmethod
    def _rank(query: Any, vectors: dict[str, Any]) -> list[tuple[str, float]]:
        return sorted(
            (
                (label, float(query @ vector))
                for label, vector in vectors.items()
            ),
            key=lambda value: value[1],
            reverse=True,
        )

    def _neighbor_scores(
        self, query: Any, field: str, allowed: set[str]
    ) -> dict[str, float]:
        if self._silver_vectors is None:
            return {}
        grouped: dict[str, list[float]] = {}
        similarities = self._silver_vectors @ query
        for row, similarity in zip(self._silver_vector_rows, similarities):
            label = str(row.get(field, ""))
            if label in allowed:
                grouped.setdefault(label, []).append(float(similarity))
        scores: dict[str, float] = {}
        k = int(self.model_config.get("knn_k", 5))
        for label, values in grouped.items():
            top = sorted(values, reverse=True)[:k]
            weights = list(range(len(top), 0, -1))
            scores[label] = sum(
                value * weight for value, weight in zip(top, weights)
            ) / sum(weights)
        return scores

    def _blend_scores(
        self,
        centroid_scores: list[tuple[str, float]],
        neighbor_scores: dict[str, float],
    ) -> list[tuple[str, float]]:
        blended = []
        for label, centroid in centroid_scores:
            neighbor = neighbor_scores.get(label)
            score = (
                centroid
                if neighbor is None
                else 0.45 * centroid + 0.55 * neighbor
            )
            blended.append((label, score))
        return sorted(blended, key=lambda value: value[1], reverse=True)

    def classify_semantic(
        self, title: str, summary: str, tags: list[str] | None = None
    ) -> tuple[ClassificationResult | None, dict[str, Any], bool]:
        if not self._ensure_semantic():
            return None, {"error": self._model_error}, True
        assert self._model is not None
        query = self._model.encode(
            [article_text(title, summary, tags)],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        parent_centroids = self._rank(query, self._parent_vectors)
        parent_neighbors = self._neighbor_scores(
            query, "level_1_category", set(self._parent_vectors)
        )
        parent_scores = self._blend_scores(parent_centroids, parent_neighbors)
        top_parent, parent_score = parent_scores[0]
        second_parent_score = parent_scores[1][1]
        parent_margin = parent_score - second_parent_score
        open_set_ambiguous = False
        other_margin_threshold = float(
            self.model_config.get("other_margin_threshold", 0.04)
        )
        if top_parent == self.other_label and parent_margin < other_margin_threshold:
            top_parent, parent_score = next(
                value
                for value in parent_scores
                if value[0] != self.other_label
            )
            second_parent_score = max(
                score
                for label, score in parent_scores
                if label not in {self.other_label, top_parent}
            )
            parent_margin = parent_score - second_parent_score
            open_set_ambiguous = True
        elif (
            top_parent != self.other_label
            and parent_scores[1][0] == self.other_label
            and parent_margin < other_margin_threshold
        ):
            second_parent_score = max(
                score
                for label, score in parent_scores
                if label not in {self.other_label, top_parent}
            )
            parent_margin = parent_score - second_parent_score
            open_set_ambiguous = True
        parent_threshold = float(
            self.model_config["parent_similarity_threshold"]
        )
        parent_margin_threshold = float(
            self.model_config["parent_margin_threshold"]
        )
        trace: dict[str, Any] = {
            "parents": parent_scores[:3],
            "parent_margin": parent_margin,
        }
        parent_is_confident = (
            parent_score >= parent_threshold
            and parent_margin >= parent_margin_threshold
        )
        if top_parent == self.other_label:
            candidate = self._result(
                self.other_label,
                "semantic",
                parent_score,
                (
                    f"语义模型最接近开放集；相似度 {parent_score:.3f}，"
                    f"领先第二名 {parent_margin:.3f}。"
                ),
                self.model_revision,
            )
            return candidate, trace, not parent_is_confident
        if not parent_is_confident:
            return None, trace, True

        child_vectors = {
            label: self._child_vectors[label]
            for label in self.parent_children[top_parent]
        }
        child_centroids = self._rank(query, child_vectors)
        child_neighbors = self._neighbor_scores(
            query, "level_2_category", set(child_vectors)
        )
        child_scores = self._blend_scores(child_centroids, child_neighbors)
        top_child, child_score = child_scores[0]
        second_child_score = child_scores[1][1] if len(child_scores) > 1 else -1.0
        child_margin = child_score - second_child_score
        trace["children"] = child_scores[:3]
        trace["child_margin"] = child_margin
        child_is_confident = (
            child_score >= float(self.model_config["child_similarity_threshold"])
            and child_margin >= float(self.model_config["child_margin_threshold"])
        )
        if child_is_confident:
            return (
                self._result(
                    top_child,
                    "semantic",
                    child_score,
                    (
                        f"语义模型在 {top_parent} 内最接近 {top_child}；"
                        f"相似度 {child_score:.3f}，领先第二名 {child_margin:.3f}。"
                    ),
                    self.model_revision,
                ),
                trace,
                open_set_ambiguous,
            )
        generic_parent = self._result(
            top_parent,
            "semantic",
            parent_score,
            (
                f"一级类别 {top_parent} 可信，但二级类别边界不清；"
                f"最佳二级相似度 {child_score:.3f}，分差 {child_margin:.3f}。"
            ),
            self.model_revision,
        )
        return generic_parent, trace, True

    def _llm_payload(
        self,
        title: str,
        summary: str,
        tags: list[str] | None,
        semantic_trace: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "title": clean_text(title),
            "summary": clean_text(summary)[:1500],
            "tags": tags or [],
            "semantic_candidates": semantic_trace,
            "allowed_labels": [
                {
                    "level_2_category": label,
                    "level_1_category": self.label_parent[label],
                    "definition": self.label_definitions[label],
                }
                for label in sorted(self.allowed_labels)
            ],
        }

    def _call_llm_api(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        env = {**load_env_file(self.env_path), **os.environ}
        base_url = env.get("LLM_BASE_URL", "").rstrip("/")
        api_key = env.get("LLM_API_KEY", "")
        model = env.get("LLM_MODEL", "")
        if not (base_url and api_key and model):
            return None
        endpoint = base_url + "/chat/completions"
        prompt = (
            "你是医疗健康投研新闻分类器。只能从 allowed_labels 中选择一个"
            " level_2_category；允许选择其他/综合。根据标题和摘要的核心业务对象分类，"
            "不要被融资、获批、临床等事件词替代赛道判断。"
            "只返回 JSON 对象，字段为 level_2_category、confidence、reason。\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = str(result["choices"][0]["message"]["content"]).strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        parsed = json.loads(content)
        parsed["_model"] = model
        return parsed

    def classify_llm(
        self,
        title: str,
        summary: str,
        tags: list[str] | None,
        semantic_trace: dict[str, Any],
    ) -> ClassificationResult | None:
        if not self.enable_llm:
            return None
        payload = self._llm_payload(title, summary, tags, semantic_trace)
        try:
            response = (
                self.llm_classifier(payload)
                if self.llm_classifier is not None
                else self._call_llm_api(payload)
            )
            if not response:
                return None
            label = str(response.get("level_2_category", ""))
            if label not in self.allowed_labels:
                return None
            confidence = float(response.get("confidence", 0))
            if not math.isfinite(confidence):
                return None
            reason = clean_text(str(response.get("reason", "")))
            if not reason:
                return None
            return self._result(
                label,
                "llm",
                confidence,
                reason,
                str(response.get("_model", "injected-llm")),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ):
            return None

    def classify(
        self, title: str, summary: str = "", tags: list[str] | None = None
    ) -> ClassificationResult:
        if PLACEHOLDER_SUMMARY_MARKER in clean_text(summary):
            return self._result(
                self.other_label,
                "other",
                1.0,
                "来源仅抓到栏目占位页，正文信息不足，保留开放集。",
                "placeholder-policy:1.0",
            )
        rule_result = self.classify_rule(title, summary, tags)
        if rule_result is not None:
            return rule_result
        semantic_result, semantic_trace, needs_llm = self.classify_semantic(
            title, summary, tags
        )
        if not needs_llm and semantic_result is not None:
            return semantic_result
        llm_result = self.classify_llm(
            title, summary, tags, semantic_trace
        )
        if llm_result is not None:
            return llm_result
        if semantic_result is not None:
            if needs_llm:
                return self._result(
                    semantic_result.level_2_category,
                    "semantic_fallback",
                    semantic_result.classification_confidence,
                    (
                        f"{semantic_result.classification_reason} "
                        "LLM 兜底未配置或调用失败，保留语义候选。"
                    ),
                    semantic_result.classification_model_revision,
                )
            return semantic_result
        return self._result(
            self.other_label,
            "other",
            0.0,
            "高精度规则未命中，语义模型不可用或置信度不足，LLM 兜底未配置或失败。",
            "none",
        )

    def model_status(self) -> dict[str, Any]:
        ready = self._ensure_semantic()
        return {
            "ready": ready,
            "model_path": str(self.model_path),
            "model_revision": self.model_revision,
            "error": self._model_error,
            "silver_rows": len(self.silver_rows),
        }


_DEFAULT_ENGINE: ClassificationEngine | None = None


def get_default_engine() -> ClassificationEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = ClassificationEngine()
    return _DEFAULT_ENGINE


def classify_article(
    title: str, summary: str = "", tags: list[str] | None = None
) -> dict[str, Any]:
    return get_default_engine().classify(title, summary, tags).to_dict()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("--summary", default="")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    engine = get_default_engine()
    if args.status:
        print(json.dumps(engine.model_status(), ensure_ascii=False))
    else:
        print(
            json.dumps(
                engine.classify(args.title, args.summary).to_dict(),
                ensure_ascii=False,
                indent=2,
            )
        )
