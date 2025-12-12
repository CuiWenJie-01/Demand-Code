import os
import shutil
import sys

def copy_with_test_packet_structure(txt_path, target_root):
    """
    根据TXT文件中的路径，按指定层级结构复制内容：
    1. 从路径中提取倒数第三个文件夹名称作为一级目标文件夹
    2. 在一级目标文件夹中创建"试题包"二级文件夹
    3. 将原路径中的最终文件夹（如1、3等）复制到"试题包"中
    """
    # 创建目标根目录（若不存在）
    os.makedirs(target_root, exist_ok=True)
    print(f"📌 目标根目录：{os.path.abspath(target_root)}\n")

    # 检查TXT文件是否存在
    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"❌ TXT文件不存在：{os.path.abspath(txt_path)}")

    with open(txt_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            src_path = line.strip()  # 去除路径前后的空格和换行符
            if not src_path:
                print(f"⚠️  第{line_num}行：空路径，跳过")
                continue

            # 检查源路径是否存在
            if not os.path.exists(src_path):
                print(f"⚠️  第{line_num}行：路径不存在 -> {src_path}，跳过")
                continue

            # 拆分路径为层级列表（兼容Windows/Linux路径分隔符）
            # 先统一替换为os.sep，再拆分，避免混合分隔符问题
            normalized_path = src_path.replace('/', os.sep).replace('\\', os.sep)
            path_parts = normalized_path.split(os.sep)
            # 过滤空字符串（处理路径以分隔符开头/结尾的情况）
            path_parts = [part for part in path_parts if part]

            # 检查路径层级是否足够（至少需要3个层级：倒数第三+倒数第二+最后一级）
            if len(path_parts) < 3:
                print(f"⚠️  第{line_num}行：路径层级不足3层（需≥3层）-> {src_path}，跳过")
                continue

            # 提取关键层级
            third_last_folder = path_parts[-3]  # 倒数第三个文件夹（一级目标文件夹名）
            final_folder = path_parts[-1]       # 最后一个文件夹（需复制的文件夹，如1、3）

            # 构建目标路径结构：目标根目录/倒数第三个文件夹/试题包/
            first_level_dir = os.path.join(target_root, third_last_folder)
            test_packet_dir = os.path.join(first_level_dir, "试题包")  # 二级文件夹固定为"试题包"
            os.makedirs(test_packet_dir, exist_ok=True)  # 自动创建多级目录

            # 复制源文件夹到目标路径
            try:
                if os.path.isdir(src_path):
                    dst_dir = os.path.join(test_packet_dir, final_folder)
                    
                    # 处理目标文件夹已存在的情况（先删除旧目录，避免残留）
                    if os.path.exists(dst_dir):
                        shutil.rmtree(dst_dir)
                        print(f"ℹ️  第{line_num}行：目标文件夹已存在，先删除 -> {dst_dir}")
                    
                    # 递归复制文件夹（包含所有子文件/子目录）
                    shutil.copytree(src_path, dst_dir)
                    
                    print(f"✅ 第{line_num}行：复制完成")
                    print(f"   源：{src_path}")
                    print(f"   目标：{dst_dir}\n")

                else:
                    print(f"⚠️  第{line_num}行：不是文件夹（跳过）-> {src_path}\n")

            except Exception as e:
                print(f"❌ 第{line_num}行：复制失败 -> {src_path}")
                print(f"   错误信息：{str(e)}\n")

def main():
    # -------------------------- 适配Shell脚本参数逻辑 --------------------------
    # 接收参数：python 脚本名 <input_dir> <output_dir> <level> <subject>
    # 对应Shell中的：$output_dir(前序URL输出目录) $output_dir(图片输出目录) $level $subject
    if len(sys.argv) != 3:
        print("📋 用法（适配Shell工作流）：python 2_cp_txt2file.py <input_dir> <output_dir> <level> <subject>")
        print("示例：python 2_cp_txt2file.py /data/output /data/output 高中 地理")
        print("说明：")
        print("   - input_dir：前序1_select_url.py输出的unique_urls.txt所在目录")
        print("   - output_dir：图片最终输出根目录（会在该目录下创建层级结构）")
        print("   - level/subject：兼容Shell参数（无实际影响，保持调用格式统一）")
        sys.exit(1)

    # 提取Shell传递的参数
    input_dir = sys.argv[1]    # unique_urls.txt所在目录（前序脚本输出目录）
    output_dir = sys.argv[2]   # 图片输出根目录（最终生成"xxx/试题包/xxx"结构）
    # level = sys.argv[3]       # 兼容参数（无需使用，保持格式）
    # subject = sys.argv[4]     # 兼容参数（无需使用，保持格式）

    # -------------------------- 自动推导文件路径 --------------------------
    # 推导unique_urls.txt路径（前序1_select_url.py/1_select_url2.py的输出文件）
    txt_filename = "unique_urls.txt"
    txt_path = os.path.join(input_dir, txt_filename)

    # 推导图片输出根目录下的具体目录（保持与前序脚本的"image"目录命名一致）
    target_root = os.path.join(output_dir, "image")

    # -------------------------- 执行核心复制逻辑 --------------------------
    try:
        print("="*80)
        print("          开始按「倒数第三层文件夹/试题包/最终文件夹」结构复制图片")
        print("="*80)
        print(f"📥 读取URL列表：{os.path.abspath(txt_path)}")
        print(f"📤 图片输出根目录：{os.path.abspath(target_root)}")
        print("="*80 + "\n")

        copy_with_test_packet_structure(txt_path, target_root)

        print("="*80)
        print("          所有路径处理完毕！")
        print(f"📊 最终图片结构：{os.path.abspath(target_root)}/[倒数第三层文件夹]/试题包/[最终文件夹]")
        print("="*80)

    except Exception as e:
        print(f"\n❌ 程序执行失败：{str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()