from __future__ import annotations

# Stable keys mapped to file fallbacks in FilePromptSource
ASK_DATA_SYSTEM = "ask_data.system"
RAG_SYSTEM = "rag.system"
RAG_INSUFFICIENT_EVIDENCE = "rag.insufficient_evidence"
# The prompts that decide how a data answer is written and when the analyst agent takes a question. Each has its file in
# backend/prompts as the default; a version published in Prompts (or by scripts/push_prompts.py) replaces it without a redeploy.
ASK_DATA_ANALYST = "ask_data.analyst"  # result_analyst.md: the answer to a governed query and its fuller analysis
ASK_DATA_AGENT = "ask_data.agent"  # agent_tools.md: how the agent investigates
ASK_DATA_AGENT_REPORT = "ask_data.agent_report"  # agent_tool_report.md: the agent's headline, summary and full analysis
ASK_DATA_TURN_READER = "ask_data.turn_reader"  # conversation_rewrite.md: reads a question in its conversation; chooses data or analysis

KNOWN_PROMPT_KEYS = frozenset({ASK_DATA_SYSTEM, RAG_SYSTEM, RAG_INSUFFICIENT_EVIDENCE, ASK_DATA_ANALYST, ASK_DATA_AGENT, ASK_DATA_AGENT_REPORT, ASK_DATA_TURN_READER})
