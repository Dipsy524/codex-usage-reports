#!/usr/bin/env python3
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


def latest_seen(rows):
    values = []
    for row in rows:
        quota = row.get("quota") or {}
        values.append(quota.get("latest_seen_at") or "")
        values.append(row.get("generated_at") or "")
    return max((value for value in values if value), default="")


def all_weeks(rows):
    for row in rows:
        machine = row.get("machine_id", "unknown")
        for week in (row.get("quota") or {}).get("weeks", []):
            yield machine, week


def summary(rows):
    weeks = list(all_weeks(rows))
    quotas = [row.get("quota") or {} for row in rows]
    return {
        "machine_count": len(rows),
        "snapshot_count": sum(q.get("snapshot_count") or 0 for q in quotas),
        "five_hour_max_percent": max_percent(q.get("five_hour_max_percent") for q in quotas),
        "seven_day_max_percent": max_percent(q.get("seven_day_max_percent") for q in quotas),
        "near_limit_week_count": sum(1 for _, week in weeks if week.get("near_limit")),
        "latest_seen_at": latest_seen(rows),
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
        f"- 数据更新时间：`{total['latest_seen_at']}`",
        "",
        "## 汇总",
        "",
        "| 标识数 | 额度快照数 | 5小时最高使用 | 7天最高使用 | 触顶周数 | 最新额度快照 |",
        "|---:|---:|---:|---:|---:|---|",
        "| "
        + " | ".join(
            [
                fmt_int(total["machine_count"]),
                fmt_int(total["snapshot_count"]),
                fmt_percent(total["five_hour_max_percent"]),
                fmt_percent(total["seven_day_max_percent"]),
                fmt_int(total["near_limit_week_count"]),
                total["latest_seen_at"],
            ]
        )
        + " |",
        "",
        "## 按机器/账号",
        "",
        "| 机器/账号 | 额度快照数 | 5小时最高使用 | 7天最高使用 | 触顶周数 | 最新额度快照 | 上传时间 |",
        "|---|---:|---:|---:|---:|---|---|",
    ]

    for row in rows:
        quota = row.get("quota") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    row.get("machine_id", "unknown"),
                    fmt_int(quota.get("snapshot_count") or 0),
                    fmt_percent(quota.get("five_hour_max_percent")),
                    fmt_percent(quota.get("seven_day_max_percent")),
                    fmt_int(quota.get("near_limit_week_count") or 0),
                    quota.get("latest_seen_at") or "",
                    row.get("generated_at", ""),
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
                "| 周 | 周期 | 额度快照数 | 5小时最高使用 | 5小时最后使用 | 7天最高使用 | 7天最后使用 | 是否触顶 | 最新额度快照 |",
                "|---|---|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        if not weeks:
            lines.append("| 无 | 无 | 0 | — | — | — | — | 否 |  |")
            continue
        for week in weeks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        week.get("week", ""),
                        f"{week.get('start', '')} 到 {week.get('end', '')}",
                        fmt_int(week.get("snapshot_count") or 0),
                        fmt_percent(week.get("five_hour_max_percent")),
                        fmt_percent(week.get("five_hour_latest_percent")),
                        fmt_percent(week.get("seven_day_max_percent")),
                        fmt_percent(week.get("seven_day_latest_percent")),
                        "是" if week.get("near_limit") else "否",
                        week.get("latest_seen_at") or "",
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
        index_lines.append(f"最新数据更新时间：`{summary(grouped[latest])['latest_seen_at']}`")
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
