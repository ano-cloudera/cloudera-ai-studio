"""How long a claim takes from the moment NiFi creates it to the moment Trino can read it.

The generators in the NiFi flow put the creation time in the claim id (KLM-N and KLM-F followed by yyMMddHHmmss in the NiFi
servers' clock, UTC). This script polls hi_klaim_baru and, for every claim it sees for the first time, prints the seconds between that
time and the moment Trino returned the row. Start the generators in NiFi first. Read only.

    HI_TRINO_CATALOG=iceberg HI_TRINO_SCHEMA=demo_asuransi python samples/health_insurance/nifi/measure_latency.py --claims 10
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from datetime import datetime, timezone


def claim_time(claim_id: str) -> datetime | None:
    """The creation time in a generator's claim id, or None for a claim that did not come from a generator."""
    stamp = claim_id[5:17] if claim_id[:5] in ("KLM-N", "KLM-F") else ""
    try:
        return datetime.strptime(stamp, "%y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def connect():
    import trino
    from trino.auth import BasicAuthentication

    user, password = os.environ["TRINO_USER"], os.environ.get("TRINO_PASSWORD", "")
    kwargs = dict(host=os.environ["TRINO_HOST"], port=int(os.environ.get("TRINO_PORT", "443")), user=user, http_scheme=os.environ.get("TRINO_HTTP_SCHEME", "https"))
    if password:
        kwargs["auth"] = BasicAuthentication(user, password)
    return trino.dbapi.connect(**kwargs).cursor()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--claims", type=int, default=10, help="how many new claims to time")
    parser.add_argument("--wait", type=int, default=300, help="give up after this many seconds")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between two reads")
    args = parser.parse_args(argv)
    catalog, schema = os.getenv("HI_TRINO_CATALOG"), os.getenv("HI_TRINO_SCHEMA")
    if not catalog or not schema:
        print("Set HI_TRINO_CATALOG and HI_TRINO_SCHEMA to where the sample was loaded.", file=sys.stderr)
        return 2
    cursor = connect()
    table = f"{catalog}.{schema}.hi_klaim_baru"
    cursor.execute(f"SELECT id_klaim FROM {table}")
    seen = {row[0] for row in cursor.fetchall()}
    print(f"[START] {len(seen)} claims already in {table}; timing the next {args.claims}", flush=True)
    lags: list[float] = []
    deadline = time.monotonic() + args.wait
    while len(lags) < args.claims and time.monotonic() < deadline:
        cursor.execute(f"SELECT id_klaim FROM {table}")
        now = datetime.now(timezone.utc)
        for (claim_id,) in cursor.fetchall():
            if claim_id in seen:
                continue
            seen.add(claim_id)
            created = claim_time(claim_id)
            if created is None:
                continue
            lags.append((now - created).total_seconds())
            print(f"[CLAIM] {claim_id}: readable in Trino {lags[-1]:.1f}s after it was created", flush=True)
        time.sleep(args.interval)
    if not lags:
        print("[NONE] no new claim appeared; start the generators in NiFi", file=sys.stderr)
        return 1
    print(f"[RESULT] {len(lags)} claims: median {statistics.median(lags):.1f}s, slowest {max(lags):.1f}s "
          f"(the reading itself adds up to {args.interval:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
