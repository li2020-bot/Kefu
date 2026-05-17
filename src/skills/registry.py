"""Skill registry - loads and manages all available skills.

Skills are defined as YAML files in the skills/ directory.
Each skill has: skill.yaml (config), system_prompt.md (prompt), sop.md (procedure).
"""

import logging
from pathlib import Path

import yaml

from src.skills.base import BaseSkill, SkillConfig

logger = logging.getLogger(__name__)

# Default skills directory relative to project root
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


class SkillRegistry:
    """Central registry for all customer service skills.

    Loads skill definitions from YAML files and provides
    lookup by name or intent.
    """

    _skills: dict[str, BaseSkill] = {}
    _intent_map: dict[str, str] = {}  # intent -> skill_name
    _loaded = False

    @classmethod
    def load(cls, skills_dir: Path | None = None) -> None:
        """Load all skills from the skills directory."""
        if cls._loaded:
            return

        directory = skills_dir or SKILLS_DIR
        if not directory.exists():
            logger.warning("skills_dir_not_found: %s", directory)
            cls._load_defaults()
            cls._loaded = True
            return

        for skill_dir in sorted(directory.iterdir()):
            if not skill_dir.is_dir():
                continue

            yaml_file = skill_dir / "skill.yaml"
            if not yaml_file.exists():
                continue

            try:
                config_data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                config = SkillConfig(**config_data)
                skill = BaseSkill(config, directory)
                cls._skills[config.name] = skill

                # Build intent map
                for intent in config.trigger_intents:
                    cls._intent_map[intent] = config.name

                logger.info("skill_loaded: %s", config.name)
            except Exception as e:
                logger.error("skill_load_failed %s: %s", yaml_file, e)

        if not cls._skills:
            cls._load_defaults()

        cls._loaded = True
        logger.info("skills_registry_ready: %d skills", len(cls._skills))

    @classmethod
    def get(cls, name: str) -> BaseSkill | None:
        """Get a skill by name."""
        if not cls._loaded:
            cls.load()
        return cls._skills.get(name)

    @classmethod
    def get_by_intent(cls, intent: str) -> BaseSkill | None:
        """Get the skill that handles a given intent."""
        if not cls._loaded:
            cls.load()
        skill_name = cls._intent_map.get(intent)
        if skill_name:
            return cls._skills.get(skill_name)
        return cls._skills.get("pre_sales")  # default fallback

    @classmethod
    def list_all(cls) -> list[dict]:
        """List all registered skills."""
        if not cls._loaded:
            cls.load()
        return [skill.to_dict() for skill in cls._skills.values()]

    @classmethod
    def reload(cls) -> None:
        """Hot-reload all skills from disk."""
        cls._skills.clear()
        cls._intent_map.clear()
        cls._loaded = False
        cls.load()
        logger.info("skills_reloaded")

    @classmethod
    def _load_defaults(cls) -> None:
        """Load built-in default skills when no YAML files are present."""
        defaults = _get_default_skills()
        for name, (display_name, description, intents, prompt) in defaults.items():
            config = SkillConfig(
                name=name,
                display_name=display_name,
                description=description,
                trigger_intents=intents,
            )
            skill = BaseSkill(config, SKILLS_DIR)
            skill._system_prompt = prompt
            cls._skills[name] = skill
            for intent in intents:
                cls._intent_map[intent] = name

        logger.info("default_skills_loaded: %d", len(cls._skills))


def _get_default_skills() -> dict:
    """Return built-in default skill definitions."""
    return {
        "pre_sales": (
            "售前咨询",
            "产品咨询、价格查询、库存查询、促销活动",
            ["product_inquiry", "pricing_inquiry", "stock_check", "general_inquiry"],
            """你是一个售前咨询专家客服。你的职责是帮助客户了解产品信息、价格、库存和促销活动。

## 服务规范
1. 热情问候客户，了解需求
2. 准确介绍产品特点、价格、优惠活动
3. 根据客户需求推荐合适的产品
4. 引导客户下单，告知支付方式和配送时效
5. 如客户超出售前范畴（如售后问题），引导至相应服务

## 注意事项
- 不承诺无货商品的到货时间
- 促销规则需准确说明，不夸大
- 价格以页面实际显示为准""",
        ),
        "after_sales": (
            "售后服务",
            "订单查询、物流跟踪、修改订单、发票开具",
            ["order_status", "logistics_query", "modify_order"],
            """你是一个售后服务专家客服。你的职责是帮助客户查询订单、跟踪物流、修改订单和开具发票。

## 服务规范
1. 先核实客户身份（订单号或手机号）
2. 准确查询订单状态，如实告知
3. 物流异常时主动帮客户催促快递公司
4. 修改订单需确认是否已发货
5. 发票问题按公司财务政策处理""",
        ),
        "return_exchange": (
            "退换货处理",
            "退货、换货、退款查询",
            ["return_request", "exchange_request", "refund_inquiry"],
            """你是一个退换货处理专家客服。你的职责是帮助客户处理退货、换货和退款事宜。

## 服务规范
1. 先表达歉意，安抚客户情绪
2. 确认退货/换货原因
3. 根据退换货政策判断是否符合条件
4. 清晰告知退货流程、地址、运费规则
5. 退款时效如实告知，不夸大

## 退换货政策要点
- 7天无理由退货（特殊商品除外）
- 质量问题商家承担全部运费
- 非质量问题客户承担寄回运费
- 退款在验收后3-5个工作日到账""",
        ),
        "complaint": (
            "投诉处理",
            "投诉、不满意反馈",
            ["complaint"],
            """你是一个投诉处理专家客服。你的职责是妥善处理客户投诉，化解矛盾。

## 服务规范
1. 首先诚恳道歉，表达理解和重视
2. 耐心倾听客户诉求，不打断
3. 确认投诉事实，不推卸责任
4. 提供具体解决方案和补偿措施
5. 无法当场解决的，明确告知处理流程和时限
6. 记录投诉详情，提交工单跟进

## 重要原则
- 永远不争辩对错，先解决问题
- 补偿权限：优惠券、赠品、部分退款需按权限审批
- 涉及金额超过权限的，升级至主管处理""",
        ),
        "technical_support": (
            "技术支持",
            "功能使用、故障排查、Bug反馈",
            ["technical_issue"],
            """你是一个技术支持专家客服。你的职责是帮助客户解决产品使用中的技术问题。

## 服务规范
1. 先确认问题现象，引导客户描述具体情况
2. 按排查步骤引导客户操作（由简到繁）
3. 需要截图/录屏时礼貌请求
4. 无法远程解决的，创建技术工单
5. 告知处理进度和预计时间

## 常用排查步骤
1. 刷新页面 / 重启APP
2. 清除缓存和Cookie
3. 换浏览器 / 更新版本
4. 检查网络连接
5. 提供错误截图/日志""",
        ),
        "account_mgmt": (
            "账户管理",
            "注册登录、密码找回、账号安全",
            ["account_issue"],
            """你是一个账户管理专家客服。你的职责是帮助客户解决账户相关问题。

## 服务规范
1. 涉及账户操作前必须验证客户身份
2. 密码相关操作引导客户自助完成
3. 涉及敏感信息（手机号、邮箱等），需二次确认
4. 账号安全事件优先处理（冻结、异常登录等）

## 安全原则
- 永远不要索要或记录客户的明文密码
- 验证码只能发送到注册手机/邮箱
- 异地登录提醒需建议客户立即修改密码""",
        ),
    }
