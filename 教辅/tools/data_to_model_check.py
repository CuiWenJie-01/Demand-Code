import logging
import os
import sys
import json
import shutil
import zipfile
from tqdm import tqdm

# -------------------------- 命令行参数解析（更新为8个参数） --------------------------
# 接收Shell脚本传递的8个参数，顺序对应：
# 1. file_path (shell中的$file_path)
# 2. output_path1 (model1的输出文件夹)
# 3. output_path2 (model2的输出文件夹)
# 4. name (shell中的$name)
# 5. model1 (第一个模型名称)
# 6. model2 (第二个模型名称)
# 7. batch (shell中的$batch)
# 8. root (shell中的$root)
if len(sys.argv) != 9:
    print("错误：参数数量不正确！")
    print("正确用法：python script.py <file_path> <output_path1> <output_path2> <name> <model1> <model2> <batch> <root>")
    print("示例：python data_to_model_check.py /DL/xxx/14_select_check_xxx /DL/xxx/out1 /DL/xxx/out2 胡佳驹 gemini2.5-pro-多模 qwen3-vl-235b 10.9提交文件-290本 /DL/xxx/切题链路合并")
    sys.exit(1)

# 解析命令行参数
FILE_PATH = sys.argv[1]       # 输入目录（JSON文件来源）
OUTPUT_PATH1 = sys.argv[2]    # model1的输出文件夹
OUTPUT_PATH2 = sys.argv[3]    # model2的输出文件夹
NAME = sys.argv[4]            # 执行人名称
MODEL1 = sys.argv[5]          # 第一个模型名称
MODEL2 = sys.argv[6]          # 第二个模型名称
BATCH = sys.argv[7]           # 批次名称
ROOT = sys.argv[8]            # 根目录

# -------------------------- 动态生成双model核心路径 --------------------------
INPUT_DIR = FILE_PATH  # 输入目录=file_path（两个model共用同一输入）
BASE_IMG_DIR = os.path.join(ROOT, BATCH)  # 图片基准目录=root/batch（共用）

# ========== Model1 路径配置 ==========
FINAL_OUTPUT_JSON_NAME1 = f"{NAME}_{BATCH}_单轮自动化质检_{MODEL1}_认知基础-SFT.json"
FINAL_OUTPUT_JSON_PATH1 = os.path.join(OUTPUT_PATH1, FINAL_OUTPUT_JSON_NAME1)
DEST_IMG_FOLDER1 = os.path.splitext(FINAL_OUTPUT_JSON_PATH1)[0]  # model1图片文件夹（与JSON同名）
ZIP_FILE_PATH1 = f"{DEST_IMG_FOLDER1}.zip"  # model1图片压缩包

# ========== Model2 路径配置 ==========
FINAL_OUTPUT_JSON_NAME2 = f"{NAME}_{BATCH}_单轮自动化质检_{MODEL2}_认知基础-SFT.json"
FINAL_OUTPUT_JSON_PATH2 = os.path.join(OUTPUT_PATH2, FINAL_OUTPUT_JSON_NAME2)
DEST_IMG_FOLDER2 = os.path.splitext(FINAL_OUTPUT_JSON_PATH2)[0]  # model2图片文件夹（与JSON同名）
ZIP_FILE_PATH2 = f"{DEST_IMG_FOLDER2}.zip"  # model2图片压缩包

# -------------------------------------------------------------------------

# 统一使用的题目一致性判定prompt（保持不变）
UNIFIED_PROMPT = (
"你收到一组图片，以及一道从这些图片中抽取的题目。多数情况下，一道题目位于单张图片，但也可能会跨图片出现，需要准确定位。\n"
"提供的题目里肯定有错误或者跟图片有差异，你需要根据图片，检查提供的题目，判断题目和图片一致性，最终按输出格式要求输出判断结果。\n"
"\n"
"## 按照以下步骤一步步执行：\n"
"Step1. 在一组图片中找到提供的题目对应的原始出处。\n"
"Step2. 对图片中展示的这道题目，检查上下文，看是否有关联的背景知识。\n"
"Step3. 以图片为准，将提供的题目和图片中展示的完整题目进行仔细对比，找出所有差异的地方。\n"
"Step4. 根据差异的地方，判断提供的题目和图片中展示的完整题目是否一致，并给出详细判断理由。\n"
"\n"
"## 每一步的注意事项\n"
"\n"
"### 找出提供的题目在图片中的位置\n"
"1. 图片是按顺序提供的，判断题目在几张图片，可能会跨图片出现，例如\"【题目在第几张图片】: 2, 3\"，如果未找到，【题目在第几张图片】中输出\"0 \"。\n"
"2. 若存在下面任何一种情况，直接判定【题目和图片是否一致】为“否”，在判断理由中详细说明。\n"
"  - 在所有提供的图片中均无法找到与提供的题目内容匹配的题目\n"
"  - 题目内容明显被截断（如出现在图片边缘且不完整），且后续图片无延续\n"
"  - 题目内容严重变形或无法识别（如大面积遮挡、模糊）\n"
"\n"
"### 检查图片中展示的上下文\n"
"1. 背景知识是指阅读材料、图表、案例描述等，被一个或多个连续子题共用。例如提供的题目中要求“结合材料作答”“对文中划线句子怎么理解”等，必定存在对应的背景知识。\n"
"2. 如果图片中存在背景知识，提供的题目属于引用背景知识的子题之一，但提供的题目没有这段背景知识，判定【共享题干是否缺失】为“是”，直接判定【题目和图片是否一致】为“否”。\n"
"3. 如果没有背景知识，提供的题目提问意图清晰，单看题目就可以作答，判定【共享题干是否缺失】为“否”。\n"
"4. 如果不存在背景知识，图片中展示的完整题目就对应了<提供的题目>；如果存在背景知识，图片中展示的完整题目就对应了<背景知识+提供的题目>。\n"
"\n"
"### 找出提供的题目中存在的差异和错误\n"
"1. 文字：对照图片展示的完整题目，逐字核对提供的题目。\n"
"2. 强调标记：对照图片展示的完整题目，逐个核对提供的题目中文字下方的横线、波浪线、加点等特殊标记的位置。\n"
"3. 插图：提供的题目中使用的插图会统一用<fig>（描述性文本）</fig>格式表示，不需要核对插图。\n"
"4. 表：对照图片展示的完整题目，核对提供的题目中的表格格式、文字内容。\n"
"5. 核对完成后，把全部有差异的地方输出到【题目和图片的差异】。\n"
"\n"
"### 判断一致性原则\n"
"1.根据【题目和图片的差异】，进行一致性的判断，并输出理由到【详细判断理由】。\n"
"2. **需要仔细对比的情况**：\n"
"  - 错别字、缺漏字句是否影响题目意图、是否影响题目解答；\n"
"  - 解答题目需要的横线、波浪线、加点字等特殊标记是否在正确的位置，例如题目要求填空但提供的题目中没有填空的位置，会影响解答。\n"
"3. 决定一致性判断的情况：\n"
"  - 文字增删导致语义变化、知识性术语错误（如“不正确的是”变成“正确的是”）；\n"
"  - 用于提示答题重点的关键字句的加点/加粗/下划线缺失（如要求解释加点字的意思，但没有标记加点字的位置）；\n"
"  - 选择题缺少选项，选项内容空白；\n"
"  - 存在上述任何一种情况，直接判定【题目和图片是否一致】为”否“。\n"
"4. 不影响一致性的判断的情况：\n"
"  - 提供的题目缺少题目编号；\n"
"  - 多字、漏字但未影响题意，例如多了一个“的”字，判断题添加了“判断题：”前缀等；\n"
"  - 横线、波浪线、加点字等特殊标记使用了下划线表示，但都在正确的位置；\n"
"  - 横线、波浪线、加点字等细节与题目解答无关，未影响题意；\n"
"  - 大段长文本中存在局部缺漏字句，但未影响整体题意和题目作答；\n"
"  - latex字符渲染方式、标点符号、有无空格或者空格长度不同等轻微差异；\n"
"  - 只存在上述的差异，未影响最终题意，判定【题目和图片是否一致】为”是“。\n"
"\n"
"## 最终输出格式要求：\n"
"【题目在第几张图片】: int, 【共享题干是否缺失】: 是/否, 【题目和图片的差异】: str,【题目和图片是否一致】：是/否, 【详细判断理由】: str\n"
"\n"
"**重要提示**：\n"
"图片中展示的字词有可能会违反你的知识惯性，**杜绝受常识或认知惯性影响**，严格按照图片中展示的完整题目的内容为准。\n"
"提供的题目里**肯定有错误或者跟图片有差异**，不会完全一致，80%的差异都在文字内容上。\n"
"有差异不一定会影响一致性，根据**判断一致性原则**进行判断。\n"
"\n"
"按照给出的步骤一步步执行，严格按照最终输出格式要求给出回复。\n"
"\n"
"提供的题目：\n"
"{query}"
)

def safe_strip(value):
    """安全处理strip()，兼容字符串和非字符串类型"""
    if isinstance(value, str):
        return value.strip()
    elif isinstance(value, list):
        str_elements = [str(item).strip() for item in value if isinstance(item, (str, int, float))]
        return " ".join(str_elements).strip()
    else:
        return str(value).strip() if value is not None else ""

def extract_qa_text(entry):
    """提取题目内容（适配单题型和多题型）"""
    q_text = ""
    if "sub_qa" in entry and isinstance(entry["sub_qa"], list):
        q_parts = []
        bg = entry.get("题目背景知识", "无")
        cleaned_bg = safe_strip(bg)
        if cleaned_bg and cleaned_bg != "无":
            q_parts.append(cleaned_bg)
        for qa in entry["sub_qa"]:
            ques = qa.get("题目内容", "")
            cleaned_ques = safe_strip(ques)
            if cleaned_ques:
                q_parts.append(cleaned_ques)
        q_text = "\n".join(filter(None, q_parts))
    else:
        ques = entry.get("题目内容", "")
        cleaned_ques = safe_strip(ques)
        if cleaned_ques and cleaned_ques[0].isdigit() and (cleaned_ques[1] == "." or cleaned_ques[1] == "、"):
            cleaned_ques = cleaned_ques[2:].strip()
        q_text = cleaned_ques
    return q_text

def get_relevant_img_paths(all_img_paths, target_index):
    """根据目标索引获取前后各2张图片路径（共5张，越界则取存在的）"""
    if not isinstance(target_index, int) or target_index < 0 or target_index >= len(all_img_paths):
        return []
    start_idx = max(0, target_index - 2)
    end_idx = min(len(all_img_paths) - 1, target_index + 2)
    return [all_img_paths[i] for i in range(start_idx, end_idx + 1)]

def collect_json_files(input_dir):
    """收集输入目录下所有JSON文件（不递归子文件夹）"""
    json_files = []
    for file_name in os.listdir(input_dir):
        file_path = os.path.join(input_dir, file_name)
        if os.path.isfile(file_path) and file_name.lower().endswith(".json"):
            json_files.append(file_path)
    return json_files

def process_first_script(input_dir):
    """第一个脚本的核心逻辑：处理输入目录的JSON文件，返回处理后的JSON行列表（双model共用同一处理结果）"""
    # 检查输入目录
    if not os.path.exists(input_dir):
        print(f"错误：输入目录不存在 → {input_dir}")
        sys.exit(1)
    
    # 收集JSON文件
    json_files = collect_json_files(input_dir)
    if not json_files:
        print(f"错误：输入目录 {input_dir} 下未找到JSON文件")
        sys.exit(1)
    
    print(f"找到 {len(json_files)} 个JSON文件，开始批量处理（第一步：生成质检任务，双model共用）...")
    
    # 统计总行数
    total_valid_lines = 0
    print("正在统计所有文件的有效数据行数...")
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                total_valid_lines += len(lines)
        except Exception as e:
            print(f"警告：统计文件 {os.path.basename(file_path)} 时出错 → {str(e)[:100]}，跳过该文件")
    
    print(f"\n统计完成：共 {len(json_files)} 个JSON文件，预计处理 {total_valid_lines} 条有效数据")
    print("="*60)
    
    # 处理所有文件，生成JSON行列表
    processed_json_lines = []
    processed_lines = 0
    
    with tqdm(total=total_valid_lines, desc="第一步：生成质检任务进度") as global_pbar:
        for file_idx, file_path in enumerate(json_files, 1):
            file_name = os.path.basename(file_path)
            print(f"\n正在处理文件 {file_idx}/{len(json_files)}：{file_name}")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as in_f:
                    lines = in_f.readlines()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            data = json.loads(line)
                            # 提取题目文本
                            q_text = extract_qa_text(data)
                            full_prompt = UNIFIED_PROMPT.format(query=q_text)
                            
                            # 构建id_info
                            id_info = {
                                "original_data": data,
                                "source_type": safe_strip(data.get("source_type", "")),
                                "section": safe_strip(data.get("section", "")),
                                "url": safe_strip(data.get("url", "")),
                                "img_path": data.get("img_path", [])
                            }
                            
                            # 处理图片路径
                            all_img_paths = data.get("img_path", [])
                            merged_img_paths = []
                            
                            if "sub_qa" in data and isinstance(data["sub_qa"], list):
                                temp_paths = []
                                for sub_qa in data["sub_qa"]:
                                    sub_target_page = sub_qa.get("题目位于第几张图片", 0)
                                    try:
                                        sub_target_index = int(sub_target_page) - 1
                                    except (ValueError, TypeError):
                                        sub_target_index = -1
                                    sub_relevant_paths = get_relevant_img_paths(all_img_paths, sub_target_index)
                                    temp_paths.extend(sub_relevant_paths)
                                # 去重
                                seen = set()
                                for path in temp_paths:
                                    if path not in seen:
                                        seen.add(path)
                                        merged_img_paths.append(path)
                            else:
                                target_page = data.get("题目位于第几张图片", 0)
                                try:
                                    target_index = int(target_page) - 1
                                except (ValueError, TypeError):
                                    target_index = -1
                                merged_img_paths = get_relevant_img_paths(all_img_paths, target_index)
                            
                            # 构建输出对象（双model共用同一对象结构，仅后续输出路径不同）
                            output_obj = {
                                "query": full_prompt,
                                "id": id_info,
                                "img_path": merged_img_paths
                            }
                            
                            processed_json_lines.append(output_obj)
                            processed_lines += 1
                            global_pbar.update(1)
                            
                        except Exception as e:
                            logging.error(f"文件 {file_name} 处理数据行时出错 → {str(e)[:100]}，数据片段：{line[:200]}")
                            continue
            except Exception as e:
                print(f"警告：读取文件 {file_name} 时出错 → {str(e)[:100]}，跳过该文件")
                continue
    
    print("\n" + "="*60)
    print("第一步处理完成！")
    print(f"处理文件总数：{len(json_files)} 个")
    print(f"生成质检任务数：{processed_lines} 条（双model共用）")
    print("="*60)
    
    return processed_json_lines

def get_absolute_path(relative_path, base_dir):
    """将相对路径转换为绝对路径（如果已是绝对路径则直接返回）"""
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.abspath(os.path.join(base_dir, relative_path))

def extract_image_paths_from_json(json_lines, base_img_dir):
    """从JSON行中提取图片路径（处理相对路径，去重）"""
    image_abs_paths = set()
    
    print("\n开始提取图片路径（第二步：准备复制图片，双model共用同一图片集）...")
    for data in tqdm(json_lines, desc="提取图片路径"):
        try:
            if "img_path" in data and isinstance(data["img_path"], list):
                for img_path in data["img_path"]:
                    if isinstance(img_path, str) and img_path.strip():
                        path = img_path.strip()
                        abs_path = get_absolute_path(path, base_img_dir)
                        image_abs_paths.add(abs_path)
        except Exception as e:
            print(f"警告：提取图片路径时出错 → {str(e)[:100]}，跳过该记录")
            continue
    
    print(f"\n从JSON中提取到 {len(image_abs_paths)} 个不重复的图片绝对路径")
    return image_abs_paths

def copy_unique_images(image_abs_paths, dest_folder, model_name):
    """复制去重后的图片到指定文件夹（适配双model分别输出）"""
    os.makedirs(dest_folder, exist_ok=True)
    success_paths = set()
    missing_paths = []
    
    print(f"\n开始复制图片（{model_name} - 第二步：复制图片到目标文件夹）...")
    for abs_path in tqdm(image_abs_paths, desc=f"{model_name} 复制图片进度"):
        if not os.path.exists(abs_path):
            missing_paths.append(abs_path)
            continue
        
        filename = os.path.basename(abs_path)
        dest_path = os.path.join(dest_folder, filename)
        
        if os.path.exists(dest_path):
            success_paths.add(abs_path)
            continue
        
        try:
            shutil.copy2(abs_path, dest_path)
            success_paths.add(abs_path)
        except Exception as e:
            print(f"警告：{model_name} 复制图片 {abs_path} 时出错 - {str(e)}，跳过该文件")
            missing_paths.append(abs_path)
    
    print(f"\n=== {model_name} 图片复制完成 ===")
    print(f"成功复制/已存在：{len(success_paths)} 张图片")
    print(f"未找到或复制失败：{len(missing_paths)} 张图片")
    
    if missing_paths:
        missing_record_path = os.path.join(dest_folder, "missing_images.txt")
        with open(missing_record_path, 'w', encoding='utf-8') as f:
            f.write(f"{model_name} - 未找到或复制失败的图片绝对路径：\n")
            for idx, path in enumerate(missing_paths, 1):
                f.write(f"{idx}. {path}\n")
        print(f"未找到的路径已保存至：{missing_record_path}")
    
    return success_paths

def compress_image_folder(folder_path, zip_path, model_name):
    """压缩图片文件夹为zip包（适配双model分别压缩）"""
    if not os.path.exists(folder_path):
        print(f"警告：{model_name} 图片文件夹不存在，跳过压缩 → {folder_path}")
        return False
    
    # 获取文件夹内所有文件（不递归子文件夹）
    image_files = []
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if os.path.isfile(file_path):
            image_files.append((file_path, file_name))
    
    if not image_files:
        print(f"警告：{model_name} 图片文件夹内无文件，跳过压缩")
        return False
    
    print(f"\n开始压缩图片文件夹（{model_name} - 共 {len(image_files)} 个文件）...")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            for file_path, arcname in tqdm(image_files, desc=f"{model_name} 压缩进度"):
                zipf.write(file_path, arcname=arcname)
        
        zip_size = os.path.getsize(zip_path) / (1024 * 1024)
        print(f"{model_name} 压缩完成！")
        print(f"压缩包路径：{os.path.abspath(zip_path)}")
        print(f"压缩包大小：{zip_size:.2f} MB")
        return True
    except Exception as e:
        print(f"{model_name} 压缩图片文件夹时出错 → {str(e)}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False

def update_json_img_paths(json_lines, dest_folder, output_json_path, model_name):
    """更新JSON中的img_path并保存（适配双model分别输出）"""
    dest_folder_name = os.path.basename(os.path.normpath(dest_folder))
    updated_lines = []
    
    print(f"\n开始更新JSON中的图片路径（{model_name} - 第二步：生成最终文件）...")
    for data in tqdm(json_lines, desc=f"{model_name} 更新JSON进度"):
        if "img_path" in data and isinstance(data["img_path"], list):
            updated_img_paths = []
            for img_path in data["img_path"]:
                if isinstance(img_path, str) and img_path.strip():
                    filename = os.path.basename(img_path.strip())
                    new_path = f"{dest_folder_name}/{filename}"
                    updated_img_paths.append(new_path)
            data["img_path"] = updated_img_paths
        updated_lines.append(json.dumps(data, ensure_ascii=False))
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_json_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    with open(output_json_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(updated_lines) + "\n")
    
    print(f"\n{model_name} 最终JSON文件已保存至：{os.path.abspath(output_json_path)}")

def main():
    # 打印双model关键路径信息
    
    print(f"\n【关键路径信息】")
    print(f"Model1 - 提单JSON：{FINAL_OUTPUT_JSON_PATH1}")
    print(f"Model1 - 图片文件夹：{DEST_IMG_FOLDER1}")
    print(f"Model1 - 图片压缩包：{ZIP_FILE_PATH1}")
    print(f"Model2 - 提单JSON：{FINAL_OUTPUT_JSON_PATH2}")
    print(f"Model2 - 图片文件夹：{DEST_IMG_FOLDER2}")
    print(f"Model2 - 图片压缩包：{ZIP_FILE_PATH2}")
    print(f"图片基准目录：{BASE_IMG_DIR}")
    print("="*80)
    
    # 第一步：生成质检任务（双model共用同一结果）
    processed_json_lines = process_first_script(INPUT_DIR)
    if not processed_json_lines:
        print("没有生成任何质检任务，终止后续流程")
        sys.exit(1)
    
    # 第二步：提取图片路径（双model共用同一图片集）
    image_abs_paths = extract_image_paths_from_json(processed_json_lines, BASE_IMG_DIR)
    
    print("\n" + "="*80)
    print(f"开始处理 {MODEL1} 输出文件")
    print("="*80)
    success_paths1 = set()
    if image_abs_paths:
        success_paths1 = copy_unique_images(image_abs_paths, DEST_IMG_FOLDER1, MODEL1)
    else:
        print(f"{MODEL1} 未提取到任何图片路径，无需复制图片")
    update_json_img_paths(processed_json_lines, DEST_IMG_FOLDER1, FINAL_OUTPUT_JSON_PATH1, MODEL1)
    if success_paths1:
        compress_image_folder(DEST_IMG_FOLDER1, ZIP_FILE_PATH1, MODEL1)
    else:
        print(f"\n{MODEL1} 无成功复制的图片，跳过压缩步骤")
    
    print("\n" + "="*80)
    print(f"开始处理 {MODEL2} 输出文件")
    print("="*80)
    success_paths2 = set()
    if image_abs_paths:
        success_paths2 = copy_unique_images(image_abs_paths, DEST_IMG_FOLDER2, MODEL2)
    else:
        print(f"{MODEL2} 未提取到任何图片路径，无需复制图片")
    update_json_img_paths(processed_json_lines, DEST_IMG_FOLDER2, FINAL_OUTPUT_JSON_PATH2, MODEL2)
    if success_paths2:
        compress_image_folder(DEST_IMG_FOLDER2, ZIP_FILE_PATH2, MODEL2)
    else:
        print(f"\n{MODEL2} 无成功复制的图片，跳过压缩步骤")
    
    # 最终统计汇总
    if os.path.exists(ZIP_FILE_PATH1):
        print(f"   - 图片压缩包：{os.path.abspath(ZIP_FILE_PATH1)}")
    print(f"【{MODEL2}】")
    print(f"   - 质检任务数：{len(processed_json_lines)} 条")
    print(f"   - 成功复制图片数：{len(success_paths2)} 张")
    print(f"   - 提单JSON：{os.path.abspath(FINAL_OUTPUT_JSON_PATH2)}")
    if os.path.exists(ZIP_FILE_PATH2):
        print(f"   - 图片压缩包：{os.path.abspath(ZIP_FILE_PATH2)}")
    print("="*80)

if __name__ == "__main__":
    main()