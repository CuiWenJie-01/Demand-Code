#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import subprocess
import sys

def run_ocr_processing(root, batch, source):
    """执行OCR处理步骤"""
    print("=================step.2 ocr结果处理==================")
    
    if source == "教辅QA":
        # 教辅QA场景使用专用脚本
        script_path = "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/2_model_res_ocr_process_edu.py"
    else:
        # 其他场景使用原脚本
        script_path = "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/2_model_res_ocr_process.py"
    
    try:
        result = subprocess.run(["python", script_path, root, batch], check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"OCR处理步骤出错: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    
    return True

def run_tidan_generation(root, batch, source):
    """执行提单文件生成步骤"""
    print("=================step.3 生成提单文件==================")
    
    if source == "教辅QA":
        # 教辅QA场景使用专用脚本
        script_path = "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/3_tidan_qa_edu.py"
    else:
        # 其他场景使用原脚本
        script_path = "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/3_tidan_qa.py"
    
    try:
        result = subprocess.run(["python", script_path, root, batch], check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"提单生成步骤出错: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    
    return True

def merge_json_files(input_dir, output_file):
    """合并JSON文件"""
    merged_data = []

    # 获取文件夹中所有json文件，按文件名排序
    json_files = sorted(
        [f for f in os.listdir(input_dir) if f.endswith(".json")]
    )

    for file_name in json_files:
        file_path = os.path.join(input_dir, file_name)
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

    with open(output_file, 'w', encoding='utf-8') as out_f:  # 使用'w'模式而不是'a'模式确保每次都是全新写入
        for obj in merged_data:
            json_line = json.dumps(obj, ensure_ascii=False)
            out_f.write(json_line + '\n')

    print(f"合并完成，共合并 {len(json_files)} 个文件，输出行数为 {len(merged_data)} 行")

def main():
    # 设置参数
    batch = '1128-单模文件提交-239本'
    root = '/DL_data_new/ftpdata/wjcui/code/教辅'
    source = '教辅QA'  # 教辅QA、中高考、竞赛
    
    print(f"当前batch参数值：[{batch}]")
    
    # 执行OCR处理步骤
    if not run_ocr_processing(root, batch, source):
        print("OCR处理失败，终止程序")
        sys.exit(1)
    
    # 执行提单文件生成步骤
    if not run_tidan_generation(root, batch, source):
        print("提单文件生成失败，终止程序")
        sys.exit(1)
    
    # 执行数据合并步骤
    input_dir = f'{root}/{batch}/4_tidan_qa_{batch}'
    output_file = f'{root}/{batch}/4_tidan_qa_{batch}/全学科_提取qa_{batch}.json'
    
    print("=================step.4 合并JSON文件==================")
    merge_json_files(input_dir=input_dir, output_file=output_file)

if __name__ == "__main__":
    main()
