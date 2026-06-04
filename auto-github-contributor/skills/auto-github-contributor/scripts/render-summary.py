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
    template = Path(template_path).read_text(encoding='utf-8')

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

    Path(output_path).write_text(content, encoding='utf-8')


def update_aggregated_summary(data, template_path, aggr_file_path):
    """更新汇总文件，在开头插入新条目"""
    aggr_file = Path(aggr_file_path)

    template = Path(template_path).read_text(encoding='utf-8')
    new_entry = template
    for key, value in data.items():
        placeholder = "{{" + key.upper() + "}}"
        new_entry = new_entry.replace(placeholder, str(value))

    if aggr_file.exists():
        existing = aggr_file.read_text(encoding='utf-8')
    else:
        existing = "# 我的开源贡献\n\n"

    updated = existing.replace("# 我的开源贡献\n\n",
                                f"# 我的开源贡献\n\n{new_entry}\n")

    aggr_file.write_text(updated, encoding='utf-8')


def main():
    """主函数：从 stdin 读取 JSON，生成 Markdown 文件"""
    data = json.load(sys.stdin)

    script_dir = Path(__file__).parent
    template_path = script_dir.parent / "templates" / "SUMMARY.template.md"

    repo_slug = data["repo_name"].replace("/", "-")
    date_str = data["created_at"]
    filename = f"{repo_slug}-pr-{data['pr_number']}-{date_str}.md"

    contributions_dir = Path.home() / "contributions"
    contributions_dir.mkdir(parents=True, exist_ok=True)

    individual_file = contributions_dir / filename
    render_individual_summary(data, str(template_path), str(individual_file))
    print(f"Generated: {individual_file}")

    aggr_file = contributions_dir / "my-oss-contributions.md"
    update_aggregated_summary(data, str(template_path), str(aggr_file))
    print(f"Updated: {aggr_file}")


if __name__ == "__main__":
    main()
