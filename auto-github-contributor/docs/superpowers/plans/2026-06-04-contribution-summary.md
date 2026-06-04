# 贡献总结功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 auto-github-contributor 添加自动生成贡献总结文档的功能，用于记录开源贡献到简历

**Architecture:** Shell + Python 混合方案。Shell 脚本负责数据提取和流程编排，Python 脚本负责 Markdown 生成和文件管理。集成到 create-pr.sh 的 PR 创建流程后。

**Tech Stack:** Bash, Python 3, gh CLI, git, Markdown

---

## 文件结构

### 新增文件

1. **`skills/auto-github-contributor/templates/SUMMARY.template.md`**
   - Markdown 模板文件
   - 定义贡献总结的结构
   - 包含占位符供 Python 替换

2. **`skills/auto-github-contributor/scripts/render-summary.py`**
   - Python Markdown 生成器
   - 职责：解析 JSON 数据，生成 Markdown，管理文件
   - 核心函数：`render_individual()`, `update_aggregated()`

3. **`skills/auto-github-contributor/scripts/generate-summary.sh`**
   - Shell 编排脚本
   - 职责：参数解析，调用 git/gh 提取数据，调用 Python 脚本
   - 错误处理和日志输出

### 修改文件

1. **`skills/auto-github-contributor/scripts/create-pr.sh:154`**
   - 在 PR URL 打印后添加调用 generate-summary.sh
   - 使用 `|| agc::log` 确保失败不影响主流程

---

## Task 1: 创建 Markdown 模板

**Files:**
- Create: `skills/auto-github-contributor/templates/SUMMARY.template.md`

### 步骤

- [ ] **Step 1: 创建模板文件**

创建 Markdown 模板，定义贡献总结的结构：

```markdown
## {{REPO_NAME}} - PR #{{PR_NUMBER}}

**日期**: {{CREATED_AT}}  
**状态**: {{STATUS}}  
**链接**: [PR #{{PR_NUMBER}}]({{PR_URL}})

### 问题描述

{{PROBLEM}}

### 解决方案

{{SOLUTION}}

### 使用的技术和技能

{{TECHNOLOGIES}}

### 技术指标

- 修改文件: {{FILES_CHANGED}} 个
- 新增代码: {{INSERTIONS}} 行
- 删除代码: {{DELETIONS}} 行

---
```

- [ ] **Step 2: 提交模板文件**

```bash
git add skills/auto-github-contributor/templates/SUMMARY.template.md
git commit -m "feat: add contribution summary template"
```

---

## Task 2: 实现 Python Markdown 生成器 (TDD)

**Files:**
- Create: `skills/auto-github-contributor/scripts/render-summary.py`
- Create: `skills/auto-github-contributor/scripts/test_render_summary.py` (测试文件)

### 步骤

- [ ] **Step 1: 编写第一个测试 - 渲染单独文件**

创建测试文件 `skills/auto-github-contributor/scripts/test_render_summary.py`:

```python
#!/usr/bin/env python3
import json
import os
import tempfile
from pathlib import Path

def test_render_individual_summary():
    """测试生成单独的贡献总结文件"""
    # 准备测试数据
    data = {
        "pr_number": 123,
        "pr_title": "Fix typo in README",
        "pr_url": "https://github.com/cli/cli/pull/123",
        "repo_name": "cli/cli",
        "created_at": "2026-06-04",
        "status": "待合并",
        "problem": "README 中有拼写错误",
        "solution": "修正了 'teh' 为 'the'",
        "technologies": "Markdown, Documentation",
        "files_changed": 1,
        "insertions": 1,
        "deletions": 1
    }
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "cli-cli-pr-123-2026-06-04.md"
        template_path = Path(__file__).parent.parent / "templates" / "SUMMARY.template.md"
        
        # 调用函数（尚未实现）
        from render_summary import render_individual_summary
        render_individual_summary(data, str(template_path), str(output_file))
        
        # 验证文件已创建
        assert output_file.exists()
        
        # 验证内容
        content = output_file.read_text()
        assert "cli/cli - PR #123" in content
        assert "README 中有拼写错误" in content
        assert "修正了 'teh' 为 'the'" in content
        assert "待合并" in content
    
    print("✓ test_render_individual_summary passed")

if __name__ == "__main__":
    test_render_individual_summary()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd skills/auto-github-contributor/scripts
python3 test_render_summary.py
```

预期输出: 失败，提示 `ModuleNotFoundError: No module named 'render_summary'`

- [ ] **Step 3: 实现最小化代码使测试通过**

创建 `skills/auto-github-contributor/scripts/render-summary.py`:

```python
#!/usr/bin/env python3
"""
贡献总结 Markdown 生成器

从 JSON 数据生成贡献总结文档：
1. 单独文件：每个贡献一个 Markdown 文件
2. 汇总文件：所有贡献的聚合文档
"""

import json
import sys
from pathlib import Path


def render_individual_summary(data, template_path, output_path):
    """
    生成单独的贡献总结文件
    
    Args:
        data: 包含 PR 信息的字典
        template_path: 模板文件路径
        output_path: 输出文件路径
    """
    # 读取模板
    template = Path(template_path).read_text()
    
    # 替换占位符
    content = template
    content = content.replace("{{REPO_NAME}}", data["repo_name"])
    content = content.replace("{{PR_NUMBER}}", str(data["pr_number"]))
    content = content.replace("{{CREATED_AT}}", data["created_at"])
    content = content.replace("{{STATUS}}", data["status"])
    content = content.replace("{{PR_URL}}", data["pr_url"])
    content = content.replace("{{PROBLEM}}", data["problem"])
    content = content.replace("{{SOLUTION}}", data["solution"])
    content = content.replace("{{TECHNOLOGIES}}", data["technologies"])
    content = content.replace("{{FILES_CHANGED}}", str(data["files_changed"]))
    content = content.replace("{{INSERTIONS}}", str(data["insertions"]))
    content = content.replace("{{DELETIONS}}", str(data["deletions"]))
    
    # 写入文件
    Path(output_path).write_text(content, encoding='utf-8')


def main():
    """主函数：从 stdin 读取 JSON，生成 Markdown 文件"""
    # 从 stdin 读取 JSON 数据
    data = json.load(sys.stdin)
    
    # 确定路径
    script_dir = Path(__file__).parent
    template_path = script_dir.parent / "templates" / "SUMMARY.template.md"
    
    # 生成文件名
    repo_slug = data["repo_name"].replace("/", "-")
    date_str = data["created_at"]
    filename = f"{repo_slug}-pr-{data['pr_number']}-{date_str}.md"
    
    # 生成单独文件
    contributions_dir = Path.home() / "contributions"
    contributions_dir.mkdir(parents=True, exist_ok=True)
    
    individual_file = contributions_dir / filename
    render_individual_summary(data, str(template_path), str(individual_file))
    
    print(f"✓ Generated: {individual_file}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd skills/auto-github-contributor/scripts
python3 test_render_summary.py
```

预期输出: `✓ test_render_individual_summary passed`

- [ ] **Step 5: 提交代码**

```bash
git add skills/auto-github-contributor/scripts/render-summary.py
git add skills/auto-github-contributor/scripts/test_render_summary.py
git commit -m "feat: add render_individual_summary with test"
```

- [ ] **Step 6: 实现更新汇总文件函数**

在 `render-summary.py` 中添加：

```python
def update_aggregated_summary(data, template_path, aggr_file_path):
    """更新汇总文件，在开头插入新条目"""
    aggr_file = Path(aggr_file_path)
    
    # 生成新条目
    template = Path(template_path).read_text()
    new_entry = template
    for key, value in data.items():
        placeholder = "{{" + key.upper() + "}}"
        new_entry = new_entry.replace(placeholder, str(value))
    
    # 读取现有内容
    if aggr_file.exists():
        existing = aggr_file.read_text()
    else:
        existing = "# 我的开源贡献\n\n"
    
    # 在开头插入新条目
    updated = existing.replace("# 我的开源贡献\n\n", 
                                f"# 我的开源贡献\n\n{new_entry}\n")
    
    aggr_file.write_text(updated, encoding='utf-8')
```

更新 main() 函数调用汇总：

```python
# 在 main() 函数末尾添加
aggr_file = contributions_dir / "my-oss-contributions.md"
update_aggregated_summary(data, str(template_path), str(aggr_file))
print(f"✓ Updated: {aggr_file}")
```

- [ ] **Step 7: 提交代码**

```bash
git add skills/auto-github-contributor/scripts/render-summary.py
git commit -m "feat: add update_aggregated_summary function"
```

---

## Task 3: 实现 Shell 编排脚本

**Files:**
- Create: `skills/auto-github-contributor/scripts/generate-summary.sh`

- [ ] **Step 1: 创建脚本框架**

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/config.sh"

PR_URL=""
ISSUE_NUMBER=""
WORKDIR=""

while (($#)); do
  case "$1" in
    --pr-url) PR_URL="$2"; shift 2 ;;
    --issue-number) ISSUE_NUMBER="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    *) agc::die "unknown flag: $1" ;;
  esac
done

[[ -z "$PR_URL" ]] && agc::die "--pr-url required"
[[ -z "$WORKDIR" ]] && agc::die "--workdir required"

agc::log "generating contribution summary for $PR_URL"
```

- [ ] **Step 2: 添加数据提取**

```bash
# 提取 PR 信息
PR_JSON=$(gh pr view "$PR_URL" --json number,title,url,repository,createdAt 2>/dev/null || echo "{}")
PR_NUMBER=$(echo "$PR_JSON" | jq -r '.number // "unknown"')
REPO_NAME=$(echo "$PR_JSON" | jq -r '.repository.nameWithOwner // "unknown"')

# 提取代码统计
cd "$WORKDIR"
DIFF_STAT=$(git diff --stat origin/${AGC_BASE_BRANCH}...HEAD 2>/dev/null || echo "")
FILES_CHANGED=$(echo "$DIFF_STAT" | tail -1 | awk '{print $1}')
INSERTIONS=$(echo "$DIFF_STAT" | tail -1 | awk '{print $4}')
DELETIONS=$(echo "$DIFF_STAT" | tail -1 | awk '{print $6}')

# 提取 SPEC 内容
PROBLEM=$(grep -A 10 "^## Problem" "$WORKDIR/.auto-pr/SPEC.md" | tail -n +2 || echo "无")
SOLUTION=$(grep -A 10 "^## Approach" "$WORKDIR/.auto-pr/SPEC.md" | tail -n +2 || echo "无")
```

- [ ] **Step 3: 构建 JSON 数据**

```bash
cat > /tmp/summary-data.json <<JSON
{
  "pr_number": $PR_NUMBER,
  "pr_title": "$(echo "$PR_JSON" | jq -r '.title')",
  "pr_url": "$PR_URL",
  "repo_name": "$REPO_NAME",
  "created_at": "$(date +%Y-%m-%d)",
  "status": "待合并",
  "problem": "$PROBLEM",
  "solution": "$SOLUTION",
  "technologies": "待提取",
  "files_changed": ${FILES_CHANGED:-0},
  "insertions": ${INSERTIONS:-0},
  "deletions": ${DELETIONS:-0}
}
JSON
```

- [ ] **Step 4: 调用 Python 脚本**

```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/render-summary.py" < /tmp/summary-data.json
rm -f /tmp/summary-data.json
agc::log "contribution summary generated"
```

- [ ] **Step 5: 提交脚本**

```bash
chmod +x skills/auto-github-contributor/scripts/generate-summary.sh
git add skills/auto-github-contributor/scripts/generate-summary.sh
git commit -m "feat: add generate-summary.sh script"
```

---

## Task 4: 集成到 create-pr.sh

**Files:**
- Modify: `skills/auto-github-contributor/scripts/create-pr.sh:154`

- [ ] **Step 1: 在 create-pr.sh 添加调用**

在第 154 行（打印 PR_URL 后）添加：

```bash
# 生成贡献总结
if [[ -n "$PR_URL" ]]; then
  bash "$SKILL_DIR/scripts/generate-summary.sh" \
    --pr-url "$PR_URL" \
    --issue-number "${ISSUE_NUMBER:-}" \
    --workdir "$WORKDIR" \
    || agc::log "warning: summary generation failed"
fi
```

- [ ] **Step 2: 提交修改**

```bash
git add skills/auto-github-contributor/scripts/create-pr.sh
git commit -m "feat: integrate summary generation into PR flow"
```

---

## Task 5: 端到端测试

- [ ] **Step 1: 手工测试完整流程**

运行 `/auto-contribute` 对一个测试仓库创建 PR：

```bash
/auto-contribute owner/test-repo
```

- [ ] **Step 2: 验证生成的文件**

检查单独文件：

```bash
ls -la ~/contributions/
cat ~/contributions/owner-test-repo-pr-*.md
```

验证内容：
- PR 链接正确
- 问题和解决方案已填充
- 技术指标准确

- [ ] **Step 3: 验证汇总文件**

```bash
cat ~/contributions/my-oss-contributions.md
```

验证：
- 新条目在最前面
- 日期格式正确
- Markdown 格式正确

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat: contribution summary generation complete"
git push
```

---

## 执行选项

**计划已完成并保存到 `docs/superpowers/plans/2026-06-04-contribution-summary.md`**

**两种执行方式：**

**1. Subagent-Driven（推荐）** - 每个任务派发一个新的 subagent，任务间审查，快速迭代

**2. Inline Execution** - 在当前会话中使用 executing-plans 执行，批量执行带检查点

**选择哪种方式？**
