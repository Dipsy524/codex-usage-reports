#!/usr/bin/env python3
import datetime as dt
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
USAGE_DIR = ROOT / "usage"
REPORTS_DIR = ROOT / "reports"


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def usage_files():
    return sorted(USAGE_DIR.glob("monthly/*/*/*.json"))


def collect_monthly():
    grouped = {}
    for path in usage_files():
        data = load_json(path)
        period = data.get("period") or {}
        quota = data.get("quota") or {}
        if period.get("type") != "monthly" or not isinstance(quota.get("weeks"), list):
            continue
        key = period.get("start")
        if key:
            grouped.setdefault(key, []).append(data)
    return grouped


def fmt_int(value):
    return f"{int(value):,}"


def fmt_percent(value):
    if value is None:
        return "—"
    return f"{float(value):.0f}%"


def max_percent(values):
    present = [value for value in values if value is not None]
    return max(present, default=None)


def fmt_timestamp(value):
    if not value:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def latest_generated_at(rows):
    values = [fmt_timestamp(row.get("generated_at")) for row in rows]
    return max((value for value in values if value), default="")


def fmt_week(value):
    marker = "-W"
    if isinstance(value, str) and marker in value:
        number = value.rsplit(marker, 1)[-1]
        if number.isdigit():
            return f"第{int(number)}周"
    return value or ""


def summary(rows):
    quotas = [row.get("quota") or {} for row in rows]
    return {
        "machine_count": len(rows),
        "snapshot_count": sum(q.get("snapshot_count") or 0 for q in quotas),
        "seven_day_max_percent": max_percent(q.get("seven_day_max_percent") for q in quotas),
        "generated_at": latest_generated_at(rows),
    }


def title_for(key):
    return f"Codex 额度月报 - {key[:7]}"


def report_path(key):
    return REPORTS_DIR / "monthly" / f"{key[:7]}.md"


def render_report(key, rows):
    rows = sorted(rows, key=lambda row: (row.get("quota") or {}).get("seven_day_max_percent") or 0, reverse=True)
    total = summary(rows)
    period = rows[0]["period"]

    lines = [
        f"# {title_for(key)}",
        "",
        f"- 统计周期：`{period['start']}` 到 `{period['end']}`",
        f"- 机器/账号标识数量：`{len(rows)}`",
        f"- 数据更新时间：`{total['generated_at']}`",
        "",
        "## 汇总",
        "",
        "| 标识数 | 额度快照数 | 7天最高使用 |",
        "|---:|---:|---:|",
        "| "
        + " | ".join(
            [
                fmt_int(total["machine_count"]),
                fmt_int(total["snapshot_count"]),
                fmt_percent(total["seven_day_max_percent"]),
            ]
        )
        + " |",
        "",
        "## 按机器/账号",
        "",
        "| 机器/账号 | 额度快照数 | 7天最高使用 | 上传时间 |",
        "|---|---:|---:|---|",
    ]

    for row in rows:
        quota = row.get("quota") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    row.get("machine_id", "unknown"),
                    fmt_int(quota.get("snapshot_count") or 0),
                    fmt_percent(quota.get("seven_day_max_percent")),
                    fmt_timestamp(row.get("generated_at")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 按周明细",
        ]
    )
    for row in rows:
        machine = row.get("machine_id", "unknown")
        weeks = sorted((row.get("quota") or {}).get("weeks", []), key=lambda item: item.get("start", ""))
        lines.extend(
            [
                "",
                f"### {machine}",
                "",
                "| 周 | 周期 | 额度快照数 | 7天最高使用 | 最新额度快照 |",
                "|---|---|---:|---:|---|",
            ]
        )
        if not weeks:
            lines.append("| 无 | 无 | 0 | — |  |")
            continue
        for week in weeks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        fmt_week(week.get("week")),
                        f"{week.get('start', '')} 到 {week.get('end', '')}",
                        fmt_int(week.get("snapshot_count") or 0),
                        fmt_percent(week.get("seven_day_max_percent")),
                        fmt_timestamp(week.get("latest_seen_at")),
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
    if REPORTS_DIR.exists():
        shutil.rmtree(REPORTS_DIR)

    grouped = collect_monthly()
    for key, rows in grouped.items():
        write(report_path(key), render_report(key, rows))

    latest = max(grouped, default="")
    index_lines = [
        "# Codex 额度报告",
        "",
    ]
    if latest:
        month = latest[:7]
        index_lines.append(f"最新数据更新时间：`{summary(grouped[latest])['generated_at']}`")
        index_lines.append("")
        index_lines.append(f"- 最新月报：[reports/monthly/{month}.md](monthly/{month}.md)")
    else:
        index_lines.append("未找到新版月度额度 JSON 文件。")
    index_lines.append("")
    write(REPORTS_DIR / "index.md", "\n".join(index_lines))

    if latest:
        latest_text = report_path(latest).read_text(encoding="utf-8")
        write(REPORTS_DIR / "latest.md", latest_text)
        write(REPORTS_DIR / "latest-monthly.md", latest_text)
    return {"monthly": latest}


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2, ensure_ascii=False))
