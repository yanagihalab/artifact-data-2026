#!/usr/bin/env python3
"""
Analyze multiple Osmosis Skip Go related CosmWasm contracts from actual block data.

Default contracts:
  Entry Point:
    osmo10a3k4hvk37cc4hnxctw4p95fhscd2z6h2rmx0aukc6rm8u9qqx9smfsh7u
  IBC Transfer Adapter:
    osmo1m8wg4vxkefhs374qxmmqpyusgz289wmulex5qdwpfx7jnrxzer5s9cv83q
  PoolManager Swap Adapter:
    osmo1xzphwrc9aahmq7smwaggukwx5w2w8mmtqf5mk0ky0v6hh75paxsszfnlu5

It scans CometBFT /block_results for each block in the selected range and
detects tx events whose _contract_address matches one of the target contracts.\nBy default it saves extracted records only; raw /block_results and /block JSON can\nbe saved with --save-raw-block-results / --save-raw-blocks.

It can optionally enrich matching transactions through Cosmos REST:
  /cosmos/tx/v1beta1/txs/{hash}

Examples:
  python3 analyze_osmosis_skipgo_contracts_blockdata.py \
    --from-height 61169000 \
    --to-height 61170000 \
    --workers 4 \
    --plot \
    --out-dir osmosis_skipgo_contracts_61169000_61170000

  python3 analyze_osmosis_skipgo_contracts_blockdata.py \
    --last-n-blocks 20000 \
    --workers 4 \
    --plot \
    --out-dir osmosis_skipgo_contracts_latest_20000

  python3 analyze_osmosis_skipgo_contracts_blockdata.py \
    --from-time "2026-05-08T11:30:00Z" \
    --to-time "2026-05-08T12:00:00Z" \
    --workers 4 \
    --plot \
    --out-dir osmosis_skipgo_contracts_time_range

Notes:
  - This script does not broadcast or sign anything.
  - Wide block ranges on public RPC endpoints can be slow or rate-limited.
  - /tx_search is intentionally not used; this is block-data based.
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
DEFAULT_LCDS = [
    "https://osmosis-lcd.publicnode.com:443",
    "https://lcd.osmosis.zone",
]

DEFAULT_CONTRACTS = {
    "entry_point": "osmo10a3k4hvk37cc4hnxctw4p95fhscd2z6h2rmx0aukc6rm8u9qqx9smfsh7u",
    "ibc_transfer_adapter": "osmo1m8wg4vxkefhs374qxmmqpyusgz289wmulex5qdwpfx7jnrxzer5s9cv83q",
    "poolmanager_swap_adapter": "osmo1xzphwrc9aahmq7smwaggukwx5w2w8mmtqf5mk0ky0v6hh75paxsszfnlu5",
}

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


@dataclass
class BlockScanResult:
    height: int
    ok: bool
    matching_records: list[Json]
    error: str = ""


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_raw_json(path: Path, data: Any, compress: bool) -> None:
    ensure_dir(path.parent)
    if compress:
        if not str(path).endswith(".gz"):
            path = Path(str(path) + ".gz")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
            f.write("\n")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def short(value: Any, limit: int = 600) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def parse_contract_arg(values: Sequence[str] | None) -> dict[str, str]:
    if not values:
        return dict(DEFAULT_CONTRACTS)
    out: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit("--contract must be NAME=ADDRESS")
        name, address = item.split("=", 1)
        name = name.strip()
        address = address.strip()
        if not name or not address:
            raise SystemExit("--contract must be NAME=ADDRESS")
        out[name] = address
    return out


def invert_contracts(contracts: Mapping[str, str]) -> dict[str, str]:
    return {address: name for name, address in contracts.items()}


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_payload: Any = None,
    http: HttpConfig,
) -> tuple[bool, int | None, Any, str | None, str]:
    last_error = None
    for attempt in range(http.retries + 1):
        try:
            res = session.request(method, url, params=params, json=json_payload, timeout=http.timeout)
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
    ok, status, data, error, final_url = request_json(session, "GET", url, params=params or {}, http=cfg.http)
    if not ok:
        raise RuntimeError(f"RPC failed: url={final_url} status={status} error={error}")
    if isinstance(data, Mapping) and "result" in data:
        return data["result"]
    return data


def get_status(session: requests.Session, cfg: RpcConfig) -> Json:
    return rpc_get(session, cfg, "/status")


def get_latest_earliest(session: requests.Session, cfg: RpcConfig) -> tuple[int, int | None]:
    status = get_status(session, cfg)
    sync = status.get("sync_info", {})
    latest = int(sync["latest_block_height"])
    earliest_raw = sync.get("earliest_block_height")
    earliest = int(earliest_raw) if earliest_raw not in (None, "") else None
    return latest, earliest


def parse_rfc3339(value: str) -> datetime:
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Convert RFC3339Nano to Python-supported microseconds.
    m = re.match(r"^(.*T\d{2}:\d{2}:\d{2})\.(\d+)([+-]\d{2}:\d{2})$", s)
    if m:
        head, frac, tz = m.groups()
        s = f"{head}.{frac[:6]}{tz}"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_block(session: requests.Session, cfg: RpcConfig, height: int) -> Json:
    return rpc_get(session, cfg, "/block", {"height": str(height)})


def get_block_results(session: requests.Session, cfg: RpcConfig, height: int) -> Json:
    return rpc_get(session, cfg, "/block_results", {"height": str(height)})


def get_block_time(session: requests.Session, cfg: RpcConfig, height: int, cache: dict[int, datetime]) -> datetime:
    if height in cache:
        return cache[height]
    block = get_block(session, cfg, height)
    t = parse_rfc3339(block["block"]["header"]["time"])
    cache[height] = t
    return t


def find_first_height_at_or_after_time(
    session: requests.Session,
    cfg: RpcConfig,
    target: datetime,
    earliest: int,
    latest: int,
    cache: dict[int, datetime],
) -> int:
    lo, hi = earliest, latest
    ans = latest + 1
    while lo <= hi:
        mid = (lo + hi) // 2
        t = get_block_time(session, cfg, mid, cache)
        if t >= target:
            ans = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return ans


def find_last_height_at_or_before_time(
    session: requests.Session,
    cfg: RpcConfig,
    target: datetime,
    earliest: int,
    latest: int,
    cache: dict[int, datetime],
) -> int:
    lo, hi = earliest, latest
    ans = earliest - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        t = get_block_time(session, cfg, mid, cache)
        if t <= target:
            ans = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return ans


def resolve_range(args: argparse.Namespace, session: requests.Session, cfg: RpcConfig) -> tuple[int, int, Json]:
    latest, earliest_raw = get_latest_earliest(session, cfg)
    earliest = earliest_raw or 1
    meta: Json = {"latest_height": latest, "earliest_height": earliest_raw}

    if args.last_n_blocks is not None:
        to_height = args.to_height if args.to_height is not None else latest
        from_height = max(earliest, to_height - args.last_n_blocks + 1)
        return from_height, to_height, meta

    if args.from_time or args.to_time:
        if not (args.from_time and args.to_time):
            raise SystemExit("--from-time and --to-time must be supplied together")
        from_time = parse_rfc3339(args.from_time)
        to_time = parse_rfc3339(args.to_time)
        if from_time > to_time:
            raise SystemExit("--from-time must be <= --to-time")
        cache: dict[int, datetime] = {}
        from_height = find_first_height_at_or_after_time(session, cfg, from_time, earliest, latest, cache)
        to_height = find_last_height_at_or_before_time(session, cfg, to_time, earliest, latest, cache)
        if from_height > to_height:
            raise SystemExit("No blocks found for the requested time range")
        meta.update({
            "from_time_utc": from_time.isoformat(),
            "to_time_utc": to_time.isoformat(),
            "resolved_from_height": from_height,
            "resolved_to_height": to_height,
        })
        return from_height, to_height, meta

    if args.from_height is None or args.to_height is None:
        raise SystemExit("Specify --from-height/--to-height, --from-time/--to-time, or --last-n-blocks")
    if args.from_height > args.to_height:
        raise SystemExit("--from-height must be <= --to-height")
    return args.from_height, args.to_height, meta


def is_probably_base64(value: str) -> bool:
    if not value or len(value) < 8:
        return False
    if value.startswith((
        "osmo1", "cosmos1", "neutron1", "terra1", "sei1", "inj1", "archway1",
        "ibc/", "factory/", "cw20:", "transfer/", "http://", "https://", "/",
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

    padded = s + "=" * (-len(s) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
        text = raw.decode("utf-8")
    except Exception:
        return s

    printable = sum(1 for ch in text if ch.isprintable())
    if printable / max(1, len(text)) < 0.90:
        return s
    return text or s


def iter_event_attrs(events: list[Json]) -> Iterable[tuple[int, str, str, str]]:
    for event_index, event in enumerate(events or []):
        event_type = maybe_decode_text(event.get("type", ""))
        for attr in event.get("attributes", []) or []:
            key = maybe_decode_text(attr.get("key", ""))
            val = maybe_decode_text(attr.get("value", ""))
            yield event_index, event_type, key, val


def tx_hashes_from_block(block: Json) -> list[str]:
    out: list[str] = []
    txs = block.get("block", {}).get("data", {}).get("txs", []) or []
    for tx_b64 in txs:
        try:
            tx_bytes = base64.b64decode(tx_b64)
            out.append(hashlib.sha256(tx_bytes).hexdigest().upper())
        except Exception:
            out.append("")
    return out


def normalize_execute_msg(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        # Try JSON text, then base64-encoded JSON text.
        try:
            return json.loads(value)
        except Exception:
            pass
        try:
            raw = base64.b64decode(value + "=" * (-len(value) % 4))
            text = raw.decode("utf-8")
            return json.loads(text)
        except Exception:
            return value
    return value


def fetch_lcd_tx(session: requests.Session, lcds: list[str], tx_hash: str, http: HttpConfig) -> tuple[Json | None, str, str]:
    for lcd in lcds:
        url = f"{lcd.rstrip('/')}/cosmos/tx/v1beta1/txs/{tx_hash}"
        ok, status, data, error, _ = request_json(session, "GET", url, http=http)
        if ok and isinstance(data, Mapping):
            return dict(data), lcd, ""
        last_error = f"{lcd}: status={status} error={error}"
    return None, "", last_error if "last_error" in locals() else "not attempted"


def extract_lcd_tx_details(lcd_data: Json | None, contracts_by_addr: Mapping[str, str]) -> Json:
    if not lcd_data:
        return {
            "timestamp": "",
            "sender": "",
            "fee_amount": "",
            "fee_gas_limit": "",
            "memo": "",
            "msg_types": "",
            "direct_msg_counts": {},
            "direct_execute_msgs": {},
            "direct_funds": {},
            "contracts_seen_in_top_level_msgs": [],
            "lcd_code": "",
            "lcd_raw_log": "",
        }

    tx = lcd_data.get("tx", {}) or {}
    body = tx.get("body", {}) or {}
    auth_info = tx.get("auth_info", {}) or {}
    fee = auth_info.get("fee", {}) or {}
    tx_response = lcd_data.get("tx_response", {}) or {}

    messages = body.get("messages", []) or []
    msg_types: list[str] = []
    senders: set[str] = set()
    direct_msg_counts: Counter[str] = Counter()
    direct_execute_msgs: dict[str, list[Any]] = defaultdict(list)
    direct_funds: dict[str, list[Any]] = defaultdict(list)
    contracts_seen: list[str] = []

    for msg in messages:
        if not isinstance(msg, Mapping):
            continue
        msg_type = str(msg.get("@type", ""))
        msg_types.append(msg_type)
        contract = msg.get("contract")
        if contract:
            contracts_seen.append(str(contract))

        if msg_type.endswith("MsgExecuteContract") and contract in contracts_by_addr:
            name = contracts_by_addr[str(contract)]
            direct_msg_counts[name] += 1
            if msg.get("sender"):
                senders.add(str(msg.get("sender")))
            direct_execute_msgs[name].append(normalize_execute_msg(msg.get("msg")))
            direct_funds[name].append(msg.get("funds", []))

    fee_amount = ";".join(
        f"{coin.get('amount', '')}{coin.get('denom', '')}"
        for coin in (fee.get("amount", []) or [])
        if isinstance(coin, Mapping)
    )

    return {
        "timestamp": tx_response.get("timestamp", ""),
        "sender": ";".join(sorted(senders)),
        "fee_amount": fee_amount,
        "fee_gas_limit": fee.get("gas_limit", ""),
        "memo": body.get("memo", ""),
        "msg_types": ";".join(msg_types),
        "direct_msg_counts": dict(direct_msg_counts),
        "direct_execute_msgs": dict(direct_execute_msgs),
        "direct_funds": dict(direct_funds),
        "contracts_seen_in_top_level_msgs": sorted(set(contracts_seen)),
        "lcd_code": tx_response.get("code", ""),
        "lcd_raw_log": tx_response.get("raw_log", ""),
    }


def analyze_tx_events(events: list[Json], contracts_by_addr: Mapping[str, str]) -> Json:
    event_counts: dict[str, Counter[str]] = {name: Counter() for name in contracts_by_addr.values()}
    all_contract_events: list[Json] = []
    message_actions: Counter[str] = Counter()
    message_modules: Counter[str] = Counter()

    for event_index, event_type, key, value in iter_event_attrs(events):
        if event_type == "message" and key == "action":
            message_actions[value] += 1
        if event_type == "message" and key == "module":
            message_modules[value] += 1

        if key == "_contract_address" and value in contracts_by_addr:
            name = contracts_by_addr[value]
            event_counts[name][event_type] += 1
            all_contract_events.append({
                "event_index": event_index,
                "event_type": event_type,
                "contract_name": name,
                "contract_address": value,
            })

    matched_contracts = sorted({ev["contract_name"] for ev in all_contract_events})
    first_order: list[str] = []
    seen: set[str] = set()
    for ev in sorted(all_contract_events, key=lambda x: int(x["event_index"])):
        if ev["contract_name"] not in seen:
            first_order.append(ev["contract_name"])
            seen.add(ev["contract_name"])

    return {
        "event_counts": {name: dict(counter) for name, counter in event_counts.items()},
        "matched_contracts": matched_contracts,
        "contract_event_sequence": all_contract_events,
        "contract_flow": "->".join(first_order),
        "message_actions": dict(message_actions),
        "message_modules": dict(message_modules),
    }


def get_contract_count(event_counts: Mapping[str, Mapping[str, int]], name: str, event_type: str) -> int:
    return int((event_counts.get(name, {}) or {}).get(event_type, 0) or 0)


def parse_entry_point_swap_details(execute_msgs: list[Any]) -> list[Json]:
    rows: list[Json] = []
    for msg in execute_msgs:
        if not isinstance(msg, Mapping):
            continue
        saa = msg.get("swap_and_action")
        if not isinstance(saa, Mapping):
            continue

        user_swap = saa.get("user_swap", {})
        if not isinstance(user_swap, Mapping):
            user_swap = {}

        swap_mode = ""
        swap_venue = ""
        ops: list[Json] = []

        if "swap_exact_asset_in" in user_swap and isinstance(user_swap["swap_exact_asset_in"], Mapping):
            swap_mode = "swap_exact_asset_in"
            node = user_swap["swap_exact_asset_in"]
            swap_venue = str(node.get("swap_venue_name", ""))
            ops = [dict(x) for x in (node.get("operations", []) or []) if isinstance(x, Mapping)]

        elif "smart_swap_exact_asset_in" in user_swap and isinstance(user_swap["smart_swap_exact_asset_in"], Mapping):
            swap_mode = "smart_swap_exact_asset_in"
            node = user_swap["smart_swap_exact_asset_in"]
            swap_venue = str(node.get("swap_venue_name", ""))
            for route in node.get("routes", []) or []:
                if not isinstance(route, Mapping):
                    continue
                for op in route.get("operations", []) or []:
                    if isinstance(op, Mapping):
                        ops.append(dict(op))

        min_asset = saa.get("min_asset", {})
        min_denom = ""
        min_amount = ""
        if isinstance(min_asset, Mapping):
            native = min_asset.get("native", {})
            if isinstance(native, Mapping):
                min_denom = str(native.get("denom", ""))
                min_amount = str(native.get("amount", ""))

        action_type = ""
        receiver = ""
        recover_address = ""
        source_channel = ""
        to_address = ""
        action = saa.get("post_swap_action", {})
        if isinstance(action, Mapping) and action:
            action_type = next(iter(action.keys()))
            if "ibc_transfer" in action and isinstance(action["ibc_transfer"], Mapping):
                ibc_info = action["ibc_transfer"].get("ibc_info", {})
                if isinstance(ibc_info, Mapping):
                    source_channel = str(ibc_info.get("source_channel", ""))
                    receiver = str(ibc_info.get("receiver", ""))
                    recover_address = str(ibc_info.get("recover_address", ""))
            if "transfer" in action and isinstance(action["transfer"], Mapping):
                to_address = str(action["transfer"].get("to_address", ""))
            if "contract_call" in action and isinstance(action["contract_call"], Mapping):
                to_address = str(action["contract_call"].get("contract_address", ""))

        affiliates = saa.get("affiliates", []) or []
        aff_count = 0
        aff_bps = 0
        for aff in affiliates:
            if isinstance(aff, Mapping):
                aff_count += 1
                try:
                    aff_bps += int(aff.get("basis_points_fee") or 0)
                except Exception:
                    pass

        rows.append({
            "swap_mode": swap_mode,
            "swap_venue": swap_venue,
            "swap_operation_count": len(ops),
            "pool_ids": ";".join(str(op.get("pool", "")) for op in ops if op.get("pool") is not None),
            "denoms_in": ";".join(str(op.get("denom_in", "")) for op in ops if op.get("denom_in")),
            "denoms_out": ";".join(str(op.get("denom_out", "")) for op in ops if op.get("denom_out")),
            "min_asset_denom": min_denom,
            "min_asset_amount": min_amount,
            "post_swap_action_type": action_type,
            "source_channel": source_channel,
            "receiver": receiver,
            "recover_address": recover_address,
            "to_address": to_address,
            "affiliate_count": aff_count,
            "affiliate_bps_total": aff_bps,
        })
    return rows


def scan_height(
    height: int,
    cfg: RpcConfig,
    lcds: list[str],
    contracts_by_addr: Mapping[str, str],
    include_lcd_details: bool,
    include_event_json: bool,
    raw_dir: Path | None = None,
    raw_save_mode: str = "none",
    save_raw_block_results: bool = False,
    save_raw_blocks: bool = False,
    raw_compress: bool = True,
) -> BlockScanResult:
    session = requests.Session()
    try:
        block_results = get_block_results(session, cfg, height)
        if raw_dir is not None and raw_save_mode == "all" and save_raw_block_results:
            write_raw_json(raw_dir / "block_results" / f"{height}.json", block_results, raw_compress)

        tx_results = block_results.get("txs_results") or block_results.get("tx_results") or []
        if not tx_results:
            if raw_dir is not None and raw_save_mode == "all" and save_raw_blocks:
                block_for_raw = get_block(session, cfg, height)
                write_raw_json(raw_dir / "blocks" / f"{height}.json", block_for_raw, raw_compress)
            return BlockScanResult(height=height, ok=True, matching_records=[])

        matching_indices: list[int] = []
        tx_event_analyses: dict[int, Json] = {}
        for idx, tx_result in enumerate(tx_results):
            events = tx_result.get("events", []) or []
            analysis = analyze_tx_events(events, contracts_by_addr)
            if analysis["matched_contracts"]:
                matching_indices.append(idx)
                tx_event_analyses[idx] = analysis

        should_save_matching_raw = bool(matching_indices) and raw_dir is not None and raw_save_mode in {"matching", "all"}

        if should_save_matching_raw and save_raw_block_results and raw_save_mode != "all":
            write_raw_json(raw_dir / "block_results" / f"{height}.json", block_results, raw_compress)

        if not matching_indices:
            if raw_dir is not None and raw_save_mode == "all" and save_raw_blocks:
                block_for_raw = get_block(session, cfg, height)
                write_raw_json(raw_dir / "blocks" / f"{height}.json", block_for_raw, raw_compress)
            return BlockScanResult(height=height, ok=True, matching_records=[])

        block = get_block(session, cfg, height)
        if raw_dir is not None and raw_save_mode in {"matching", "all"} and save_raw_blocks:
            write_raw_json(raw_dir / "blocks" / f"{height}.json", block, raw_compress)
        tx_hashes = tx_hashes_from_block(block)

        records: list[Json] = []
        for idx in matching_indices:
            tx_result = tx_results[idx]
            tx_hash = tx_hashes[idx] if idx < len(tx_hashes) else ""

            lcd_data = None
            lcd_source = ""
            lcd_error = ""
            if include_lcd_details and tx_hash:
                lcd_data, lcd_source, lcd_error = fetch_lcd_tx(session, lcds, tx_hash, cfg.http)

            lcd_details = extract_lcd_tx_details(lcd_data, contracts_by_addr)
            event_analysis = tx_event_analyses[idx]
            event_counts = event_analysis["event_counts"]

            # Entry Point swap details are only parsed for direct entry point messages.
            entry_name = "entry_point"
            entry_msgs = (lcd_details.get("direct_execute_msgs", {}) or {}).get(entry_name, [])
            swap_details = parse_entry_point_swap_details(entry_msgs)

            record: Json = {
                "height": height,
                "tx_index": idx,
                "tx_hash": tx_hash,
                "success": int(tx_result.get("code", 0) or 0) == 0,
                "code": tx_result.get("code", 0),
                "codespace": tx_result.get("codespace", ""),
                "gas_wanted": tx_result.get("gas_wanted", ""),
                "gas_used": tx_result.get("gas_used", ""),
                "timestamp": lcd_details["timestamp"],
                "sender": lcd_details["sender"],
                "fee_amount": lcd_details["fee_amount"],
                "fee_gas_limit": lcd_details["fee_gas_limit"],
                "memo": lcd_details["memo"],
                "msg_types": lcd_details["msg_types"],
                "matched_contracts": ";".join(event_analysis["matched_contracts"]),
                "contract_flow": event_analysis["contract_flow"],
                "message_actions": event_analysis["message_actions"],
                "message_modules": event_analysis["message_modules"],
                "event_counts": event_counts,
                "direct_msg_counts": lcd_details["direct_msg_counts"],
                "contracts_seen_in_top_level_msgs": ";".join(lcd_details["contracts_seen_in_top_level_msgs"]),
                "direct_execute_msgs": lcd_details["direct_execute_msgs"],
                "direct_funds": lcd_details["direct_funds"],
                "entry_point_swap_details": swap_details,
                "lcd_source": lcd_source,
                "lcd_error": lcd_error,
                "raw_log": tx_result.get("log", "") or lcd_details.get("lcd_raw_log", ""),
            }

            for name in contracts_by_addr.values():
                record[f"{name}_execute_events"] = get_contract_count(event_counts, name, "execute")
                record[f"{name}_wasm_events"] = get_contract_count(event_counts, name, "wasm")
                record[f"{name}_other_events"] = sum(
                    int(v or 0)
                    for k, v in (event_counts.get(name, {}) or {}).items()
                    if k not in {"execute", "wasm"}
                )
                record[f"{name}_direct_msg_count"] = int((lcd_details["direct_msg_counts"].get(name, 0) or 0))

            if include_event_json:
                record["events"] = tx_result.get("events", []) or []

            records.append(record)

        return BlockScanResult(height=height, ok=True, matching_records=records)
    except Exception as exc:
        if raw_dir is not None and raw_save_mode in {"failed", "all"}:
            write_raw_json(raw_dir / "errors" / f"{height}.json", {"height": height, "error": str(exc)}, raw_compress)
        return BlockScanResult(height=height, ok=False, matching_records=[], error=str(exc))


def unique_records(records: list[Json]) -> list[Json]:
    seen: set[str] = set()
    out: list[Json] = []
    for rec in records:
        key = rec.get("tx_hash") or f"{rec.get('height')}:{rec.get('tx_index')}"
        if key in seen:
            continue
        seen.add(str(key))
        out.append(rec)
    out.sort(key=lambda r: (int(r.get("height") or 0), int(r.get("tx_index") or 0)))
    return out


def parse_uosmo(value: Any) -> int:
    if value is None:
        return 0
    total = 0
    for part in str(value).split(";"):
        m = re.fullmatch(r"(\d+)uosmo", part.strip())
        if m:
            total += int(m.group(1))
    return total


def flatten_tx_record(rec: Json, contract_names: list[str]) -> Json:
    row = {
        "height": rec.get("height", ""),
        "timestamp": rec.get("timestamp", ""),
        "tx_index": rec.get("tx_index", ""),
        "tx_hash": rec.get("tx_hash", ""),
        "success": rec.get("success", ""),
        "code": rec.get("code", ""),
        "sender": rec.get("sender", ""),
        "matched_contracts": rec.get("matched_contracts", ""),
        "contract_flow": rec.get("contract_flow", ""),
        "msg_types": rec.get("msg_types", ""),
        "gas_used": rec.get("gas_used", ""),
        "gas_wanted": rec.get("gas_wanted", ""),
        "fee_amount": rec.get("fee_amount", ""),
        "fee_uosmo": parse_uosmo(rec.get("fee_amount")),
        "fee_gas_limit": rec.get("fee_gas_limit", ""),
        "message_actions": json.dumps(rec.get("message_actions", {}), ensure_ascii=False),
        "message_modules": json.dumps(rec.get("message_modules", {}), ensure_ascii=False),
        "contracts_seen_in_top_level_msgs": rec.get("contracts_seen_in_top_level_msgs", ""),
        "entry_point_swap_details": short(rec.get("entry_point_swap_details", []), 2000),
        "lcd_source": rec.get("lcd_source", ""),
        "lcd_error": rec.get("lcd_error", ""),
    }
    for name in contract_names:
        row[f"{name}_execute_events"] = rec.get(f"{name}_execute_events", 0)
        row[f"{name}_wasm_events"] = rec.get(f"{name}_wasm_events", 0)
        row[f"{name}_other_events"] = rec.get(f"{name}_other_events", 0)
        row[f"{name}_direct_msg_count"] = rec.get(f"{name}_direct_msg_count", 0)
    return row


def write_csv(path: Path, rows: Iterable[Json], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: Iterable[Json]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def build_per_height(records: list[Json], contract_names: list[str], from_height: int, to_height: int) -> list[Json]:
    by_height: dict[int, Json] = {}
    for h in range(from_height, to_height + 1):
        row: Json = {"height": h, "tx_count_any_target": 0}
        for name in contract_names:
            row[f"{name}_tx_count"] = 0
            row[f"{name}_execute_event_count"] = 0
            row[f"{name}_wasm_event_count"] = 0
            row[f"{name}_direct_msg_count"] = 0
        by_height[h] = row

    for rec in records:
        h = int(rec["height"])
        row = by_height[h]
        row["tx_count_any_target"] += 1
        matched = set(str(rec.get("matched_contracts", "")).split(";")) if rec.get("matched_contracts") else set()
        for name in contract_names:
            if name in matched:
                row[f"{name}_tx_count"] += 1
            row[f"{name}_execute_event_count"] += int(rec.get(f"{name}_execute_events") or 0)
            row[f"{name}_wasm_event_count"] += int(rec.get(f"{name}_wasm_events") or 0)
            row[f"{name}_direct_msg_count"] += int(rec.get(f"{name}_direct_msg_count") or 0)

    return list(by_height.values())


def build_entry_point_action_rows(records: list[Json]) -> list[Json]:
    rows: list[Json] = []
    for rec in records:
        details = rec.get("entry_point_swap_details") or []
        if not isinstance(details, list):
            continue
        for detail in details:
            if not isinstance(detail, Mapping):
                continue
            row = {
                "height": rec.get("height", ""),
                "timestamp": rec.get("timestamp", ""),
                "tx_hash": rec.get("tx_hash", ""),
                "sender": rec.get("sender", ""),
                "fee_amount": rec.get("fee_amount", ""),
                "gas_used": rec.get("gas_used", ""),
                **dict(detail),
            }
            rows.append(row)
    return rows


def summarize(records: list[Json], block_statuses: list[Json], contracts: Mapping[str, str], from_height: int, to_height: int, rpc: str) -> Json:
    contract_names = list(contracts.keys())
    contract_summary: dict[str, Json] = {}
    for name in contract_names:
        tx_count = sum(1 for rec in records if name in str(rec.get("matched_contracts", "")).split(";"))
        contract_summary[name] = {
            "address": contracts[name],
            "tx_count": tx_count,
            "execute_event_count": sum(int(rec.get(f"{name}_execute_events") or 0) for rec in records),
            "wasm_event_count": sum(int(rec.get(f"{name}_wasm_events") or 0) for rec in records),
            "other_event_count": sum(int(rec.get(f"{name}_other_events") or 0) for rec in records),
            "direct_msg_count": sum(int(rec.get(f"{name}_direct_msg_count") or 0) for rec in records),
            "blocks_with_hits": len({
                int(rec["height"])
                for rec in records
                if name in str(rec.get("matched_contracts", "")).split(";")
            }),
        }

    cooccurrence = Counter(str(rec.get("matched_contracts", "")) for rec in records)
    flows = Counter(str(rec.get("contract_flow", "")) for rec in records)
    msg_actions = Counter()
    msg_types = Counter()
    for rec in records:
        actions = rec.get("message_actions", {}) or {}
        if isinstance(actions, Mapping):
            for k, v in actions.items():
                msg_actions[k] += int(v or 0)
        for mt in str(rec.get("msg_types", "")).split(";"):
            if mt:
                msg_types[mt] += 1

    return {
        "rpc": rpc,
        "from_height": from_height,
        "to_height": to_height,
        "blocks_scanned": to_height - from_height + 1,
        "blocks_failed": sum(1 for x in block_statuses if not x.get("ok")),
        "tx_count_any_target": len(records),
        "success_tx_count": sum(1 for rec in records if rec.get("success")),
        "failed_tx_count": sum(1 for rec in records if not rec.get("success")),
        "fee_uosmo_total": sum(parse_uosmo(rec.get("fee_amount")) for rec in records),
        "fee_osmo_total": sum(parse_uosmo(rec.get("fee_amount")) for rec in records) / 1_000_000,
        "gas_used_total": sum(int(rec.get("gas_used") or 0) for rec in records),
        "contract_summary": contract_summary,
        "cooccurrence_counts": dict(cooccurrence),
        "contract_flow_counts": dict(flows),
        "message_action_counts": dict(msg_actions),
        "message_type_counts": dict(msg_types),
    }


def write_counter_csv(path: Path, counter_dict: Mapping[str, int], key_name: str = "key") -> None:
    rows = [{key_name: k, "count": v} for k, v in sorted(counter_dict.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))]
    write_csv(path, rows, [key_name, "count"])


def plot_outputs(out_dir: Path, per_height: list[Json], contract_names: list[str]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"[plot] matplotlib unavailable: {exc}", file=sys.stderr)
        return []

    files: list[str] = []
    heights = [int(r["height"]) for r in per_height]

    # Separate plots per contract to avoid visually overloaded charts.
    for name in contract_names:
        series_specs = [
            (f"{name}_tx_count", "tx count", f"{name}_tx_count_by_height.png"),
            (f"{name}_execute_event_count", "execute event count", f"{name}_execute_events_by_height.png"),
            (f"{name}_direct_msg_count", "top-level direct MsgExecuteContract count", f"{name}_direct_msgs_by_height.png"),
        ]
        for column, ylabel, filename in series_specs:
            values = [int(r.get(column) or 0) for r in per_height]
            if not any(values):
                continue
            path = out_dir / filename
            plt.figure(figsize=(13, 6))
            plt.plot(heights, values)
            plt.xlabel("block height")
            plt.ylabel(ylabel)
            plt.title(f"{name}: {ylabel} by height")
            plt.tight_layout()
            plt.savefig(path, dpi=160)
            plt.close()
            files.append(str(path))

            cumulative: list[int] = []
            run = 0
            for v in values:
                run += v
                cumulative.append(run)
            cpath = out_dir / filename.replace("_by_height.png", "_cumulative.png")
            plt.figure(figsize=(13, 6))
            plt.plot(heights, cumulative)
            plt.xlabel("block height")
            plt.ylabel(f"cumulative {ylabel}")
            plt.title(f"{name}: cumulative {ylabel}")
            plt.tight_layout()
            plt.savefig(cpath, dpi=160)
            plt.close()
            files.append(str(cpath))

    total_values = [int(r.get("tx_count_any_target") or 0) for r in per_height]
    if any(total_values):
        path = out_dir / "any_target_tx_count_by_height.png"
        plt.figure(figsize=(13, 6))
        plt.plot(heights, total_values)
        plt.xlabel("block height")
        plt.ylabel("tx count")
        plt.title("Any target contract: tx count by height")
        plt.tight_layout()
        plt.savefig(path, dpi=160)
        plt.close()
        files.append(str(path))

    return files


def write_markdown(out_dir: Path, summary: Json, plot_files: list[str]) -> None:
    lines: list[str] = []
    lines.append("# Osmosis Skip Go Contracts Block Data Analysis")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    for key in [
        "from_height",
        "to_height",
        "blocks_scanned",
        "blocks_failed",
        "tx_count_any_target",
        "success_tx_count",
        "failed_tx_count",
        "fee_osmo_total",
        "gas_used_total",
    ]:
        lines.append(f"| {key} | `{summary.get(key, '')}` |")

    lines.append("")
    lines.append("## Contract summary")
    lines.append("")
    lines.append("| Contract | Address | Tx count | Execute events | Wasm events | Other events | Direct MsgExecuteContract | Blocks with hits |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for name, row in summary.get("contract_summary", {}).items():
        lines.append(
            f"| `{name}` | `{row.get('address')}` | {row.get('tx_count', 0)} | {row.get('execute_event_count', 0)} | "
            f"{row.get('wasm_event_count', 0)} | {row.get('other_event_count', 0)} | {row.get('direct_msg_count', 0)} | {row.get('blocks_with_hits', 0)} |"
        )

    lines.append("")
    lines.append("## Co-occurrence counts")
    lines.append("")
    lines.append("| Matched contracts in tx | Count |")
    lines.append("|---|---:|")
    for key, count in sorted(summary.get("cooccurrence_counts", {}).items(), key=lambda kv: (-int(kv[1]), str(kv[0]))):
        lines.append(f"| `{key}` | {count} |")

    lines.append("")
    lines.append("## Flow pattern counts")
    lines.append("")
    lines.append("| First-seen contract flow | Count |")
    lines.append("|---|---:|")
    for key, count in sorted(summary.get("contract_flow_counts", {}).items(), key=lambda kv: (-int(kv[1]), str(kv[0]))):
        lines.append(f"| `{key}` | {count} |")

    lines.append("")
    lines.append("## Output files")
    lines.append("")
    raw_save = summary.get("raw_save", {})
    if raw_save and raw_save.get("raw_dir"):
        lines.append("")
        lines.append("## Raw block data")
        lines.append("")
        lines.append(f"- Raw directory: `{raw_save.get('raw_dir')}`")
        lines.append(f"- Save mode: `{raw_save.get('raw_save_mode')}`")
        lines.append(f"- Saved /block_results: `{raw_save.get('save_raw_block_results')}`")
        lines.append(f"- Saved /block: `{raw_save.get('save_raw_blocks')}`")
        lines.append(f"- Compressed: `{raw_save.get('compressed')}`")
        lines.append("")

    for name in [
        "summary.json",
        "contracts_summary.csv",
        "txs.csv",
        "txs.jsonl",
        "per_height.csv",
        "entry_point_actions.csv",
        "cooccurrence_counts.csv",
        "contract_flow_counts.csv",
        "message_action_counts.csv",
        "message_type_counts.csv",
        "block_status.csv",
    ]:
        if (out_dir / name).exists():
            lines.append(f"- `{name}`")
    for path in plot_files:
        lines.append(f"- `{Path(path).name}`")

    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze multiple Osmosis Skip Go contracts from block data.")
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--lcd", action="append", default=[], help="LCD/REST endpoint. Can be repeated.")
    parser.add_argument("--contract", action="append", default=[], help="Contract target as NAME=ADDRESS. If omitted, defaults to the 3 Skip Go Osmosis contracts.")
    parser.add_argument("--from-height", type=int)
    parser.add_argument("--to-height", type=int)
    parser.add_argument("--from-time")
    parser.add_argument("--to-time")
    parser.add_argument("--last-n-blocks", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=0.7)
    parser.add_argument("--no-lcd-details", action="store_true", help="Do not fetch decoded tx details from LCD. Faster, but no direct MsgExecuteContract details.")
    parser.add_argument("--include-event-json", action="store_true", help="Include raw events in txs.jsonl. Output can become large.")
    parser.add_argument("--save-raw-block-results", action="store_true", help="Save raw /block_results JSON.")
    parser.add_argument("--save-raw-blocks", action="store_true", help="Save raw /block JSON. This is larger and requires fetching /block for all saved heights.")
    parser.add_argument("--raw-save-mode", choices=["none", "matching", "all", "failed"], default="none", help="Which heights to save raw data for. matching saves only blocks with target contract hits.")
    parser.add_argument("--no-raw-compress", action="store_true", help="Save raw JSON uncompressed. Default saves .json.gz.")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--max-blocks-warning", type=int, default=50000)
    args = parser.parse_args(argv)

    contracts = parse_contract_arg(args.contract)
    contracts_by_addr = invert_contracts(contracts)
    contract_names = list(contracts.keys())

    http = HttpConfig(timeout=args.timeout, retries=args.retries, retry_sleep=args.retry_sleep)
    cfg = RpcConfig(rpc=args.rpc.rstrip("/"), http=http)
    lcds = [x.rstrip("/") for x in args.lcd] or DEFAULT_LCDS

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    session = requests.Session()
    from_height, to_height, range_meta = resolve_range(args, session, cfg)
    total_blocks = to_height - from_height + 1

    if total_blocks > args.max_blocks_warning:
        print(f"WARNING: scanning {total_blocks} blocks on a public RPC may be slow/rate-limited.", file=sys.stderr)

    print(f"[scan] contracts: {json.dumps(contracts, ensure_ascii=False)}", flush=True)
    print(f"[scan] range: {from_height}..{to_height} ({total_blocks} blocks)", flush=True)

    block_statuses: list[Json] = []
    all_records: list[Json] = []

    raw_dir: Path | None = None
    if args.raw_save_mode != "none" and (args.save_raw_block_results or args.save_raw_blocks):
        raw_dir = out_dir / "raw_blocks"
        ensure_dir(raw_dir)

    def one(height: int) -> BlockScanResult:
        return scan_height(
            height=height,
            cfg=cfg,
            lcds=lcds,
            contracts_by_addr=contracts_by_addr,
            include_lcd_details=not args.no_lcd_details,
            include_event_json=args.include_event_json,
            raw_dir=raw_dir,
            raw_save_mode=args.raw_save_mode,
            save_raw_block_results=args.save_raw_block_results,
            save_raw_blocks=args.save_raw_blocks,
            raw_compress=not args.no_raw_compress,
        )

    heights = list(range(from_height, to_height + 1))
    if args.workers <= 1:
        for i, h in enumerate(heights, 1):
            res = one(h)
            block_statuses.append({"height": h, "ok": res.ok, "matching_tx_count": len(res.matching_records), "error": res.error})
            all_records.extend(res.matching_records)
            if i % 100 == 0 or i == len(heights):
                print(f"[scan] {i}/{len(heights)} blocks, matched_txs={len(all_records)}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futs = {executor.submit(one, h): h for h in heights}
            done = 0
            for fut in as_completed(futs):
                h = futs[fut]
                res = fut.result()
                block_statuses.append({"height": h, "ok": res.ok, "matching_tx_count": len(res.matching_records), "error": res.error})
                all_records.extend(res.matching_records)
                done += 1
                if done % 100 == 0 or done == len(futs):
                    print(f"[scan] {done}/{len(futs)} blocks, matched_txs={len(all_records)}", flush=True)

    block_statuses.sort(key=lambda x: int(x["height"]))
    records = unique_records(all_records)

    per_height = build_per_height(records, contract_names, from_height, to_height)
    entry_actions = build_entry_point_action_rows(records)
    summary = summarize(records, block_statuses, contracts, from_height, to_height, args.rpc)
    summary["range_meta"] = range_meta
    summary["lcds"] = lcds
    summary["contracts"] = contracts
    summary["raw_save"] = {
        "raw_dir": str(raw_dir) if raw_dir else "",
        "raw_save_mode": args.raw_save_mode,
        "save_raw_block_results": bool(args.save_raw_block_results),
        "save_raw_blocks": bool(args.save_raw_blocks),
        "compressed": not args.no_raw_compress,
    }

    # CSV outputs.
    tx_rows = [flatten_tx_record(rec, contract_names) for rec in records]
    tx_fields = [
        "height", "timestamp", "tx_index", "tx_hash", "success", "code", "sender", "matched_contracts", "contract_flow",
        "msg_types", "gas_used", "gas_wanted", "fee_amount", "fee_uosmo", "fee_gas_limit", "message_actions",
        "message_modules", "contracts_seen_in_top_level_msgs", "entry_point_swap_details", "lcd_source", "lcd_error",
    ]
    for name in contract_names:
        tx_fields.extend([f"{name}_execute_events", f"{name}_wasm_events", f"{name}_other_events", f"{name}_direct_msg_count"])

    write_csv(out_dir / "txs.csv", tx_rows, tx_fields)
    write_jsonl(out_dir / "txs.jsonl", records)

    per_height_fields = ["height", "tx_count_any_target"]
    for name in contract_names:
        per_height_fields.extend([
            f"{name}_tx_count",
            f"{name}_execute_event_count",
            f"{name}_wasm_event_count",
            f"{name}_direct_msg_count",
        ])
    write_csv(out_dir / "per_height.csv", per_height, per_height_fields)

    contracts_summary_rows = [
        {"contract": name, **row}
        for name, row in summary["contract_summary"].items()
    ]
    write_csv(
        out_dir / "contracts_summary.csv",
        contracts_summary_rows,
        ["contract", "address", "tx_count", "execute_event_count", "wasm_event_count", "other_event_count", "direct_msg_count", "blocks_with_hits"],
    )

    write_csv(out_dir / "block_status.csv", block_statuses, ["height", "ok", "matching_tx_count", "error"])
    write_counter_csv(out_dir / "cooccurrence_counts.csv", summary["cooccurrence_counts"], "matched_contracts")
    write_counter_csv(out_dir / "contract_flow_counts.csv", summary["contract_flow_counts"], "contract_flow")
    write_counter_csv(out_dir / "message_action_counts.csv", summary["message_action_counts"], "message_action")
    write_counter_csv(out_dir / "message_type_counts.csv", summary["message_type_counts"], "message_type")

    action_fields = [
        "height", "timestamp", "tx_hash", "sender", "fee_amount", "gas_used", "swap_mode", "swap_venue",
        "swap_operation_count", "pool_ids", "denoms_in", "denoms_out", "min_asset_denom", "min_asset_amount",
        "post_swap_action_type", "source_channel", "receiver", "recover_address", "to_address",
        "affiliate_count", "affiliate_bps_total",
    ]
    write_csv(out_dir / "entry_point_actions.csv", entry_actions, action_fields)

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    plot_files: list[str] = []
    if args.plot:
        plot_files = plot_outputs(out_dir, per_height, contract_names)

    write_markdown(out_dir, summary, plot_files)

    print(json.dumps({
        "out_dir": str(out_dir),
        "from_height": from_height,
        "to_height": to_height,
        "tx_count_any_target": summary["tx_count_any_target"],
        "contract_summary": summary["contract_summary"],
        "blocks_failed": summary["blocks_failed"],
        "plot_files": plot_files,
    }, ensure_ascii=False))
    print(f"Markdown summary written: {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
