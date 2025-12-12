import os
import json
import sys
import shutil
import logging
import zipfile  # 压缩所需库
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm
from prompt_loader import *
import threading
from concurrent.futures import ThreadPoolExecutor
import multiprocessing as mp

# 加载第一阶段 prompt（workflow可选 "中高考" 或 "教辅QA"）
current_dir = Path(__file__).parent
config_path = current_dir / "prompts.yaml"
loader = PromptLoader(str(config_path))
ocr_prompt = loader.build_prompt(stage="1_ocr", workflow="教辅QA")

# ================== 新增：目录压缩函数 ==================
def zip_directory(source_dir, zip_output_path):
    """
    将指定目录压缩为ZIP包（优化版本）
    :param source_dir: 待压缩的源目录路径
    :param zip_output_path: 压缩包输出路径（含文件名）
    """
    if not os.path.exists(source_dir):
        logging.error(f"待压缩目录不存在：{source_dir}")
        print(f"待压缩目录不存在：{source_dir}")
        return False
    
    # 使用存储模式（无压缩）来最大化速度
    with zipfile.ZipFile(zip_output_path, 'w', zipfile.ZIP_STORED) as zipf:
        # 收集所有文件路径
        file_paths = []
        for root, _, files in os.walk(source_dir):
            for file in files:
                file_path = os.path.join(root, file)
                file_paths.append((file_path, os.path.relpath(file_path, source_dir)))
        
        # 使用多线程写入文件
        with ThreadPoolExecutor(max_workers=min(len(file_paths), mp.cpu_count())) as executor:
            def write_file(args):
                file_path, arcname = args
                try:
                    zipf.write(file_path, arcname)
                    logging.debug(f"压缩包添加文件：{arcname}")
                    return True
                except Exception as e:
                    logging.error(f"添加文件到压缩包失败：{arcname} → 错误：{str(e)}")
                    return False
            
            # 批量处理文件写入
            results = list(executor.map(write_file, file_paths))
    
    # 验证压缩包有效性
    if os.path.exists(zip_output_path) and os.path.getsize(zip_output_path) > 0:
        zip_size = os.path.getsize(zip_output_path) / 1024 / 1024  # 转MB单位
        logging.info(f"压缩包生成成功：{zip_output_path}（大小：{zip_size:.2f}MB）")
        print(f"\n 压缩包生成成功：{zip_output_path}")
        print(f"压缩包大小：{zip_size:.2f}MB")
        return True
    else:
        logging.error(f"压缩包生成失败或为空：{zip_output_path}")
        print(f" 压缩包生成失败：{zip_output_path}")
        return False

def merge_all_images(src_root, dst_folder, img_extensions=(".png", ".jpg", ".jpeg", ".bmp", ".gif")):
    if not os.path.exists(dst_folder):
        os.makedirs(dst_folder)
    name_count = {}  # 处理重复文件名
    
    # 收集所有文件路径
    file_paths = []
    for root, _, files in os.walk(src_root):
        for file in files:
            if file.lower().endswith(img_extensions):
                src_path = os.path.join(root, file)
                file_paths.append(src_path)
    
    # 使用多线程复制文件
    with ThreadPoolExecutor(max_workers=min(len(file_paths), mp.cpu_count())) as executor:
        def copy_file(src_path):
            try:
                file = os.path.basename(src_path)
                base_name = os.path.splitext(file)[0]
                ext = os.path.splitext(file)[1]
                
                # 重命名重复文件（如 "1.jpg" 重复则改为 "1_1.jpg"）
                new_name = file
                if new_name in name_count:
                    name_count[new_name] += 1
                    new_name = f"{base_name}_{name_count[new_name]}{ext}"
                else:
                    name_count[new_name] = 0

                dst_path = os.path.join(dst_folder, new_name)
                shutil.copy2(src_path, dst_path)  # 保留文件元数据
                return True
            except Exception as e:
                logging.error(f"复制文件失败：{src_path} → 错误：{str(e)}")
                return False
        
        # 批量处理文件复制
        results = list(executor.map(copy_file, file_paths))
    
    print(f" 所有图片已合并至：{dst_folder}")

def extract_section_and_source(test_package_path):
    """从试题包路径提取section（书籍名）和source_type（学段学科）"""
    normalized_path = os.path.normpath(test_package_path)
    path_parts = normalized_path.split(os.sep)
    
    # 提取section：试题包的上级目录（书籍文件夹名）
    try:
        test_package_idx = path_parts.index("试题包")
        section = path_parts[test_package_idx - 1]
    except (ValueError, IndexError):
        raise ValueError(f"路径中未找到'试题包'目录：{test_package_path}")
    
    # 提取source_type：优先取试题包上两级（适配 "图片包/学段学科/书籍/试题包" 结构）
    try:
        test_package_idx = path_parts.index("试题包")
        source_type = path_parts[test_package_idx - 2]  # 原始source_type（仅用于JSON内标识）
    except Exception as e:
        source_type = "unknown_source"
        logging.error(f"未知source_type（路径：{test_package_path}）→ 错误：{str(e)}")
    
    return section, source_type

def get_single_sub_type(url):
    """判断文件路径的sub类型（题目/答案/混合）"""
    lower_url = url.lower().split('/')[-2]
    has_question = ("题目" in lower_url) or ("试题" in lower_url)
    has_answer = "答案" in lower_url
    
    if has_question and not has_answer:
        return "题目"
    elif has_answer and not has_question:
        return "答案"
    else:
        logging.error(f"未知sub_type（路径：{url}）")
        return "题目/答案"

def collect_all_test_package_images(root_dir):
    """遍历根目录，收集所有试题包的JPG图片并分组"""
    if not os.path.exists(root_dir):
        print(f" 根目录不存在：{root_dir}")
        return None
    if not os.path.isdir(root_dir):
        print(f" 根路径不是文件夹：{root_dir}")
        return None
    
    all_image_groups = defaultdict(lambda: {"package_nums": [], "urls": []})
    total_scanned = 0
    processed_test_packages = 0
    
    print(f"开始遍历根目录：{root_dir}（仅识别JPG/JPEG图片）")
    logging.info(f"开始遍历根目录：{root_dir}（仅识别JPG/JPEG图片）")
    print("="*60)
    
    # 遍历书籍文件夹
    for book_folder in os.listdir(root_dir):
        book_folder_path = os.path.join(root_dir, book_folder)
        if not os.path.isdir(book_folder_path):
            continue
        
        # 定位"试题包"目录
        test_package_path = os.path.join(book_folder_path, "试题包")
        if not os.path.exists(test_package_path) or not os.path.isdir(test_package_path):
            logging.error(f"书籍 {book_folder} 下无'试题包'，跳过")
            continue
        
        processed_test_packages += 1
        logging.info(f"[{processed_test_packages}] 处理书籍：{book_folder} → 试题包路径：{test_package_path}")
        
        # 收集试题包下的JPG图片
        for dirpath, _, filenames in os.walk(test_package_path):
            for filename in filenames:
                if filename.lower().endswith((".jpg", ".jpeg")):
                    total_scanned += 1
                    img_abs_path = os.path.join(dirpath, filename)
                    img_filename = filename
                    
                    # 提取图片类型和所属试题包编号
                    sub_type = get_single_sub_type(img_abs_path)
                    rel_dir = os.path.relpath(dirpath, test_package_path)
                    rel_parts = rel_dir.split(os.sep)
                    package_num = rel_parts[0] if (rel_parts and rel_parts[0]) else "root"
                    
                    # 按（书籍名+图片名+类型）分组，避免重复
                    group_key = (book_folder, img_filename, sub_type)
                    all_image_groups[group_key]["package_nums"].append(package_num)
                    all_image_groups[group_key]["urls"].append(img_abs_path)
    
    # 输出遍历统计
    print("\n" + "="*60)
    print(f"遍历完成：共处理 {processed_test_packages} 个试题包")
    print(f"扫描到 {total_scanned} 张JPG/JPEG图片 → 去重后剩余 {len(all_image_groups)} 张")
    logging.info(f"遍历完成：{processed_test_packages} 个试题包，{total_scanned} 张原图 → 去重后 {len(all_image_groups)} 张")
    print("="*60)
    
    return all_image_groups

# 保留原有source_type拼接逻辑（仅用于JSON内标识，不影响路径）
def generate_ocr_json(root_dir, output_jsonl, batch, source):
    """生成OCR任务的JSONL文件"""
    logging.info(f"开始生成JSONL：{root_dir} → 输出：{output_jsonl}")

    # 收集图片数据
    all_image_groups = collect_all_test_package_images(root_dir)
    if not all_image_groups:
        logging.error("无有效图片数据，无法生成JSONL")
        return
    
    # 创建输出目录
    output_dir = os.path.dirname(output_jsonl)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        logging.info(f"创建JSONL输出目录：{output_dir}")
    
    # 生成JSONL
    print(f"\n开始生成JSON数据（输出路径：{output_jsonl}）")
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for (book_folder, img_filename, sub_type) in tqdm(all_image_groups.keys(), desc="生成JSON"):
            try:
                group_data = all_image_groups[(book_folder, img_filename, sub_type)]
                sample_url = group_data["urls"][0]
                section, original_source_type = extract_section_and_source(sample_url)  # 原始source_type
                
                # 拼接处理后的source_type（仅用于JSON内标识，不影响后续路径）
                source_type = f"{batch}_{original_source_type}_{source}"
                
                # 统一图片文件名格式（去除后缀后重新拼接，确保为.jpg）
                name_without_ext = os.path.splitext(img_filename)[0]
                img_path = f"{name_without_ext}.jpg"
                
                # 构建JSON对象（多模多轮格式）
                json_obj = {
                    "query": [
                        ocr_prompt, 
                        "严格对照图片，逐字检查修正ocr文本，并输出最终结果。输出结果必须与图片内容完全一致，仅输出修正后的文本，不要添加任何说明、总结或额外内容。"
                    ],
                    "img_path": [img_path],
                    "id": {
                        "source_type": source_type,  # 处理后的source_type（仅JSON内标识）
                        "section": section,
                        "sub": sub_type,
                        "package_num": sorted(group_data["package_nums"]),
                        "url": sorted(group_data["urls"], key=lambda x: x.split('/')[-3]),  # 按目录排序路径
                        "total_images": "1",
                        "all_image_paths": [img_path]
                    }
                }
                
                # 写入JSONL（禁用ASCII转义，保留中文）
                f.write(json.dumps(json_obj, ensure_ascii=False) + "\n")
            
            except Exception as e:
                err_msg = str(e)[:80] + "..." if len(str(e)) > 80 else str(e)
                logging.error(f"处理失败：书籍={book_folder}，文件名={img_filename} → 错误：{err_msg}")
    
    # 输出生成结果
    json_count = len(all_image_groups)
    print(f"\nJSONL生成完成！输出路径：{os.path.abspath(output_jsonl)}")
    print(f" 共生成 {json_count} 条JSON记录（均为JPG格式）")
    logging.info(f"JSONL生成完成：{os.path.abspath(output_jsonl)} → {json_count} 条记录")

def process_subfolder(args):
    """处理单个子文件夹的任务函数"""
    root, batch, source, sub_folder, input_png_dir, output_dir = args
    
    print(f"\n" + "="*60)
    print(f" 正在处理子文件夹：{sub_folder}")
    logging.info(f"处理子文件夹：{sub_folder}")
    
    # 子文件夹路径配置
    subfolder_png_path = os.path.join(input_png_dir, sub_folder)
    output_subfolder = os.path.join(output_dir, sub_folder)
    os.makedirs(output_subfolder, exist_ok=True)
    
    # 合并图片到子文件夹下的"TOTAL_pic"目录
    merge_all_images(subfolder_png_path, os.path.join(output_subfolder, "TOTAL_pic"))
    # 生成JSON（仍传入batch和source，用于JSON内标识）
    generate_ocr_json(subfolder_png_path, os.path.join(output_subfolder, f"{sub_folder}.json"), batch, source)
    
    return sub_folder

if __name__ == "__main__":
    # 命令行参数检查（共6个参数：root、batch、date、name、model、source）
    if len(sys.argv) != 7:
        print("用法: python script.py <root目录> <batch名称> <日期> <名称> <model> <source>")
        print("示例: python script.py /DL_data_new/ftpdata/jjhu32/code 8.18重新传输文件-22 20251016 胡佳驹 model1 source1")
        sys.exit(1)
    
    # 解析命令行参数
    root = sys.argv[1]
    batch = sys.argv[2]
    date = sys.argv[3]
    name = sys.argv[4]
    model = sys.argv[5]
    source = sys.argv[6]  # source参数
    merge = 1  # 是否合并JSON文件（1=合并，0=不合并）
    w_size = 1
    s_size = 1
    
    # 核心路径配置
    input_png_dir = f"{root}/{batch}/0_raw_png_{batch}"  # 原始PNG目录（源文件夹所在目录）
    output_dir = f"{root}/{batch}/{name}_{batch.replace('.','')}_{model}_认知基础-SFT"  # 结果目录
    zip_output_path = f"{output_dir}.zip"  # 压缩包路径（与结果目录同级）
    os.makedirs(output_dir, exist_ok=True)  # 创建结果目录
    
    # 日志配置（写入结果目录的"日志.log"）
    err_log = f"{output_dir}/日志.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=err_log,
        filemode='w',  # 覆盖写入日志（如需追加改为'a'）
        encoding="utf-8"
    )
    
    # 获取原始PNG目录下的子文件夹（源文件夹名，即原始source_type）
    sub_folders = [d for d in os.listdir(input_png_dir) if os.path.isdir(os.path.join(input_png_dir, d))]
    if not sub_folders:
        print(f" 在目录 {input_png_dir} 中未找到子文件夹")
        logging.error(f"无可用子文件夹：{input_png_dir}")
        sys.exit(1)
    
    # 输出任务基本信息
    print("="*80)
    print(f" 任务信息")
    print(f"输入PNG目录：{input_png_dir}")
    print(f"结果输出目录：{output_dir}")
    print(f"压缩包输出路径：{zip_output_path}")
    print(f"待处理子文件夹数量：{len(sub_folders)}")
    print(f"source参数值：{source}")
    print("="*80)
    logging.info(f"任务启动：输入={input_png_dir}，输出={output_dir}，子文件夹={len(sub_folders)}，source={source}")

    # 1. 并行处理每个子文件夹（图片合并 + 单文件夹JSON生成）
    with ThreadPoolExecutor(max_workers=min(len(sub_folders), mp.cpu_count())) as executor:
        # 准备任务参数
        tasks = [(root, batch, source, sub_folder, input_png_dir, output_dir) for sub_folder in sub_folders]
        # 并行处理所有子文件夹
        results = list(tqdm(executor.map(process_subfolder, tasks), total=len(sub_folders), desc="处理子文件夹"))

    # 2. 合并所有子文件夹的JSON文件，并删除源JSON
    if merge:
        print(f"\n" + "="*60)
        print(f" 开始合并JSON文件...")
        logging.info("开始合并所有子文件夹的JSON文件")
        
        # 收集所有源JSON文件路径
        original_tidan_file_list = [
            os.path.join(output_dir, sub_folder, f"{sub_folder}.json")
            for sub_folder in sub_folders
            if os.path.exists(os.path.join(output_dir, sub_folder, f"{sub_folder}.json"))
        ]
        # 合并后的JSON文件路径（与结果目录同级）
        merge_tidan_file = f"{output_dir}.json"
        
        # 写入合并后的JSON（核心修改：用源文件夹名替换处理后的source_type）
        with open(merge_tidan_file, "w", encoding="utf-8") as merge_file:
            for original_file_path in original_tidan_file_list:
                if not os.path.exists(original_file_path):
                    logging.warning(f"源JSON文件不存在，跳过：{original_file_path}")
                    continue
                
                # 【核心修改1：从源JSON文件路径中解析出"源文件夹名"（原始source_type）】
                # 源JSON路径格式：output_dir/源文件夹名/源文件夹名.json → 取"源文件夹名"层级
                src_folder = os.path.basename(os.path.dirname(original_file_path))
                
                with open(original_file_path, "r", encoding="utf-8") as original_file:
                    for line in original_file:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            # 修正img_path：使用源文件夹名（原始source_type），而非处理后的source_type
                            zip_root_dir = os.path.basename(output_dir)
                            # 去除日期
                            # new_img_path = [
                            #     os.path.join(zip_root_dir, src_folder, "TOTAL_pic", img_path)
                            #     for img_path in data["img_path"]
                            # ]
                            # 保留日期
                            new_img_path = [
                                os.path.join(date, zip_root_dir, src_folder, "TOTAL_pic", img_path)
                                for img_path in data["img_path"]
                            ]
                            # 保持多模多轮格式
                            data["img_path"] = [new_img_path, []]
                            merge_file.write(json.dumps(data, ensure_ascii=False) + "\n")
                        except Exception as e:
                            logging.error(f"合并JSON行失败（文件：{original_file_path}）→ 错误：{str(e)}")
                            continue
        
        # 合并成功后，删除源JSON文件
        if os.path.exists(merge_tidan_file) and os.path.getsize(merge_tidan_file) > 0:
            print(f"\n 开始删除源JSON文件...")
            logging.info("合并成功，开始删除源JSON文件")
            for original_file_path in original_tidan_file_list:
                if os.path.exists(original_file_path):
                    try:
                        os.remove(original_file_path)
                        print(f"已删除：{os.path.relpath(original_file_path, root)}")
                        logging.info(f"删除源JSON文件：{original_file_path}")
                    except Exception as e:
                        print(f"删除失败：{os.path.relpath(original_file_path, root)} → 错误：{str(e)}")
                        logging.error(f"删除源JSON文件失败：{original_file_path} → 错误：{str(e)}")
                else:
                    print(f"跳过不存在的文件：{os.path.relpath(original_file_path, root)}")
        else:
            print(f"\n 合并文件不存在或为空，不执行删除操作")
            logging.warning("合并文件无效，不删除源JSON文件")

    # 3. 执行目录压缩（所有文件处理完成后）
    print(f"\n" + "="*60)
    print(f"开始压缩结果目录...")
    logging.info(f"开始压缩目录：{output_dir} → 压缩包：{zip_output_path}")
    zip_success = zip_directory(output_dir, zip_output_path)

    # 4. 输出最终任务总结
    print(f"\n" + "="*80)
    print(f"任务最终状态")
    print(f"原始结果目录：{output_dir}")
    print(f"合并JSON文件：{merge_tidan_file if merge else '未启用合并'}")
    print(f"压缩包状态：{'成功' if zip_success else '失败'}")
    print(f"日志文件路径：{err_log}")
    print(f"new_img_path使用的source_type：源文件夹原始名称（如 {sub_folders[0]} 等）")  # 提示路径使用的source_type类型
    print("="*80)
    logging.info(f"任务结束：压缩包状态={'成功' if zip_success else '失败'}，日志路径={err_log}，new_img_path使用源文件夹原始名称")