#!/usr/bin/env python3
"""
Estimate Skip Go transaction completion times from Osmosis block data.

Target use case:
  You already collected Osmosis block data / tx data for Skip Go related contracts
  using analyze_osmosis_skipgo_contracts_blockdata_v2.py.

This script estimates completion time in two ways:

  1) IBC packet completion:
       source TX inclusion time
         -> acknowledge_packet or timeout_packet observed later on Osmosis

     This is the best source-chain block-data estimate for IBC transfer completion.
     Destination-chain receive time usually happens before the acknowledgement returns
     to Osmosis, so acknowledgement time is an upper-bound / confirmation-style
     completion timestamp from the source-chain perspective.

  2) Same-chain post-swap transfer:
       source TX inclusion time -> same block
       completion_seconds = 0

Inputs:
  - txs.jsonl from analyze_osmosis_skipgo_contracts_blockdata_v2.py
  - optional raw_blocks/block_results/*.json.gz saved by the v2 analyzer
  - optional entry_point_actions.csv for same-chain transfer classification

Examples:

  python3 estimate_skipgo_tx_completion_times.py \
    --input-dir osmosis_skipgo_3contracts_61161000_61170000_raw_matching \
    --lookahead-blocks 30000 \
    --workers 4 \
    --plot \
    --out-dir osmosis_skipgo_completion_61161000_61170000

  python3 estimate_skipgo_tx_completion_times.py \
    --txs-jsonl osmosis_skipgo_3contracts_61161000_61170000_raw_matching/txs.jsonl \
    --raw-dir osmosis_skipgo_3contracts_61161000_61170000_raw_matching \
    --scan-to-height 61200000 \
    --workers 4 \
    --plot \
    --out-dir osmosis_skipgo_completion_custom

Notes:
  - Read-only. Does not sign, simulate, or broadcast anything.
  - Wide lookahead ranges on public RPC endpoints can be slow.
  - For exact destination-chain arrival time, scan the destination chain's
    recv_packet events. This script measures source-chain acknowledgement.
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import json
import math
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import requests


DEFAULT_RPC = "https://osmosis-rpc.publicnode.com:443"
Json = dict[str, Any]


@dataclass(frozen=True)
class HttpConfig:
    timeout: float
    retries: int
    retry_sleep: float


@dataclass(frozen=True)
class RpcConfig:
    rpc: str
    http: HttpConfig


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def short(value: Any, limit: int = 800) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


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


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # RFC3339Nano -> Python microseconds.
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)([+-]\d{2}:\d{2})$", s)
    if m:
        head, frac, tz = m.groups()
        s = f"{head}.{frac[:6]}{tz}"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def request_json(
    session: requests.Session,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    http: HttpConfig,
) -> tuple[bool, int | None, Any, str | None, str]:
    last_error = None
    for attempt in range(http.retries + 1):
        try:
            res = session.get(url, params=params or {}, timeout=http.timeout)
            try:
                data = res.json()
            except Exception:
                data = res.text
            if res.status_code >= 400:
                return False, res.status_code, data, short(data), res.url
            if isinstance(data, Mapping) and data.get("error"):
                return False, res.status_code, data, short(data.get("error")), res.url
            return True, res.status_code, data, None, res.url
        except Exception as exc:
            last_error = str(exc)
            if attempt < http.retries:
                time.sleep(http.retry_sleep * (attempt + 1))
    return False, None, None, last_error, url


def rpc_get(session: requests.Session, cfg: RpcConfig, path: str, params: Mapping[str, Any] | None = None) -> Any:
    url = f"{cfg.rpc.rstrip('/')}/{path.lstrip('/')}"
    ok, status, data, err, final_url = request_json(session, url, params=params, http=cfg.http)
    if not ok:
        raise RuntimeError(f"RPC failed: {final_url} status={status} error={err}")
    if isinstance(data, Mapping) and "result" in data:
        return data["result"]
    return data


def get_status(session: requests.Session, cfg: RpcConfig) -> Json:
    return rpc_get(session, cfg, "/status")


def get_latest_height(session: requests.Session, cfg: RpcConfig) -> int:
    status = get_status(session, cfg)
    return int(status["sync_info"]["latest_block_height"])


def get_block(session: requests.Session, cfg: RpcConfig, height: int) -> Json:
    return rpc_get(session, cfg, "/block", {"height": str(height)})


def get_block_results(session: requests.Session, cfg: RpcConfig, height: int) -> Json:
    return rpc_get(session, cfg, "/block_results", {"height": str(height)})


def block_time(session: requests.Session, cfg: RpcConfig, height: int, cache: dict[int, datetime]) -> datetime | None:
    if height in cache:
        return cache[height]
    block = get_block(session, cfg, height)
    t = block.get("block", {}).get("header", {}).get("time", "")
    dt = parse_time(t)
    if dt is not None:
        cache[height] = dt
    return dt


def is_probably_base64(value: str) -> bool:
    if not value or len(value) < 8:
        return False
    if value.startswith((
        "osmo1", "cosmos1", "terra1", "juno1", "akash1", "celestia1",
        "ibc/", "factory/", "transfer/", "/", "http://", "https://",
    )):
        return False
    if any(ch in value for ch in ["_", "-", ".", ":", "/"]):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value))


def maybe_decode_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    s = value
    if not is_probably_base64(s):
        return s
    try:
        raw = base64.b64decode(s + "=" * (-len(s) % 4), validate=True)
        text = raw.decode("utf-8")
    except Exception:
        return s
    printable = sum(1 for ch in text if ch.isprintable())
    if printable / max(1, len(text)) < 0.90:
        return s
    return text or s


def attrs_for_event(event: Json) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    event_type = maybe_decode_text(event.get("type", ""))
    out["_event_type"].append(event_type)
    for attr in event.get("attributes", []) or []:
        key = maybe_decode_text(attr.get("key", ""))
        value = maybe_decode_text(attr.get("value", ""))
        out[key].append(value)
    return dict(out)


def first_attr(attrs: Mapping[str, list[str]], *names: str) -> str:
    for name in names:
        vals = attrs.get(name)
        if vals:
            return str(vals[0])
    return ""


def packet_fields_from_attrs(attrs: Mapping[str, list[str]]) -> Json:
    return {
        "sequence": first_attr(attrs, "packet_sequence", "packet_seq", "sequence"),
        "src_port": first_attr(attrs, "packet_src_port", "packet_source_port", "src_port", "source_port"),
        "src_channel": first_attr(attrs, "packet_src_channel", "packet_source_channel", "src_channel", "source_channel"),
        "dst_port": first_attr(attrs, "packet_dst_port", "packet_destination_port", "dst_port", "destination_port"),
        "dst_channel": first_attr(attrs, "packet_dst_channel", "packet_destination_channel", "dst_channel", "destination_channel"),
        "timeout_timestamp": first_attr(attrs, "packet_timeout_timestamp", "timeout_timestamp"),
        "timeout_height": first_attr(attrs, "packet_timeout_height", "timeout_height"),
    }


def packet_key(fields: Mapping[str, Any]) -> str:
    return f"{fields.get('src_port','')}|{fields.get('src_channel','')}|{fields.get('sequence','')}"


def reverse_packet_key(fields: Mapping[str, Any]) -> str:
    return f"{fields.get('dst_port','')}|{fields.get('dst_channel','')}|{fields.get('sequence','')}"


def looks_like_send_event_type(event_type: str) -> bool:
    return event_type == "send_packet" or "send_packet" in event_type


def looks_like_ack_event_type(event_type: str) -> bool:
    return (
        event_type in {"acknowledge_packet", "ack_packet", "write_acknowledgement"}
        or "acknowledge_packet" in event_type
        or "ack_packet" in event_type
        or "write_acknowledgement" in event_type
    )


def looks_like_timeout_event_type(event_type: str) -> bool:
    return event_type == "timeout_packet" or "timeout_packet" in event_type


def tx_hashes_from_block(block: Json) -> list[str]:
    txs = block.get("block", {}).get("data", {}).get("txs", []) or []
    out: list[str] = []
    for tx_b64 in txs:
        try:
            tx_bytes = base64.b64decode(tx_b64)
            out.append(hashlib.sha256(tx_bytes).hexdigest().upper())
        except Exception:
            out.append("")
    return out


def load_jsonl(path: Path) -> list[Json]:
    rows: list[Json] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_csv(path: Path) -> list[Json]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: Path, rows: Iterable[Json], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_raw_block_results(raw_dir: Path | None, height: int) -> Json | None:
    if raw_dir is None:
        return None
    candidates = [
        raw_dir / "raw_blocks" / "block_results" / f"{height}.json.gz",
        raw_dir / "raw_blocks" / "block_results" / f"{height}.json",
        raw_dir / "block_results" / f"{height}.json.gz",
        raw_dir / "block_results" / f"{height}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        if str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def get_tx_result_for_record(
    session: requests.Session,
    cfg: RpcConfig,
    record: Json,
    raw_input_dir: Path | None,
) -> tuple[Json | None, str]:
    if isinstance(record.get("events"), list):
        return {"events": record.get("events"), "code": record.get("code", 0)}, "embedded_events"

    height = to_int(record.get("height"))
    tx_index = to_int(record.get("tx_index"), -1)
    if height <= 0 or tx_index < 0:
        return None, "missing_height_or_tx_index"

    block_results = load_raw_block_results(raw_input_dir, height)
    source = "raw_block_results" if block_results is not None else "rpc_block_results"
    if block_results is None:
        block_results = get_block_results(session, cfg, height)

    txs = block_results.get("txs_results") or block_results.get("tx_results") or []
    if tx_index >= len(txs):
        return None, f"tx_index_out_of_range:{tx_index}/{len(txs)}"
    return txs[tx_index], source


def extract_send_packets_from_tx(record: Json, tx_result: Json, source: str, source_time: datetime | None) -> list[Json]:
    out: list[Json] = []
    events = tx_result.get("events", []) or []
    for event_idx, event in enumerate(events):
        event_type = maybe_decode_text(event.get("type", ""))
        if not looks_like_send_event_type(event_type):
            continue
        attrs = attrs_for_event(event)
        fields = packet_fields_from_attrs(attrs)
        key = packet_key(fields)
        if not fields["sequence"] or not fields["src_channel"]:
            continue
        out.append({
            "packet_key": key,
            "source_tx_hash": str(record.get("tx_hash", "")).upper(),
            "source_height": to_int(record.get("height")),
            "source_tx_index": to_int(record.get("tx_index"), -1),
            "source_time": iso(source_time),
            "source_event_index": event_idx,
            "source_event_type": event_type,
            "src_port": fields["src_port"],
            "src_channel": fields["src_channel"],
            "dst_port": fields["dst_port"],
            "dst_channel": fields["dst_channel"],
            "sequence": fields["sequence"],
            "timeout_timestamp": fields["timeout_timestamp"],
            "timeout_height": fields["timeout_height"],
            "source_event_source": source,
            "matched_contracts": record.get("matched_contracts", ""),
            "contract_flow": record.get("contract_flow", ""),
            "sender": record.get("sender", ""),
            "fee_amount": record.get("fee_amount", ""),
            "gas_used": record.get("gas_used", ""),
        })
    return out


def collect_source_packets(
    session: requests.Session,
    cfg: RpcConfig,
    tx_records: list[Json],
    raw_input_dir: Path | None,
) -> tuple[list[Json], list[Json]]:
    packets: list[Json] = []
    errors: list[Json] = []
    time_cache: dict[int, datetime] = {}

    for i, record in enumerate(tx_records, 1):
        height = to_int(record.get("height"))
        source_time = parse_time(record.get("timestamp"))
        if source_time is None and height > 0:
            try:
                source_time = block_time(session, cfg, height, time_cache)
            except Exception:
                source_time = None

        try:
            tx_result, source = get_tx_result_for_record(session, cfg, record, raw_input_dir)
            if tx_result is None:
                errors.append({
                    "tx_hash": record.get("tx_hash", ""),
                    "height": height,
                    "error": source,
                })
                continue
            packets.extend(extract_send_packets_from_tx(record, tx_result, source, source_time))
        except Exception as exc:
            errors.append({
                "tx_hash": record.get("tx_hash", ""),
                "height": height,
                "error": str(exc),
            })

        if i % 100 == 0 or i == len(tx_records):
            print(f"[source-packets] {i}/{len(tx_records)} txs, packets={len(packets)}", flush=True)

    # Deduplicate by source tx + packet key + event index.
    seen: set[str] = set()
    deduped: list[Json] = []
    for p in packets:
        k = f"{p['source_tx_hash']}|{p['source_height']}|{p['source_tx_index']}|{p['packet_key']}|{p['source_event_index']}"
        if k in seen:
            continue
        seen.add(k)
        deduped.append(p)
    return deduped, errors


def extract_completion_events_from_tx(
    events: list[Json],
    pending_keys: set[str],
) -> list[Json]:
    out: list[Json] = []
    for event_idx, event in enumerate(events):
        event_type = maybe_decode_text(event.get("type", ""))
        is_ack = looks_like_ack_event_type(event_type)
        is_timeout = looks_like_timeout_event_type(event_type)
        if not (is_ack or is_timeout):
            continue
        attrs = attrs_for_event(event)
        fields = packet_fields_from_attrs(attrs)
        keys = {packet_key(fields), reverse_packet_key(fields)}
        matched = sorted(k for k in keys if k in pending_keys)
        if not matched:
            continue
        for key in matched:
            out.append({
                "packet_key": key,
                "completion_event_type": event_type,
                "completion_status": "acknowledged" if is_ack else "timeout",
                "completion_event_index": event_idx,
                "completion_fields": fields,
            })
    return out


def scan_height_for_completions(
    height: int,
    cfg: RpcConfig,
    pending_keys: set[str],
) -> tuple[int, list[Json], str]:
    session = requests.Session()
    try:
        block_results = get_block_results(session, cfg, height)
        tx_results = block_results.get("txs_results") or block_results.get("tx_results") or []
        matches: list[Json] = []
        if not tx_results:
            return height, [], ""

        for tx_index, tx_result in enumerate(tx_results):
            events = tx_result.get("events", []) or []
            evs = extract_completion_events_from_tx(events, pending_keys)
            for ev in evs:
                ev["completion_height"] = height
                ev["completion_tx_index"] = tx_index
                ev["completion_code"] = tx_result.get("code", 0)
                matches.append(ev)

        if matches:
            block = get_block(session, cfg, height)
            tx_hashes = tx_hashes_from_block(block)
            completion_time = parse_time(block.get("block", {}).get("header", {}).get("time", ""))
            for m in matches:
                idx = int(m["completion_tx_index"])
                m["completion_tx_hash"] = tx_hashes[idx] if idx < len(tx_hashes) else ""
                m["completion_time"] = iso(completion_time)

        return height, matches, ""
    except Exception as exc:
        return height, [], str(exc)


def find_completions(
    cfg: RpcConfig,
    packets: list[Json],
    scan_from: int,
    scan_to: int,
    workers: int,
) -> tuple[dict[str, Json], list[Json]]:
    pending_keys = {p["packet_key"] for p in packets if p.get("packet_key")}
    completion_by_key: dict[str, Json] = {}
    errors: list[Json] = []

    if not pending_keys:
        return completion_by_key, errors

    heights = list(range(scan_from, scan_to + 1))
    print(f"[completion-scan] scanning {len(heights)} blocks: {scan_from}..{scan_to}; pending_keys={len(pending_keys)}", flush=True)

    def one(h: int) -> tuple[int, list[Json], str]:
        return scan_height_for_completions(h, cfg, pending_keys)

    if workers <= 1:
        for i, h in enumerate(heights, 1):
            height, matches, err = one(h)
            if err:
                errors.append({"height": height, "error": err})
            for m in matches:
                key = m["packet_key"]
                if key not in completion_by_key:
                    completion_by_key[key] = m
            if i % 100 == 0 or i == len(heights):
                print(f"[completion-scan] {i}/{len(heights)}; completions={len(completion_by_key)}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(one, h): h for h in heights}
            done = 0
            for fut in as_completed(futs):
                height, matches, err = fut.result()
                if err:
                    errors.append({"height": height, "error": err})
                for m in matches:
                    key = m["packet_key"]
                    if key not in completion_by_key:
                        completion_by_key[key] = m
                done += 1
                if done % 100 == 0 or done == len(futs):
                    print(f"[completion-scan] {done}/{len(futs)}; completions={len(completion_by_key)}", flush=True)

    return completion_by_key, errors


def enrich_packet_rows(packets: list[Json], completion_by_key: Mapping[str, Json]) -> list[Json]:
    rows: list[Json] = []
    for p in packets:
        c = completion_by_key.get(p["packet_key"])
        row = dict(p)
        if c:
            row.update({
                "completion_status": c.get("completion_status", ""),
                "completion_event_type": c.get("completion_event_type", ""),
                "completion_height": c.get("completion_height", ""),
                "completion_tx_index": c.get("completion_tx_index", ""),
                "completion_tx_hash": c.get("completion_tx_hash", ""),
                "completion_time": c.get("completion_time", ""),
            })
            source_time = parse_time(row.get("source_time"))
            completion_time = parse_time(row.get("completion_time"))
            if source_time and completion_time:
                row["completion_seconds"] = (completion_time - source_time).total_seconds()
            else:
                row["completion_seconds"] = ""
            if row.get("completion_height") != "":
                row["completion_blocks"] = to_int(row["completion_height"]) - to_int(row["source_height"])
            else:
                row["completion_blocks"] = ""
        else:
            row.update({
                "completion_status": "not_found",
                "completion_event_type": "",
                "completion_height": "",
                "completion_tx_index": "",
                "completion_tx_hash": "",
                "completion_time": "",
                "completion_seconds": "",
                "completion_blocks": "",
            })
        rows.append(row)
    rows.sort(key=lambda r: (to_int(r.get("source_height")), to_int(r.get("source_tx_index")), str(r.get("packet_key"))))
    return rows


def load_same_chain_completion_rows(entry_actions_path: Path) -> list[Json]:
    rows: list[Json] = []
    if not entry_actions_path.exists():
        return rows
    for r in read_csv(entry_actions_path):
        action = r.get("post_swap_action_type", "")
        if action not in {"transfer", "contract_call"}:
            continue
        rows.append({
            "tx_hash": r.get("tx_hash", ""),
            "height": r.get("height", ""),
            "timestamp": r.get("timestamp", ""),
            "completion_kind": "same_chain_action",
            "completion_status": "same_chain_included",
            "completion_seconds": 0,
            "completion_blocks": 0,
            "post_swap_action_type": action,
            "sender": r.get("sender", ""),
            "to_address": r.get("to_address", ""),
            "fee_amount": r.get("fee_amount", ""),
            "gas_used": r.get("gas_used", ""),
        })
    return rows


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * pct / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] * (c - k) + values[c] * (k - f)


def summarize(packet_rows: list[Json], same_chain_rows: list[Json], scan_from: int, scan_to: int, source_errors: list[Json], scan_errors: list[Json]) -> Json:
    status_counts = Counter(r.get("completion_status", "") for r in packet_rows)
    channel_counts = Counter(r.get("src_channel", "") for r in packet_rows)
    ack_secs = [float(r["completion_seconds"]) for r in packet_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_seconds", "")) != ""]
    ack_blocks = [float(r["completion_blocks"]) for r in packet_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_blocks", "")) != ""]
    all_completed_secs = ack_secs + [0.0 for _ in same_chain_rows]

    by_channel: dict[str, Json] = {}
    for ch in sorted(channel_counts):
        ch_rows = [r for r in packet_rows if r.get("src_channel") == ch]
        ch_ack_secs = [float(r["completion_seconds"]) for r in ch_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_seconds", "")) != ""]
        by_channel[ch] = {
            "packet_count": len(ch_rows),
            "acknowledged": sum(1 for r in ch_rows if r.get("completion_status") == "acknowledged"),
            "timeout": sum(1 for r in ch_rows if r.get("completion_status") == "timeout"),
            "not_found": sum(1 for r in ch_rows if r.get("completion_status") == "not_found"),
            "median_completion_seconds": percentile(ch_ack_secs, 50),
            "p90_completion_seconds": percentile(ch_ack_secs, 90),
        }

    return {
        "scan_from_height": scan_from,
        "scan_to_height": scan_to,
        "source_packet_count": len(packet_rows),
        "same_chain_completion_count": len(same_chain_rows),
        "status_counts": dict(status_counts),
        "source_errors": len(source_errors),
        "completion_scan_errors": len(scan_errors),
        "ack_completion_seconds": {
            "count": len(ack_secs),
            "min": min(ack_secs) if ack_secs else None,
            "p50": percentile(ack_secs, 50),
            "p90": percentile(ack_secs, 90),
            "p95": percentile(ack_secs, 95),
            "max": max(ack_secs) if ack_secs else None,
            "mean": statistics.mean(ack_secs) if ack_secs else None,
        },
        "ack_completion_blocks": {
            "count": len(ack_blocks),
            "min": min(ack_blocks) if ack_blocks else None,
            "p50": percentile(ack_blocks, 50),
            "p90": percentile(ack_blocks, 90),
            "p95": percentile(ack_blocks, 95),
            "max": max(ack_blocks) if ack_blocks else None,
            "mean": statistics.mean(ack_blocks) if ack_blocks else None,
        },
        "all_estimated_completion_seconds_including_same_chain": {
            "count": len(all_completed_secs),
            "min": min(all_completed_secs) if all_completed_secs else None,
            "p50": percentile(all_completed_secs, 50),
            "p90": percentile(all_completed_secs, 90),
            "p95": percentile(all_completed_secs, 95),
            "max": max(all_completed_secs) if all_completed_secs else None,
            "mean": statistics.mean(all_completed_secs) if all_completed_secs else None,
        },
        "by_source_channel": by_channel,
    }


def write_csv(path: Path, rows: Iterable[Json], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def plot_outputs(out_dir: Path, packet_rows: list[Json], same_chain_rows: list[Json]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"[plot] matplotlib unavailable: {exc}", file=sys.stderr)
        return []

    files: list[str] = []

    ack_secs = [float(r["completion_seconds"]) for r in packet_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_seconds", "")) != ""]
    ack_blocks = [float(r["completion_blocks"]) for r in packet_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_blocks", "")) != ""]
    statuses = Counter(r.get("completion_status", "") for r in packet_rows)

    if statuses:
        labels = list(statuses.keys())
        values = [statuses[k] for k in labels]
        p = out_dir / "completion_status_counts.png"
        plt.figure(figsize=(10, 6))
        plt.bar(labels, values)
        plt.xlabel("completion status")
        plt.ylabel("packet count")
        plt.title("IBC packet completion status counts")
        plt.tight_layout()
        plt.savefig(p, dpi=160)
        plt.close()
        files.append(str(p))

    if ack_secs:
        p = out_dir / "ack_completion_seconds_histogram.png"
        plt.figure(figsize=(10, 6))
        plt.hist(ack_secs, bins=min(40, max(8, int(math.sqrt(len(ack_secs))) + 1)))
        plt.xlabel("seconds")
        plt.ylabel("packet count")
        plt.title("Osmosis source TX -> IBC acknowledgement time")
        plt.tight_layout()
        plt.savefig(p, dpi=160)
        plt.close()
        files.append(str(p))

        p = out_dir / "ack_completion_seconds_by_source_height.png"
        xs = [to_int(r["source_height"]) for r in packet_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_seconds", "")) != ""]
        ys = [float(r["completion_seconds"]) for r in packet_rows if r.get("completion_status") == "acknowledged" and str(r.get("completion_seconds", "")) != ""]
        plt.figure(figsize=(13, 6))
        plt.scatter(xs, ys)
        plt.xlabel("source height")
        plt.ylabel("seconds")
        plt.title("IBC acknowledgement time by source height")
        plt.tight_layout()
        plt.savefig(p, dpi=160)
        plt.close()
        files.append(str(p))

    if ack_blocks:
        p = out_dir / "ack_completion_blocks_histogram.png"
        plt.figure(figsize=(10, 6))
        plt.hist(ack_blocks, bins=min(40, max(8, int(math.sqrt(len(ack_blocks))) + 1)))
        plt.xlabel("blocks")
        plt.ylabel("packet count")
        plt.title("Source TX -> IBC acknowledgement block distance")
        plt.tight_layout()
        plt.savefig(p, dpi=160)
        plt.close()
        files.append(str(p))

    channel_secs: dict[str, list[float]] = defaultdict(list)
    for r in packet_rows:
        if r.get("completion_status") == "acknowledged" and str(r.get("completion_seconds", "")) != "":
            channel_secs[str(r.get("src_channel", ""))].append(float(r["completion_seconds"]))
    if channel_secs:
        med = {ch: percentile(vals, 50) or 0 for ch, vals in channel_secs.items()}
        items = sorted(med.items(), key=lambda x: (-x[1], x[0]))[:30]
        labels = [x[0] for x in items]
        values = [x[1] for x in items]
        p = out_dir / "source_channel_median_ack_seconds.png"
        plt.figure(figsize=(12, 7))
        plt.bar(labels, values)
        plt.xlabel("source channel")
        plt.ylabel("median seconds")
        plt.title("Median acknowledgement time by source channel")
        plt.xticks(rotation=35, ha="right")
        plt.tight_layout()
        plt.savefig(p, dpi=160)
        plt.close()
        files.append(str(p))

    if same_chain_rows:
        p = out_dir / "same_chain_completion_count.png"
        plt.figure(figsize=(7, 5))
        plt.bar(["same_chain_included"], [len(same_chain_rows)])
        plt.xlabel("completion type")
        plt.ylabel("tx count")
        plt.title("Same-chain completion count")
        plt.tight_layout()
        plt.savefig(p, dpi=160)
        plt.close()
        files.append(str(p))

    return files


def write_markdown(out_dir: Path, summary: Json, plots: list[str]) -> None:
    lines: list[str] = []
    lines.append("# Skip Go TX Completion Time Estimate")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- IBC completion is measured as `source TX inclusion time -> acknowledge_packet/timeout_packet on Osmosis`.")
    lines.append("- Destination receive time may be earlier than acknowledgement time; this is a source-chain confirmation estimate.")
    lines.append("- Same-chain transfer actions are treated as completed in the source TX block.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for key in [
        "scan_from_height",
        "scan_to_height",
        "source_packet_count",
        "same_chain_completion_count",
        "source_errors",
        "completion_scan_errors",
    ]:
        lines.append(f"| {key} | `{summary.get(key)}` |")

    lines.append("")
    lines.append("## Status counts")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|---|---:|")
    for k, v in sorted((summary.get("status_counts") or {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| `{k}` | {v} |")

    lines.append("")
    lines.append("## Acknowledgement time, seconds")
    lines.append("")
    lines.append("| Stat | Value |")
    lines.append("|---|---:|")
    for k, v in (summary.get("ack_completion_seconds") or {}).items():
        lines.append(f"| {k} | `{v}` |")

    lines.append("")
    lines.append("## Acknowledgement block distance")
    lines.append("")
    lines.append("| Stat | Value |")
    lines.append("|---|---:|")
    for k, v in (summary.get("ack_completion_blocks") or {}).items():
        lines.append(f"| {k} | `{v}` |")

    lines.append("")
    lines.append("## By source channel")
    lines.append("")
    lines.append("| Source channel | Packets | Ack | Timeout | Not found | Median sec | P90 sec |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for ch, row in sorted((summary.get("by_source_channel") or {}).items(), key=lambda kv: (-int(kv[1].get("packet_count", 0)), kv[0])):
        lines.append(
            f"| `{ch}` | {row.get('packet_count')} | {row.get('acknowledged')} | {row.get('timeout')} | "
            f"{row.get('not_found')} | `{row.get('median_completion_seconds')}` | `{row.get('p90_completion_seconds')}` |"
        )

    lines.append("")
    lines.append("## Output files")
    lines.append("")
    for name in [
        "source_packets.csv",
        "packet_completions.csv",
        "same_chain_completions.csv",
        "source_packet_errors.csv",
        "completion_scan_errors.csv",
        "summary.json",
    ]:
        if (out_dir / name).exists():
            lines.append(f"- `{name}`")
    for p in plots:
        lines.append(f"- `{Path(p).name}`")

    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate Skip Go TX completion times from Osmosis block data.")
    parser.add_argument("--input-dir", help="Directory generated by analyze_osmosis_skipgo_contracts_blockdata_v2.py.")
    parser.add_argument("--txs-jsonl", help="Path to txs.jsonl. Defaults to <input-dir>/txs.jsonl.")
    parser.add_argument("--raw-dir", help="Directory containing raw_blocks/. Defaults to --input-dir.")
    parser.add_argument("--entry-actions-csv", help="Path to entry_point_actions.csv. Defaults to <input-dir>/entry_point_actions.csv.")
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--lookahead-blocks", type=int, default=30000)
    parser.add_argument("--scan-from-height", type=int, help="Override completion scan start height.")
    parser.add_argument("--scan-to-height", type=int, help="Override completion scan end height.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=0.7)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir) if args.input_dir else None
    txs_jsonl = Path(args.txs_jsonl) if args.txs_jsonl else (input_dir / "txs.jsonl" if input_dir else None)
    if txs_jsonl is None or not txs_jsonl.exists():
        raise SystemExit("txs.jsonl not found. Supply --input-dir or --txs-jsonl.")

    raw_dir = Path(args.raw_dir) if args.raw_dir else input_dir
    entry_actions_csv = Path(args.entry_actions_csv) if args.entry_actions_csv else (input_dir / "entry_point_actions.csv" if input_dir else None)

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    cfg = RpcConfig(rpc=args.rpc.rstrip("/"), http=HttpConfig(args.timeout, args.retries, args.retry_sleep))
    session = requests.Session()

    tx_records = load_jsonl(txs_jsonl)
    print(f"[load] tx_records={len(tx_records)}", flush=True)

    packets, source_errors = collect_source_packets(session, cfg, tx_records, raw_dir)
    print(f"[source-packets] total={len(packets)} errors={len(source_errors)}", flush=True)

    if packets:
        min_source = min(to_int(p["source_height"]) for p in packets)
        max_source = max(to_int(p["source_height"]) for p in packets)
    else:
        min_source = 0
        max_source = 0

    latest = get_latest_height(session, cfg)
    scan_from = args.scan_from_height or min_source
    scan_to = args.scan_to_height or min(max_source + args.lookahead_blocks, latest)
    if packets and scan_to < scan_from:
        raise SystemExit("completion scan range is invalid.")

    completion_by_key, scan_errors = ({}, [])
    if packets:
        completion_by_key, scan_errors = find_completions(cfg, packets, scan_from, scan_to, max(1, args.workers))

    packet_rows = enrich_packet_rows(packets, completion_by_key)

    same_chain_rows = []
    if entry_actions_csv is not None:
        same_chain_rows = load_same_chain_completion_rows(entry_actions_csv)

    summary = summarize(packet_rows, same_chain_rows, scan_from, scan_to, source_errors, scan_errors)
    summary["input"] = {
        "input_dir": str(input_dir) if input_dir else "",
        "txs_jsonl": str(txs_jsonl),
        "raw_dir": str(raw_dir) if raw_dir else "",
        "entry_actions_csv": str(entry_actions_csv) if entry_actions_csv else "",
        "rpc": args.rpc,
    }
    summary["latest_height"] = latest
    summary["lookahead_blocks"] = args.lookahead_blocks

    packet_fields = [
        "packet_key", "source_tx_hash", "source_height", "source_tx_index", "source_time",
        "source_event_index", "source_event_type", "src_port", "src_channel", "dst_port", "dst_channel",
        "sequence", "timeout_timestamp", "timeout_height", "matched_contracts", "contract_flow",
        "sender", "fee_amount", "gas_used", "completion_status", "completion_event_type",
        "completion_height", "completion_tx_index", "completion_tx_hash", "completion_time",
        "completion_seconds", "completion_blocks",
    ]
    write_csv(out_dir / "source_packets.csv", packets, packet_fields[:18])
    write_csv(out_dir / "packet_completions.csv", packet_rows, packet_fields)

    same_chain_fields = [
        "tx_hash", "height", "timestamp", "completion_kind", "completion_status",
        "completion_seconds", "completion_blocks", "post_swap_action_type", "sender",
        "to_address", "fee_amount", "gas_used",
    ]
    write_csv(out_dir / "same_chain_completions.csv", same_chain_rows, same_chain_fields)
    write_csv(out_dir / "source_packet_errors.csv", source_errors, ["tx_hash", "height", "error"])
    write_csv(out_dir / "completion_scan_errors.csv", scan_errors, ["height", "error"])

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    plots: list[str] = []
    if args.plot:
        plots = plot_outputs(out_dir, packet_rows, same_chain_rows)

    write_markdown(out_dir, summary, plots)

    print(json.dumps({
        "out_dir": str(out_dir),
        "source_packet_count": summary["source_packet_count"],
        "same_chain_completion_count": summary["same_chain_completion_count"],
        "status_counts": summary["status_counts"],
        "ack_completion_seconds": summary["ack_completion_seconds"],
        "completion_scan_errors": summary["completion_scan_errors"],
    }, ensure_ascii=False))
    print(f"Summary written: {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
