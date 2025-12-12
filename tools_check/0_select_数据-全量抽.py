import os
import json
import random
import sys

# 关键修改：接收4个参数（原2个 + 新增level、subject）
if len(sys.argv) != 5:
    print("用法: python 0_select_数据-全量抽.py <input_dir> <output_dir> <level> <subject>")
    print("示例: python 0_select_数据-全量抽.py /input /output 高考 文综")
    sys.exit(1)

# 提取参数（新增level和subject的接收）
input_dir = sys.argv[1]
output_dir = sys.argv[2]
level = sys.argv[3]       # 接收shell中的$level值（如"高考"）
subject = sys.argv[4]     # 接收shell中的$subject值（如"文综"）

# =========================
all_lines = []

# 遍历文件夹，收集所有 JSON 文件的行（逻辑不变）
for root, dirs, files in os.walk(input_dir):
    for file in files:
        if file.lower().endswith(".json"):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                    all_lines.extend(lines)
            except Exception as e:
                print(f"读取失败: {file_path}, 错误: {e}")

# 根据总数据量动态确定抽取数量（逻辑不变）
total_count = len(all_lines)
if total_count < 10:
    total_sample_size = 0
elif total_count < 100:
    total_sample_size = 10
elif 100 <= total_count < 1000:
    total_sample_size = 20
elif 1000 <= total_count < 10000:
    total_sample_size = 40
else:  # 10000及以上
    total_sample_size = 60

# 确保抽取数量不超过总数据量（逻辑不变）
total_sample_size = min(total_sample_size, total_count)

# 随机抽取（逻辑不变）
if total_count <= total_sample_size:
    sampled_results = all_lines  # 数据不够就全用
else:
    sampled_results = random.sample(all_lines, total_sample_size)

# 打乱顺序（可选）
random.shuffle(sampled_results)

# 关键修改：用level和subject拼接文件名（而非原dir_name）
output_file = os.path.join(output_dir, f"select-{level}{subject}.json")
# 示例：level=高考、subject=文综 → 文件名"select-高考文综.json"

# 确保输出目录存在（逻辑不变）
os.makedirs(output_dir, exist_ok=True)

# 写入文件（逻辑不变）
with open(output_file, "w", encoding="utf-8") as f:
    for line in sampled_results:
        f.write(line + "\n")

print(f"总数据量: {total_count} 条，根据数据量确定抽取 {total_sample_size} 条，输出到: {output_file}")