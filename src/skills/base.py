"""Base skill class and skill configuration model."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillConfig:
    """Configuration for a skill, typically loaded from YAML."""

    name: str
    display_name: str
    description: str
    trigger_intents: list[str] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    knowledge_bases: list[dict] = field(default_factory=list)
    prompt_file: str = ""
    sop_file: str = ""

    # Escalation rules
    escalation: dict = field(default_factory=dict)
    escalation_keywords: list[str] = field(default_factory=list)
    unsatisfied_count: int = 2
    timeout_minutes: int = 30


class BaseSkill:
    """Base class for all customer service skills.

    A skill bundles:
    - system_prompt: domain-specific instructions
    - tools: subset of MCP tools available to this skill
    - knowledge_bases: which document collections to search
    - sop: standard operating procedure for this skill type
    """

    def __init__(self, config: SkillConfig, skills_dir: Path):
        self.config = config
        self.skills_dir = skills_dir
        self._system_prompt: str | None = None
        self._sop: str | None = None

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def display_name(self) -> str:
        return self.config.display_name

    def get_system_prompt(self) -> str:
        """Get the system prompt, loading from file if needed."""
        if self._system_prompt is None:
            prompt_path = self.skills_dir / self.name / self.config.prompt_file
            if prompt_path.exists():
                self._system_prompt = prompt_path.read_text(encoding="utf-8")
            else:
                self._system_prompt = self._default_prompt()
        return self._system_prompt

    def get_sop(self) -> str:
        """Get the SOP document, loading from file if needed."""
        if self._sop is None:
            sop_path = self.skills_dir / self.name / self.config.sop_file
            if sop_path.exists():
                self._sop = sop_path.read_text(encoding="utf-8")
            else:
                self._sop = ""
        return self._sop

    def get_tools(self) -> list[dict]:
        """Get the list of MCP tools assigned to this skill."""
        return self.config.tools

    def get_knowledge_bases(self) -> list[dict]:
        """Get the knowledge base scopes for this skill."""
        return self.config.knowledge_bases

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.config.description,
            "trigger_intents": self.config.trigger_intents,
            "tools": self.config.tools,
            "knowledge_bases": self.config.knowledge_bases,
        }

    def _default_prompt(self) -> str:
        return f"""你是一个{self.config.display_name}专家客服。请专业、耐心地帮助客户解决问题。
- 始终基于知识库内容回答
- 语气亲切友好
- 遇到无法解决的问题时，主动建议转接人工客服"""
