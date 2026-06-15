# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kefu is an enterprise intelligent customer service system (智能客服系统) built on LangGraph + RAG + MCP. It supports multi-skill routing, Function Calling tool invocation, hybrid retrieval, and human handoff. All UI text and system prompts are in Chinese.

## Git Safety

```bash
# 推送前检查是否包含 api key，使用 --verify 参数执行检查
./scripts/git_push_with_key_check.sh --verify
```

克隆仓库后首次推送需要配置 pre-push hook：
```bash
cp scripts/git_push_with_key_check.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start infrastructure (PostgreSQL/pgvector, Redis, OpenSearch, Jaeger)
docker-compose up -d

# Initialize knowledge base + seed data
python scripts/ingest_faq.py
python scripts/seed_business_data.py

# Run the API server
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Run unit tests
pytest tests/unit/

# Run a single test file
pytest tests/unit/test_intent.py
```

## Architecture

### LangGraph State Machine

The agent is a `StateGraph` compiled with a `MemorySaver` checkpointer. The flow:

```
START → intent_classify → [human_handoff] → handoff → END
                         → [skill_dispatch → retrieve_knowledge → generate_answer → evaluate] → [handoff | END]
```

Key files:
- `src/agent/graph.py` — builds and compiles the StateGraph
- `src/agent/state.py` — `AgentState` definition (shared state across all nodes)
- `src/agent/nodes/` — individual node implementations

**Intent routing is conditional**: `HUMAN_HANDOFF` goes directly to handoff; everything else (including `SLOT_FILLING`) goes through `skill_dispatch`. `SLOT_FILLING` preserves the active skill and tools so the LLM can use data provided in response to a prior assistant question.

### State Flow

`AgentState` fields with `Annotated[..., add_messages]` use additive merging — messages accumulate across all nodes. All other fields are replaced per node. Key fields:

- `messages` — accumulated conversation history
- `intent` / `intent_confidence` — classified intent
- `active_skill` — currently active `SkillName`
- `available_tools` — OpenAI function-calling format tool schemas (filtered per skill)
- `retrieved_docs` — RAG results
- `needs_handoff` / `handoff_reason` — escalation signals set by evaluation node
- `pending_handoff` / `pending_handoff_reason` — pre-flagged handoff from slot-filling or skill dispatch

### Skills System (YAML-Driven)

Skills are defined in `skills/<name>/skill.yaml` with no code changes needed to add a new skill. Each skill has:
- `trigger_intents` — intents that activate this skill
- `tools` — which MCP server tools are available to this skill
- `knowledge_bases` — which RAG namespaces to search

The `SkillRegistry` loads all skill.yaml files at startup. `dispatch_skill` node resolves intent → skill via the registry, then filters MCP tools by the skill's YAML-configured tool names.

### MCP Tool Servers

Three FastMCP servers provide tools:
- `crm_server` — customer lookup
- `order_server` — order queries, refund operations
- `ticket_server` — ticket CRUD

Tools are converted to OpenAI function-calling format via `tools_to_openai()` in `src/mcp/client.py` and passed to the LLM in the `generate_answer` node.

### RAG: Hybrid Retrieval

Retrieval uses three stages:
1. **Dense**: `pgvector` via `DenseRetriever` (BAAI/bge-small-zh-v1.5 embeddings)
2. **Sparse**: OpenSearch BM25 via `SparseRetriever`
3. **Fusion**: RRF (Reciprocal Rank Fusion) via `HybridRetriever`

Namespaces filter which documents are searched per-skill. Reranking via BAAI/bge-reranker-v2-m3 before returning top-k results.

### Intent Classification

Two-layer classification in `src/agent/nodes/intent.py`:
1. **Fast rule-based** (`_fast_intent_classify`): keyword/regex matching for common intents
2. **BERT model** (`IntentClassifier`): semantic similarity for complex cases, only used when fast classification returns `None`

### Database Schema

PostgreSQL with pgvector extension stores:
- `knowledge_chunks` — embedded FAQ/documents with namespace
- `conversations` / `messages` — session history
- `customers` / `orders` / `tickets` / `refunds` — business data

## Key Patterns

### Adding a New Skill

1. Create `skills/<name>/skill.yaml` with `trigger_intents`, `tools`, `knowledge_bases`
2. Optionally add `system_prompt.md` and `sop.md` in the same directory
3. No code changes needed — `SkillRegistry` hot-reloads on restart

### Adding a New MCP Tool

1. Add the tool to the appropriate server in `src/mcp/servers/`
2. Reference it in a skill's `skill.yaml` under `tools`
3. `dispatch_skill` will automatically include it for that skill

### Handoff Logic

Handoff is triggered when:
- User explicitly requests it (`HUMAN_HANDOFF` intent)
- Evaluation node detects low satisfaction (`needs_handoff` flag)
- `pending_handoff` was set by `skill_dispatch` (pre-flagged before evaluation)
- Conversation exceeds `max_conversation_turns` or timeout threshold
