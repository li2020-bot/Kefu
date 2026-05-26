# Human-in-the-Loop 转人工确认设计

## 背景

原转人工逻辑是自动触发式：当用户表达不满达到阈值或明确要求转人工时，系统直接跳转到 handoff 节点，用户没有拒绝的机会。

改进为 human-in-the-loop 模式：触发转人工判断时，询问用户确认，用户可以选择转人工或继续对话。

## 交互设计

### 触发条件
当 `evaluation.py` 满足以下任一条件时：
1. 用户明确输入「转人工」「人工客服」「找经理」「找主管」
2. 用户连续 2 次（可配置）表达不满关键词

### 询问方式
- 在 AI 回复后，以**独立按钮行**形式呈现：
  ```
  [AI 回复内容]

  [检测到您可能需要人工客服，是否需要转接？]
  [转人工]  [继续]
  ```

### 用户选择
| 用户行为 | 系统响应 |
|---------|---------|
| 点击「转人工」 | 执行 `needs_handoff=True`，跳转 handoff 节点 |
| 点击「继续」 | 清空 `pending_handoff`，正常继续对话 |
| 输入新消息 | 清空 `pending_handoff`，按正常流程处理 |

## 状态设计

新增两个状态字段：

```python
pending_handoff: bool = False           # 待确认的转接请求
pending_handoff_reason: str | None = None  # 触发原因（用于按钮旁提示语）
```

**状态流转：**
```
无 pending_handoff
    ↓ (evaluation 满足转人工条件)
pending_handoff=True + pending_handoff_reason
    ↓ (generation 渲染按钮，等待用户)
    ├─ 用户点"转人工" → needs_handoff=True → 跳转 handoff 节点
    └─ 用户点"继续" / 新消息 → pending_handoff=False → 继续正常对话
```

## 实现要点

### 1. evaluation.py 改动
- 满足转人工条件时，设置 `pending_handoff=True` 和 `pending_handoff_reason`
- **不再**设置 `needs_handoff=True`（那是确认后才设置的）

### 2. generation.py 改动
- 当 `state.pending_handoff=True` 时，在 AI 回复后追加按钮块
- 按钮以独立行呈现，附带简短提示语

### 3. graph.py 改动
- `_should_handoff` 条件不变，仍然检查 `needs_handoff`
- `pending_handoff` 状态在用户确认后才转化为 `needs_handoff`

### 4. 前端交互处理
- 「转人工」按钮点击 → 发送带有标记的消息（如 `/handoff_confirm`）或通过 UI 动作触发状态更新
- 「继续」按钮点击 → 发送 `/handoff_cancel` 或等效 UI 动作
- 输入新消息 → 自动清空 `pending_handoff`

### 5. 特殊情况
- 显式「转人工」关键词（用户主动要求）是否需要二次确认？
  - 建议：用户主动要求时，可以直接转接，不显示按钮（尊重用户明确意图）
  - 按钮确认仅针对「连续不满」触发的自动判断

## 文件改动清单

| 文件 | 改动内容 |
|------|---------|
| `src/agent/state.py` | 新增 `pending_handoff`, `pending_handoff_reason` 字段 |
| `src/agent/nodes/evaluation.py` | 满足条件时设 `pending_handoff`，不再直接设 `needs_handoff` |
| `src/agent/nodes/generation.py` | `pending_handoff=True` 时渲染按钮 |
| `src/agent/graph.py` | 条件边逻辑不变，依赖 `needs_handoff` 判断 |

## 测试场景

1. 用户说「转人工」→ 应直接转接（不显示按钮）
2. 用户连续 2 次说「不满意」→ 显示按钮，用户点「转人工」→ 转接
3. 用户连续 2 次说「不满意」→ 显示按钮，用户点「继续」→ 正常继续
4. 用户连续 2 次说「不满意」→ 显示按钮，用户输入新消息 → 正常处理，按钮消失