#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import subprocess
import sys

def run_qa_extraction_dedup_filter(root, batch, source):
    """执行qa提取、去重和过滤步骤"""
    print("=================step.4 qa提取==================")
    
    if source == "教辅QA":
        # 教辅QA场景使用专用脚本
        script_path = "/DL_data_new/ftpdata/wjcui/code/教辅/tools/4_model_res_qa_process_edu.py"
    else:
        # 其他场景使用原脚本
        script_path = "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/4_model_res_qa_process.py"
    
    try:
        result = subprocess.run(["python", script_path, root, batch], check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"QA提取步骤出错: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    
    print("=================step.5 去重及脚本过滤==================")
    
    if source == "教辅QA":
        # 教辅QA场景使用专用脚本
        script_path = "/DL_data_new/ftpdata/wjcui/code/教辅/tools/5_qa_dedup_optim_edu.py"
    else:
        # 其他场景使用原脚本
        script_path = "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/5_qa_dedup_optim.py"
    
    try:
        result = subprocess.run(["python", script_path, root, batch], check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"去重及脚本过滤步骤出错: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    
    print("=================step.6 二轮过滤提单==================")
    
    if source == "教辅QA":
        # 教辅QA场景使用专用脚本
        script_path = "/DL_data_new/ftpdata/wjcui/code/教辅/tools/6_llm_filter_tidan_edu.py"
    else:
        # 其他场景使用原脚本
        script_path = "/DL_data_new/ftpdata/wjcui/code/教辅/tools/6_llm_filter_tidan.py"
    
    try:
        result = subprocess.run(["python", script_path, root, batch], check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"二轮过滤提单步骤出错: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    
    return True

def merge_json_files(input_dir, output_file):
    """合并JSON文件"""
    print("=================step.7 合并JSON文件==================")
    
    merged_data = []

    # 获取文件夹中所有json文件，按文件名排序
    json_files = sorted(
        [f for f in os.listdir(input_dir) if f.endswith(".json")]
    )

    for file_name in json_files:
        file_path = os.path.join(input_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        merged_data.append(obj)
                    except json.JSONDecodeError as e:
                        print(f"跳过无效JSON行：{file_name} 中的行 => {line}")
        except Exception as e:
            print(f"读取文件 {file_name} 时出错: {e}")

    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    try:
        with open(output_file, 'w', encoding='utf-8') as out_f:  # 使用'w'模式确保每次都是全新写入
            for obj in merged_data:
                json_line = json.dumps(obj, ensure_ascii=False)
                out_f.write(json_line + '\n')

        print(f"合并完成，共合并 {len(json_files)} 个文件，输出行数为 {len(merged_data)} 行")
    except Exception as e:
        print(f"写入输出文件时出错: {e}")
        return False
    
    return True

def main():
    # 设置参数
    batch = '1128-单模文件提交-239本'
    root = '/DL_data_new/ftpdata/wjcui/code/教辅'
    source = '教辅QA'  # 教辅QA、中高考、竞赛
    
    print(f"当前batch参数值：[{batch}]")
    
    # 执行qa提取、去重和过滤步骤
    if not run_qa_extraction_dedup_filter(root, batch, source):
        print("qa提取、去重和过滤处理失败，终止程序")
        sys.exit(1)
    
    # 执行数据合并步骤
    input_dir = f'{root}/{batch}/8_tidan_filter_{batch}'
    output_file = f'{root}/{batch}/8_tidan_filter_{batch}/全学科_可用性检查_{batch}.json'
    
    if not merge_json_files(input_dir=input_dir, output_file=output_file):
        print("JSON文件合并失败，终止程序")
        sys.exit(1)

if __name__ == "__main__":
    main()

