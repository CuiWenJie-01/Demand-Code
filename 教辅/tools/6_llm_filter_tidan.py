import logging
import os, sys
import json
import glob
import sys
import shutil
from pathlib import Path
from sympy import EX
from tqdm import tqdm
from prompt_loader import *
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from collections import defaultdict
import multiprocessing as mp

# 加载第三阶段 prompt
current_dir = Path(__file__).parent
config_path = current_dir / "prompts.yaml"

# 创建线程局部存储，避免多线程环境下重复创建loader实例
thread_local = threading.local()

def get_thread_loader():
    """获取线程本地的prompt loader实例"""
    if not hasattr(thread_local, 'loader'):
        thread_local.loader = PromptLoader(str(config_path))
    return thread_local.loader

# gcl修改：所有xxx.get("字段名", "").strip()改为(xxx.get("字段名") or "").strip()
def extract_qa_text(entry):
    # 判断是否是多题型
    if "sub_qa" in entry and isinstance(entry["sub_qa"], list):
        # 背景知识
        # 结果是 None、空字符串 ""、或其他"假值"（falsy value），就用空字符串 "" 代替，然后再调用 .strip()
        bg = (entry.get("题目背景知识") or "").strip()
        # q 部分
        q_parts = []
        if bg:
            q_parts.append(bg)
        for qa in entry["sub_qa"]:
            num = (qa.get("题目编号") or "").strip()
            ques = (qa.get("题目内容") or "").strip()
            full_ques = f"题目{num}  {ques}" if num else f"{ques}"
            q_parts.append(full_ques)
        q_text = "\n".join(filter(None, q_parts))
        # a 部分
        a_parts = []
        for qa in entry["sub_qa"]:
            num = (qa.get("题目编号") or "").strip()
            ans = (qa.get("对应答案") or "").strip()
            full_ans = f"题目{num}  {ans}" if num else f"{ans}"
            a_parts.append(full_ans)
        a_text = "\n".join(filter(None, a_parts))
    else:
        # 单题型
        num = (entry.get("题目编号") or "").strip()
        ques = (entry.get("题目内容") or "").strip()
        ans = (entry.get("对应答案") or "").strip()
        q_parts = []
        a_parts = []
        full_ques = f"题目{num}  {ques}" if num else f"{ques}"
        full_ans = f"题目{num}  {ans}" if num else f"{ans}"
        if ques:
            q_parts.append(full_ques)
        if ans:
            a_parts.append(full_ans)
        q_text = "\n".join(filter(None, q_parts))
        a_text = "\n".join(filter(None, a_parts))
    
    return q_text, a_text

def extract_subject_from_source(source_type: str) -> str:
    """从 source_type 字符串中提取学科名称"""
    # 使用字典查找提高效率
    subject_keywords = {
        '英语': '英语',
        '政治': '政治',
        '道德与法治': '政治',
        '历史': '历史',
        '语文': '语文',
        '地理': '地理',
        '地化生物数': '地理',
        '文综': '文综',
        '信息': '信息科技'
    }
    
    for keyword, subject in subject_keywords.items():
        if keyword in source_type:
            return subject
            
    raise ValueError(f"无法从 source_type '{source_type}' 中识别学科")

def process_single_line(data, file_path, subject):
    """处理单行数据"""
    try:
        q_text, a_text = extract_qa_text(data)
    except Exception as e:
        logging.error(f"处理时发生错误{e}，原数据如下:{data}")
        return None

    # 动态构建第三阶段 prompt
    answer_for_prompt = "没有答案" if 'only_q' in file_path else a_text
    
    # 获取线程本地loader
    local_loader = get_thread_loader()
    
    try:
        full_prompt = local_loader.build_prompt(
            stage="3_check_availability",
            subject=subject,
            query=q_text,
            answer=answer_for_prompt
        )
    except Exception as e:
        logging.error(f"构建prompt时发生错误: {e}")
        return None

    # 创建输出对象
    id_info = {
        "original_data": data,
        "source_type": data.get('source_type', ''),
        "section": data.get('section', ''),
        "url": data.get('url', ''),
        "img_path": data.get('img_path', '')
    }

    output_obj = {
        "query": full_prompt,
        "id": id_info,
    }
    
    return json.dumps(output_obj, ensure_ascii=False)

def process_single_file(file_path, subject):
    """处理单个文件，返回处理结果列表"""
    results = []
    file_name = os.path.basename(file_path)
    
    # 读取输入文件
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                    
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON解析错误 in {file_name} line {line_num}: {e}")
                    continue
                
                result = process_single_line(data, file_path, subject)
                if result:
                    results.append(result)
    except Exception as e:
        logging.error(f"读取文件 {file_path} 时发生错误: {e}")
        
    return results

def process_folder(input_folder, output_file, max_workers=4):
    """处理文件夹中的所有JSON文件并合并为一个输出文件"""
    source_type = os.path.basename(input_folder)

    # 动态加载第三阶段 prompt
    subject = extract_subject_from_source(source_type)

    # 确保输出文件夹存在
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 获取所有JSON文件
    json_files = glob.glob(os.path.join(input_folder, "*.json"))
    
    # 过滤掉err文件
    json_files = [f for f in json_files if 'err' not in os.path.basename(f)]
    
    processed_count = 0
    total_files = len(json_files)
    
    # 打开输出文件准备写入（JSON Lines格式）
    with open(output_file, 'w', encoding='utf-8') as out_f:
        # 使用线程池并发处理文件
        with ThreadPoolExecutor(max_workers=min(max_workers, len(json_files))) as executor:
            # 提交所有任务
            future_to_file = {
                executor.submit(process_single_file, file_path, subject): file_path 
                for file_path in json_files
            }
            
            # 处理完成的任务
            for future in tqdm(as_completed(future_to_file), total=total_files, desc="Processing files"):
                file_path = future_to_file[future]
                try:
                    results = future.result()
                    # 写入结果
                    for result_line in results:
                        out_f.write(result_line + "\n")
                    processed_count += 1
                except Exception as e:
                    logging.error(f"处理文件 {file_path} 时出错: {e}")
    
    print(f"\n处理完成！已处理 {processed_count} 个文件。")
    print(f"结果已保存到: {output_file}")
    return processed_count

# 原脚本其他部分保持不变，只修改循环处理部分

if __name__ == "__main__":
    # 保留原脚本的参数和路径设置
    root = sys.argv[1]
    batch = sys.argv[2]
    input_png_dir = f'{root}/{batch}/7_qa_filter_{batch}'
    output_parent_dir = f'{root}/{batch}/8_tidan_filter_{batch}'
    
    # 创建输出目录（无需再创建子文件夹，直接在父目录下生成两个合并文件）
    os.makedirs(output_parent_dir, exist_ok=True)
    
    # 定义两个合并文件的路径
    normal_path = os.path.join(output_parent_dir, f'{batch}_llm_filter可用性检查.json')
    only_q_path = os.path.join(output_parent_dir, f'{batch}only_q_llm_filter可用性检查.json')
    merged_path = os.path.join(output_parent_dir, f'{batch}_llm_filter可用性检查_qa和only_q合并版.json')

    # 初始化三个文件（清空或创建）
    for path in [normal_path, only_q_path, merged_path]:
        with open(path, 'w', encoding='utf-8') as f:
            pass

    # 初始化计数器
    count_normal = 0  # 有答案的
    count_only_q = 0  # 无答案的

    # 获取所有子文件夹
    sub_folders = [d for d in os.listdir(input_png_dir)
                   if os.path.isdir(os.path.join(input_png_dir, d))]

    if not sub_folders:
        print(f"在目录 {input_png_dir} 中未找到子文件夹")
        sys.exit(1)

    print(f"输入目录: {input_png_dir}")
    print(f"输出文件:")
    print(f"  1. qa: {normal_path}")
    print(f"  2. only_q: {only_q_path}")
    print(f"  3. merged: {merged_path}")
    print(f"找到 {len(sub_folders)} 个子文件夹，开始处理...")

    # 根据CPU核心数确定最大并发数
    max_workers = min(len(sub_folders), mp.cpu_count())

    for sub_folder in sub_folders:
        if 'err' in sub_folder:
            continue
            
        subfolder_path = os.path.join(input_png_dir, sub_folder)
        # 生成临时输出文件路径（处理完成后会合并）
        temp_output = os.path.join(output_parent_dir, f'temp_{sub_folder}_llm_filter_{batch.replace(".", "")}.json')
        
        # 调用原处理函数生成单个子文件夹的JSON结果
        processed_count = process_folder(subfolder_path, temp_output, max_workers)
        
        # 判断是否为 only_q 类型
        is_only_q = 'only_q' in sub_folder
        target_path = only_q_path if is_only_q else normal_path

        line_count = 0
        # 读取临时文件并写入对应文件 + 合并文件
        try:
            with open(temp_output, 'r', encoding='utf-8') as temp_f:
                lines = [line for line in temp_f if line.strip()]
        except Exception as e:
            logging.error(f"读取临时文件 {temp_output} 时出错: {e}")
            lines = []

        # 写入对应类型文件
        try:
            with open(target_path, 'a', encoding='utf-8') as type_f:
                for line in lines:
                    type_f.write(line)
        except Exception as e:
            logging.error(f"写入目标文件 {target_path} 时出错: {e}")

        # 写入合并文件
        try:
            with open(merged_path, 'a', encoding='utf-8') as merged_f:
                for line in lines:
                    merged_f.write(line)
        except Exception as e:
            logging.error(f"写入合并文件 {merged_path} 时出错: {e}")

        # 更新计数
        line_count = len(lines)
        if is_only_q:
            count_only_q += line_count
            print(f"✅ [only_q]  {sub_folder} -> {os.path.basename(target_path)} (+{line_count}行)")
        else:
            count_normal += line_count
            print(f"✅ [normal]  {sub_folder} -> {os.path.basename(target_path)} (+{line_count}行)")

        # 删除临时文件
        try:
            os.remove(temp_output)
        except Exception as e:
            logging.error(f"删除临时文件 {temp_output} 时出错: {e}")

    # 最终统计
    total = count_normal + count_only_q
    print("\n" + "="*60)
    print("📊 处理完成！输出三个文件：")
    print(f"   1. 有答案 (normal): {count_normal} 条 -> {os.path.basename(normal_path)}")
    print(f"   2. 没有答案 (only_q): {count_only_q} 条 -> {os.path.basename(only_q_path)}")
    print(f"   3. 合并总计: {total} 条 -> {os.path.basename(merged_path)}")