from pathlib import Path

from app.core.impala_env import load_impala_profile


def test_load_impala_profile_aws_section(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        """
### IMPALA CREDENTIALS AWS ENV
IMPALA_HOST=aws-coordinator.example
IMPALA_PORT=443
IMPALA_AUTH_MECHANISM=LDAP
IMPALA_USE_HTTP_TRANSPORT=true

### IMPALA CREDENTIALS INGRAM ENV
IMPALA_HOST=ingram-coordinator.example
IMPALA_PORT=21050
""".strip(),
        encoding="utf-8",
    )
    overrides = load_impala_profile(env, "aws")
    assert overrides["impala_host"] == "aws-coordinator.example"
    assert overrides["impala_port"] == 443
    assert overrides["impala_auth_mechanism"] == "LDAP"
    assert overrides["impala_use_http_transport"] is True
