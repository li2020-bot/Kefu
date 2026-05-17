"""MCP tool utilities — OpenAI schema conversion.

Skill-to-tool mapping is driven by skill.yaml files (via skill.get_tools()),
not hardcoded maps. Adding a new skill only requires creating a new skill.yaml.
"""


def tools_to_openai(mcp_tools: list) -> list[dict]:
    """Convert MCP tool objects to OpenAI function-calling format.

    Handles both:
    - mcp.types.Tool (has .inputSchema) — from Client.list_tools()
    - fastmcp.tools.FunctionTool (has .parameters) — from FastMCP.list_tools()
    """
    schemas = []
    for t in mcp_tools:
        params = getattr(t, 'inputSchema', None) or getattr(t, 'parameters', None) or {}
        schemas.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": params,
            },
        })
    return schemas

