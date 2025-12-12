import json
import sys
import os

# 关键修改：参数数量改为4个（input_dir + output_dir + level + subject）
if len(sys.argv) != 4:
    print("用法: python 1_select_url.py <input_dir> <output_dir> <level> <subject>")
    print("示例: python 1_select_url.py /input /output 高考 文综")
    print("说明: input_dir=前序JSON文件所在目录，output_dir=URL文件输出目录")
    sys.exit(1)

# 提取参数（新增 level 和 subject 接收）
input_dir = sys.argv[1]
output_dir = sys.argv[2]
batch = sys.argv[3]
# level = sys.argv[3]       # 接收shell中的$level（如"高考"）
# subject = sys.argv[4]     # 接收shell中的$subject（如"文综"）

# 关键修改：用 level 和 subject 推导输入文件路径（适配前序脚本输出）
input_filename = f"select-{batch}.json"  # 前序生成的JSON文件（如"select-高考文综.json"）
input_file = os.path.join(input_dir, input_filename)
output_file = os.path.join(output_dir, "unique_urls.txt")  # 输出URL文件（保持原命名不变）

# 确保输出目录存在（逻辑不变）
os.makedirs(output_dir, exist_ok=True)

urls = set()

# 读取 jsonl 文件并提取 url（核心逻辑不变）
try:
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                url = data.get('url')
                if url:
                    urls.add(url)  # 用set自动去重
            except json.JSONDecodeError:
                continue  # 跳过无效JSON行

    # 写入去重后的URL（逻辑不变）
    with open(output_file, 'w', encoding='utf-8') as f:
        for url in sorted(urls):  # 按字母排序（可删除sorted()取消排序）
            f.write(url + '\n')

    print(f"共提取并去重 {len(urls)} 条 URL，保存至 {output_file}")
    
except FileNotFoundError:
    # 错误提示适配新的输入文件名
    print(f"错误：输入文件 {input_file} 不存在（需先运行0_select_数据-全量抽.py生成该文件）")
    sys.exit(1)
except Exception as e:
    print(f"处理过程中发生错误：{e}")
    sys.exit(1)