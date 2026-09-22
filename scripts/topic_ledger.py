#!/usr/bin/env python3
"""topic_ledger.py — 月明防重复台账查询脚本

用法：
    python topic_ledger.py check --topic "需求映射 7 字段" --days 30
    python topic_ledger.py add --topic "..." --quadrant Q3 --platform 公众号
    python topic_ledger.py list --days 30

状态：P2 stub。当前版本仅返回结构化空结果，等用户确认数据源后接真实数据。

接入真实数据时建议：
- 数据源：飞书表格 API / 本地 JSON / SQLite
- 主键：topic_id 或 核心命题 hash
- 防重复规则（来自知识库 04）：
    * 近 30 天同核心命题 + 同主要受众不重写
    * 近 14 天同真实案例不得只换标题重讲
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


LEDGER_FILE = Path(__file__).parent.parent / "data" / "topic_ledger.json"


def check(topic: str, days: int, audience: str = "") -> dict:
    """查询近 N 天是否有重复选题。

    Args:
        topic: 核心命题或标题
        days: 查询天数（默认 30）
        audience: 主要受众标签（可选）

    Returns:
        结构化结果字典。
    """
    cutoff = datetime.now() - timedelta(days=days)

    # P2 stub：返回结构化结果，不读真实文件
    result = {
        "query_topic": topic,
        "query_days": days,
        "query_audience": audience,
        "cutoff": cutoff.isoformat(),
        "found": False,
        "matches": [],
        "note": "P2 stub — 接真实数据源后启用",
        "rule": "知识库 04 防重复红线：近 30 天同核心命题 + 同主要受众不重写"
    }

    # 等真实数据接入后，这里会读 LEDGER_FILE 并匹配
    if LEDGER_FILE.exists():
        try:
            entries = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
            for entry in entries:
                published = datetime.fromisoformat(entry.get("published_at", "1970-01-01"))
                if published < cutoff:
                    continue
                if topic in entry.get("topic", "") or entry.get("topic", "") in topic:
                    result["matches"].append(entry)
            result["found"] = len(result["matches"]) > 0
            result["note"] = "已查询真实台账"
        except Exception as exc:
            result["note"] = f"读取台账失败: {exc}"

    return result


def add(topic: str, quadrant: str, platform: str, audience: str = "") -> dict:
    """新增一条选题到台账。

    Args:
        topic: 核心命题或标题
        quadrant: 象限（Q1/Q2/Q3/Q4）
        platform: 发布平台
        audience: 主要受众（可选）

    Returns:
        新增的台账条目。
    """
    entry = {
        "topic": topic,
        "quadrant": quadrant,
        "platform": platform,
        "audience": audience,
        "added_at": datetime.now().isoformat(),
        "published_at": None
    }

    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)

    if LEDGER_FILE.exists():
        try:
            entries = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    else:
        entries = []

    entries.append(entry)
    LEDGER_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return entry


def list_entries(days: int = 30) -> dict:
    """列出近 N 天的台账条目。"""
    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    if LEDGER_FILE.exists():
        try:
            all_entries = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
            for entry in all_entries:
                added = datetime.fromisoformat(entry.get("added_at", "1970-01-01"))
                if added >= cutoff:
                    entries.append(entry)
        except Exception as exc:
            return {"error": f"读取失败: {exc}"}
    return {"count": len(entries), "entries": entries}


def main():
    parser = argparse.ArgumentParser(
        description="月明选题防重复台账（P2 stub + JSON 存储）"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="查询重复选题")
    p_check.add_argument("--topic", required=True, help="核心命题或标题")
    p_check.add_argument("--days", type=int, default=30, help="查询天数")
    p_check.add_argument("--audience", default="", help="主要受众标签")

    p_add = sub.add_parser("add", help="新增选题到台账")
    p_add.add_argument("--topic", required=True)
    p_add.add_argument("--quadrant", required=True, choices=["Q1", "Q2", "Q3", "Q4"])
    p_add.add_argument("--platform", required=True)
    p_add.add_argument("--audience", default="")

    p_list = sub.add_parser("list", help="列出近期台账")
    p_list.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.cmd == "check":
        result = check(args.topic, args.days, args.audience)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "add":
        entry = add(args.topic, args.quadrant, args.platform, args.audience)
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        print(f"[info] 已写入台账：{LEDGER_FILE}", file=sys.stderr)
    elif args.cmd == "list":
        result = list_entries(args.days)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()