"""Answer generation node - generates customer-facing responses with function calling support.

Calls litellm with available MCP tools as function-calling tools.
When the LLM returns tool calls, executes them via fastmcp.Client
and loops until a text response is produced.
"""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from fastmcp import Client
from pydantic import create_model, Field, ValidationError

from src.agent.state import AgentState, _get_msg_content, _get_msg_role
from src.core.config import settings
from src.mcp.servers.crm_server import crm_mcp
from src.mcp.servers.order_server import order_mcp
from src.mcp.servers.ticket_server import ticket_mcp
import litellm


MAX_TOOL_CALL_ROUNDS = 10

# Server lookup by name
_SERVER_BY_NAME = {
    "crm": crm_mcp,
    "order": order_mcp,
    "ticket": ticket_mcp,
}

# Tool → server routing (built once at first use)
_tool_server_map: dict[str, str] = {}

# Tool → JSON Schema (inputSchema from FastMCP, built lazily)
_tool_schema_map: dict[str, dict] = {}

# Tool → Pydantic validator model (cached)
_validator_cache: dict[str, type] = {}

# JSON Schema type → Python type
_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _json_type_to_python(schema: dict):
    """Convert a JSON Schema property definition to a Python type."""
    type_str = schema.get("type")
    if type_str in _JSON_TYPE_MAP:
        return _JSON_TYPE_MAP[type_str]
    # Handle anyOf (e.g., {"anyOf": [{"type": "number"}, {"type": "null"}]})
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            t = sub.get("type")
            if t and t != "null" and t in _JSON_TYPE_MAP:
                return _JSON_TYPE_MAP[t]
    return str  # fallback


def _build_validator(tool_name: str, schema: dict) -> type:
    """Build a Pydantic model from a JSON Schema for tool argument validation."""
    from typing import Optional as Opt

    fields = {}
    required = set(schema.get("required", []))
    for prop_name, prop_schema in schema.get("properties", {}).items():
        py_type = _json_type_to_python(prop_schema)
        default = prop_schema.get("default")

        if prop_name not in required:
            py_type = Opt[py_type]
            if default is not None:
                fields[prop_name] = (py_type, Field(default=default))
            else:
                fields[prop_name] = (py_type, None)
        else:
            fields[prop_name] = (py_type, ...)

    model_name = f"{tool_name}_args".replace("-", "_")
    return create_model(model_name, **fields)


def _validate_tool_args(tool_name: str, args: dict) -> tuple[bool, dict | str]:
    """Validate tool arguments against the tool's JSON Schema via Pydantic.

    Returns (True, validated_dict) on success, or (False, error_message) on failure.
    """
    schema = _tool_schema_map.get(tool_name)
    if not schema or not schema.get("properties"):
        return True, args  # no schema to validate against

    if tool_name not in _validator_cache:
        try:
            _validator_cache[tool_name] = _build_validator(tool_name, schema)
        except Exception as e:
            logger.warning("validator_build_failed", tool=tool_name, error=str(e))
            return True, args  # can't build validator, pass through

    Validator = _validator_cache[tool_name]
    try:
        validated = Validator(**args)
        return True, validated.model_dump()
    except ValidationError as e:
        error_detail = e.errors(include_url=False)
        error_msg = f"工具 {tool_name} 参数校验失败，请修正后重试：\n"
        for err in error_detail:
            loc = ".".join(str(l) for l in err["loc"])
            error_msg += f"  - {loc}: {err['msg']}\n"
        logger.info("tool_args_validation_failed", tool=tool_name, errors=error_detail, raw_args=str(args)[:200])
        return False, error_msg.strip()


async def _ensure_tool_map():
    """Build tool→server routing map and tool→schema map lazily."""
    if _tool_server_map:
        return
    for name, server in _SERVER_BY_NAME.items():
        async with Client(server) as client:
            tools = await client.list_tools()
            for tool in tools:
                _tool_server_map[tool.name] = name
                schema = getattr(tool, "inputSchema", None) or getattr(tool, "parameters", None) or {}
                _tool_schema_map[tool.name] = schema


async def _call_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool via in-memory Client, returning the result as a string."""
    import json

    server_name = _tool_server_map.get(tool_name)
    if not server_name:
        return f"Unknown tool: {tool_name}"

    server = _SERVER_BY_NAME.get(server_name)
    if not server:
        return f"Server {server_name} not found"

    try:
        logger.info("tool_call_start", tool=tool_name, args=str(arguments)[:200])
        async with Client(server) as client:
            result = await client.call_tool(tool_name, arguments)
        if result.is_error:
            logger.error("tool_call_error", tool=tool_name, error=str(result.data))
            return f"Tool error: {result.data}"

        # result.data: string for simple returns, dict for structured returns
        if isinstance(result.data, str):
            output = result.data
        elif isinstance(result.data, dict):
            output = json.dumps(result.data, ensure_ascii=False)
        elif result.content:
            output = "\n".join(block.text for block in result.content if hasattr(block, 'text') and block.text)
        else:
            output = str(result.data)
        logger.info("tool_call_success", tool=tool_name, output_len=len(output))
        return output
    except Exception as e:
        error_msg = f"Tool call failed: {str(e)}"
        logger.error("tool_call_failed", tool=tool_name, error=str(e))
        return error_msg


def _messages_to_dict(messages: list) -> list[dict]:
    """Convert state messages to OpenAI dict format for litellm.

    Only role + content are needed — tool_calls, tool_call_id, and reasoning_content
    are stripped upstream by _filter_conversation_messages and the fact that
    generate_answer only persists the final answer to state.
    """
    result = []
    for msg in messages:
        if isinstance(msg, dict):
            result.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
        else:
            result.append({
                "role": _get_msg_role(msg),
                "content": _get_msg_content(msg),
            })
    return result


def _filter_conversation_messages(messages: list) -> list:
    """Keep user messages, final assistant answers, and the current turn's system prompt.

    Removes:
    - Old system prompts (keep only the last one, which is the current turn's skill prompt)
    - Tool call intermediate steps and tool results
    """
    # Find the index of the last system message (current turn's skill prompt)
    last_system_idx = -1
    for i, msg in enumerate(messages):
        role = msg.get("role", "") if isinstance(msg, dict) else _get_msg_role(msg)
        if role == "system":
            last_system_idx = i

    filtered = []
    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            role = msg.get("role", "")
            if role == "system" and i != last_system_idx:
                continue
            if role == "tool":
                continue
            if role == "assistant" and msg.get("tool_calls"):
                continue
            filtered.append(msg)
        else:
            role = _get_msg_role(msg)
            if role == "system" and i != last_system_idx:
                continue
            if role == "tool":
                continue
            if role == "assistant" and getattr(msg, "tool_calls", None):
                continue
            filtered.append(msg)
    return filtered


def _build_rag_context(state: AgentState) -> str:
    """Build knowledge base context from retrieved documents."""
    if not state.retrieved_docs:
        return "暂无相关知识库信息。"

    context_parts = []
    for i, doc in enumerate(state.retrieved_docs, 1):
        context_parts.append(f"[来源{i}] {doc.source}\n{doc.content}")
    return "\n\n---\n\n".join(context_parts)


async def generate_answer(state: AgentState) -> dict:
    """Generate a customer-facing answer using LLM with RAG context and function calling."""
    await _ensure_tool_map()

    if not state.messages:
        return {"final_answer": "您好，请问有什么可以帮您的？"}

    last_user_msg = None
    for msg in reversed(state.messages):
        if _get_msg_role(msg) == "user":
            last_user_msg = _get_msg_content(msg)
            break

    if not last_user_msg:
        return {"final_answer": "请问您遇到了什么问题？"}

    # Build RAG context
    context_text = _build_rag_context(state)
    rag_msg = {"role": "system", "content": f"""## 知识库参考
{context_text}

## 回答规则
1. 始终基于知识库内容回答，不要编造信息
2. 如果知识库中没有相关信息，诚实告知客户并建议联系人工客服
3. 语气要亲切、耐心、专业
4. 回复中标注引用来源，格式：[来源X]
5. 如果涉及操作步骤，请分点清晰列出
6. 控制回复长度在200字以内，简洁明了
7. 对于退换货、退款、投诉等敏感问题，先表达歉意再给出解决方案
8. 严禁在回复中暴露任何内部代码、变量名、函数名、技术错误信息或调试日志，用客户能理解的通俗语言表达"""}

    # Build message list for LLM — filter out stale system prompts, intermediate
    # tool calls, and tool results from previous turns. Fresh system prompt comes
    # from skill_dispatch, fresh RAG context comes from the rag_msg below.
    conversation = _filter_conversation_messages(state.messages)
    llm_messages = _messages_to_dict(conversation)
    llm_messages.insert(-1, rag_msg)

    tools = state.available_tools if hasattr(state, 'available_tools') else []
    tool_call_count = state.tool_call_count if hasattr(state, 'tool_call_count') else 0

    try:
        logger.info("llm_call_start", msg_count=len(llm_messages), tools_count=len(tools),
                     tool_round=tool_call_count)

        response_messages = []
        current_messages = list(llm_messages)

        for _round in range(MAX_TOOL_CALL_ROUNDS):
            kwargs = {
                "model": settings.llm_model,
                "messages": current_messages,
                "api_key": settings.llm_api_key,
                "temperature": 0,
                "base_url": settings.llm_base_url,
            }
            if tools:
                kwargs["tools"] = tools

            response = await litellm.acompletion(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            # Check if LLM wants to call a tool
            if msg.tool_calls and tools:
                import json

                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
                # DeepSeek reasoning/thinking mode: must pass reasoning_content back
                reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
                if reasoning:
                    assistant_msg["reasoning_content"] = reasoning
                current_messages.append(assistant_msg)
                response_messages.append(assistant_msg)

                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    # Pydantic validation: if args don't match the tool's JSON Schema,
                    # return the validation error to the LLM for retry
                    valid, validated_or_error = _validate_tool_args(tool_name, args)
                    if not valid:
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": validated_or_error,
                        }
                        current_messages.append(tool_msg)
                        response_messages.append(tool_msg)
                        continue

                    tool_result = await _call_tool(tool_name, validated_or_error)

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    }
                    current_messages.append(tool_msg)
                    response_messages.append(tool_msg)

                    logger.info(
                        "tool_call_executed",
                        tool=tool_name,
                        args=str(validated_or_error)[:100],
                        result_preview=tool_result[:100],
                    )

                tool_call_count += 1
                continue

            # Normal text response
            answer = msg.content or ""

            logger.info("llm_response", preview=answer[:120])

            # Only persist the final answer to state, not intermediate tool_calls/tool results.
            # ReAct loop messages (assistant tool_calls, tool results) are only needed within
            # this turn's current_messages — they should not pollute state for the next turn.
            return {
                "final_answer": answer,
                "messages": [{"role": "assistant", "content": answer}],
                "tool_call_count": tool_call_count,
            }

        logger.warning("max_tool_call_rounds_reached", rounds=MAX_TOOL_CALL_ROUNDS)
        fallback = "非常抱歉，我暂时无法完成您的请求。正在为您转接人工客服..."
        return {
            "final_answer": fallback,
            "messages": [{"role": "assistant", "content": fallback}],
            "needs_handoff": True,
            "handoff_reason": "Max tool call rounds exceeded",
            "tool_call_count": tool_call_count,
        }

    except Exception as e:
        logger.error("generation_failed", error=str(e))
        fallback = "非常抱歉，我暂时无法处理您的问题。正在为您转接人工客服..."
        return {
            "final_answer": fallback,
            "messages": [{"role": "assistant", "content": fallback}],
            "needs_handoff": True,
            "handoff_reason": f"Generation failed: {str(e)}",
        }
