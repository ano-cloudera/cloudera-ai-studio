# Cloudera AI Studio — AMP packaging

## Current status

**AMP artifact generation** is still tied to successful **real CAI deployment** validation. This repo ships the **accelerator content** and **readiness gates** SEs use before packaging.

## Accelerator kit (in repo)

| Asset | Purpose |
|-------|---------|
| [AMP_ACCELERATOR_PLAYBOOK.md](../../docs/deployment/AMP_ACCELERATOR_PLAYBOOK.md) | SE demo script, bootstrap, UAT |
| [config/examples/accelerator.env.example](../../config/examples/accelerator.env.example) | Deployment env template |
| [config/examples/accelerator-demo-presentation.json](../../config/examples/accelerator-demo-presentation.json) | Ontology-style Ask Data UX preset |
| `scripts/demo/bootstrap_golden_banking.py` | Connector + Knowledge + Semantic |
| `scripts/demo/apply_accelerator_demo_profile.py` | Starters + presentation preset |
| `scripts/demo/run_amp_accelerator_readiness.py` | Local readiness gate |
| `scripts/demo/banking_uat_english_memory_3q.py` | English memory UAT |
| `scripts/demo/banking_robustness_10q.py` | 10-turn robustness UAT |

## Deployment specs (for AMP build)

- [../backend/SPEC.md](../backend/SPEC.md)
- [../frontend/SPEC.md](../frontend/SPEC.md)
- [../qdrant/SPEC.md](../qdrant/SPEC.md)

## Quick start (local)

```bash
# After CAI sim backend is up
python3 scripts/demo/bootstrap_golden_banking.py --apply
python3 scripts/demo/apply_accelerator_demo_profile.py
python3 scripts/demo/run_amp_accelerator_readiness.py --live-uat
```

Sign-off checklist: [CAI_REAL_DEPLOYMENT_CHECKLIST.md](../../docs/deployment/CAI_REAL_DEPLOYMENT_CHECKLIST.md)
