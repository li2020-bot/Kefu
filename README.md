# Kefu - 企业智能客服系统

基于 LangGraph + RAG + MCP 的企业级智能客服系统，支持多技能路由、Function Calling 工具调用、混合检索和人工转接。

## 功能特性

### 智能对话
- **意图识别**：基于 BERT 语义相似度的 15 类意图分类，支持槽位填充（slot-filling）检测
- **多技能路由**：6 大客服技能（售前、售后、退换货、投诉、技术支持、账户管理），YAML 驱动配置
- **ReAct Function Calling**：LLM 自动调用 CRM、订单、工单系统，最多 10 轮工具调用循环
- **上下文记忆**：基于 LangGraph checkpointer 的多轮对话状态管理

### 技能覆盖

| 技能 | 触发意图 | 可用工具 |
|------|---------|---------|
| 售前咨询 | 商品咨询、价格查询、库存查询 | 客户查询 |
| 售后服务 | 订单查询、物流查询、修改订单 | 订单查询、客户查询 |
| 退换货 | 退货申请、换货申请、退款咨询 | 退款资格检查、发起退款、订单查询、客户查询 |
| 投诉处理 | 投诉 | 创建工单、查询工单、更新工单、客户查询 |
| 技术支持 | 技术问题 | 创建工单、查询工单、客户查询 |
| 账户管理 | 账户问题 | 客户查询、更新客户信息、创建工单 |

### 知识库（RAG）
- 混合检索：稠密向量（pgvector）+ 稀疏检索（BM25） + RRF 融合
- 跨命名空间并行检索，按技能自动过滤
- BAAI/bge-small-zh-v1.5 中文嵌入模型（512 维）
- BAAI/bge-reranker-v2-m3 重排序

### 对话管理
- 不满意连续检测 → 自动转人工
- 超时/多轮自动转人工
- 会话持久化存储
- PII 敏感信息过滤与脱敏

### 安全与可观测
- Prompt 注入检测
- OpenTelemetry 分布式链路追踪（Jaeger）
- 结构化日志（structlog）
- Pydantic 动态参数校验：LLM 工具调用参数实时验证，格式错误自动重试

## 技术架构

```
用户 → FastAPI → LangGraph Agent
                    ├── intent_classify (BERT 意图分类)
                    ├── skill_dispatch (YAML 技能路由 + MCP 工具加载)
                    ├── retrieve_knowledge (混合 RAG 检索)
                    ├── generate_answer (LLM + Function Calling)
                    ├── evaluate (满意度评估)
                    └── handoff (人工转接)

依赖服务：
  PostgreSQL (pgvector) → 向量存储 + 业务数据
  Redis → 会话缓存
  OpenSearch → BM25 稀疏检索
  FastMCP → CRM / 订单 / 工单 系统
  Jaeger → 链路追踪
```

## 快速开始

### 环境要求

- Python ≥ 3.12
- Docker & Docker Compose（用于启动 PostgreSQL、Redis、OpenSearch）

### 1. 启动基础设施

```bash
docker-compose up -d
```

这会启动 PostgreSQL（pgvector）、Redis、OpenSearch 和 Jaeger。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，配置以下必要参数：

```env
LLM_API_KEY=your-deepseek-or-openai-api-key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek/deepseek-v4-pro
```

### 4. 初始化数据

```bash
# 导入知识库 FAQ 数据
python scripts/ingest_faq.py

# 导入业务种子数据（订单、客户、工单）
python scripts/seed_business_data.py
```

### 5. 启动服务

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 体验在线客服界面。

### Docker 部署

```bash
# 构建镜像
docker build -t kefu:latest .

# 运行
docker run -p 8000:8000 --env-file .env kefu:latest
```

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat` | POST | 发送消息，返回 AI 回复 |
| `/api/v1/chat/{session_id}/stream` | GET | SSE 流式对话 |
| `/api/v1/sessions` | GET | 查询会话列表 |
| `/api/v1/feedback` | POST | 提交用户反馈 |
| `/api/v1/skills` | GET | 查询可用技能列表 |
| `/health` | GET | 健康检查 |

## 添加新技能

在 `skills/` 目录创建 YAML 文件即可，无需修改代码：

```yaml
name: my_skill
display_name: 我的技能
trigger_intents:
  - my_intent
system_prompt: |
  你是一个专业的客服...
tools:
  - server: crm
    tools:
      - lookup_customer
knowledge_bases:
  - namespace: my_knowledge
    weight: 1.0
```

## 项目结构

```
Kefu/
├── src/
│   ├── agent/           # LangGraph 状态图 + 各节点
│   │   ├── nodes/       # intent, skill_dispatch, rag, generation, evaluation, handoff
│   │   ├── state.py     # AgentState 定义
│   │   └── graph.py     # StateGraph 组装
│   ├── api/             # FastAPI 路由 + 中间件
│   ├── core/            # 配置、数据库、日志、安全
│   ├── mcp/             # MCP 工具定义（CRM / 订单 / 工单）
│   ├── rag/             # 文档解析、嵌入、混合检索
│   └── skills/          # 技能注册与 YAML 加载
├── skills/              # 6 大技能 YAML 配置 + 提示词
├── seed_data/           # FAQ 及业务种子数据
├── scripts/             # 数据导入脚本
├── static/              # 前端聊天界面
├── tests/               # 单元测试
├── docker-compose.yml   # 基础设施编排
└── requirements.txt
```
