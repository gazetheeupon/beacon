#!/usr/bin/env python3
"""Write beacons.json from GitHub issues. Runs on GitHub Actions, not a laptop."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEACONS = ROOT / "beacons.json"
HOST = "0x1e59553f1c9283cde70e7d008602e24eac51e627"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
MIN_UNITS = 1000  # 0.001 USDC, 6 decimals
RPC = "https://mainnet.base.org"
REPO = "gazetheeupon/beacon"
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    data = json.loads(BEACONS.read_text(encoding="utf-8"))
    data.setdefault("beacons", [])
    data.setdefault("used_tx", [])
    return data


def save(data: dict) -> None:
    data["updated"] = iso(now())
    BEACONS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def expire(data: dict) -> int:
    t = now()
    before = len(data["beacons"])
    kept = []
    for b in data["beacons"]:
        until = b.get("until")
        if not until:
            kept.append(b)
            continue
        try:
            dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError:
            kept.append(b)
            continue
        if dt > t or b.get("tier") == "host":
            kept.append(b)
    data["beacons"] = kept
    return before - len(kept)


def rpc(method: str, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        RPC,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "beacon-pulse/1"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


def verify_usdc(tx: str) -> tuple[bool, str]:
    tx = tx.lower().strip()
    if not tx.startswith("0x") or len(tx) != 66:
        return False, "tx hash must be 0x + 64 hex"
    try:
        receipt = rpc("eth_getTransactionReceipt", [tx])
    except Exception as e:
        return False, f"rpc: {e}"
    if not receipt or receipt.get("status") not in ("0x1", "1"):
        return False, "tx not found or failed"
    for log in receipt.get("logs") or []:
        addr = (log.get("address") or "").lower()
        topics = [t.lower() for t in (log.get("topics") or [])]
        if addr != USDC or not topics or topics[0] != TRANSFER_TOPIC or len(topics) < 3:
            continue
        to_addr = "0x" + topics[2][-40:]
        amount = int(log.get("data") or "0x0", 16)
        if to_addr == HOST and amount >= MIN_UNITS:
            return True, f"ok {amount} units"
    return False, "no USDC transfer of >= 0.001 to host"


def parse_body(raw: str) -> dict | None:
    if not raw:
        return None
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
        else:
            return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def comment(issue: str, text: str) -> None:
    if not TOKEN or not issue:
        print("comment skipped", text[:200])
        return
    url = f"https://api.github.com/repos/{REPO}/issues/{issue}/comments"
    body = json.dumps({"body": text}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "beacon-pulse/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        print("comment failed", e.read()[:300])


def close_issue(issue: str) -> None:
    if not TOKEN or not issue:
        return
    url = f"https://api.github.com/repos/{REPO}/issues/{issue}"
    body = json.dumps({"state": "closed"}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "beacon-pulse/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as e:
        print("close failed", e.read()[:300])


def upsert(data: dict, entry: dict, replace_github: str | None, paid: bool) -> None:
    if replace_github and not paid:
        data["beacons"] = [
            b
            for b in data["beacons"]
            if not (b.get("github") == replace_github and b.get("tier") == "free")
        ]
    data["beacons"].insert(0, entry)


def handle_issue(data: dict) -> None:
    title = (os.environ.get("ISSUE_TITLE") or "").strip().lower()
    body = os.environ.get("ISSUE_BODY") or ""
    user = os.environ.get("ISSUE_USER") or ""
    number = os.environ.get("ISSUE_NUMBER") or ""
    if title != "pulse":
        comment(number, "Ignored: title must be exactly `pulse`. See https://gazetheeupon.github.io/beacon/pulse/how.html")
        close_issue(number)
        return
    obj = parse_body(body)
    if not obj:
        comment(number, "Ignored: body must contain a JSON object. See how.html")
        close_issue(number)
        return
    name = str(obj.get("name") or "").strip()[:80]
    url = str(obj.get("url") or "").strip()[:300]
    note = str(obj.get("note") or "").strip()[:200]
    address = str(obj.get("address") or "").strip()[:64]
    tx = str(obj.get("tx") or "").strip()
    if not name:
        comment(number, "Ignored: `name` required.")
        close_issue(number)
        return
    if url and not (url.startswith("https://") or url.startswith("http://")):
        comment(number, "Ignored: `url` must start with http(s).")
        close_issue(number)
        return
    paid = False
    until = now() + timedelta(hours=24)
    tier = "free"
    if tx:
        tx_l = tx.lower()
        if tx_l in [x.lower() for x in data.get("used_tx", [])]:
            comment(number, "Ignored: that tx was already used.")
            close_issue(number)
            return
        ok, msg = verify_usdc(tx_l)
        if not ok:
            comment(number, f"Payment check failed: {msg}")
            close_issue(number)
            return
        paid = True
        until = now() + timedelta(days=7)
        tier = "paid"
        data.setdefault("used_tx", []).append(tx_l)
    entry = {
        "name": name,
        "url": url,
        "note": note,
        "address": address,
        "until": iso(until),
        "tier": tier,
        "github": user,
    }
    if paid:
        entry["tx"] = tx.lower()
    upsert(data, entry, user, paid)
    comment(
        number,
        f"Listed as `{name}` until {iso(until)} ({tier}). Log: https://gazetheeupon.github.io/beacon/beacons.json",
    )
    close_issue(number)


def main() -> None:
    data = load()
    dropped = expire(data)
    print("expired", dropped)
    if os.environ.get("EVENT_NAME") == "issues":
        handle_issue(data)
    save(data)
    print("beacons", len(data["beacons"]))


if __name__ == "__main__":
    main()
