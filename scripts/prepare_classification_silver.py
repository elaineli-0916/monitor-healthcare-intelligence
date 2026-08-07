#!/usr/bin/env python3
"""Materialize the approved LLM-silver classification sample.

The labels below were assigned by the current LLM from the latest dashboard's
title and summary. They are deliberately called silver labels: they are useful
for calibration and regression tests, but they are not human gold labels.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

from classification_engine import DEFAULT_RUNTIME_ROOT


LABELS = {
    "O": "其他/综合",
    "1": "1. 创新药",
    "1.1": "1.1 小分子创新药",
    "1.2": "1.2 生物药（抗体/蛋白/核酸/ADC/XDC偶联药物）",
    "1.3": "1.3 细胞与基因治疗（CGT）",
    "1.4": "1.4 医药CXO（CRO/CDMO/CSO）",
    "1.5": "1.5 AI制药",
    "1.6": "1.6 合成生物学",
    "2": "2. 医疗器械",
    "2.3": "2.3 体外诊断（IVD）",
    "2.4": "2.4 医学影像",
    "2.5": "2.5 手术机器人",
    "2.6": "2.6 神经调控与脑机接口",
    "3": "3. 医疗服务",
    "3.3": "3.3 数字医疗/互联网医院",
    "4.3": "4.3 减重/代谢管理",
}


# (article id, approved label key, LLM confidence)
SILVER_LABELS = [
    ("6dab96c504531ccf", "O", 0.98),
    ("04247e9a0d9d7a57", "1.1", 0.75),
    ("11af13753305de63", "1", 0.72),
    ("d84f06a17782af7f", "O", 0.99),
    ("a4772f40c98d50d8", "1.3", 0.75),
    ("777bba45b91dabef", "O", 0.90),
    ("384b6080671a8c4e", "O", 0.96),
    ("1c6a5ca0229d439d", "O", 0.96),
    ("28a4202d4b85d0ac", "1", 0.80),
    ("77d4fa037ee2c1a8", "1.2", 0.97),
    ("01ddc1cd530b1da1", "1.1", 0.93),
    ("2d6ddf8b7b3b1040", "4.3", 0.65),
    ("f40257225a91b10c", "1", 0.78),
    ("ba907a8bf526114b", "1.4", 0.61),
    ("bcb5d06e7cf291ba", "1", 0.78),
    ("c7ce5c73b0e8bb5f", "O", 0.92),
    ("0d3c30a933d23b93", "1.1", 0.92),
    ("b4ffba1f297b089e", "2", 0.88),
    ("51c449446313bb0d", "1", 0.70),
    ("fe5b5aeb7114e6d2", "O", 0.98),
    ("43d64d1fc10f8da7", "O", 0.78),
    ("7326185bc70fc228", "O", 0.99),
    ("dba529d5ead50c68", "2", 0.65),
    ("35c21adb1a19f4c4", "1", 0.72),
    ("a9e5de6054c5df42", "1.1", 0.70),
    ("d79fc91367fa75ca", "O", 0.88),
    ("792e3bb558034f10", "O", 0.95),
    ("f8531c44c764ff94", "O", 0.65),
    ("b7c5774c99f55698", "1.2", 0.97),
    ("078beba2c97896e6", "O", 0.99),
    ("5752dd9e0cdbdb37", "O", 0.99),
    ("d98ed3524961fbcb", "O", 0.95),
    ("b9ab2b0daf27f31e", "1.1", 0.96),
    ("584470d855371415", "1.4", 0.60),
    ("0dc20f5de4fc3936", "2", 0.65),
    ("1f56f5f22369c320", "1", 0.90),
    ("daf42e8ee3bde95c", "O", 0.99),
    ("36d3606d0c2acc2d", "1.2", 0.96),
    ("2f08bc7f433c4e82", "1.3", 0.88),
    ("994474ba18bc9bd7", "O", 0.92),
    ("823da877fd7e7b53", "O", 0.99),
    ("b59115b81531979e", "1", 0.86),
    ("c4eed72800438be2", "1", 0.75),
    ("51edb38e972325d6", "1.2", 0.98),
    ("28039e3f888019d7", "O", 0.99),
    ("eb8e421acda79c93", "1", 0.65),
    ("443b96aa874c935f", "O", 0.80),
    ("732d25472d0cd411", "O", 0.97),
    ("ccdc8a90de39d6aa", "O", 0.97),
    ("470446b1e9a8402e", "3.3", 0.82),
    ("a7b91458956b6f2e", "O", 0.75),
    ("b5671f732a355790", "2.3", 0.86),
    ("e2206c2086c5422b", "O", 0.96),
    ("988660d302403fee", "O", 0.99),
    ("59c0a6429b325eee", "1", 0.90),
    ("b8545a1898fd2a22", "O", 0.90),
    ("6561e87968de0106", "3.3", 0.78),
    ("1e2363dadd09b6ff", "O", 0.98),
    ("5b4501612dda1681", "O", 0.99),
    ("e99aba252fb56387", "3.3", 0.96),
    ("823eb5fc41e25b66", "O", 0.92),
    ("d3fb3bea88b32e93", "2.3", 0.82),
    ("a5a3edef33e49ead", "1.1", 0.89),
    ("08f178b4c1e6398d", "1.1", 0.95),
    ("08d4085c1ceabdc8", "O", 0.99),
    ("806dc35d59b00b43", "O", 0.99),
    ("46ad2830382b2868", "1.1", 0.84),
    ("61f348f2fea4ea57", "1", 0.75),
    ("3f3bb241b8482a1e", "1.5", 0.70),
    ("8b7827633535e772", "3", 0.68),
    ("15843c92b0a57dde", "1.1", 0.78),
    ("c4591447d9bc4446", "O", 0.99),
    ("af5dfe84c019036b", "1.2", 0.98),
    ("45d8cbdc1dfbc09a", "1.5", 0.96),
    ("f67c9c5cb41ec996", "O", 0.99),
    ("4adca2cb20570d18", "1", 0.55),
    ("07e4b8980f12e11b", "O", 0.99),
    ("9cdba76aa20cf5d7", "1.1", 0.86),
    ("4c280b7cf6657c12", "1", 0.72),
    ("f80acc5326f2f297", "1.4", 0.65),
    ("17faf1e52c937921", "1.2", 0.94),
    ("76b5b4605d97846e", "1.3", 0.98),
    ("83a93658d13f7799", "1", 0.70),
    ("d61f5b4c306c6e7c", "1.3", 0.98),
    ("93988fbc412f2c35", "1", 0.75),
    ("e77d12d5495be08a", "1.2", 0.78),
    ("352d8c6cac907533", "1.2", 0.72),
    ("e6d28117474f741f", "1.2", 0.90),
    ("282f7af89812fe0f", "1.2", 0.97),
    ("a35066f29c648e3e", "1.3", 0.82),
    ("cfbfdedc08e5ccd6", "1.2", 0.99),
    ("a53d9a282f51ea87", "1.5", 0.82),
    ("c5cc4858d0b8ffc2", "O", 0.78),
    ("5cba8d99fa240230", "1.2", 0.99),
    ("601cbb7fa904b19f", "1", 0.62),
    ("fa0e6a12238c725f", "1", 0.72),
    ("fab7a4f22d896478", "2.5", 0.78),
    ("348e659e2f447f3f", "O", 0.99),
    ("e80ee0ce0920d234", "2.6", 0.99),
    ("78eec2f98f7f145e", "1.2", 0.80),
    ("2f0412c4234a73ac", "O", 0.96),
    ("7421fbf39ec8aff0", "O", 0.75),
    ("602fa86f457c4fb8", "O", 0.96),
    ("9b7e5e6d516c2857", "O", 0.97),
    ("b5001063eaf7f070", "O", 0.99),
    ("aa10e22a520c4e78", "O", 0.96),
    ("25ecad5541a9f56b", "1.5", 0.93),
    ("c535d119fc5449e3", "O", 0.65),
    ("23158ca7b9331d97", "2.4", 0.90),
    ("7ebdf5351cd75abc", "O", 0.99),
    ("dc51f4452c3d9af3", "3.3", 0.90),
    ("5294dd23b73e0cb9", "2.6", 0.96),
    ("fc91aaba19c01cb9", "1.4", 0.97),
    ("84e444ec354302ad", "O", 0.98),
    ("b9b2c3e09f90452e", "4.3", 0.98),
    ("293a3015e78a6c97", "1", 0.88),
    ("c342fc6e59863c92", "O", 0.95),
    ("a07b91fd82711a0a", "O", 0.97),
    ("9c07802cd96789bb", "4.3", 0.98),
    ("9513fce137e951eb", "4.3", 0.99),
]


REASONS = {
    "O": "主题属于政策、基础研究、泛行业或非医疗内容，现有四赛道边界不足以可靠承接。",
    "1": "主题明确涉及创新药公司、管线或交易，但现有信息不足以可靠判断具体药物模态。",
    "1.1": "标题或摘要明确指向小分子、化学药、抑制剂或相关药物研发。",
    "1.2": "标题或摘要明确指向抗体、蛋白、核酸、疫苗、ADC/XDC 或其他生物药。",
    "1.3": "标题或摘要明确指向细胞治疗、基因治疗或 CAR-T 等 CGT 技术。",
    "1.4": "主题核心是药物研发、生产或商业化外包及专业服务。",
    "1.5": "主题核心是人工智能或计算方法驱动的药物研发。",
    "1.6": "主题核心是合成生物学、生物制造或工程化生物系统。",
    "2": "主题明确属于医疗器械或医用材料，但信息不足以可靠判断具体器械子类。",
    "2.3": "主题核心是体外诊断、检验、病理或相关诊断平台。",
    "2.4": "主题核心是医学影像、病理影像或相关成像平台。",
    "2.5": "主题核心是临床手术机器人或机器人介入设备。",
    "2.6": "主题核心是神经调控、脑机接口或神经监测设备。",
    "3": "主题明确属于医疗服务，但信息不足以可靠判断具体服务子类。",
    "3.3": "主题核心是数字医疗、互联网医疗、医疗 AI 或远程健康管理。",
    "4.3": "主题核心是减重、肥胖治疗、GLP-1 或代谢管理。",
}


def parent_for(label: str) -> str:
    if label == "其他/综合":
        return label
    prefix = label.split(".", 1)[0]
    return {
        "1": "1. 创新药",
        "2": "2. 医疗器械",
        "3": "3. 医疗服务",
        "4": "4. 消费医疗与医美",
    }[prefix]


def load_articles(dashboard: Path) -> dict[str, dict]:
    content = dashboard.read_text(encoding="utf-8")
    match = re.search(r"const ARTICLES = (\[.*?\]);\n", content, re.DOTALL)
    if not match:
        raise RuntimeError(f"cannot find embedded ARTICLES in {dashboard}")
    articles = json.loads(match.group(1))
    return {str(article.get("id")): article for article in articles}


def latest_dashboard(pattern: str) -> Path:
    matches = [Path(path) for path in glob.glob(pattern)]
    if not matches:
        raise RuntimeError(f"no dashboard matches {pattern}")
    return max(matches, key=lambda path: path.stat().st_mtime)


def materialize(dashboard: Path, output: Path) -> dict[str, int]:
    articles = load_articles(dashboard)
    output.parent.mkdir(parents=True, exist_ok=True)
    counts = {"calibration": 0, "test": 0}
    rows = []
    missing = []
    for index, (article_id, label_key, confidence) in enumerate(SILVER_LABELS):
        article = articles.get(article_id)
        if article is None:
            missing.append(article_id)
            continue
        label = LABELS[label_key]
        split = "test" if index % 3 == 0 else "calibration"
        counts[split] += 1
        rows.append(
            {
                "sample_index": index,
                "id": article_id,
                "title": article.get("title", ""),
                "summary": (article.get("summary") or "")[:800],
                "source": article.get("source", ""),
                "current_level_1_category": article.get("level_1_category", ""),
                "current_level_2_category": article.get("level_2_category", ""),
                "level_1_category": parent_for(label),
                "level_2_category": label,
                "is_other": label == "其他/综合",
                "confidence": confidence,
                "reason": REASONS[label_key],
                "evidence": article.get("title", ""),
                "label_source": "llm_silver",
                "split": split,
                "schema_version": "1.0",
            }
        )
    if missing:
        raise RuntimeError(f"dashboard is missing {len(missing)} labeled articles: {missing}")
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dashboard",
        type=Path,
        help="Dashboard HTML containing const ARTICLES; defaults to latest runtime dashboard",
    )
    parser.add_argument(
        "--dashboard-pattern",
        default=str(DEFAULT_RUNTIME_ROOT / "dashboard_*.html"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RUNTIME_ROOT / "classification" / "silver_labels.jsonl",
    )
    args = parser.parse_args()
    dashboard = args.dashboard or latest_dashboard(args.dashboard_pattern)
    counts = materialize(dashboard.resolve(), args.output.resolve())
    print(
        json.dumps(
            {
                "status": "ok",
                "dashboard": str(dashboard),
                "output": str(args.output),
                "rows": sum(counts.values()),
                "splits": counts,
                "label_source": "llm_silver",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
