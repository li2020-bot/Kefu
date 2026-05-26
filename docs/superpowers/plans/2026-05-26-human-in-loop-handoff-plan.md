# Human-in-the-Loop 转人工确认实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将转人工从自动触发改为用户确认模式：触发条件满足时显示「转人工/继续」按钮，用户点确认后才执行转接。

**Architecture:** 在 `AgentState` 新增 `pending_handoff` + `pending_handoff_reason` 字段；`evaluation` 满足条件时设 `pending_handoff` 而非直接设 `needs_handoff`；`generation` 在 `pending_handoff=True` 时渲染确认按钮；用户点按钮或输入新消息时清空 `pending_handoff`。

**Tech Stack:** LangGraph state graph, Pydantic state model, litellm

---

## 文件改动概览

| 文件 | 职责 |
|------|------|
| `src/agent/state.py` | 新增 `pending_handoff`, `pending_handoff_reason` 字段 |
| `src/agent/nodes/evaluation.py` | 满足转人工条件时设 `pending_handoff`，显式请求保持直接转接 |
| `src/agent/nodes/generation.py` | `pending_handoff=True` 时渲染按钮 |
| `src/agent/nodes/handoff.py` | 接收按钮交互结果，更新 `needs_handoff` |
| `src/agent/graph.py` | 条件边逻辑不变 |

---

### Task 1: 新增状态字段

**Files:**
- Modify: `src/agent/state.py:86-127`

- [ ] **Step 1: 在 `AgentState` 新增字段**

在 `needs_handoff: bool = False` 和 `handoff_reason` 之后新增：

```python
# Human-in-the-loop handoff confirmation
pending_handoff: bool = False
pending_handoff_reason: str | None = None
```

Run: `grep -n "needs_handoff" src/agent/state.py`
Expected: 显示 `needs_handoff` 所在行，新字段在其后

- [ ] **Step 2: Commit**

```bash
git add src/agent/state.py
git commit -m "feat(state): add pending_handoff fields for user confirmation"
```

---

### Task 2: 修改 evaluation.py — 触发待确认状态

**Files:**
- Modify: `src/agent/nodes/evaluation.py:38-58`

**逻辑区分：**
- 显式请求关键词（转人工/人工客服/找经理/找主管）→ 直接设 `needs_handoff=True`，不显示按钮
- 连续不满触发的自动判断 → 设 `pending_handoff=True` + `pending_handoff_reason`，显示按钮

- [ ] **Step 1: 修改显式请求分支（line 38-44）**

原代码：
```python
if any(kw in last_user_msg for kw in ["转人工", "人工客服", "找经理", "找主管"]):
    return {
        "satisfaction_score": 1.0,
        "needs_handoff": True,
        "handoff_reason": "User requested human agent",
    }
```

改为：
```python
if any(kw in last_user_msg for kw in ["转人工", "人工客服", "找经理", "找主管"]):
    return {
        "satisfaction_score": 1.0,
        "needs_handoff": True,
        "handoff_reason": "User requested human agent",
    }
```

**保持不变**，显式请求尊重用户意图，直接转接。

- [ ] **Step 2: 修改连续不满分支（line 46-58）**

将 `needs_handoff` 相关返回值改为 `pending_handoff`：

```python
if dissatisfaction_count > 0:
    score = max(1.0, 4.0 - dissatisfaction_count * 1.5)
    new_low_count = state.low_satisfaction_count + 1
    needs_handoff = new_low_count >= settings.handoff_unsatisfied_threshold

    if needs_handoff:
        return {
            "satisfaction_score": score,
            "low_satisfaction_count": new_low_count,
            "pending_handoff": True,
            "pending_handoff_reason": f"连续 {new_low_count} 次表达不满，是否需要转接人工客服？",
        }

    return {
        "satisfaction_score": score,
        "low_satisfaction_count": new_low_count,
    }
```

- [ ] **Step 3: 修改初始返回值（line 25-26）**

将 `messages` 为空时的默认返回值也重置 `pending_handoff`：

```python
if not state.messages:
    return {"satisfaction_score": 5.0, "needs_handoff": False, "pending_handoff": False}
```

- [ ] **Step 4: 修改无消息时默认值（line 35-36）**

```python
if not last_user_msg:
    return {"satisfaction_score": 5.0, "pending_handoff": False}
```

- [ ] **Step 5: 修改积极交互重置分支（line 60-64）**

```python
return {
    "satisfaction_score": 4.5,
    "low_satisfaction_count": 0,
    "pending_handoff": False,
}
```

- [ ] **Step 6: Commit**

```bash
git add src/agent/nodes/evaluation.py
git commit -m "feat(evaluation): use pending_handoff for auto-triggered handoff"
```

---

### Task 3: 修改 generation.py — 渲染确认按钮

**Files:**
- Modify: `src/agent/nodes/generation.py:336-350`

**注意：** 不在这里渲染按钮，按钮应该作为独立行在 AI 回复后显示。

按钮的渲染应该放在消息组装阶段或在 `graph.py` 的 `generate_answer` → `evaluate` 之间处理。

由于 `final_answer` 最终会发往前端，前端负责渲染按钮样式。但为了支持纯后端测试，在 generation 输出中追加按钮文本标记。

**方案：** 在 `final_answer` 后面追加按钮标记文本，前端解析并渲染按钮。

- [ ] **Step 1: 在 generation 返回前检测 pending_handoff**

在 return 语句前（line 336 附近）追加按钮文本：

```python
# If pending_handoff is set, append handoff confirmation prompt
if state.pending_handoff and state.pending_handoff_reason:
    answer += f"\n\n---\n{state.pending_handoff_reason}\n[转人工] [继续]"
```

完整 return 改为：
```python
return {
    "final_answer": answer,
    "messages": [{"role": "assistant", "content": answer}],
    "tool_call_count": tool_call_count,
}
```

- [ ] **Step 2: Commit**

```bash
git add src/agent/nodes/generation.py
git commit -m "feat(generation): append handoff confirmation buttons when pending"
```

---

### Task 4: 修改 graph.py — 处理用户按钮点击

**Files:**
- Modify: `src/agent/graph.py`

**需要增加一个新节点** `handle_handoff_confirmation` 用于处理按钮交互。

实际上按钮点击会作为新的 user 消息发进来。关键是在 `intent_classify` 或 `evaluation` 前检测用户是否在确认按钮。

**方案：** 在 `evaluation` 中新增对按钮点击的处理逻辑。

- [ ] **Step 1: 在 evaluation.py 新增按钮点击检测逻辑**

在 `evaluate_satisfaction` 开头（line 25-36 之间）新增：

```python
# Handle handoff confirmation button clicks
if last_user_msg in ["转人工", "确认转人工"]:
    return {
        "needs_handoff": True,
        "handoff_reason": "User confirmed handoff via button",
        "pending_handoff": False,
        "low_satisfaction_count": 0,
    }

if last_user_msg in ["继续", "取消转接", "不需要转人工"]:
    return {
        "pending_handoff": False,
        "low_satisfaction_count": 0,
    }
```

在 `if not last_user_msg:` 判断之前插入。

- [ ] **Step 2: Commit**

```bash
git add src/agent/nodes/evaluation.py
git commit -m "feat(evaluation): handle handoff button click responses"
```

---

### Task 5: 修改 handoff.py — 处理系统触发的转接

**Files:**
- Modify: `src/agent/nodes/handoff.py:1-50`

当前 handoff 节点只处理转接逻辑。需要确认：当 `needs_handoff=True` 进入时，按钮确认标记不需要重复处理。

- [ ] **Step 1: Read handoff.py**

确认其实现逻辑是否需要修改。

Run: `cat src/agent/nodes/handoff.py`

- [ ] **Step 2: Commit（若无改动需求则跳过）**

```bash
git add src/agent/nodes/handoff.py
git commit -m "chore(handoff): no-op for pending_handoff flow"
```

---

## 测试场景验证

1. 用户说「转人工」→ 直接转接，不显示按钮 ✅
2. 用户连续 2 次「不满意」→ AI 回复后显示「[转人工] [继续]」
3. 用户点「转人工」→ 转接人工客服
4. 用户点「继续」→ 对话继续，正常处理
5. 用户输入新消息（没点按钮）→ 对话继续，按钮消失