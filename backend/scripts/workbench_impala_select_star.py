#!/usr/bin/env python3
"""Workbench CAI — simple SELECT * (hardcoded Ingram .env)."""

from impala.dbapi import connect

IMPALA_HOST = "cbase02.imid.local"
IMPALA_PORT = 21050
IMPALA_DATABASE = "gold"
IMPALA_AUTH_MECHANISM = "GSSAPI"
IMPALA_USER = "partner-multipolar"
IMPALA_PASSWORD = "imid@Jakarta1!"
IMPALA_USE_SSL = True
IMPALA_USE_HTTP_TRANSPORT = False
IMPALA_HTTP_PATH = "cliservice"
IMPALA_KERBEROS_SERVICE_NAME = "impala"

# ganti table / limit sesuka hati
TABLE = "gold.corr_b2b_branch_material_month"
LIMIT = 20

conn = connect(
    host=IMPALA_HOST,
    port=IMPALA_PORT,
    database=IMPALA_DATABASE,
    auth_mechanism=IMPALA_AUTH_MECHANISM,
    user=IMPALA_USER or None,
    password=IMPALA_PASSWORD or None,
    use_ssl=IMPALA_USE_SSL,
    use_http_transport=IMPALA_USE_HTTP_TRANSPORT,
    http_path=IMPALA_HTTP_PATH,
    kerberos_service_name=IMPALA_KERBEROS_SERVICE_NAME,
)
cur = conn.cursor()
cur.execute(f"SELECT * FROM {TABLE} LIMIT {LIMIT}")
cols = [c[0] for c in cur.description]
print(cols)
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
