import os
import shutil
import sys

def copy_and_preserve_last_folder(txt_path, target_root):
    os.makedirs(target_root, exist_ok=True)

    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            src_path = line.strip()
            if not src_path:
                continue

            if not os.path.exists(src_path):
                print(f"路径无效: {src_path}")
                continue

            # 获取最后一层文件夹名称或文件名（不含扩展名）
            last_name = os.path.basename(src_path.rstrip(os.sep))

            # 目标路径（保留最后一层文件夹）
            dst_path = os.path.join(target_root, last_name)
            os.makedirs(dst_path, exist_ok=True)

            if os.path.isdir(src_path):
                # 如果是文件夹，复制里面所有文件（不递归）
                for file in os.listdir(src_path):
                    src_file = os.path.join(src_path, file)
                    if os.path.isfile(src_file):
                        shutil.copy(src_file, dst_path)
                        print(f"已复制文件: {src_file} -> {dst_path}")
            elif os.path.isfile(src_path):
                # 如果是单个文件，复制进去
                shutil.copy(src_path, dst_path)
                print(f"已复制文件: {src_path} -> {dst_path}")
            else:
                print(f"无法识别的路径类型: {src_path}")

# 从命令行获取输入目录和输出目录参数
if len(sys.argv) != 3:
    print("用法: python 2_cp_txt2file.py <input_dir> <output_dir>")
    sys.exit(1)

input_dir = sys.argv[1]
output_dir = sys.argv[2]

# 构建输入txt文件路径和目标文件夹路径
dir_name = os.path.basename(output_dir)
txt_file = os.path.join(output_dir, "unique_urls.txt")  # 使用前一步生成的URL文件
target_dir = os.path.join(output_dir, "image")  # 在输出目录下创建image子目录

# 执行复制操作
copy_and_preserve_last_folder(txt_file, target_dir)
