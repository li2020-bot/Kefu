"""Skill dispatcher node - routes to appropriate skill based on intent.

Intent→Skill mapping is driven by skill.yaml trigger_intents (via SkillRegistry).
Tool→Skill mapping is driven by skill.yaml tools field (via skill.get_tools()).
Adding a new skill only requires creating a new skill.yaml file.
"""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from fastmcp import Client

from src.agent.state import AgentState, IntentType, SkillName
from src.mcp.client import tools_to_openai
from src.mcp.servers.crm_server import crm_mcp
from src.mcp.servers.order_server import order_mcp
from src.mcp.servers.ticket_server import ticket_mcp
from src.skills.registry import SkillRegistry


# FastMCP server instances for in-memory Client connections
_MCP_SERVERS = [crm_mcp, order_mcp, ticket_mcp]


def _build_enriched_prompt(skill_prompt: str, knowledge_bases: list[dict]) -> str:
    """Append knowledge base info to the skill's system prompt."""
    prompt = skill_prompt
    if knowledge_bases:
        kb_lines = [
            f"  - {kb.get('namespace', '')}（权重: {kb.get('weight', 1.0)}）"
            for kb in knowledge_bases
        ]
        prompt += "\n\n## 可用的知识库\n回答问题时系统会自动从以下知识库检索相关内容供你参考：\n"
        prompt += "\n".join(kb_lines)
    return prompt


def _get_skill_tool_names(skill) -> set[str]:
    """Extract tool name set from a skill's YAML tools config."""
    names = set()
    for server_group in skill.get_tools():
        for tool_name in server_group.get("tools", []):
            names.add(tool_name)
    return names


async def _list_all_tools() -> list:
    """List all tools from all MCP servers via in-memory Client connections."""
    all_tools = []
    for server in _MCP_SERVERS:
        async with Client(server) as client:
            all_tools.extend(await client.list_tools())
    return all_tools


async def dispatch_skill(state: AgentState) -> dict:
    """Dispatch to the appropriate skill based on classified intent.

    Intent→Skill and Tool→Skill mappings are both YAML-driven.
    """
    intent = state.intent or IntentType.GENERAL_INQUIRY

    # Human handoff: bypass skill dispatch
    if intent == IntentType.HUMAN_HANDOFF:
        return {
            "needs_handoff": True,
            "handoff_reason": "User requested human agent",
        }

    # Slot-filling: user is providing data (phone, order ID, etc.) in response
    # to a previous assistant question. Preserve the current active skill and tools
    # so the LLM can use the provided data to call tools correctly.
    if intent == IntentType.SLOT_FILLING:
        if state.active_skill and state.available_tools:
            logger.info("slot_filling_preserving_skill", skill=state.active_skill.value, tools_count=len(state.available_tools))
            return {
                "active_skill": state.active_skill,
                "available_tools": state.available_tools,
                "knowledge_namespaces": state.knowledge_namespaces,
            }
        # No active skill yet — fall through to normal dispatch
        logger.warning("slot_filling_no_active_skill", intent=intent.value)

    # Resolve skill from intent via YAML-driven SkillRegistry
    skill = SkillRegistry.get_by_intent(intent.value)
    if skill is None:
        logger.warning("skill_not_found_for_intent", intent=intent.value)
        skill = SkillRegistry.get("pre_sales")

    try:
        target_skill = SkillName(skill.name)
    except ValueError:
        target_skill = SkillName.PRE_SALES

    # Check if skill needs to change
    if state.active_skill and state.active_skill != target_skill:
        logger.info("skill_switching", from_skill=state.active_skill.value, to_skill=target_skill.value)

    # Knowledge base namespaces for RAG filtering
    namespaces = [kb.get("namespace") for kb in skill.get_knowledge_bases() if kb.get("namespace")]

    # List all MCP tools, filter by skill's YAML-configured tool names
    all_tools = await _list_all_tools()
    allowed_names = _get_skill_tool_names(skill)
    skill_tools = [t for t in all_tools if t.name in allowed_names]
    available_tools = tools_to_openai(skill_tools)

    # Build enriched system prompt
    system_msg = {
        "role": "system",
        "content": _build_enriched_prompt(skill.get_system_prompt(), skill.get_knowledge_bases()),
    }

    logger.info("skill_dispatched", skill=target_skill.value, tools_count=len(available_tools), namespaces=namespaces)

    return {
        "active_skill": target_skill,
        "knowledge_namespaces": namespaces,
        "available_tools": available_tools,
        "messages": [system_msg],
    }
