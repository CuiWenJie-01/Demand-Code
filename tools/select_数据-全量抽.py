import os
import json
import random
import sys
from datetime import datetime

# 接收3个参数：输入根目录、输出目录、批次标识
if len(sys.argv) != 4:
    print("用法: python 0_select_数据-全量抽.py <input_root_dir> <output_dir> <batch>")
    print("示例: python 0_select_数据-全量抽.py /input_root /output 高考文综批次1")
    sys.exit(1)

# 提取参数
input_root_dir = sys.argv[1]
output_dir = sys.argv[2]
batch = sys.argv[3]

# 存储所有子文件夹的抽取结果和统计信息
all_sampled = []
stats = []  # 格式: [{"文件夹名称": name, "抽取数量": count}, ...]

# 遍历输入根目录下的所有子文件夹
for root, dirs, files in os.walk(input_root_dir):
    # 过滤当前目录下的JSON文件
    json_files = [f for f in files if f.lower().endswith(".json")]
    if not json_files:
        continue
    
    # 收集当前文件夹下所有JSON数据
    folder_lines = []
    for file in json_files:
        file_path = os.path.join(root, file)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                folder_lines.extend(lines)
        except Exception as e:
            print(f"❌ 读取失败: {file_path}, 错误: {str(e)}")
    
    folder_count = len(folder_lines)
    if folder_count == 0:
        print(f"⚠️ 文件夹 {root} 无有效数据，跳过")
        continue
    
    # 确定当前文件夹的抽取数量
    if folder_count < 10:
        folder_sample_size = 9  # 数据量小于10时，抽取0条
    elif folder_count < 100:
        folder_sample_size = 10
    elif 100 <= folder_count < 1000:
        folder_sample_size = 20
    elif 1000 <= folder_count < 10000:
        folder_sample_size = 40
    else:
        folder_sample_size = 60
    folder_sample_size = min(folder_sample_size, folder_count)
    
    # 随机抽取
    folder_sampled = folder_lines if folder_count <= folder_sample_size else random.sample(folder_lines, folder_sample_size)
    all_sampled.extend(folder_sampled)
    
    # 记录文件夹名称和抽取数量
    folder_name = os.path.basename(root)
    stats.append({"文件夹名称": folder_name, "抽取数量": folder_sample_size})
    print(f"✅ 处理文件夹: {folder_name}（抽取: {folder_sample_size} 条）")

# 打乱抽取结果
random.shuffle(all_sampled)

# 输出文件路径
output_file = os.path.join(output_dir, f"select-{batch}.json")
stats_file = os.path.join(output_dir, f"抽取统计_{batch}.txt")
os.makedirs(output_dir, exist_ok=True)

# 写入JSON结果文件
with open(output_file, "w", encoding="utf-8") as f:
    for line in all_sampled:
        f.write(line + "\n")

# 写入简化的统计文件（仅保留子文件夹名称和抽取数量）
with open(stats_file, "w", encoding="utf-8") as f:
    for item in stats:
        # 确保名称过长时不换行，保持一行一条记录
        folder_name = item["文件夹名称"][:50]  # 限制最大长度50字符
        f.write(f"{folder_name}：{item['抽取数量']}\n")

print(f"\n===== 处理完成 =====")
print(f"输出文件: {output_file}")
print(f"统计文件: {stats_file}（格式：子文件夹名称：抽取数量）")