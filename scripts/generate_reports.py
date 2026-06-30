#!/usr/bin/env python3
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USAGE_DIR = ROOT / "usage"
REPORTS_DIR = ROOT / "reports"
PRO_MONTHLY_USD = 200


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def usage_files(kind):
    if kind == "daily":
        pattern = "daily/*/*/*/*.json"
    else:
        pattern = "monthly/*/*/*.json"
    return sorted((USAGE_DIR).glob(pattern))


def collect(kind):
    grouped = {}
    for path in usage_files(kind):
        data = load_json(path)
        period = data.get("period", {})
        if period.get("type") != kind:
            continue
        key = period.get("start")
        if not key:
            continue
        grouped.setdefault(key, []).append(data)
    return grouped


def add_totals(rows):
    total = {
        "requests": 0,
        "session_count": 0,
        "fresh_input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "real_total_tokens": 0,
        "cost_usd": 0.0,
    }
    for row in rows:
        totals = row["totals"]
        for key in total:
            total[key] += totals.get(key, 0)
    cacheable = total["fresh_input_tokens"] + total["cache_read_tokens"] + total["cache_creation_tokens"]
    total["cache_hit_rate"] = total["cache_read_tokens"] / cacheable if cacheable else 0
    return total


def fmt_int(value):
    return f"{int(value):,}"


def fmt_rate(value):
    return f"{value * 100:.2f}%"


def fmt_cost(value):
    return f"${value:.6f}"


def fmt_roi(cost):
    return f"{cost / PRO_MONTHLY_USD:.2f}x"


def title_for(kind, key):
    if kind == "daily":
        return f"Codex 用量日报 - {key}"
    return f"Codex 用量月报 - {key[:7]}"


def report_path(kind, key):
    if kind == "daily":
        return REPORTS_DIR / "daily" / f"{key}.md"
    return REPORTS_DIR / "monthly" / f"{key[:7]}.md"


def render_report(kind, key, rows):
    rows = sorted(rows, key=lambda row: row["totals"].get("real_total_tokens", 0), reverse=True)
    total = add_totals(rows)
    source_updated_at = max((row.get("generated_at", "") for row in rows), default="")
    period = rows[0]["period"]

    lines = [
        f"# {title_for(kind, key)}",
        "",
        f"- 统计周期：`{period['start']}` 到 `{period['end']}`",
        f"- 机器数量：`{len(rows)}`",
        f"- 数据更新时间：`{source_updated_at}`",
        "",
        "## 汇总",
        "",
        "| 请求数 | 会话数 | 真实 Token | 新增输入 | 输出 | 缓存读取 | 命中率 | 估算成本 | 回本倍率 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| "
        + " | ".join(
            [
                fmt_int(total["requests"]),
                fmt_int(total["session_count"]),
                fmt_int(total["real_total_tokens"]),
                fmt_int(total["fresh_input_tokens"]),
                fmt_int(total["output_tokens"]),
                fmt_int(total["cache_read_tokens"]),
                fmt_rate(total["cache_hit_rate"]),
                fmt_cost(total["cost_usd"]),
                fmt_roi(total["cost_usd"]),
            ]
        )
        + " |",
        "",
        "## 按机器明细",
        "",
        "| 机器 | 请求数 | 会话数 | 真实 Token | 新增输入 | 输出 | 缓存读取 | 命中率 | 估算成本 | 回本倍率 | 更新时间 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for row in rows:
        totals = row["totals"]
        lines.append(
            "| "
            + " | ".join(
                [
                    row.get("machine_id", "unknown"),
                    fmt_int(totals.get("requests", 0)),
                    fmt_int(totals.get("session_count", 0)),
                    fmt_int(totals.get("real_total_tokens", 0)),
                    fmt_int(totals.get("fresh_input_tokens", 0)),
                    fmt_int(totals.get("output_tokens", 0)),
                    fmt_int(totals.get("cache_read_tokens", 0)),
                    fmt_rate(totals.get("cache_hit_rate", 0)),
                    fmt_cost(totals.get("cost_usd", 0)),
                    fmt_roi(totals.get("cost_usd", 0)),
                    row.get("generated_at", ""),
                ]
            )
            + " |"
        )

    lines.append("")
    return "\n".join(lines)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def generate():
    latest = {}
    source_updates = []
    for kind in ("daily", "monthly"):
        grouped = collect(kind)
        for key, rows in grouped.items():
            source_updates.extend(row.get("generated_at", "") for row in rows)
            write(report_path(kind, key), render_report(kind, key, rows))
        if grouped:
            latest[kind] = max(grouped)
    source_updated_at = max((value for value in source_updates if value), default="")

    index_lines = [
        "# Codex 用量报告",
        "",
        f"最新数据更新时间：`{source_updated_at}`",
        "",
    ]
    if "daily" in latest:
        key = latest["daily"]
        index_lines.append(f"- 最新日报：[reports/daily/{key}.md](daily/{key}.md)")
    if "monthly" in latest:
        key = latest["monthly"][:7]
        index_lines.append(f"- 最新月报：[reports/monthly/{key}.md](monthly/{key}.md)")
    if len(index_lines) == 4:
        index_lines.append("未找到用量 JSON 文件。")
    index_lines.append("")
    write(REPORTS_DIR / "index.md", "\n".join(index_lines))

    latest_daily = latest.get("daily")
    if latest_daily:
        latest_text = (REPORTS_DIR / "daily" / f"{latest_daily}.md").read_text(encoding="utf-8")
        write(REPORTS_DIR / "latest.md", latest_text)
    latest_monthly = latest.get("monthly")
    if latest_monthly:
        latest_monthly_text = (REPORTS_DIR / "monthly" / f"{latest_monthly[:7]}.md").read_text(encoding="utf-8")
        write(REPORTS_DIR / "latest-monthly.md", latest_monthly_text)
    return latest


if __name__ == "__main__":
    latest = generate()
    print(json.dumps(latest, indent=2, ensure_ascii=False))
