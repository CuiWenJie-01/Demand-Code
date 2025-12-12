import os, sys
import logging
import shutil
from PIL import Image
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
from tqdm import tqdm
import threading
import time

# 定义需要特殊处理的书籍名称（精确匹配，避免误作用于其他书籍）
SPECIAL_BOOK_NAME = "9787536989627百校联盟高中毕业升学真题详解2026高一期末冲刺全国十大名校月考期中期末真卷精选名校名卷英语外研版高一2025"

def process_single_file(args):
    """
    处理单个文件的任务函数，用于多进程处理
    返回处理状态和可能的错误信息
    """
    (source_file_path, target_file_path, book_name, test_package_path, is_special_book) = args
    
    try:
        # 如果目标文件已存在则跳过
        if os.path.exists(target_file_path):
            return True, None

        # 计算相对于试题包的路径
        foldername = os.path.dirname(source_file_path)
        rel_path = os.path.relpath(foldername, test_package_path)
        if rel_path == '.':
            rel_parts = []
        else:
            rel_parts = rel_path.split(os.sep)

        # 特殊书籍处理
        if is_special_book and "题目" in rel_parts:
            title_idx = rel_parts.index("题目")
            if title_idx + 1 < len(rel_parts):
                rel_parts = rel_parts[:title_idx + 1]

        # 自动归类
        if '题目' not in rel_parts and '答案' not in rel_parts:
            rel_parts.append('题目')

        # 重新构建目标路径
        filename = os.path.basename(source_file_path)
        base_name = os.path.splitext(filename)[0]
        target_file_name = f'{book_name}-{rel_parts[-1]}-{base_name}.jpg'
        
        # 确保目标目录存在
        target_subdir = os.path.dirname(target_file_path)
        os.makedirs(target_subdir, exist_ok=True)

        # 复制或转换
        ext = filename.lower()
        if ext.endswith(('.png', '.jpeg', '.tif', '.bmp', '.gif', '.webp')):
            with Image.open(source_file_path) as img:
                # 使用更快的重采样算法
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                # 使用更快的JPEG编码参数
                img.save(target_file_path, "JPEG", quality=85, optimize=False, progressive=False)
        elif ext.endswith('.jpg'):
            shutil.copy2(source_file_path, target_file_path)
        
        return True, None
    except Exception as e:
        return False, f"处理 {source_file_path} 时发生错误: {str(e)}"

def collect_tasks(input_subfolder, output_subfolder, test_package_path, target_package_path):
    """
    收集指定目录下的所有处理任务
    """
    tasks = []
    book_name = os.path.basename(input_subfolder)
    is_special_book = (book_name == SPECIAL_BOOK_NAME)
    
    for foldername, _, filenames in os.walk(test_package_path):
        for filename in filenames:
            source_file_path = os.path.join(foldername, filename)
            if not os.path.isfile(source_file_path):
                continue
                
            # 计算相对路径以确定目标文件名
            rel_path = os.path.relpath(foldername, test_package_path)
            if rel_path == '.':
                rel_parts = []
            else:
                rel_parts = rel_path.split(os.sep)
                
            # 特殊书籍处理
            if is_special_book and "题目" in rel_parts:
                title_idx = rel_parts.index("题目")
                if title_idx + 1 < len(rel_parts):
                    rel_parts = rel_parts[:title_idx + 1]
                    
            # 自动归类
            if '题目' not in rel_parts and '答案' not in rel_parts:
                rel_parts.append('题目')
                
            # 构建目标路径
            base_name = os.path.splitext(filename)[0]
            target_file_name = f'{book_name}-{rel_parts[-1]}-{base_name}.jpg'
            target_subdir = os.path.join(target_package_path, *rel_parts[-2:])
            target_file_path = os.path.join(target_subdir, target_file_name)
            
            # 添加到任务列表
            tasks.append((source_file_path, target_file_path, book_name, test_package_path, is_special_book))
            
    return tasks

def copy_and_convert(input_subfolder, output_subfolder):
    """
    处理单个书籍目录（其下直接包含 试题包/试题库/试题）
    input_subfolder: 例如 /.../中教万联新全优.../
    output_subfolder: 对应的输出目录
    """
    if not os.path.exists(input_subfolder):
        print(f"错误：路径不存在 - {input_subfolder}")
        return []
    if not os.path.isdir(input_subfolder):
        print(f"错误：{input_subfolder} 不是一个文件夹")
        return []

    # 直接在 input_subfolder 下找试题包（不再遍历其子目录）
    test_package_path = None
    for candidate in ["试题包", "试题库", "试题"]:
        candidate_path = os.path.join(input_subfolder, candidate)
        if os.path.isdir(candidate_path):
            test_package_path = candidate_path
            break
    if not test_package_path:
        logging.error(f'{input_subfolder} 中没有找到试题包/试题库/试题')
        return []

    target_package_path = os.path.join(output_subfolder, "试题包")
    os.makedirs(target_package_path, exist_ok=True)

    # 收集所有需要处理的文件任务
    tasks = collect_tasks(input_subfolder, output_subfolder, test_package_path, target_package_path)
    return tasks

def process_all_books(subject_tasks, max_workers=None):
    """
    并行处理所有书籍任务，并显示总体进度
    """
    if not max_workers:
        max_workers = min(mp.cpu_count(), 8)  # 限制最大进程数防止系统过载
    
    total_tasks = sum(len(tasks) for tasks in subject_tasks.values())
    if total_tasks == 0:
        print("没有需要处理的任务")
        return
    
    success_count = 0
    error_count = 0
    
    # 创建进度条
    with tqdm(total=total_tasks, desc="总体处理进度", unit="文件") as pbar:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_source = {}
            for tasks in subject_tasks.values():
                for task in tasks:
                    future = executor.submit(process_single_file, task)
                    future_to_source[future] = task[0]  # task[0]是source_file_path
            
            # 处理完成的任务
            for future in as_completed(future_to_source):
                success, error_msg = future.result()
                if success:
                    success_count += 1
                else:
                    error_count += 1
                    logging.error(error_msg)
                
                # 更新进度条
                pbar.update(1)
                pbar.set_postfix(成功=success_count, 失败=error_count)
    
    print(f"全部处理完成: 成功 {success_count}, 失败 {error_count}")

def get_subject_paths(input_dir):
    """
    获取所有符合条件的科目路径
    """
    subject_folders = [d for d in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, d))]
    subject_paths = {}
    
    for sub_folder in subject_folders:
        # 过滤条件：处理所有文件夹（原代码中 if '' not in sub_folder 是无效条件）
        subject = sub_folder
        subject_path = os.path.join(input_dir, subject)
        subject_paths[subject] = subject_path
        
    return subject_paths

def get_book_paths(subject_path):
    """
    获取指定科目下的所有书籍路径
    """
    # 判断是否为语文或英语（支持初中/高中前缀）
    subject_name = os.path.basename(subject_path)
    is_chinese_or_english = any(kw in subject_name for kw in ["语文", "英语"])

    book_paths = {}

    # 默认：无细分，直接处理 subject 下的每套试题
    if not is_chinese_or_english:
        # 非语文/英语：直接遍历 subject 下的每套试题目录
        book_dirs = [d for d in os.listdir(subject_path) if os.path.isdir(os.path.join(subject_path, d))]
        for book in book_dirs:
            input_subfolder = os.path.join(subject_path, book)
            book_paths[book] = input_subfolder
    else:
        # 是语文或英语：检查下一级是否为"辅学类"或"刷题类"
        next_level_dirs = [d for d in os.listdir(subject_path) if os.path.isdir(os.path.join(subject_path, d))]
        has_category = any(d in ["辅学类", "刷题类"] for d in next_level_dirs)

        if has_category:
            # 有细分：遍历"辅学类"、"刷题类"下的每套试题
            for category in ["辅学类", "刷题类"]:
                category_path = os.path.join(subject_path, category)
                if not os.path.exists(category_path):
                    continue
                book_dirs = [d for d in os.listdir(category_path) if os.path.isdir(os.path.join(category_path, d))]
                for book in book_dirs:
                    input_subfolder = os.path.join(category_path, book)
                    # 用分类标识书籍
                    book_key = f"{category}/{book}"
                    book_paths[book_key] = input_subfolder
        else:
            # 无细分：直接处理 subject 下的每套试题
            book_dirs = [d for d in os.listdir(subject_path) if os.path.isdir(os.path.join(subject_path, d))]
            for book in book_dirs:
                input_subfolder = os.path.join(subject_path, book)
                book_paths[book] = input_subfolder
                
    return book_paths

if __name__ == "__main__":
    # 核心修改：接收三个参数：1.输入路径 2.输出路径 3.batch名称
    if len(sys.argv) != 4:
        print("用法：python 0_1_cp_png.py <输入路径> <输出路径> <batch名称>")
        print("示例：python 0_1_cp_png.py "
              "/DL_data_new/自动化切题/原始数据/教辅QA/正式交付数据/图片包/信息科技1009 "
              "/DL_data_new/ftpdata/jjhu32/code/中高考ocr切题/信息科技1009/0_raw_png_信息科技1009 "
              "信息科技1009")
        sys.exit(1)

    # 直接接收三个参数，无需从路径提取batch
    input_dir = sys.argv[1]    # 第一个参数：输入路径
    output_dir = sys.argv[2]   # 第二个参数：输出路径
    batch = sys.argv[3]        # 第三个参数：明确传入的batch名称

    # 保留原逻辑：创建必要目录和日志配置
    os.makedirs(output_dir, exist_ok=True)
    
    err_log = f"{output_dir}/日志.log"
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=err_log,
        filemode='w'
        )

    # 收集所有任务
    all_tasks = {}
    
    print("正在收集处理任务...")
    subject_paths = get_subject_paths(input_dir)
    
    for subject, subject_path in subject_paths.items():
        book_paths = get_book_paths(subject_path)
        
        for book_key, input_subfolder in book_paths.items():
            if not os.path.exists(input_subfolder):
                continue
                
            # 构建输出路径
            if "/" in book_key:  # 包含分类的情况
                category, book = book_key.split("/", 1)
                output_subfolder = os.path.join(output_dir, f"{subject}-{category}", book)
            else:
                output_subfolder = os.path.join(output_dir, subject, book_key)
                
            os.makedirs(output_subfolder, exist_ok=True)
            
            # 收集此书籍的任务
            tasks = copy_and_convert(input_subfolder, output_subfolder)
            if tasks:
                task_key = f"{subject}/{book_key}"
                all_tasks[task_key] = tasks

    # 执行所有任务
    print(f"开始处理 {len(all_tasks)} 个书籍目录，共 {sum(len(t) for t in all_tasks.values())} 个文件...")
    process_all_books(all_tasks)


# 总体进度条：

# 使用一个总体的 tqdm 进度条显示所有文件的处理进度
# 显示成功和失败的数量统计
# 性能优化：

# 禁用了 JPEG 的 optimize 和 progressive 参数以加快处理速度
# 减少了进程中重复计算路径的操作
# 优化了图像转换流程
# 架构优化：

# 将任务收集与执行分离，先收集所有任务再并行处理
# 更清晰的代码结构和函数划分
# 避免了每个书籍目录都创建进程池的开销
# 内存效率：

# 减少了不必要的中间变量和重复数据
# 优化了路径处理逻辑
