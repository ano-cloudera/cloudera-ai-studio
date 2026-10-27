# Analysis Workspace visibility (post-UAT M9)

The right-hand Analysis Workspace opens only when the assistant response includes a **structured analytical artifact** (table, chart, KPI, governed query result).

## Rules

| Response | Main chat | Analysis Workspace |
|----------|-----------|-------------------|
| General / clarification | yes | closed |
| Knowledge RAG | yes | closed |
| Uploaded-file RAG | yes | closed |
| Ask Data + table/chart/query | summary in chat | open |

Implementation: `analysisArtifactFromResponse()` / `shouldOpenAnalysisPanel()` in `frontend/src/lib/analysisArtifact.ts`.

RAG citations use the **Sources drawer** (`RagSourcesDrawer`), not the Analysis Workspace tabs.

When the workspace is closed, chat uses the full split-pane width (existing split-pane behavior).
