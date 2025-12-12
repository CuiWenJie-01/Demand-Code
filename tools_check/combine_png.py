import os
import shutil
import sys

def merge_all_images(src_root, dst_folder, img_extensions=(".png", ".jpg", ".jpeg", ".bmp", ".gif")):
    # 确保目标合并目录存在
    os.makedirs(dst_folder, exist_ok=True)
    
    # 记录文件名重复次数，避免覆盖
    name_count = {}
    
    # 遍历源图片目录下所有图片
    for root, dirs, files in os.walk(src_root):
        for file in files:
            # 只处理指定格式的图片
            if file.lower().endswith(img_extensions):
                src_path = os.path.join(root, file)
                # 拆分文件名和扩展名
                base_name = os.path.splitext(file)[0]
                ext = os.path.splitext(file)[1]
                new_name = file
                
                # 处理重复文件名（添加序号后缀）
                if new_name in name_count:
                    name_count[new_name] += 1
                    new_name = f"{base_name}_{name_count[new_name]}{ext}"
                else:
                    name_count[new_name] = 0
                
                # 复制图片（copy2保留文件元数据，如创建时间）
                dst_path = os.path.join(dst_folder, new_name)
                shutil.copy2(src_path, dst_path)

    print(f"✅ 所有图片已合并至: {dst_folder}")

# 从命令行获取输入目录和输出目录参数
if len(sys.argv) != 3:
    print("用法: python 3_merge_all_images.py <input_dir> <output_dir>")
    sys.exit(1)

input_dir = sys.argv[1]  # 兼容前序脚本参数格式，实际未使用
output_dir = sys.argv[2]

# 构建源图片目录和目标合并目录路径（与前序脚本目录对齐）
src_root = os.path.join(input_dir, "image")          # 前序脚本生成的分散图片目录
dst_folder = os.path.join(output_dir, "combine_image")# 本脚本输出的合并图片目录

# 执行图片合并操作
merge_all_images(src_root=src_root, dst_folder=dst_folder)