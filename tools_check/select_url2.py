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

def process_url(path):
    """
    按/分隔路径，排除最后两个层级，返回处理后的路径
    示例：
    输入：/a/b/c/d/e.png → 按/分隔为['', 'a', 'b', 'c', 'd', 'e.png']
    排除最后两层（'d'和'e.png'）→ 保留前4段 → 拼接为 /a/b/c
    """
    # 按/分隔路径（处理开头/结尾的分隔符，避免空元素干扰）
    path_segments = [seg for seg in path.strip('/').split('/') if seg]
    # 若路径层级≤2（如"/a/b"或"a.png"），返回空字符串（无足够层级可排除）
    if len(path_segments) <= 2:
        return ""
    # 保留除最后两个层级外的部分，重新拼接为路径
    processed_segments = path_segments[:-2]
    return '/' + '/'.join(processed_segments)  # 开头补/，恢复标准路径格式

# 读取 jsonl 文件并提取 url（核心逻辑：新增路径处理）
try:
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                raw_url = data.get('url')
                if not raw_url:
                    continue  # 跳过空url
                # 关键修改：处理url，排除最后两个层级
                processed_url = process_url(raw_url)
                if processed_url:  # 仅保留处理后非空的路径
                    urls.add(processed_url)
            except json.JSONDecodeError:
                continue  # 跳过无效JSON行

    # 写入去重后的URL（逻辑不变）
    with open(output_file, 'w', encoding='utf-8') as f:
        for url in sorted(urls):  # 按字母排序（可删除sorted()取消排序）
            f.write(url + '\n')

    print(f"共提取并去重 {len(urls)} 条 URL（已排除最后两个层级），保存至 {output_file}")
    
except FileNotFoundError:
    # 错误提示适配新的输入文件名
    print(f"错误：输入文件 {input_file} 不存在（需先运行0_select_数据-全量抽.py生成该文件）")
    sys.exit(1)
except Exception as e:
    print(f"处理过程中发生错误：{e}")
    sys.exit(1)