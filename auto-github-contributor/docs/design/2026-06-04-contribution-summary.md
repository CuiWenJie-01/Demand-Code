# 贡献总结功能设计文档

**日期**：2026-06-04  
**项目**：auto-github-contributor

## 1. 需求总结

### 功能目标
为 auto-github-contributor 添加自动生成贡献总结文档的功能，方便用户将开源贡献记录到简历中。

### 核心需求
1. **格式**：Markdown (.md)
2. **内容**：包含完整信息
   - PR 基本元数据（链接、仓库、日期）
   - 问题描述和解决方案
   - 使用的技术和展示的技能
   - 技术指标（代码行数、文件数等）
3. **存储**：
   - 单独文件：每个贡献一个 Markdown 文件
   - 汇总文件：所有贡献的聚合文档
   - 位置：`~/contributions/` 目录
4. **时机**：
   - PR 创建时自动生成
   - PR 合并时自动更新（添加合并日期）
5. **组织**：按日期排序（最新在前）

## 2. 整体架构

### 系统组件

新增三个核心组件：
1. `scripts/generate-summary.sh` - Shell 脚本，负责数据提取和流程编排
2. `scripts/render-summary.py` - Python 脚本，负责 Markdown 生成和文件管理
3. `templates/SUMMARY.template.md` - Markdown 模板文件

### 集成点

在 `scripts/create-pr.sh` 的第 154 行（打印 PR URL 之后）添加调用：

```bash
# 生成贡献总结
if [[ -n "$PR_URL" ]]; then
  bash "$SKILL_DIR/scripts/generate-summary.sh" \
    --pr-url "$PR_URL" \
    --issue-number "$ISSUE_NUMBER" \
    --workdir "$WORKDIR" \
    || agc::log "warning: summary generation failed"
fi
```

### 数据流

```
PR 创建成功（create-pr.sh）
    ↓
调用 generate-summary.sh
    ↓
提取数据（git log, git diff --stat, gh pr view）
    ↓
传递数据给 render-summary.py
    ↓
生成 Markdown 文件：
  1. 单独文件：~/contributions/{owner}-{repo}-pr-{num}-{date}.md
  2. 汇总文件：~/contributions/my-oss-contributions.md（追加到开头）
```

### 存储结构

```
~/contributions/
├── my-oss-contributions.md              # 汇总文件
├── cli-cli-pr-123-2026-06-04.md         # 单独文件
├── express-express-pr-456-2026-06-03.md # 单独文件
└── ...
```

## 3. 组件详细设计

### 3.1 generate-summary.sh

**职责**：
- 验证输入参数（PR URL、issue number、workdir）
- 调用 git/gh CLI 提取数据
- 调用 Python 脚本生成 Markdown
- 处理错误和日志输出

**输入参数**：
- `--pr-url <url>` - PR 的完整 URL
- `--issue-number <num>` - Issue 编号（可选）
- `--workdir <path>` - 工作目录路径

**数据提取**：
```bash
# PR 基本信息
gh pr view "$PR_URL" --json number,title,url,repository,createdAt

# 提交信息
git -C "$WORKDIR" log --oneline -1

# 代码变更统计
git -C "$WORKDIR" diff --stat origin/$AGC_BASE_BRANCH...HEAD

# SPEC 和 TODO 内容
cat "$WORKDIR/.auto-pr/SPEC.md"
cat "$WORKDIR/.auto-pr/TODO.md"
```

**错误处理**：
- PR URL 无效：记录警告，跳过生成
- Git 命令失败：使用默认值
- Python 脚本失败：记录错误，不影响主流程

### 3.2 render-summary.py

**职责**：
- 接收 JSON 格式的数据
- 使用模板生成 Markdown
- 管理单独文件和汇总文件
- 处理日期排序和文件追加

**输入**：JSON 格式的数据（通过 stdin）
```json
{
  "pr_number": 123,
  "pr_title": "Fix typo in README",
  "pr_url": "https://github.com/owner/repo/pull/123",
  "repo_name": "owner/repo",
  "created_at": "2026-06-04",
  "merged_at": null,
  "problem": "README 中的拼写错误",
  "solution": "修正了 'teh' 为 'the'",
  "technologies": ["Markdown", "Documentation"],
  "skills": ["文档改进", "细节关注"],
  "stats": {
    "files_changed": 1,
    "insertions": 1,
    "deletions": 1
  }
}
```

**输出**：
1. 单独文件：`~/contributions/{owner}-{repo}-pr-{num}-{date}.md`
2. 更新汇总文件：在开头插入新条目

**核心逻辑**：
```python
def generate_individual_summary(data, template):
    """生成单独的贡献总结文件"""
    # 使用模板渲染 Markdown
    # 保存到 ~/contributions/{filename}.md
    
def update_aggregated_summary(data):
    """更新汇总文件，保持按日期排序"""
    # 读取现有汇总文件
    # 在开头插入新条目
    # 保持日期排序（最新在前）
```

### 3.3 SUMMARY.template.md

**模板结构**：
```markdown
## {{REPO_NAME}} - PR #{{PR_NUMBER}}

**日期**：{{CREATED_AT}}  
**状态**：{{STATUS}}  
**链接**：[PR #{{PR_NUMBER}}]({{PR_URL}})

### 问题描述
{{PROBLEM}}

### 解决方案
{{SOLUTION}}

### 使用的技术和技能
{{TECHNOLOGIES}}

### 技术指标
- 修改文件：{{FILES_CHANGED}} 个
- 新增代码：{{INSERTIONS}} 行
- 删除代码：{{DELETIONS}} 行

---
```

## 4. 实现要点

### 4.1 数据提取

从多个来源提取数据：
1. **gh CLI**：PR 基本信息、仓库信息
2. **git**：提交历史、代码变更统计
3. **文件**：SPEC.md、TODO.md 内容

### 4.2 Markdown 生成

使用 Python 的字符串模板：
- 简单替换：使用 `str.replace()` 或 `str.format()`
- 保持代码简洁，避免引入额外依赖

### 4.3 文件管理

**目录创建**：
```bash
mkdir -p ~/contributions
```

**文件命名规范**：
- 单独文件：`{owner}-{repo}-pr-{number}-{YYYY-MM-DD}.md`
- 汇总文件：`my-oss-contributions.md`

**汇总文件更新策略**：
1. 读取现有内容
2. 解析日期
3. 在正确位置插入新条目（保持降序）
4. 写回文件

### 4.4 合并状态更新

**初始实现**：PR 创建时标记为 "待合并"

**未来增强**：
- 添加 `/update-contributions` 命令
- 轮询 GitHub API 检查合并状态
- 更新单独文件和汇总文件中的状态

## 5. 测试策略

### 单元测试
- Python 脚本的 Markdown 生成逻辑
- 文件命名和路径处理
- 日期排序逻辑

### 集成测试
- 完整流程：从 PR 创建到文件生成
- 错误处理：无效输入、文件权限问题
- 边界情况：特殊字符、长标题

### 手工测试
1. 运行 `/auto-contribute` 完成一个真实贡献
2. 检查生成的单独文件内容和格式
3. 检查汇总文件是否正确更新
4. 验证日期排序是否正确

## 6. 文件清单

新增文件：
1. `scripts/generate-summary.sh` - Shell 编排脚本
2. `scripts/render-summary.py` - Python Markdown 生成器
3. `templates/SUMMARY.template.md` - Markdown 模板

修改文件：
1. `scripts/create-pr.sh` - 添加生成总结的调用（第 154 行后）

生成文件（用户目录）：
1. `~/contributions/my-oss-contributions.md` - 汇总文件
2. `~/contributions/{owner}-{repo}-pr-{num}-{date}.md` - 单独文件

## 7. 实施计划

1. 创建模板文件（SUMMARY.template.md）
2. 实现 Python 脚本（render-summary.py）
3. 实现 Shell 脚本（generate-summary.sh）
4. 修改 create-pr.sh 添加集成调用
5. 测试完整流程
6. 提交代码

---

**设计完成时间**：2026-06-04
