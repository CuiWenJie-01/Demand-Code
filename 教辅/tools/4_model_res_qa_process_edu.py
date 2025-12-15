import json
import os, sys
import re
import logging
import multiprocessing as mp
from tqdm import tqdm
from collections import defaultdict
import functools

def robust_json_parse(json_str):
    """更健壮的JSON解析方法，处理特殊字符和格式问题"""
    max_attempts = 3  # 减少尝试次数以提升性能
    attempts = 0

    while attempts < max_attempts:
        attempts += 1
        try:
            # 尝试标准解析
            return json.loads(json_str), None
        except json.JSONDecodeError as e:
            # 特定错误修复
            error_msg = str(e).lower()
            
            if "unterminated string" in error_msg:
                # 修复未终止的字符串：在错误位置插入缺失的引号
                pos = e.pos
                if pos < len(json_str):
                    json_str = json_str[:pos] + '"' + json_str[pos:]
                else:
                    json_str += '"'
                    
            elif "expecting ',' delimiter" in error_msg:
                # 修复缺失的逗号：在错误位置插入逗号
                pos = e.pos
                if pos < len(json_str):
                    json_str = json_str[:pos] + ',' + json_str[pos:]
                    
            elif "extra data" in error_msg:
                # 处理多余数据：截取到有效部分
                pos = e.pos
                json_str = json_str[:pos]
                
            elif "expecting property name" in error_msg:
                # 修复属性名引号问题
                # 查找错误位置附近的上下文
                start = max(0, e.pos - 20)
                end = min(len(json_str), e.pos + 20)
                context = json_str[start:end]
                
                # 尝试修复单引号属性名问题
                if "'" in context:
                    # 使用正则表达式替换单引号属性名为双引号
                    json_str = re.sub(
                        r"'\s*(\w+)\s*'\s*:", 
                        r'"\1":', 
                        json_str
                    )
                # 尝试修复无引号属性名问题
                else:
                    # 在错误位置附近添加双引号
                    pos = e.pos
                    if pos < len(json_str) and json_str[pos] not in ['"', "'"]:
                        # 向前查找属性名的开始位置
                        start_pos = pos
                        while start_pos > 0 and json_str[start_pos-1] not in ['{', ',', ':']:
                            start_pos -= 1
                        # 向后查找属性名的结束位置
                        end_pos = pos
                        while end_pos < len(json_str) and json_str[end_pos] not in [':', '}']:
                            end_pos += 1
                        # 添加双引号
                        if start_pos < end_pos:
                            property_name = json_str[start_pos:end_pos].split(':')[0].strip()
                            json_str = (json_str[:start_pos] + 
                                        f'"{property_name}":' + 
                                        json_str[end_pos:])
            
            else:
                # 快速修复尝试
                try:
                    # 尝试处理未转义的控制字符
                    cleaned_str = re.sub(r'[\x00-\x1f]', ' ', json_str)
                    return json.loads(cleaned_str), None
                except:
                    try:
                        # 尝试处理单引号问题
                        normalized_str = re.sub(r"'(.*?)'", r'"\1"', json_str)
                        return json.loads(normalized_str), None
                    except:
                        try:
                            # 处理Markdown代码块标记
                            clean_str = re.sub(r'^```json\s*|\s*```$', '', json_str, flags=re.MULTILINE)
                            clean_str = clean_str.strip()
                            return json.loads(clean_str), None
                        except Exception as e2:
                            return None, f"解析失败: {str(e)}\n备用解析失败: {str(e2)}"
    
    return None, f"经过{max_attempts}次尝试后解析仍然失败"

def extract_outermost_json_objects(text):
    """
    提取文本中以最外层 {} 为界的完整 JSON 数据。
    """
    json_objects = []  # 存储完整的 JSON 对象
    buffer = ""        # 临时存储当前正在处理的内容
    brace_count = 0    # 记录大括号的嵌套层级

    # 按字符逐一处理文本
    for char in text:
        if char == '{':
            brace_count += 1  # 遇到左大括号，嵌套层级加1
        elif char == '}':
            brace_count -= 1  # 遇到右大括号，嵌套层级减1

        buffer += char  # 把当前字符添加到暂存区
        if brace_count == 0 and buffer.strip():  # 如果嵌套层级归0，意味着找到一个完整的 JSON 对象
            try:
                # 尝试解析 JSON 数据
                json_obj,_ = robust_json_parse(buffer.strip())
                # 验证是否是有效的题目对象（至少包含题目编号或背景知识）
                if isinstance(json_obj, dict) and ("题目编号" in json_obj or "题目背景知识" in json_obj):
                     json_objects.append(json_obj)
            except:
                pass  # 如果解析失败，忽略该段
            buffer = ""  # 清空缓冲区，准备处理下一个 JSON 对象

    return json_objects

def extract_num(img_path):
    """提取文件名中的序号，兼容两种格式"""
    # 先尝试原格式：xxx-数字.后缀（如 abc-123.png）
    dash_split = img_path.split("-")
    if len(dash_split) > 1:
        num_part = dash_split[-1].split(".")[0]
        if num_part.isdigit():
            return int(num_part)
    # 再尝试新格式：image+数字+字母.后缀（如 image0002243A.png）
    match = re.search(r'image(\d+)', img_path)
    if match:
        return int(match.group(1))
    # 兜底：无法提取时返回0（避免报错，同时记录警告）
    return 0

def process_single_file(args):
    """
    处理单个JSONL文件
    返回处理后的记录列表和扫描文件列表
    """
    input_file, source_type_default = args
    all_processed_records = []
    scan_file_list = []
    
    match = re.search(r"(\d{13})_(.*?)_export_all", input_file)
    source_type = match.group(2) if match else source_type_default

    # 读取并初步处理输入文件
    with open(input_file, 'r', encoding='utf-8') as infile:
        for line_num, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                original_data = json.loads(line)
            except json.JSONDecodeError as e:
                continue

            section = original_data['id'].get("file_name", "unknown_section")

            # 提取基础字段 (不包括 query)
            base_fields = {
                "img_path": original_data['id'].get("img_path", [str(line_num)]),
                "source_type": original_data['id'].get("source_type", source_type),
                "section": original_data['id'].get("section", section),
                "url": original_data['id'].get("url", None)
            }

            if 'answer_mode4' in original_data:
                answer_mode4_content = original_data.get("answer_mode4", "")
            elif 'answer' in original_data:
                answer_mode4_content = original_data.get("answer", "")
            else:
                logging.info('模型结果答案字段异常')
            
            # 尝试解析 answer_mode4 中的 JSON 对象
            parsed_objects = []
            if isinstance(answer_mode4_content, str) and answer_mode4_content.strip():
                # 使用提供的函数尝试解析
                parsed_objects = extract_outermost_json_objects(answer_mode4_content)
            elif isinstance(answer_mode4_content, dict):
                # 如果已经是 dict
                parsed_objects = [answer_mode4_content]

            if len(parsed_objects) == 0:
                scan_file_list.append(base_fields['section'])

            # 根据解析出的对象进行拆分和重组
            for answer_obj in parsed_objects:
                if not isinstance(answer_obj, dict):
                    continue # 安全检查

                # 情况1: 包含共享背景知识 (有 "题目背景知识" 和 "sub_qa")
                if "题目背景知识" in answer_obj and "sub_qa" in answer_obj:
                    new_record = {**base_fields, **answer_obj}
                    all_processed_records.append(new_record)
                
                # 情况2: 独立题干 (看起来像一个独立的题目对象，有 "题目编号")
                elif "题目编号" in answer_obj:
                    background_info = {
                        "题目是否包含背景知识": "否",
                        "题目背景知识": "无",
                    }
                    new_record = {**base_fields, **background_info, **answer_obj}
                    all_processed_records.append(new_record)

    return all_processed_records, scan_file_list

def process_and_split_jsonl(input_dir, output_dir):
    """
    并行处理JSONL文件，提取字段，拆分answer_mode4，并按source_type和section组织输出为JSON Lines。
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有输入文件
    input_files = []
    for file in os.listdir(input_dir):
        if file.endswith('.json'):
            input_files.append(os.path.join(input_dir, file))
    
    if not input_files:
        logging.info("没有找到输入文件")
        return
    
    # 默认source_type
    source_type_default = 'unknown_source_type'
    
    # 准备参数
    args_list = [(file, source_type_default) for file in input_files]
    
    # 使用多进程并行处理
    all_processed_records = []
    scan_file_lists = []
    
    with mp.Pool(processes=min(mp.cpu_count(), len(input_files))) as pool:
        results = list(tqdm(pool.imap(process_single_file, args_list), 
                           total=len(input_files), desc="Processing files"))
    
    # 合并结果
    for records, scan_list in results:
        all_processed_records.extend(records)
        scan_file_lists.extend(scan_list)
    
    # 按 source_type 和 section 组织并写入文件 (JSON Lines 格式)
    grouped_by_source = defaultdict(list)
    for record in all_processed_records:
        source_type = record.get("source_type", "unknown_source")
        grouped_by_source[source_type].append(record)

    # 为每个 source_type 创建文件夹和文件
    for source_type, records in grouped_by_source.items():
        source_dir = os.path.join(output_dir, source_type)
        os.makedirs(source_dir, exist_ok=True)
        logging.info(f"已创建目录：{source_dir}")

        # 按 section 分组记录
        section_groups = defaultdict(list)
        for record in records:
            section = record.get("section", "unknown_section")
            section_groups[section].append(record)

        # 为每个 section 创建文件
        for section, section_records in section_groups.items():
            # 按img_path中第一个图片的序号排序
            section_records.sort(key=lambda x: extract_num(x['img_path'][0]))
            
            # 清理文件名
            safe_section = "".join(c for c in section if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_section = safe_section.replace(' ', '_')

            # 处理重名文件 (JSON Lines 格式)
            file_path = os.path.join(source_dir, f"{safe_section}.json")
            
            # 写入 JSON Lines 文件 (每行一个 JSON 对象)
            try:
                with open(file_path, 'w', encoding='utf-8') as outfile:
                    for record in section_records:
                        outfile.write(json.dumps(record, ensure_ascii=False) + '\n')
                logging.info(f"已创建文件: {file_path} (包含 {len(section_records)} 条记录)")
            except Exception as e:
                logging.error(f"[错误] 写入文件 {file_path} 时失败: {e}")

    logging.info(f"所有数据处理并输出完成！总数据量{len(all_processed_records)}, 无结果试卷：{len(scan_file_lists)}")


if __name__ == "__main__":
    # 请确保 Pasted_Text_1754376870865.txt 文件与脚本在同一目录下
    # 或者修改 input_jsonl_file 为文件的完整路径
    root = sys.argv[1]
    batch = sys.argv[2]
    input_dir = rf"{root}/{batch}/5_model_res_qa_{batch}"
    output_dir = rf"{root}/{batch}/6_extract_qa_{batch}"
    os.makedirs(output_dir, exist_ok=True)
    err_log = f"{output_dir}/日志.log"
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=err_log,
        filemode='w'
    )

    process_and_split_jsonl(input_dir, output_dir)