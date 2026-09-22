#!/usr/bin/env python3
"""data_ingest.py — 月明选题复盘数据接入与分析

P2 stub：等用户确认数据源后启用。当前提供：
- CSV / JSON 解析 schema 校验
- 简单的"按象限 / 主任务 / 标题公式"聚合分析

用法：
    python data_ingest.py ingest < data.csv
    python data_ingest.py ingest --json entries.json
    python data_ingest.py analyze
    python data_ingest.py schema

数据格式见 templates/data-replay.md。
"""

import argparse
import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path


DATA_FILE = Path(__file__).parent.parent / "data" / "replay_data.json"


def parse_csv(text: str) -> list:
    """解析 CSV 文本为条目列表。"""
    reader = csv.DictReader(io.StringIO(text))
    entries = []
    for row in reader:
        entry = {}
        for k, v in row.items():
            if k in ("views", "likes", "favorites", "comments", "leads", "conversions"):
                entry.setdefault("metrics", {})[k] = int(v) if v else 0
            else:
                entry[k] = v
        entries.append(entry)
    return entries


def parse_json_text(text: str) -> list:
    """解析 JSON 文本。"""
    data = json.loads(text)
    if isinstance(data, dict) and "entries" in data:
        return data["entries"]
    if isinstance(data, list):
        return data
    return []


def validate_entry(entry: dict) -> list:
    """校验单条数据，返回错误列表。"""
    errors = []
    required = ["topic_id", "published_at", "platform", "quadrant", "main_task", "title_formula"]
    for field in required:
        if field not in entry:
            errors.append(f"缺失字段: {field}")

    if "quadrant" in entry and entry["quadrant"] not in ("Q1", "Q2", "Q3", "Q4"):
        errors.append(f"象限非法: {entry['quadrant']}")

    return errors


def ingest(source: str, is_json: bool = False) -> dict:
    """导入数据。

    Args:
        source: CSV/JSON 文本内容
        is_json: 是否为 JSON 格式

    Returns:
        导入结果
    """
    try:
        if is_json:
            entries = parse_json_text(source)
        else:
            entries = parse_csv(source)
    except Exception as exc:
        return {"error": f"解析失败: {exc}"}

    valid_entries = []
    errors = []
    for entry in entries:
        errs = validate_entry(entry)
        if errs:
            errors.append({"entry": entry.get("topic_id", "?"), "errors": errs})
        else:
            valid_entries.append(entry)

    # 持久化
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    else:
        existing = []

    existing.extend(valid_entries)
    DATA_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return {
        "imported": len(valid_entries),
        "rejected": len(errors),
        "errors": errors,
        "total_in_store": len(existing),
        "store_path": str(DATA_FILE)
    }


def analyze() -> dict:
    """分析历史数据，输出"下期选题该往哪倾斜"建议。

    P2 stub：基础聚合，等数据源接入后启用更复杂的加权分析。
    """
    if not DATA_FILE.exists():
        return {
            "recommendations": [],
            "note": "无数据，请先运行 ingest"
        }

    try:
        entries = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"读取失败: {exc}"}

    # 按象限聚合
    by_quadrant = defaultdict(lambda: {"count": 0, "views": 0, "leads": 0})
    by_task = defaultdict(lambda: {"count": 0, "leads": 0})
    by_formula = defaultdict(lambda: {"count": 0, "leads": 0})

    for entry in entries:
        m = entry.get("metrics", {})
        q = entry.get("quadrant", "?")
        t = entry.get("main_task", "?")
        f = entry.get("title_formula", "?")

        by_quadrant[q]["count"] += 1
        by_quadrant[q]["views"] += m.get("views", 0)
        by_quadrant[q]["leads"] += m.get("leads", 0)

        by_task[t]["count"] += 1
        by_task[t]["leads"] += m.get("leads", 0)

        by_formula[f]["count"] += 1
        by_formula[f]["leads"] += m.get("leads", 0)

    # 计算线索率
    for d in (by_quadrant, by_task, by_formula):
        for k, v in d.items():
            if v["count"] > 0:
                v["lead_rate"] = round(v["leads"] / v["count"], 2)

    recommendations = []
    if by_quadrant:
        best_q = max(by_quadrant.items(), key=lambda x: x[1].get("lead_rate", 0))
        recommendations.append(f"线索率最高象限：{best_q[0]}（线索率 {best_q[1].get('lead_rate', 0)}）——下期可多发")
    if by_task:
        best_t = max(by_task.items(), key=lambda x: x[1].get("lead_rate", 0))
        recommendations.append(f"线索率最高主任务：{best_t[0]}（线索率 {best_t[1].get('lead_rate', 0)}）")
    if by_formula:
        best_f = max(by_formula.items(), key=lambda x: x[1].get("lead_rate", 0))
        recommendations.append(f"线索率最高标题公式：{best_f[0]}（线索率 {best_f[1].get('lead_rate', 0)}）")

    return {
        "total_entries": len(entries),
        "by_quadrant": dict(by_quadrant),
        "by_task": dict(by_task),
        "by_formula": dict(by_formula),
        "recommendations": recommendations,
        "note": "P2 stub — 当前为简单聚合，等数据量充足后启用加权分析"
    }


def schema() -> str:
    """返回数据格式约定。"""
    return """# 数据格式约定

## CSV
```csv
topic_id,published_at,platform,quadrant,main_task,title_formula,views,likes,favorites,comments,leads,conversions
T20260115-001,2026-01-15T10:00:00+08:00,公众号,Q3,方法,数字+结果,12500,320,480,56,8,2
```

## JSON
```json
{
  "entries": [
    {
      "topic_id": "T20260115-001",
      "published_at": "2026-01-15T10:00:00+08:00",
      "platform": "公众号",
      "quadrant": "Q3",
      "main_task": "方法",
      "title_formula": "数字+结果",
      "metrics": {"views": 12500, "likes": 320, "favorites": 480, "comments": 56, "leads": 8, "conversions": 2}
    }
  ]
}
```

详见 templates/data-replay.md
"""


def main():
    parser = argparse.ArgumentParser(
        description="月明选题复盘数据接入与分析（P2 stub）"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_ingest = sub.add_parser("ingest", help="导入数据（stdin 或 --json）")
    p_ingest.add_argument("--json", help="JSON 文件路径或字符串")

    sub.add_parser("analyze", help="分析历史数据")
    sub.add_parser("schema", help="打印数据格式")

    args = parser.parse_args()

    if args.cmd == "ingest":
        if args.json:
            try:
                source = Path(args.json).read_text(encoding="utf-8")
            except Exception:
                source = args.json
            is_json = True
        else:
            source = sys.stdin.read()
            is_json = source.strip().startswith("{") or source.strip().startswith("[")

        result = ingest(source, is_json)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "analyze":
        result = analyze()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "schema":
        print(schema())
    else:
        print(schema())


if __name__ == "__main__":
    main()