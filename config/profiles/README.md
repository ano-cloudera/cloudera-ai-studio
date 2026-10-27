# Configuration profiles

| Layer | Location |
|-------|----------|
| Safe full template | `config/examples/accelerator.env.example` |
| Local non-secret defaults | `deployment/profiles/local.env` |
| CAI non-secret defaults | `deployment/profiles/cai.env` |
| Customer project | `projects/<slug>/project.yaml` |
| Secrets | Environment / CAI app env / `env://` connector refs — never git |

Precedence: application defaults → deployment profile → `.env` → runtime overrides.
