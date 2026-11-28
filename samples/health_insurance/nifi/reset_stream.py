"""Empty the two tables the NiFi flow fills (hi_klaim_baru and hi_alert_baru), so the answers are the history's again.

The history (hi_klaim, hi_alert and the rest) is not touched. Run it after a demo or a test of the flow, with the generators in NiFi
stopped, so the 14 questions of judge_demo.json give their fixed numbers again. It deletes rows, so it asks for --yes.

    HI_TRINO_CATALOG=iceberg HI_TRINO_SCHEMA=demo_asuransi python samples/health_insurance/nifi/reset_stream.py --yes
"""
from __future__ import annotations

import argparse
import os
import sys

STREAM_TABLES = ("hi_klaim_baru", "hi_alert_baru")


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
    parser.add_argument("--yes", action="store_true", help="really delete the rows")
    args = parser.parse_args(argv)
    catalog, schema = os.getenv("HI_TRINO_CATALOG"), os.getenv("HI_TRINO_SCHEMA")
    if not catalog or not schema:
        print("Set HI_TRINO_CATALOG and HI_TRINO_SCHEMA to where the sample was loaded.", file=sys.stderr)
        return 2
    cursor = connect()
    for table in STREAM_TABLES:
        cursor.execute(f"SELECT count(*) FROM {catalog}.{schema}.{table}")
        rows = cursor.fetchall()[0][0]
        if not args.yes:
            print(f"[DRY RUN] {table}: {rows:,} rows would be deleted; add --yes")
            continue
        cursor.execute(f"DELETE FROM {catalog}.{schema}.{table}")
        cursor.fetchall()
        print(f"[RESET] {table}: {rows:,} rows deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
