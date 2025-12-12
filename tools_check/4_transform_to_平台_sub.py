import json
import sys
import os
from collections import defaultdict

def get_last_path_segment(path):
    """提取路径中最后一个文件/文件夹层级"""
    if not path:
        return ""
    # 移除路径末尾的分隔符（兼容 Windows/Linux）
    cleaned_path = path.rstrip(os.sep).rstrip('/').rstrip('\\')
    return os.path.basename(cleaned_path)

def transform_entry(entry):
    """将原始entry转换为平台格式，返回（categoryDesc, 转换后对象）"""
    # 提取source_type作为categoryDesc，若不存在则设为空字符串（统一分组key）
    source_type = entry.get("source_type", "").strip()
    category_desc = source_type  # 后续分组的核心key

    # 判断是否是多题型（含sub_qa列表）
    if "sub_qa" in entry and isinstance(entry["sub_qa"], list):
        # 提取背景知识
        bg = entry.get("题目背景知识", "").strip()

        # 构建q部分（背景+子题目编号+子题目内容）
        q_parts = []
        if bg:
            q_parts.append(bg)
        for qa in entry["sub_qa"]:
            num = qa.get("题目编号", "").strip()
            content = qa.get("题目内容", "").strip()
            num_str = f"题目{num}" if num else ""
            if num_str:
                q_parts.append(num_str)
            if content:
                q_parts.append(content)
        q_text = "\n".join(filter(None, q_parts))

        # 构建a部分（子题目编号+子题目答案）
        a_parts = []
        for qa in entry["sub_qa"]:
            num = qa.get("题目编号", "").strip()
            ans = qa.get("对应答案", "").strip()
            num_str = f"题目{num}" if num else ""
            if num_str:
                a_parts.append(num_str)
            if ans:
                a_parts.append(ans)
        a_text = "\n".join(filter(None, a_parts))

    else:
        # 单题型处理
        num = entry.get("题目编号", "").strip()
        content = entry.get("题目内容", "").strip()
        ans = entry.get("对应答案", "").strip()

        q_parts = []
        a_parts = []
        num_str = f"题目{num}" if num else ""
        
        if num_str:
            q_parts.append(num_str)
            a_parts.append(num_str)
        if content:
            q_parts.append(content)
        if ans:
            a_parts.append(ans)
        
        q_text = "\n".join(filter(None, q_parts))
        a_text = "\n".join(filter(None, a_parts))

    # 处理图片路径：提取每个路径的最后一个层级
    img_paths = entry.get("img_path", [])
    # 确保是列表格式（兼容可能的字符串输入）
    if isinstance(img_paths, str):
        img_paths = [img_paths]
    # 提取每个路径的最后一个层级
    processed_pics = [get_last_path_segment(path) for path in img_paths if path.strip()]
    # 用分号拼接处理后的路径
    pic_str = ";".join(processed_pics)

    # 构建平台格式对象
    platform_entry = {
        "dialogContent": [
            {
                "qualified": "",
                "sessionLabel": {},
                "content": [
                    {
                        "PIC": pic_str,  # 使用处理后的路径最后层级
                        "q": q_text,
                        "a": a_text,
                        "otherTagInfoList": [],
                        "problemLabel": {}
                    }
                ]
            }
        ],
        "language": "",
        "queryExample": "",
        "taskCategory": "TODO",
        "categoryDesc": category_desc  # 保留分组key
    }

    return (category_desc, platform_entry)  # 返回key和对象，用于后续分组

def convert_to_jsonl(input_path, output_path):
    """读取原始JSONL，按categoryDesc分组后写入新JSONL"""
    # 1. 初始化分组容器：key=categoryDesc，value=该分组的所有JSON对象列表
    category_groups = defaultdict(list)

    # 2. 读取原始文件，转换并分组
    print(f"正在读取并转换原始数据：{input_path}")
    with open(input_path, 'r', encoding='utf-8') as infile:
        for idx, line in enumerate(infile, 1):
            line = line.strip()
            if not line:
                continue  # 跳过空行
            try:
                entry = json.loads(line)  # 解析原始JSON行
                category_desc, platform_entry = transform_entry(entry)  # 转换并获取分组key
                category_groups[category_desc].append(platform_entry)  # 加入对应分组
            except Exception as e:
                print(f"[第{idx}行] 解析/转换错误，已跳过。错误信息: {str(e)[:100]}")  # 截取长错误信息

    # 3. 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    # 4. 按分组写入输出文件（相同categoryDesc的对象连续存储）
    print(f"正在按categoryDesc分组写入输出文件：{output_path}")
    with open(output_path, 'w', encoding='utf-8') as outfile:
        # 遍历所有分组（按key排序，保证输出顺序稳定）
        for category_desc in sorted(category_groups.keys()):
            group_entries = category_groups[category_desc]
            # 写入该分组的所有对象
            for entry in group_entries:
                json.dump(entry, outfile, ensure_ascii=False)
                outfile.write('\n')

    # 5. 输出分组统计信息
    print(f"\n分组统计（共{len(category_groups)}个不同categoryDesc）：")
    for category_desc in sorted(category_groups.keys()):
        count = len(category_groups[category_desc])
        # 空categoryDesc显示为"[空值]"，更易识别
        display_key = category_desc if category_desc else "[空值]"
        print(f"  • {display_key}：{count} 条数据")

# 从命令行获取参数
if __name__ == "__main__":
    # 参数数量：input_dir（原始文件目录） + output_dir（输出目录） + batch（批次标识）
    if len(sys.argv) != 5:
        print("用法: python 4_convert_to_platform_jsonl.py <input_dir> <output_dir> <batch>")
        print("示例: python 4_convert_to_platform_jsonl.py /input /output 高考文综")
        print("说明: 按categoryDesc分组整理输出JSON对象，相同categoryDesc的对象连续存储")
        sys.exit(1)

    # 提取参数
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    level = sys.argv[3]
    subject = sys.argv[4]

    # 推导输入/输出文件路径
    input_filename = f"select-{level}{subject}.json"  # 前序脚本生成的原始文件（如"select-高考文综.json"）
    output_filename = f"select-{level}{subject}-to平台.json"  # 分组后的输出文件（如"select-高考文综-to平台.json"）
    
    input_path = os.path.join(input_dir, input_filename)  # 原始JSONL的完整路径
    output_path = os.path.join(output_dir, output_filename)  # 分组后文件的完整路径

    # 校验原始文件是否存在
    if not os.path.exists(input_path):
        print(f"错误：原始文件不存在！路径：{os.path.abspath(input_path)}")
        sys.exit(1)

    # 执行转换（含分组）
    print(f"开始转换流程：{input_path} -> {output_path}")
    convert_to_jsonl(input_path, output_path)
    print(f"\n转换完成！输出文件已保存至: {os.path.abspath(output_path)}")