#!/usr/bin/env python3
"""Score hotspot candidates for Moonlit's practice-first content strategy."""

from __future__ import annotations

import argparse
import datetime as dt
from email.utils import parsedate_to_datetime
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

DIMENSIONS: dict[str, dict[str, Any]] = {
    "ip_fit": {
        "weight": 20,
        "instructions": "这个候选与 `positioning` 描述的月明账号身份和长期内容承诺有多匹配？",
        "criteria": [
            "基本无关，只能借热点泛泛评论",
            "与 AI 有关，但很难体现产品构建者身份",
            "能结合一次实践，但与长期母题关系一般",
            "直接适合真实产品或工作流实践，能强化构建者身份",
            "高度契合账号核心母题，并能形成持续系列",
        ],
    },
    "testability": {
        "weight": 20,
        "instructions": "根据 `candidate.test_plan`，月明在 24 到 72 小时内完成有意义的一手实践有多可行？",
        "criteria": [
            "没有可执行测试，只能转述",
            "测试目标模糊，结果难以判断",
            "可以做基础体验，但难以触及真实任务",
            "可以在真实任务中验证关键能力并得出明确结果",
            "能快速完成高价值真实实验，且成功失败都有内容价值",
        ],
    },
    "audience_value": {
        "weight": 15,
        "instructions": "完成该实践后，`positioning.primary_audience` 能获得多具体、多重要的判断或行动帮助？",
        "criteria": [
            "几乎没有观众收益",
            "只有新鲜感或情绪价值",
            "能帮助理解功能或趋势",
            "能帮助观众决定是否采用以及怎样尝试",
            "能显著降低真实使用、选型或构建成本",
        ],
    },
    "evidence": {
        "weight": 12,
        "instructions": "`candidate.available_evidence` 能否让最终内容呈现可核验的一手过程和结果？",
        "criteria": [
            "没有可展示证据",
            "主要依赖口头判断或二手材料",
            "能展示部分运行过程，但结果不够明确",
            "有清晰的运行、对比、数据或失败证据",
            "证据完整、直观、可复现，并能支撑明确结论",
        ],
    },
    "asset": {
        "weight": 10,
        "instructions": "`candidate.possible_asset` 在热点过去后还能留下多少可复用价值？",
        "criteria": [
            "没有可沉淀资产",
            "只形成一次性内容",
            "能形成笔记或简单模板",
            "能形成可复用代码、Skill、方法或产品增量",
            "能形成开源资产并持续被项目、观众或后续内容复用",
        ],
    },
    "distinctive": {
        "weight": 8,
        "instructions": "相对常见的热点介绍和工具测评，这个候选的一手实践角度有多稀缺？",
        "criteria": [
            "与常见转述内容基本相同",
            "只有轻微表达差异",
            "有具体任务，但同类实测较多",
            "真实场景和验证方法具有明显辨识度",
            "拥有别人难以复制的现场、数据、项目或失败过程",
        ],
    },
}


def parse_time(value: str) -> dt.datetime:
    if not isinstance(value,str) or not value.strip():raise ValueError('unknown publication time')
    try:parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:parsed=parsedate_to_datetime(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def freshness_score(candidate: dict[str, Any], now: dt.datetime) -> float:
    try:
        age_hours = (now - parse_time(candidate["published_at"])).total_seconds() / 3600
        if age_hours < 0:return 0.0
    except (KeyError, TypeError, ValueError):
        return 0.0
    if age_hours <= 24:
        return 1.0
    if age_hours <= 72:
        return 0.8
    if age_hours <= 168:
        return 0.55
    if age_hours <= 720:
        return 0.25
    return 0.0


def deterministic_points(candidate: dict[str, Any], now: dt.datetime) -> float:
    heat = max(0.0, min(100.0, float(candidate.get("heat_score", 0)))) / 100
    freshness = freshness_score(candidate, now)
    return round(15 * (0.55 * freshness + 0.45 * heat), 2)


def questions() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, definition in DIMENSIONS.items():
        result[key] = {
            "type": "score",
            "instructions": definition["instructions"],
            "criteria": definition["criteria"],
        }
    result["treatment"] = {
        "type": "choice",
        "instructions": "按照月明的实践优先策略，这个候选最适合进入哪种处理队列？",
        "criteria": {
            "quick_test": "24 小时内快速完成一个边界明确的真实测试",
            "deep_build": "投入 2 到 7 天接入真实产品并形成完整资产",
            "observe": "先补一手来源、需求信号或测试条件",
            "skip": "与定位不符、无法实践，或观众收益太弱",
        },
    }
    return result


def call_jev(candidate: dict[str, Any], api_key: str, positioning: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "state": {"positioning": positioning, "candidate": candidate},
        "questions": questions(),
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"TypeSafe HTTP {exc.code}; response body omitted") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TypeSafe connection failed: {exc.reason}") from exc


def composite(candidate: dict[str, Any], response: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    answers = response.get("answers", {})
    semantic_points = 0.0
    dimensions: dict[str, Any] = {}
    confidences: list[float] = []
    for key, definition in DIMENSIONS.items():
        answer = answers.get(key, {})
        if any(type(answer.get(k)) not in (int,float) or not math.isfinite(answer[k]) for k in ('score','confidence')) or not 0<=answer['score']<=4 or not 0<=answer['confidence']<=1:
            raise ValueError(f'Invalid or missing score response: {key}')
        normalized = max(0.0, min(1.0, float(answer.get("score", 0)) / 4))
        points = normalized * definition["weight"]
        confidence = float(answer.get("confidence", 0))
        semantic_points += points
        confidences.append(confidence)
        dimensions[key] = {
            "score_0_to_4": round(float(answer.get("score", 0)), 2),
            "confidence": round(confidence, 2),
            "points": round(points, 2),
        }

    total = semantic_points + deterministic_points(candidate, now)
    caps: list[dict[str, Any]] = []
    if not candidate.get("url"):
        caps.append({"cap": 59, "reason": "缺少原始链接"})
    if candidate.get("source_level") == "discovery_only":
        caps.append({"cap": 69, "reason": "目前只有发现源，尚未回到一手来源"})
    if not str(candidate.get("test_plan", "")).strip():
        caps.append({"cap": 64, "reason": "缺少可执行的一手测试计划"})
    if candidate.get("recent_duplicate") is True:
        caps.append({"cap": 79, "reason": "与近 30 天核心命题重复"})
    if candidate.get('dedup_complete') is not True:
        caps.append({'cap':79,'reason':'去重尚未完整核验'})
    if caps:
        total = min(total, min(item["cap"] for item in caps))

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    needs_review = avg_confidence < 0.55
    if total >= 80 and not needs_review:
        decision = "优先实测"
    elif total >= 65:
        decision = "补证后再决定"
    else:
        decision = "观察或放弃"

    treatment = answers.get("treatment", {})
    return {
        "id": candidate.get("id"),
        "title": candidate.get("title"),
        "total_score": round(total, 2),
        "decision": decision,
        "recommended_treatment": treatment.get("choice"),
        "treatment_confidence": treatment.get("confidence"),
        "average_semantic_confidence": round(avg_confidence, 2),
        "needs_human_review": needs_review,
        "deterministic_points": deterministic_points(candidate, now),
        "semantic_dimensions": dimensions,
        "caps": caps,
        "model": response.get("model"),
        "usage": response.get("usage"),
    }


def validate_candidate(candidate: dict[str, Any]) -> list[str]:
    errors = []
    for field in ("id", "title", "summary", "source", "source_level"):
        if not candidate.get(field):
            errors.append(f"missing field: {field}")
    if candidate.get("source_level") not in {"primary", "credible_secondary", "discovery_only"}:
        errors.append("source_level must be primary, credible_secondary, or discovery_only")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--positioning", type=Path, help="用户当前认可定位 JSON；真实调用必需")
    args = parser.parse_args()

    loaded = json.loads(args.input.read_text(encoding="utf-8"))
    candidates = loaded.get("candidates", []) if isinstance(loaded, dict) else loaded
    if not isinstance(candidates, list):
        raise SystemExit("input must be a JSON array")
    validation = {item.get("id", f"item-{i}"): validate_candidate(item) for i, item in enumerate(candidates)}
    invalid = {key: value for key, value in validation.items() if value}
    if invalid:
        print(json.dumps({"validation_errors": invalid}, ensure_ascii=False, indent=2))
        return 2

    now = dt.datetime.now(dt.timezone.utc)
    if args.dry_run:
        output = [
            {
                "id": item["id"],
                "title": item["title"],
                "deterministic_points": deterministic_points(item, now),
                "would_ask": list(questions()),
            }
            for item in candidates
        ]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not args.positioning:raise SystemExit('--positioning is required for live scoring')
    positioning=json.loads(args.positioning.read_text(encoding='utf-8'))
    if not isinstance(positioning,dict) or any(not positioning.get(k) for k in ('identity','promise','primary_audience','content_boundary')):raise SystemExit('positioning 缺少身份、承诺、受众或内容边界')
    if not api_key:
        raise SystemExit("TYPESAFE_API_KEY is required; do not store it in this repository")

    results = [composite(item, call_jev(item, api_key, positioning), now) for item in candidates]
    results.sort(key=lambda item: item["total_score"], reverse=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
