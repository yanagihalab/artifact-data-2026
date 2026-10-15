#!/usr/bin/env python3
"""
Run Osmosis Skip Go 3-contract block-data analysis in 100,000-block chunks.

This is a wrapper around:
  analyze_osmosis_skipgo_contracts_blockdata_v2.py

It is designed for long scans, with:
  - 100k block chunking
  - resume / skip completed chunks
  - per-chunk logs
  - merged combined outputs
  - optional combined plotting using plot_osmosis_skipgo_collected_data.py

Default analyzed contracts:
  entry_point:
    osmo10a3k4hvk37cc4hnxctw4p95fhscd2z6h2rmx0aukc6rm8u9qqx9smfsh7u
  ibc_transfer_adapter:
    osmo1m8wg4vxkefhs374qxmmqpyusgz289wmulex5qdwpfx7jnrxzer5s9cv83q
  poolmanager_swap_adapter:
    osmo1xzphwrc9aahmq7smwaggukwx5w2w8mmtqf5mk0ky0v6hh75paxsszfnlu5

Examples:

  # Scan a fixed 100k range.
  python3 run_osmosis_skipgo_100k_block_chunks.py \
    --from-height 61100000 \
    --to-height 61199999 \
    --chunk-size 100000 \
    --workers 4 \
    --save-raw-block-results \
    --raw-save-mode matching \
    --output-root osmosis_skipgo_100k_61100000_61199999

  # Scan latest 300k blocks, 100k per chunk.
  python3 run_osmosis_skipgo_100k_block_chunks.py \
    --last-n-blocks 300000 \
    --chunk-size 100000 \
    --workers 4 \
    --save-raw-block-results \
    --raw-save-mode matching \
    --output-root osmosis_skipgo_latest_300k

  # Generate combined plots after all chunks.
  python3 run_osmosis_skipgo_100k_block_chunks.py \
    --from-height 61000000 \
    --to-height 61199999 \
    --chunk-size 100000 \
    --workers 4 \
    --save-raw-block-results \
    --raw-save-mode matching \
    --plot-combined \
    --output-root osmosis_skipgo_200k

Notes:
  - This script does not sign, simulate, or broadcast anything.
  - Public RPC endpoints may rate-limit long scans. Use --resume to continue.
  - For raw data, --raw-save-mode matching is strongly recommended.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    import requests
except ImportError as exc:
    raise SystemExit("Missing dependency: requests. Install with: pip install requests") from exc


DEFAULT_RPC = "https://osmosis-rpc.publicnode.com:443"
DEFAULT_LCDS = [
    "https://osmosis-lcd.publicnode.com:443",
    "https://lcd.osmosis.zone",
]

Json = dict[str, Any]


@dataclass(frozen=True)
class Chunk:
    index: int
    start: int
    end: int

    @property
    def name(self) -> str:
        return f"chunk_{self.index:04d}_{self.start}_{self.end}"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Json:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[Json], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path) -> list[Json]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def parse_csv_count_file(path: Path, key_field: str) -> Counter[str]:
    out: Counter[str] = Counter()
    for row in read_csv(path):
        key = str(row.get(key_field, ""))
        if key:
            out[key] += to_int(row.get("count"))
    return out


def fetch_latest_height(rpc: str, timeout: float, retries: int) -> tuple[int, int | None]:
    url = rpc.rstrip("/") + "/status"
    last = None
    for attempt in range(retries + 1):
        try:
            res = requests.get(url, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            result = data.get("result", data)
            sync = result.get("sync_info", {})
            latest = int(sync["latest_block_height"])
            earliest_raw = sync.get("earliest_block_height")
            earliest = int(earliest_raw) if earliest_raw not in (None, "") else None
            return latest, earliest
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"failed to query latest height from {url}: {last}")


def make_chunks(start: int, end: int, chunk_size: int) -> list[Chunk]:
    if start > end:
        raise ValueError("start must be <= end")
    chunks: list[Chunk] = []
    current = start
    idx = 1
    while current <= end:
        chunk_end = min(end, current + chunk_size - 1)
        chunks.append(Chunk(index=idx, start=current, end=chunk_end))
        current = chunk_end + 1
        idx += 1
    return chunks


def build_analyzer_cmd(args: argparse.Namespace, chunk: Chunk, out_dir: Path) -> list[str]:
    cmd = [
        sys.executable,
        args.analyzer_script,
        "--rpc",
        args.rpc,
        "--from-height",
        str(chunk.start),
        "--to-height",
        str(chunk.end),
        "--workers",
        str(args.workers),
        "--out-dir",
        str(out_dir),
        "--timeout",
        str(args.timeout),
        "--retries",
        str(args.retries),
        "--retry-sleep",
        str(args.retry_sleep),
    ]

    for lcd in args.lcd:
        cmd.extend(["--lcd", lcd])

    if args.no_lcd_details:
        cmd.append("--no-lcd-details")
    if args.include_event_json:
        cmd.append("--include-event-json")
    if args.save_raw_block_results:
        cmd.append("--save-raw-block-results")
    if args.save_raw_blocks:
        cmd.append("--save-raw-blocks")
    if args.raw_save_mode:
        cmd.extend(["--raw-save-mode", args.raw_save_mode])
    if args.no_raw_compress:
        cmd.append("--no-raw-compress")
    if args.plot_chunks:
        cmd.append("--plot")

    # Allow custom contract list to pass through.
    for contract in args.contract:
        cmd.extend(["--contract", contract])

    return cmd


def run_chunk(args: argparse.Namespace, chunk: Chunk, chunks_dir: Path, logs_dir: Path) -> Json:
    chunk_dir = chunks_dir / chunk.name
    summary_path = chunk_dir / "summary.json"
    log_path = logs_dir / f"{chunk.name}.log"

    if summary_path.exists() and not args.overwrite:
        summary = read_json(summary_path)
        if summary:
            print(f"[skip] {chunk.name} already has summary.json", flush=True)
            return {
                "chunk": chunk.name,
                "start": chunk.start,
                "end": chunk.end,
                "status": "skipped_completed",
                "out_dir": str(chunk_dir),
                "summary": summary,
            }

    ensure_dir(chunk_dir)
    ensure_dir(logs_dir)
    cmd = build_analyzer_cmd(args, chunk, chunk_dir)

    print(f"[run] {chunk.name}: {chunk.start}..{chunk.end}", flush=True)
    print("      " + " ".join(cmd), flush=True)

    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n\n")
        log.flush()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            log.write(line)
            log.flush()
            print(line.rstrip(), flush=True)
        code = proc.wait()

    if code != 0:
        result = {
            "chunk": chunk.name,
            "start": chunk.start,
            "end": chunk.end,
            "status": "failed",
            "returncode": code,
            "out_dir": str(chunk_dir),
            "log": str(log_path),
            "summary": {},
        }
        if args.continue_on_error:
            print(f"[failed] {chunk.name}: returncode={code}. Continuing.", flush=True)
            return result
        raise RuntimeError(f"chunk failed: {chunk.name}, returncode={code}, log={log_path}")

    summary = read_json(summary_path)
    return {
        "chunk": chunk.name,
        "start": chunk.start,
        "end": chunk.end,
        "status": "ok",
        "returncode": code,
        "out_dir": str(chunk_dir),
        "log": str(log_path),
        "summary": summary,
    }


def sum_contract_summaries(chunk_results: list[Json]) -> dict[str, Json]:
    contract_summary: dict[str, Json] = {}

    for cr in chunk_results:
        summary = cr.get("summary") or {}
        for name, row in (summary.get("contract_summary") or {}).items():
            if name not in contract_summary:
                contract_summary[name] = {
                    "address": row.get("address", ""),
                    "tx_count": 0,
                    "execute_event_count": 0,
                    "wasm_event_count": 0,
                    "other_event_count": 0,
                    "direct_msg_count": 0,
                    "blocks_with_hits": 0,
                }
            for field in ["tx_count", "execute_event_count", "wasm_event_count", "other_event_count", "direct_msg_count", "blocks_with_hits"]:
                contract_summary[name][field] += to_int(row.get(field))

    return contract_summary


def sum_counter_from_summaries(chunk_results: list[Json], field: str) -> dict[str, int]:
    c: Counter[str] = Counter()
    for cr in chunk_results:
        summary = cr.get("summary") or {}
        for key, val in (summary.get(field) or {}).items():
            c[str(key)] += to_int(val)
    return dict(c)


def concat_csv_files(files: list[Path], output_path: Path) -> None:
    wrote_header = False
    with output_path.open("w", encoding="utf-8", newline="") as out:
        writer = None
        for file in files:
            if not file.exists():
                continue
            with file.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    continue
                if not wrote_header:
                    writer = csv.DictWriter(out, fieldnames=reader.fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    wrote_header = True
                elif writer is None:
                    continue
                for row in reader:
                    writer.writerow(row)


def aggregate_per_height(files: list[Path], output_path: Path) -> None:
    rows: list[Json] = []
    for file in files:
        rows.extend(read_csv(file))
    rows.sort(key=lambda r: to_int(r.get("height")))
    if rows:
        write_csv(output_path, rows, list(rows[0].keys()))
    else:
        output_path.write_text("", encoding="utf-8")


def merge_outputs(args: argparse.Namespace, output_root: Path, chunk_results: list[Json]) -> Json:
    combined_dir = output_root / "combined"
    ensure_dir(combined_dir)

    ok_chunks = [r for r in chunk_results if r.get("status") in {"ok", "skipped_completed"} and r.get("summary")]
    failed_chunks = [r for r in chunk_results if r.get("status") == "failed"]

    contract_summary = sum_contract_summaries(ok_chunks)
    cooccurrence_counts = sum_counter_from_summaries(ok_chunks, "cooccurrence_counts")
    contract_flow_counts = sum_counter_from_summaries(ok_chunks, "contract_flow_counts")
    message_action_counts = sum_counter_from_summaries(ok_chunks, "message_action_counts")
    message_type_counts = sum_counter_from_summaries(ok_chunks, "message_type_counts")

    total_blocks = sum(to_int((r.get("summary") or {}).get("blocks_scanned")) for r in ok_chunks)
    total_blocks_failed = sum(to_int((r.get("summary") or {}).get("blocks_failed")) for r in ok_chunks)
    total_tx_any = sum(to_int((r.get("summary") or {}).get("tx_count_any_target")) for r in ok_chunks)
    total_success = sum(to_int((r.get("summary") or {}).get("success_tx_count")) for r in ok_chunks)
    total_failed_tx = sum(to_int((r.get("summary") or {}).get("failed_tx_count")) for r in ok_chunks)
    total_fee_uosmo = sum(to_int((r.get("summary") or {}).get("fee_uosmo_total")) for r in ok_chunks)
    total_gas_used = sum(to_int((r.get("summary") or {}).get("gas_used_total")) for r in ok_chunks)

    first_height = min((to_int(r.get("start")) for r in ok_chunks), default=None)
    last_height = max((to_int(r.get("end")) for r in ok_chunks), default=None)

    combined_summary = {
        "from_height": first_height,
        "to_height": last_height,
        "chunk_size": args.chunk_size,
        "chunks_total": len(chunk_results),
        "chunks_ok_or_skipped": len(ok_chunks),
        "chunks_failed": len(failed_chunks),
        "blocks_scanned": total_blocks,
        "blocks_failed": total_blocks_failed,
        "tx_count_any_target": total_tx_any,
        "success_tx_count": total_success,
        "failed_tx_count": total_failed_tx,
        "fee_uosmo_total": total_fee_uosmo,
        "fee_osmo_total": total_fee_uosmo / 1_000_000,
        "gas_used_total": total_gas_used,
        "contract_summary": contract_summary,
        "cooccurrence_counts": cooccurrence_counts,
        "contract_flow_counts": contract_flow_counts,
        "message_action_counts": message_action_counts,
        "message_type_counts": message_type_counts,
        "output_root": str(output_root),
    }
    write_json(combined_dir / "summary.json", combined_summary)

    # Per-chunk table.
    chunk_rows: list[Json] = []
    for r in chunk_results:
        s = r.get("summary") or {}
        row = {
            "chunk": r.get("chunk"),
            "start": r.get("start"),
            "end": r.get("end"),
            "status": r.get("status"),
            "out_dir": r.get("out_dir"),
            "log": r.get("log", ""),
            "blocks_scanned": s.get("blocks_scanned", ""),
            "blocks_failed": s.get("blocks_failed", ""),
            "tx_count_any_target": s.get("tx_count_any_target", ""),
            "success_tx_count": s.get("success_tx_count", ""),
            "failed_tx_count": s.get("failed_tx_count", ""),
            "fee_osmo_total": s.get("fee_osmo_total", ""),
            "gas_used_total": s.get("gas_used_total", ""),
        }
        for name, cs in (s.get("contract_summary") or {}).items():
            row[f"{name}_tx_count"] = cs.get("tx_count", "")
            row[f"{name}_execute_event_count"] = cs.get("execute_event_count", "")
            row[f"{name}_direct_msg_count"] = cs.get("direct_msg_count", "")
        chunk_rows.append(row)

    # Make fieldnames robust.
    fields: list[str] = []
    for row in chunk_rows:
        for k in row.keys():
            if k not in fields:
                fields.append(k)
    if chunk_rows:
        write_csv(combined_dir / "chunks.csv", chunk_rows, fields)

    # Combined compatible files.
    chunk_dirs = [Path(r["out_dir"]) for r in ok_chunks]

    aggregate_per_height([d / "per_height.csv" for d in chunk_dirs], combined_dir / "per_height.csv")
    if args.combine_txs:
        concat_csv_files([d / "txs.csv" for d in chunk_dirs], combined_dir / "txs.csv")
        # JSONL concatenation.
        with (combined_dir / "txs.jsonl").open("w", encoding="utf-8") as out:
            for d in chunk_dirs:
                path = d / "txs.jsonl"
                if path.exists():
                    with path.open("r", encoding="utf-8") as f:
                        for line in f:
                            out.write(line)
    else:
        # Empty file allows plot script to skip tx-level plots gracefully.
        (combined_dir / "txs.csv").write_text("", encoding="utf-8")

    concat_csv_files([d / "entry_point_actions.csv" for d in chunk_dirs], combined_dir / "entry_point_actions.csv")
    concat_csv_files([d / "block_status.csv" for d in chunk_dirs], combined_dir / "block_status.csv")

    # Aggregated contract summary csv.
    contract_rows = [{"contract": name, **row} for name, row in contract_summary.items()]
    write_csv(
        combined_dir / "contracts_summary.csv",
        contract_rows,
        ["contract", "address", "tx_count", "execute_event_count", "wasm_event_count", "other_event_count", "direct_msg_count", "blocks_with_hits"],
    )

    def write_counter(path: Path, counter: Mapping[str, int], key_name: str) -> None:
        rows = [
            {key_name: key, "count": count}
            for key, count in sorted(counter.items(), key=lambda kv: (-to_int(kv[1]), str(kv[0])))
        ]
        write_csv(path, rows, [key_name, "count"])

    write_counter(combined_dir / "cooccurrence_counts.csv", cooccurrence_counts, "matched_contracts")
    write_counter(combined_dir / "contract_flow_counts.csv", contract_flow_counts, "contract_flow")
    write_counter(combined_dir / "message_action_counts.csv", message_action_counts, "message_action")
    write_counter(combined_dir / "message_type_counts.csv", message_type_counts, "message_type")

    # Markdown summary.
    lines: list[str] = []
    lines.append("# Osmosis Skip Go 100k Block Chunk Scan Summary")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for key in [
        "from_height",
        "to_height",
        "chunk_size",
        "chunks_total",
        "chunks_ok_or_skipped",
        "chunks_failed",
        "blocks_scanned",
        "blocks_failed",
        "tx_count_any_target",
        "success_tx_count",
        "failed_tx_count",
        "fee_osmo_total",
        "gas_used_total",
    ]:
        lines.append(f"| {key} | `{combined_summary.get(key)}` |")

    lines.append("")
    lines.append("## Contract summary")
    lines.append("")
    lines.append("| Contract | Address | TX count | Execute events | Wasm events | Other events | Direct MsgExecuteContract | Blocks with hits |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for name, row in contract_summary.items():
        lines.append(
            f"| `{name}` | `{row.get('address')}` | {row.get('tx_count')} | {row.get('execute_event_count')} | "
            f"{row.get('wasm_event_count')} | {row.get('other_event_count')} | {row.get('direct_msg_count')} | {row.get('blocks_with_hits')} |"
        )

    lines.append("")
    lines.append("## Chunk outputs")
    lines.append("")
    lines.append("- `combined/chunks.csv`")
    lines.append("- `combined/summary.json`")
    lines.append("- `combined/per_height.csv`")
    lines.append("- `combined/contracts_summary.csv`")
    lines.append("- `combined/cooccurrence_counts.csv`")
    lines.append("- `combined/contract_flow_counts.csv`")
    if args.combine_txs:
        lines.append("- `combined/txs.csv`")
        lines.append("- `combined/txs.jsonl`")
    lines.append("")
    lines.append("## Per-chunk directories")
    lines.append("")
    for r in chunk_results:
        lines.append(f"- `{r.get('chunk')}`: `{r.get('status')}` -> `{r.get('out_dir')}`")
    (combined_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    return combined_summary


def run_combined_plot(args: argparse.Namespace, output_root: Path) -> None:
    combined_dir = output_root / "combined"
    if not Path(args.plot_script).exists():
        print(f"[plot] plot script not found: {args.plot_script}. Skipping.", flush=True)
        return
    plot_out = output_root / "combined_plots"
    cmd = [
        sys.executable,
        args.plot_script,
        "--input-dir",
        str(combined_dir),
        "--out-dir",
        str(plot_out),
        "--rolling-window",
        str(args.rolling_window),
        "--max-bars",
        str(args.max_bars),
    ]
    print("[plot] " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Osmosis Skip Go block-data analysis in 100k chunks.")
    parser.add_argument("--from-height", type=int)
    parser.add_argument("--to-height", type=int)
    parser.add_argument("--last-n-blocks", type=int, help="Resolve latest height from RPC and scan latest N blocks.")
    parser.add_argument("--chunk-size", type=int, default=100000)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--analyzer-script", default="analyze_osmosis_skipgo_contracts_blockdata_v2.py")
    parser.add_argument("--plot-script", default="plot_osmosis_skipgo_collected_data.py")
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--lcd", action="append", default=DEFAULT_LCDS.copy())
    parser.add_argument("--contract", action="append", default=[], help="Optional contract override as NAME=ADDRESS. Repeats.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=0.7)
    parser.add_argument("--save-raw-block-results", action="store_true")
    parser.add_argument("--save-raw-blocks", action="store_true")
    parser.add_argument("--raw-save-mode", choices=["none", "matching", "all", "failed"], default="matching")
    parser.add_argument("--no-raw-compress", action="store_true")
    parser.add_argument("--no-lcd-details", action="store_true")
    parser.add_argument("--include-event-json", action="store_true")
    parser.add_argument("--plot-chunks", action="store_true", help="Generate plots per chunk. Can be slow and produce many files.")
    parser.add_argument("--plot-combined", action="store_true", help="Generate plots for combined outputs after all chunks.")
    parser.add_argument("--rolling-window", type=int, default=1000, help="Rolling window for combined plots.")
    parser.add_argument("--max-bars", type=int, default=30)
    parser.add_argument("--combine-txs", action="store_true", help="Concatenate txs.csv and txs.jsonl into combined output.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be positive")

    if args.last_n_blocks is not None:
        latest, earliest = fetch_latest_height(args.rpc, args.timeout, args.retries)
        end = args.to_height if args.to_height is not None else latest
        start = max(earliest or 1, end - args.last_n_blocks + 1)
    else:
        if args.from_height is None or args.to_height is None:
            raise SystemExit("Specify --from-height and --to-height, or --last-n-blocks.")
        start = args.from_height
        end = args.to_height

    if start > end:
        raise SystemExit("start height must be <= end height")

    output_root = Path(args.output_root)
    chunks_dir = output_root / "chunks"
    logs_dir = output_root / "logs"
    ensure_dir(chunks_dir)
    ensure_dir(logs_dir)

    chunks = make_chunks(start, end, args.chunk_size)
    plan = {
        "from_height": start,
        "to_height": end,
        "chunk_size": args.chunk_size,
        "chunks": [{"name": c.name, "start": c.start, "end": c.end} for c in chunks],
        "args": vars(args),
    }
    write_json(output_root / "plan.json", plan)

    print(json.dumps({"from_height": start, "to_height": end, "chunk_size": args.chunk_size, "chunks": len(chunks)}, ensure_ascii=False), flush=True)

    if args.dry_run:
        print("[dry-run] plan written. No chunks executed.", flush=True)
        return 0

    chunk_results: list[Json] = []
    for chunk in chunks:
        result = run_chunk(args, chunk, chunks_dir, logs_dir)
        chunk_results.append(result)
        write_json(output_root / "chunk_results.partial.json", chunk_results)

    write_json(output_root / "chunk_results.json", chunk_results)
    combined_summary = merge_outputs(args, output_root, chunk_results)

    if args.plot_combined:
        run_combined_plot(args, output_root)

    print(json.dumps({"output_root": str(output_root), "combined": combined_summary}, ensure_ascii=False))
    print(f"Combined summary: {output_root / 'combined' / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
