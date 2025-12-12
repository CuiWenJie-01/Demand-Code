import json
import os
from collections import defaultdict

def get_last_path_segment(path):
    """提取路径中最后一个文件/文件夹层级"""
    if not path:
        return ""
    cleaned_path = path.rstrip(os.sep).rstrip('/').rstrip('\\')
    return os.path.basename(cleaned_path)

def extract_answer_key(original_data):
    """提取“对应答案”作为匹配key（处理单题型/多题型，空值统一为""）"""
    if not isinstance(original_data, dict):
        return ""
    
    sub_qa_list = original_data.get("sub_qa", [])
    if isinstance(sub_qa_list, list) and sub_qa_list:
        answer_parts = []
        for qa in sub_qa_list:
            if not isinstance(qa, dict):
                qa = {}
            ans = qa.get("对应答案", "").strip()
            answer_parts.append(ans)
        return "|".join(answer_parts)
    
    return original_data.get("对应答案", "").strip()

def load_data_by_answer(input_path):
    """加载JSONL文件，以“对应答案”为key构建数据字典（一个key可能对应多个记录）"""
    answer_data_dict = defaultdict(list)
    print(f"正在加载文件：{input_path}")
    with open(input_path, 'r', encoding='utf-8') as infile:
        for idx, line in enumerate(infile, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                original_data = entry.get('id', {}).get('original_data', {}) or entry.get('original_data', {})
                answer_key = extract_answer_key(original_data)
                answer_data_dict[answer_key].append(entry)
            except Exception as e:
                print(f"[第{idx}行] 解析错误，已跳过。错误信息: {str(e)[:150]}")
    print(f"加载完成：共处理{idx}行 → 生成{len(answer_data_dict)}个答案key → 累计{sum(len(v) for v in answer_data_dict.values())}条记录")
    return answer_data_dict

def transform_entry(single_entry, multi_entry):
    """转换记录：空值直接置空，保留所有结构，不抛出终止性异常"""
    original_data = single_entry.get('id', {}).get('original_data', {}) or \
                   multi_entry.get('id', {}).get('original_data', {}) or \
                   single_entry.get('original_data', {}) or multi_entry.get('original_data', {}) or {}
    
    source_type = original_data.get('source_type', '').strip()
    single_answer = single_entry.get('answer', '').strip() if isinstance(single_entry, dict) else ""
    multi_answer = multi_entry.get('answer', '').strip() if isinstance(multi_entry, dict) else ""
    
    category_desc = f"{source_type}\nGemini：{single_answer}\nQwen3：{multi_answer}"

    sub_qa_list = original_data.get("sub_qa", [])
    if not isinstance(sub_qa_list, list):
        sub_qa_list = []

    if sub_qa_list:
        bg = original_data.get("题目背景知识", "").strip()
        q_parts = [bg] if bg else []
        for qa in sub_qa_list:
            if not isinstance(qa, dict):
                qa = {}
            num = qa.get("题目编号", "").strip()
            content = qa.get("题目内容", "").strip()
            num_str = f"题目{num}" if num else ""
            if num_str:
                q_parts.append(num_str)
            if content:
                q_parts.append(content)
        q_text = "\n".join(q_parts)

        a_parts = []
        for qa in sub_qa_list:
            if not isinstance(qa, dict):
                qa = {}
            num = qa.get("题目编号", "").strip()
            ans = qa.get("对应答案", "").strip()
            num_str = f"题目{num}" if num else ""
            if num_str:
                a_parts.append(num_str)
            if ans:
                a_parts.append(ans)
        a_text = "\n".join(a_parts)
    else:
        num = original_data.get("题目编号", "").strip()
        content = original_data.get("题目内容", "").strip()
        ans = original_data.get("对应答案", "").strip()
        num_str = f"题目{num}" if num else ""
        
        q_parts = [num_str, content] if num_str else [content]
        a_parts = [num_str, ans] if num_str else [ans]
        q_text = "\n".join(filter(None, q_parts))
        a_text = "\n".join(filter(None, a_parts))

    img_paths = original_data.get("img_path", [])
    if isinstance(img_paths, str):
        img_paths = [img_paths]
    if not isinstance(img_paths, list):
        img_paths = []
    processed_pics = [get_last_path_segment(path) for path in img_paths if path and str(path).strip()]
    pic_str = ";".join(processed_pics)

    platform_entry = {
        "dialogContent": [
            {
                "qualified": "",
                "sessionLabel": {},
                "content": [
                    {
                        "PIC": pic_str,
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
        "categoryDesc": category_desc
    }

    # 修复点1：返回source_type，供写入文件时匹配
    return (category_desc, platform_entry, source_type)

def convert_to_jsonl(input_path1, input_path2, output_dir):
    """按“对应答案”匹配数据，并按source_type分类输出到不同JSON文件"""
    print("="*60)
    print("开始加载数据（按“对应答案”分组）...")
    single_data_dict = load_data_by_answer(input_path1)
    multi_data_dict = load_data_by_answer(input_path2)
    print("="*60)

    # 收集所有唯一的source_type
    source_types = set()
    for entries in single_data_dict.values():
        for entry in entries:
            od = entry.get('id', {}).get('original_data', {}) or entry.get('original_data', {})
            st = od.get('source_type', '').strip()
            if st:
                source_types.add(st)
    for entries in multi_data_dict.values():
        for entry in entries:
            od = entry.get('id', {}).get('original_data', {}) or entry.get('original_data', {})
            st = od.get('source_type', '').strip()
            if st:
                source_types.add(st)
    # 新增：添加“未知”类型，避免source_type为空时数据丢失
    source_types.add("未知")

    # 创建输出目录并初始化按source_type分类的输出文件
    os.makedirs(output_dir, exist_ok=True)
    output_files = {}
    for st in source_types:
        filename = f"select-{st}-单轮质检-to平台.json"
        file_path = os.path.join(output_dir, filename)
        output_files[st] = open(file_path, 'w', encoding='utf-8')

    category_groups = defaultdict(list)
    matched_count = 0
    unmatched_single = sum(len(v) for v in single_data_dict.values())
    unmatched_multi = sum(len(v) for v in multi_data_dict.values())
    conversion_failed = 0

    print("开始按“对应答案”匹配数据并转换...")
    common_answer_keys = set(single_data_dict.keys()) & set(multi_data_dict.keys())
    print(f"找到{len(common_answer_keys)}个共同的“对应答案”key，开始匹配...")

    for answer_key in common_answer_keys:
        single_entries = single_data_dict[answer_key]
        multi_entries = multi_data_dict[answer_key]
        match_count = min(len(single_entries), len(multi_entries))
        for i in range(match_count):
            single_entry = single_entries[i]
            multi_entry = multi_entries[i]
            try:
                # 修复点2：接收返回的3个值，拿到正确的source_type
                category_desc, platform_entry, source_type = transform_entry(single_entry, multi_entry)
                category_groups[category_desc].append(platform_entry)
                matched_count += 1

                # 修复点3：使用返回的source_type，为空则设为“未知”
                st = source_type if source_type.strip() else '未知'
                if st in output_files:
                    json.dump(platform_entry, output_files[st], ensure_ascii=False)
                    output_files[st].write('\n')
            except Exception as e:
                conversion_failed += 1
                print(f"警告：答案key={answer_key} 对应的第{i+1}组记录转换失败。错误：{str(e)[:150]}")
        
        unmatched_single -= match_count
        unmatched_multi -= match_count

    print(f"匹配完成：成功匹配{matched_count}组记录 → 未匹配单轮{unmatched_single}条 → 未匹配多轮{unmatched_multi}条 → 转换失败{conversion_failed}条")

    # 关闭所有输出文件
    for f in output_files.values():
        f.close()

    # 输出最终统计
    print("="*60)
    print("数据转换统计汇总：")
    print(f"单轮数据总数：{sum(len(v) for v in single_data_dict.values())}")
    print(f"多轮数据总数：{sum(len(v) for v in multi_data_dict.values())}")
    print(f"共同答案key数：{len(common_answer_keys)}")
    print(f"生成不同categoryDesc组数：{len(category_groups)}")
    print(f"输出文件目录：{os.path.abspath(output_dir)}")
    print(f"生成文件列表：{', '.join([f'select-{st}-单轮质检-to平台.json' for st in source_types])}")

    print("\n前5个匹配成功的“对应答案”key示例：")
    for i, key in enumerate(list(common_answer_keys)[:5]):
        print(f"  {i+1}. 答案key：{key} → 匹配记录数：{min(len(single_data_dict[key]), len(multi_data_dict[key]))}组")

if __name__ == "__main__":
    # 路径配置（请修改为实际路径）
    input_path1 = "/DL_data_new/ftpdata/jjhu32/code/切题链路合并/1147-第一试卷网爬取-10-50/14_select_check_1147-第一试卷网爬取-10-50/认知基础-SFT_12321_gemini2.5-pro-多模_胡佳驹_1762755625147_胡佳驹_1147-第一试卷网爬取-10-50_单轮自动化质检_gemini2_export_all_shlt-gemini2.5-pro.json"
    input_path2 = "/DL_data_new/ftpdata/jjhu32/code/切题链路合并/1147-第一试卷网爬取-10-50/14_select_check_1147-第一试卷网爬取-10-50/认知基础-SFT_12322_qwen3-vl-235b-a22b-thinking_胡佳驹_1762755848439_胡佳驹_1147-第一试卷网爬取-10-50_单轮自动化质检_qwen3-vl-235b-a22b-thinking-多模_认知基础-SFT_export_all_qwen3-vl-235b-a22b-thinking_.json"
    output_dir = "/DL_data_new/ftpdata/jjhu32/code/切题链路合并/1147-第一试卷网爬取-10-50/14_select_check_1147-第一试卷网爬取-10-50"  # 输出目录，文件将按source_type在此目录下生成

    # 校验输入文件是否存在
    for idx, path in enumerate([input_path1, input_path2], 1):
        if not os.path.exists(path):
            print(f"错误：第{idx}个输入文件不存在！路径：{os.path.abspath(path)}")
            exit(1)

    # 执行转换
    print(f"开始转换流程（按“对应答案”匹配 + 按source_type分类输出）：")
    print(f"单轮数据文件：{os.path.basename(input_path1)}")
    print(f"多轮数据文件：{os.path.basename(input_path2)}")
    print(f"输出目录：{os.path.basename(output_dir)}")
    print("="*60)
    convert_to_jsonl(input_path1, input_path2, output_dir)
    print("\n" + "="*60)
    print(f"✅ 转换完成！")
    print(f"输出文件目录：{os.path.abspath(output_dir)}")
    print("="*60)