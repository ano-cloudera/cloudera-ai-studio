# Traceability matrix — AMP Banking

| Requirement | Implementation | SIT | UAT |
|-------------|----------------|-----|-----|
| R-01 Auto / pin semantic | `ask_data_settings`, `_resolve_automatic_semantic_model` | SIT-2.2 | UAT-1, UAT-4 |
| R-02 Session follow-up | `context.py` registry session follow-up | SIT-1.1 | UAT-2, UAT-3 |
| R-03 Clarification chips | `_map_picker_options_to_db_metrics`, FE `clarificationChoices` | — | UAT-6 |
| R-04 Definition panel | `QueryData` + `ReportDocumentSection` | — | UAT-5 |
| R-05 Certified questions | `certified_questions.py`, publish storage | SIT-1.3, SIT-2.4 | — |
| R-06 Readiness gate | `run_amp_accelerator_readiness.py`, demo scripts | SIT-1.4 | Automated UAT |
| R-07 Presentation | `accelerator-demo-presentation.json` | SIT-0.3 | UAT-1 UX |
| R-08 Browse catalog | `semantic_catalog_api.py`, FE `AskDataSemanticCatalogPanel` | — | UAT browse |
| R-09 Answer feedback | `POST /ask-data/feedback`, `ResponseFooter` | — | Manual |
| R-10 Space instructions | `instruction_prompt_key`, `chat.py` / `workflow.py` | — | UAT tone |
| R-11 Parity / Ranger narrative | `DATABRICKS_ONTOLOGY_PARITY.md`, `RANGER_ROW_FILTER_DEMO.md` | — | SE deck |
