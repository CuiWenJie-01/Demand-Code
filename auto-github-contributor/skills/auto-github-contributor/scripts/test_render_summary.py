#!/usr/bin/env python3
import json
import os
import sys
import tempfile
from pathlib import Path

# Import from render-summary.py (with hyphen in filename)
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import importlib.util
spec = importlib.util.spec_from_file_location("render_summary", str(SCRIPT_DIR / "render-summary.py"))
render_summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_summary)
render_individual_summary = render_summary.render_individual_summary
update_aggregated_summary = render_summary.update_aggregated_summary


def test_render_individual_summary():
    """测试生成单独的贡献总结文件"""
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

    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "cli-cli-pr-123-2026-06-04.md"
        template_path = SCRIPT_DIR.parent / "templates" / "SUMMARY.template.md"

        render_individual_summary(data, str(template_path), str(output_file))

        assert output_file.exists()

        content = output_file.read_text(encoding='utf-8')
        assert "cli/cli - PR #123" in content
        assert "README 中有拼写错误" in content
        assert "修正了 'teh' 为 'the'" in content
        assert "待合并" in content
        assert "1 个" in content
        assert "1 行" in content

    print("test_render_individual_summary passed")


def test_update_aggregated_summary():
    """测试更新汇总文件"""
    data = {
        "pr_number": 456,
        "pr_title": "Add feature X",
        "pr_url": "https://github.com/owner/repo/pull/456",
        "repo_name": "owner/repo",
        "created_at": "2026-06-05",
        "status": "已合并",
        "problem": "缺少功能 X",
        "solution": "实现了功能 X",
        "technologies": "Python, Bash",
        "files_changed": 3,
        "insertions": 50,
        "deletions": 10
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = SCRIPT_DIR.parent / "templates" / "SUMMARY.template.md"
        aggr_file = Path(tmpdir) / "my-oss-contributions.md"

        update_aggregated_summary(data, str(template_path), str(aggr_file))

        assert aggr_file.exists()
        content = aggr_file.read_text(encoding='utf-8')
        assert "# 我的开源贡献" in content
        assert "owner/repo - PR #456" in content
        assert "缺少功能 X" in content
        assert "已合并" in content

        # Test appending second entry
        data2 = {
            "pr_number": 789,
            "pr_title": "Fix bug Y",
            "pr_url": "https://github.com/owner/repo/pull/789",
            "repo_name": "owner/repo",
            "created_at": "2026-06-06",
            "status": "待合并",
            "problem": "存在 bug Y",
            "solution": "修复了 bug Y",
            "technologies": "JavaScript",
            "files_changed": 2,
            "insertions": 20,
            "deletions": 5
        }
        update_aggregated_summary(data2, str(template_path), str(aggr_file))

        content = aggr_file.read_text(encoding='utf-8')
        assert "owner/repo - PR #789" in content
        assert "owner/repo - PR #456" in content

    print("test_update_aggregated_summary passed")


if __name__ == "__main__":
    test_render_individual_summary()
    test_update_aggregated_summary()
    print("All tests passed")
