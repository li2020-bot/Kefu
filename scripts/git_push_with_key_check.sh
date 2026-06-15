#!/bin/bash
# Git pre-push hook: 检查即将推送的提交中是否包含 api key
# 用法:
#   --verify    手动检查当前工作区
#   (作为 hook) 检查将被推送的文件，exit 0 表示允许推送

set -e

VERIFY_MODE=false
if [[ "$1" == "--verify" ]]; then
    VERIFY_MODE=true
fi

# pre-push hook 接收: remote_name remote_url
# 读取但不使用（hook 必须从 stdin 读取这些数据）
if [[ "$VERIFY_MODE" != "true" ]]; then
    while read -r local_ref local_sha remote_ref remote_sha; do
        :
    done
fi

# 获取将被检查的文件
if [[ "$VERIFY_MODE" == "true" ]]; then
    CHECK_FILES=$(git diff HEAD --name-only | grep -E '\.(py|yaml|yml|json|env|txt|md|js|ts)$' || true)
else
    CHECK_FILES=$(git diff --name-only "$remote_sha" HEAD | grep -E '\.(py|yaml|yml|json|env|txt|md|js|ts)$' || true)
fi

FOUND_KEYS=false
for file in $CHECK_FILES; do
    if [[ ! -f "$file" ]]; then
        continue
    fi
    # 检测真正的 API key: sk- 开头的 token
    if grep -E 'sk-[a-zA-Z0-9]{20,}' "$file" > /dev/null 2>&1; then
        echo "警告: 文件 '$file' 可能包含 API key"
        FOUND_KEYS=true
    fi
    # 检测明显的硬编码密码 (排除字段名和注释)
    while IFS= read -r line; do
        # 跳过注释和字符串
        if [[ "$line" =~ ^[[:space:]]*# ]] || [[ "$line" =~ ^[[:space:]]*// ]]; then
            continue
        fi
        # 只检查赋值语句中的硬编码密码
        if echo "$line" | grep -qE '=[[:space:]]*["\047][^"\047]{5,}["\047]' && echo "$line" | grep -qiE '(password|secret|token)'; then
            # 排除明显是 placeholder 的
            if ! echo "$line" | grep -qiE '(placeholder|change.me|your|example|fake|test|default)'; then
                echo "警告: 文件 '$file' 可能包含硬编码密码"
                FOUND_KEYS=true
            fi
        fi
    done < <(grep -i -E "(password|secret|token)" "$file" 2>/dev/null || true)
done

if [[ "$FOUND_KEYS" == "true" ]]; then
    echo ""
    echo "错误: 检测到可能包含敏感信息的文件，请检查后再推送"
    exit 1
fi

if [[ "$VERIFY_MODE" == "true" ]]; then
    echo "检查通过: 未发现 API key"
fi

# hook 成功退出，git 会继续推送
exit 0