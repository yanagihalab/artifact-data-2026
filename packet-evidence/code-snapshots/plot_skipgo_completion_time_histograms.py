#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def parse_csv_list(s: str) -> list[str]:
    return [x.strip() for x in str(s).split(",") if x.strip()]


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def percentile(values: list[float], pct: float) -> float | None:
    vals = sorted(values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]

    k = (len(vals) - 1) * pct / 100.0
    f = math.floor(k)
    c = math.ceil(k)

    if f == c:
        return vals[int(k)]

    return vals[f] * (c - k) + vals[c] * (k - f)


def safe_name(s: str, limit: int = 180) -> str:
    out = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in s)
    return (out[:limit].strip("_") or "unknown")


def short_label(s: str, limit: int = 70) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


def read_packet_csv(path: Path, dataset: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            row = dict(r)
            row["_dataset"] = dataset
            rows.append(row)
    return rows


def find_packet_csvs(paths: list[Path]) -> list[Path]:
    found: set[Path] = set()

    for p in paths:
        if p.is_file() and p.name == "packet_completions.csv":
            found.add(p)
            continue

        if p.is_dir() and (p / "packet_completions.csv").exists():
            found.add(p / "packet_completions.csv")
            continue

        if p.exists():
            for q in p.rglob("packet_completions.csv"):
                if ".osmosisd-docker" in q.parts:
                    continue
                found.add(q)

    return sorted(found, key=lambda x: str(x))


def dataset_name(packet_csv: Path) -> str:
    parent = packet_csv.parent
    if parent.name == "completion":
        return parent.parent.name
    return parent.name


def route_key(row: dict[str, Any], group_by: list[str]) -> str:
    return "|".join(str(row.get(k, "") or "") for k in group_by)


def summarize(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
            "mean": None,
            "median": None,
        }

    return {
        "count": len(values),
        "min": min(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fmt(v: Any) -> str:
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):.3f}"
    except Exception:
        return str(v)


def plot_hist(values: list[float], out: Path, title: str, bins: int, log_y: bool = False, log_x: bool = False) -> None:
    if not values:
        return

    data = values
    bins_arg: int | list[float] = bins

    if log_x:
        data = [v for v in values if v > 0]
        if not data:
            return
        lo = min(data)
        hi = max(data)
        if lo < hi:
            bins_arg = [
                10 ** (math.log10(lo) + (math.log10(hi) - math.log10(lo)) * i / bins)
                for i in range(bins + 1)
            ]

    out.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 6))
    plt.hist(data, bins=bins_arg)

    if log_y:
        plt.yscale("log")
    if log_x:
        plt.xscale("log")

    plt.xlabel("completion seconds")
    plt.ylabel("packet count")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out, dpi=170)
    plt.close()


def plot_route_mean_bar(route_rows: list[dict[str, Any]], out: Path, top_n: int) -> None:
    rows = route_rows[:top_n] if top_n > 0 else route_rows
    if not rows:
        return

    labels = [short_label(f"{r['dataset']} | {r['route_key']}", 55) for r in rows]
    means = [float(r["mean"]) for r in rows]

    out.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(max(12, len(rows) * 0.55), 7))
    plt.bar(labels, means)
    plt.xticks(rotation=35, ha="right")
    plt.xlabel("dataset / route")
    plt.ylabel("mean completion seconds")
    plt.title("Route mean completion seconds")
    plt.tight_layout()
    plt.savefig(out, dpi=170)
    plt.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Create SkipGo completion-time histograms from packet_completions.csv.")
    ap.add_argument("--completion-dir", action="append", default=[], help="Directory containing packet_completions.csv. Repeatable.")
    ap.add_argument("--packet-csv", action="append", default=[], help="Direct packet_completions.csv path. Repeatable.")
    ap.add_argument("--search-root", action="append", default=[], help="Root directory to recursively search packet_completions.csv. Repeatable.")
    ap.add_argument("--out-dir", required=True)

    ap.add_argument("--include-status", default="acknowledged", help="Default: acknowledged. Example: acknowledged,timeout")
    ap.add_argument("--include-negative", action="store_true", help="Keep negative completion_seconds. Default is drop.")
    ap.add_argument("--min-seconds", type=float)
    ap.add_argument("--max-seconds", type=float)

    ap.add_argument("--bins", type=int, default=80)
    ap.add_argument("--log-y", action="store_true")
    ap.add_argument("--log-x", action="store_true")
    ap.add_argument("--clip-p99", action="store_true", default=True)
    ap.add_argument("--no-clip-p99", dest="clip_p99", action="store_false")

    ap.add_argument("--group-by", default="src_channel,contract_flow")
    ap.add_argument("--route-histograms", action="store_true")
    ap.add_argument("--top-routes", type=int, default=30)
    ap.add_argument("--min-packets", type=int, default=3)

    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_paths = [Path(x) for x in args.completion_dir + args.packet_csv + args.search_root]
    if not input_paths:
        raise SystemExit("Use --completion-dir, --packet-csv, or --search-root.")

    packet_csvs = find_packet_csvs(input_paths)
    if not packet_csvs:
        raise SystemExit("No packet_completions.csv found.")

    include_status = set(parse_csv_list(args.include_status))
    group_by = parse_csv_list(args.group_by)

    all_rows: list[dict[str, Any]] = []
    for p in packet_csvs:
        all_rows.extend(read_packet_csv(p, dataset_name(p)))

    filter_counts = Counter()
    kept: list[dict[str, Any]] = []

    for row in all_rows:
        filter_counts["input_rows"] += 1

        status = row.get("completion_status", "")
        if status not in include_status:
            filter_counts[f"drop_status_{status or 'empty'}"] += 1
            continue

        seconds = to_float(row.get("completion_seconds"))
        if seconds is None:
            filter_counts["drop_no_completion_seconds"] += 1
            continue

        if seconds < 0 and not args.include_negative:
            filter_counts["drop_negative_seconds"] += 1
            continue

        if args.min_seconds is not None and seconds < args.min_seconds:
            filter_counts["drop_below_min_seconds"] += 1
            continue

        if args.max_seconds is not None and seconds > args.max_seconds:
            filter_counts["drop_above_max_seconds"] += 1
            continue

        row["_completion_seconds_float"] = seconds
        row["_route_key"] = route_key(row, group_by)
        kept.append(row)
        filter_counts["kept_rows"] += 1

    values = [float(r["_completion_seconds_float"]) for r in kept]
    overall = summarize(values)

    dataset_groups: dict[str, list[float]] = defaultdict(list)
    for r in kept:
        dataset_groups[r["_dataset"]].append(float(r["_completion_seconds_float"]))

    dataset_summary: list[dict[str, Any]] = []
    for dataset, vals in sorted(dataset_groups.items()):
        dataset_summary.append({"dataset": dataset, **summarize(vals)})

    route_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in kept:
        route_groups[(r["_dataset"], r["_route_key"])].append(float(r["_completion_seconds_float"]))

    route_summary: list[dict[str, Any]] = []
    for (dataset, rk), vals in route_groups.items():
        if len(vals) < args.min_packets:
            continue
        item = {"dataset": dataset, "route_key": rk, **summarize(vals)}
        parts = rk.split("|")
        for i, field in enumerate(group_by):
            item[field] = parts[i] if i < len(parts) else ""
        route_summary.append(item)

    route_summary.sort(key=lambda r: (float(r.get("mean") or 0), int(r.get("count") or 0)), reverse=True)

    write_csv(
        out_dir / "completion_time_dataset_summary.csv",
        dataset_summary,
        ["dataset", "count", "min", "p50", "p90", "p95", "p99", "max", "mean", "median"],
    )

    write_csv(
        out_dir / "completion_time_route_summary.csv",
        route_summary,
        ["dataset", "route_key", "count", "min", "p50", "p90", "p95", "p99", "max", "mean", "median"] + group_by,
    )

    plots: list[str] = []

    p = out_dir / "completion_seconds_histogram_overall.png"
    plot_hist(values, p, "Completion seconds histogram - overall", args.bins)
    if p.exists():
        plots.append(str(p))

    p = out_dir / "completion_seconds_histogram_overall_logy.png"
    plot_hist(values, p, "Completion seconds histogram - overall log-y", args.bins, log_y=True)
    if p.exists():
        plots.append(str(p))

    if args.log_x:
        p = out_dir / "completion_seconds_histogram_overall_logx.png"
        plot_hist(values, p, "Completion seconds histogram - overall log-x", args.bins, log_y=args.log_y, log_x=True)
        if p.exists():
            plots.append(str(p))

    if args.clip_p99 and values:
        p99 = percentile(values, 99)
        clipped = [v for v in values if p99 is not None and v <= p99]
        p = out_dir / "completion_seconds_histogram_overall_clipped_p99.png"
        plot_hist(clipped, p, "Completion seconds histogram - clipped at p99", args.bins)
        if p.exists():
            plots.append(str(p))

    for ds in dataset_summary:
        dataset = ds["dataset"]
        vals = dataset_groups[dataset]
        p = out_dir / "dataset_histograms" / f"{safe_name(dataset)}.png"
        plot_hist(vals, p, f"Completion seconds histogram - {dataset}", args.bins, log_y=args.log_y)
        if p.exists():
            plots.append(str(p))

    p = out_dir / "route_mean_completion_seconds_top_routes.png"
    plot_route_mean_bar(route_summary, p, args.top_routes)
    if p.exists():
        plots.append(str(p))

    if args.route_histograms:
        selected = route_summary[: args.top_routes] if args.top_routes > 0 else route_summary
        for i, rr in enumerate(selected, 1):
            dataset = rr["dataset"]
            rk = rr["route_key"]
            vals = [
                float(r["_completion_seconds_float"])
                for r in kept
                if r["_dataset"] == dataset and r["_route_key"] == rk
            ]
            p = out_dir / "route_histograms" / f"{i:02d}_{safe_name(dataset)}_{safe_name(rk)}.png"
            plot_hist(vals, p, f"Route completion seconds\n{dataset}\n{rk}", args.bins, log_y=args.log_y)
            if p.exists():
                plots.append(str(p))

    report = {
        "input_packet_csvs": [str(p) for p in packet_csvs],
        "include_status": sorted(include_status),
        "filter_counts": dict(filter_counts),
        "overall_summary": overall,
        "dataset_summary_count": len(dataset_summary),
        "route_summary_count": len(route_summary),
        "group_by": group_by,
        "plots": plots,
    }
    write_json(out_dir / "completion_histogram_report.json", report)

    md: list[str] = []
    md.append("# SkipGo completion-time histogram report")
    md.append("")
    md.append("## Filter counts")
    md.append("")
    md.append("| Metric | Count |")
    md.append("|---|---:|")
    for k, v in dict(filter_counts).items():
        md.append(f"| `{k}` | `{v}` |")

    md.append("")
    md.append("## Overall summary")
    md.append("")
    md.append("| Metric | Value |")
    md.append("|---|---:|")
    for k, v in overall.items():
        md.append(f"| `{k}` | `{fmt(v)}` |")

    md.append("")
    md.append("## Dataset summary")
    md.append("")
    md.append("| Dataset | Count | Min | P50 | P90 | P95 | P99 | Max | Mean |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in dataset_summary:
        md.append(
            f"| `{r['dataset']}` | {r['count']} | {fmt(r['min'])} | {fmt(r['p50'])} | {fmt(r['p90'])} | "
            f"{fmt(r['p95'])} | {fmt(r['p99'])} | {fmt(r['max'])} | {fmt(r['mean'])} |"
        )

    md.append("")
    md.append("## Top route summary")
    md.append("")
    md.append("| Rank | Dataset | Route key | Count | Mean | P50 | P90 | P95 | Max |")
    md.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for i, r in enumerate(route_summary[:50], 1):
        md.append(
            f"| {i} | `{r['dataset']}` | `{r['route_key']}` | {r['count']} | "
            f"{fmt(r['mean'])} | {fmt(r['p50'])} | {fmt(r['p90'])} | {fmt(r['p95'])} | {fmt(r['max'])} |"
        )

    md.append("")
    md.append("## Plot files")
    md.append("")
    for p in plots:
        md.append(f"- `{p}`")

    (out_dir / "completion_histogram_report.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({
        "out_dir": str(out_dir),
        "packet_csvs": len(packet_csvs),
        "kept_rows": len(kept),
        "overall_summary": overall,
        "plots": len(plots),
    }, ensure_ascii=False))
    print(f"Report: {out_dir / 'completion_histogram_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
