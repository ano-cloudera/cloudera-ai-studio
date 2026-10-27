# SEM-2B test matrix (1:1 mapping)

All cases live in `frontend/src/views/semantic/semanticLayerPhase2B.matrix.test.tsx` unless noted.

| ID | Test name | Status |
|----|-----------|--------|
| SEM-2B-001 | SEM-2B-001 wizard opens | PASS |
| SEM-2B-002 | SEM-2B-002 name required | PASS |
| SEM-2B-003 | SEM-2B-003 duplicate name handling | PASS |
| SEM-2B-004 | SEM-2B-004 connector groups render | PASS |
| SEM-2B-005 | SEM-2B-005 table search | PASS |
| SEM-2B-006 | SEM-2B-006 multi-select tables | PASS |
| SEM-2B-007 | SEM-2B-007 suggestions requested | PASS |
| SEM-2B-008 | SEM-2B-008 suggestions grouped by type | PASS |
| SEM-2B-009 | SEM-2B-009 accept suggestion | PASS |
| SEM-2B-010 | SEM-2B-010 reject suggestion | PASS |
| SEM-2B-011 | SEM-2B-011 edit suggestion before accept | PASS |
| SEM-2B-012 | SEM-2B-012 rejected suggestion not persisted | PASS |
| SEM-2B-013 | SEM-2B-013 accepted suggestion gets stable ID | PASS |
| SEM-2B-014 | SEM-2B-014 duplicate conflict handling | PASS |
| SEM-2B-015 | SEM-2B-015 wizard completion state | PASS |
| SEM-2B-016 | SEM-2B-016 dirty switch tab shows custom modal | PASS |
| SEM-2B-017 | SEM-2B-017 Keep editing | PASS |
| SEM-2B-018 | SEM-2B-018 Discard changes | PASS |
| SEM-2B-019 | SEM-2B-019 Save and continue success | PASS |
| SEM-2B-020 | SEM-2B-020 Save and continue validation failure | PASS |
| SEM-2B-021 | SEM-2B-021 change semantic model while dirty | PASS |
| SEM-2B-022 | SEM-2B-022 open Advanced while dirty | PASS |
| SEM-2B-023 | SEM-2B-023 close editor while dirty | PASS |
| SEM-2B-024 | SEM-2B-024 saved editor navigates without warning | PASS |
| SEM-2B-025 | SEM-2B-025 no native confirm in normal semantic navigation | PASS |
| SEM-2B-026 | SEM-2B-026 Publish CTA visible | PASS |
| SEM-2B-027 | SEM-2B-027 publish calls orchestration endpoint | PASS |
| SEM-2B-028 | SEM-2B-028 publish progress state | PASS |
| SEM-2B-029 | SEM-2B-029 publish success | PASS |
| SEM-2B-030 | SEM-2B-030 Published state updates | PASS |
| SEM-2B-031 | SEM-2B-031 publish validation failure | PASS |
| SEM-2B-032 | SEM-2B-032 issue panel grouped/readable | PASS |
| SEM-2B-033 | SEM-2B-033 issue deep-link opens editor | PASS |
| SEM-2B-034 | SEM-2B-034 activation failure does not claim active | PASS |
| SEM-2B-035 | SEM-2B-035 previous runtime remains active | PASS |
| SEM-2B-036 | SEM-2B-036 retry activation | PASS |
| SEM-2B-037 | SEM-2B-037 version history consistency | PASS |
| SEM-2B-038 | SEM-2B-038 deployment details consistency | PASS |
| SEM-2B-039 | SEM-2B-039 new edit after publish becomes draft | PASS |
| SEM-2B-040 | SEM-2B-040 rollback product modal | PASS |
| SEM-2B-041 | SEM-2B-041 rollback updates active version | PASS |

Live browser / API closure (beyond Vitest): `backend/scripts/sem_p2b_browser_closure.py`, `backend/scripts/sem_p2b_live_gate.py`.
