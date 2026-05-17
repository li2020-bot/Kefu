"""Tests for skills registry."""

from src.skills.registry import SkillRegistry


class TestSkillRegistry:
    def test_load_defaults(self):
        SkillRegistry.reload()
        skills = SkillRegistry.list_all()
        assert len(skills) == 6
        skill_names = [s["name"] for s in skills]
        assert "pre_sales" in skill_names
        assert "after_sales" in skill_names
        assert "complaint" in skill_names
        assert "return_exchange" in skill_names
        assert "technical_support" in skill_names
        assert "account_mgmt" in skill_names

    def test_get_skill(self):
        SkillRegistry.load()
        skill = SkillRegistry.get("pre_sales")
        assert skill is not None
        assert skill.name == "pre_sales"
        assert skill.display_name == "售前咨询"

    def test_get_skill_prompt(self):
        SkillRegistry.load()
        skill = SkillRegistry.get("pre_sales")
        prompt = skill.get_system_prompt()
        assert "售前咨询" in prompt
        assert "产品" in prompt

    def test_get_by_intent(self):
        SkillRegistry.load()
        skill = SkillRegistry.get_by_intent("product_inquiry")
        assert skill is not None
        assert skill.name == "pre_sales"
