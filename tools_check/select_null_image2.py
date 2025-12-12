import os
import json
import sys
import shutil
from tqdm import tqdm
from datetime import datetime

# -------------------------- 固定配置 --------------------------
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg')
EXTRACT_BASENAME_FROM_PIC = False  # PIC已是纯文件名，无需解析路径
# -------------------------------------------------------------------------------------

def extract_unique_pics_from_jsonl(jsonl_path):
    """从JSONL的content['PIC']提取去重纯文件名（分号分隔适配）"""
    if not os.path.exists(jsonl_path):
        raise FileNotFoundError(f"❌ JSONL文件不存在：{os.path.abspath(jsonl_path)}")
    if not jsonl_path.lower().endswith((".jsonl", ".json")):
        print(f"⚠️ 警告：文件后缀非JSONL/JSON，可能不是目标文件：{os.path.abspath(jsonl_path)}")

    unique_pics = set()
    stats = {
        "total_lines": 0, "valid_json_lines": 0, "has_content_pic_lines": 0,
        "invalid_json_lines": 0, "empty_pic_lines": 0
    }

    print(f"📂 提取JSONL的content['PIC']：{os.path.abspath(jsonl_path)}")
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in tqdm(enumerate(f, 1), desc="解析JSONL"):
            line_stripped = line.strip()
            stats["total_lines"] += 1
            if not line_stripped:
                continue

            try:
                # 严格匹配平台JSON格式层级
                json_obj = json.loads(line_stripped)
                stats["valid_json_lines"] += 1

                if "dialogContent" not in json_obj or not isinstance(json_obj["dialogContent"], list) or len(json_obj["dialogContent"]) == 0:
                    continue
                if "content" not in json_obj["dialogContent"][0] or not isinstance(json_obj["dialogContent"][0]["content"], list) or len(json_obj["dialogContent"][0]["content"]) == 0:
                    continue

                pic_value = json_obj["dialogContent"][0]["content"][0].get("PIC", "").strip()
                if not pic_value:
                    stats["empty_pic_lines"] += 1
                    continue

                stats["has_content_pic_lines"] += 1
                # 拆分分号分隔的多图片
                for pic_file in [p.strip() for p in pic_value.split(";") if p.strip()]:
                    unique_pics.add(pic_file.lower())

            except json.JSONDecodeError:
                stats["invalid_json_lines"] += 1
                print(f"⚠️ 第{line_num}行：JSON格式错误，跳过")
            except Exception as e:
                print(f"⚠️ 第{line_num}行：处理异常 → {str(e)}，跳过")

    print(f"\n✅ PIC提取统计：")
    print(f"   - 去重后总数：{len(unique_pics)} | 有效JSON行：{stats['valid_json_lines']}/{stats['total_lines']} | 含PIC行：{stats['has_content_pic_lines']}")
    return unique_pics


def scan_image_folder(folder_path):
    """扫描图片文件夹，获取纯文件名集合（小写）及完整路径映射"""
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"❌ 图片文件夹不存在：{os.path.abspath(folder_path)}")
    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"❌ 输入路径不是文件夹：{os.path.abspath(folder_path)}")

    image_filenames = set()
    image_path_map = {}  # 文件名（小写）→ 完整路径
    print(f"\n📷 扫描图片文件夹：{os.path.abspath(folder_path)}")
    for root, _, files in tqdm(os.walk(folder_path), desc="扫描图片"):
        for file in files:
            if file.lower().endswith(IMAGE_EXTENSIONS):
                lower_name = file.lower()
                image_filenames.add(lower_name)
                image_path_map[lower_name] = os.path.join(root, file)  # 记录完整路径

    print(f"✅ 图片扫描统计：共找到 {len(image_filenames)} 个有效图片文件")
    return image_filenames, image_path_map


def calculate_mismatch(unique_pics, image_filenames):
    """计算PIC与物理图片的不匹配项"""
    pic_missing = sorted(list(unique_pics - image_filenames))  # PIC有、图片无
    image_unreferenced = sorted(list(image_filenames - unique_pics))  # 图片有、PIC无
    return pic_missing, image_unreferenced


def delete_unreferenced_images(unreferenced, image_path_map, image_folder, log_file):
    """删除未被PIC引用的冗余图片（强制删除，无需确认），移动到combine_image的上上一层目录，并记录日志"""
    if not unreferenced:
        print("\n⚠️ 没有需要删除的冗余图片，跳过删除步骤")
        return 0

    # 获取combine_image的上上一层目录（父目录的父目录）作为回收站位置
    grandparent_dir = os.path.dirname(os.path.dirname(image_folder))
    print(f"\n📌 操作根目录（combine_image的上上一层）：{grandparent_dir}")

    # 显示待删除列表（仅展示，无需确认）
    print(f"\n🔍 即将强制删除以下 {len(unreferenced)} 个未被PIC引用的冗余图片：")
    for idx, img in enumerate(unreferenced[:5], 1):  # 显示前5个示例
        print(f"     {idx:3d}. {img}")
    if len(unreferenced) > 5:
        print(f"     ... 省略 {len(unreferenced)-5} 个文件")

    # 创建回收站目录（在combine_image的上上一层）
    recycle_bin = os.path.join(grandparent_dir, "recycle_bin_pic")
    os.makedirs(recycle_bin, exist_ok=True)
    print(f"\n🗑️ 回收站目录：{recycle_bin}（删除的图片将移动至此）")

    # 执行强制删除（移动到回收站）
    deleted_count = 0
    failed = []
    with open(log_file, "a", encoding="utf-8") as f_log:
        f_log.write("\n===== 冗余图片强制删除记录 =====\n")  # 日志标记为“强制删除”
        f_log.write(f"删除时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f_log.write(f"删除总数：{len(unreferenced)}\n")
        
        for img in tqdm(unreferenced, desc="强制删除冗余图片"):  # 进度条描述修改为“强制删除”
            src_path = image_path_map.get(img)
            if not src_path or not os.path.exists(src_path):
                failed.append(f"文件不存在：{img}")
                continue

            # 移动到回收站（保留原始相对路径结构）
            rel_path = os.path.relpath(src_path, image_folder)
            dst_path = os.path.join(recycle_bin, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            
            try:
                shutil.move(src_path, dst_path)
                deleted_count += 1
                f_log.write(f"成功删除：{src_path} → 回收站：{dst_path}\n")
            except Exception as e:
                err_msg = f"删除失败（{str(e)}）：{src_path}"
                failed.append(err_msg)
                f_log.write(f"失败：{err_msg}\n")

    # 输出删除结果
    print(f"\n✅ 强制删除完成：成功删除 {deleted_count} 个图片，{len(failed)} 个失败")
    if failed:
        print("❌ 失败列表：")
        for err in failed[:3]:
            print(f"   - {err}")
        if len(failed) > 3:
            print(f"   - ... 省略 {len(failed)-3} 条")

    return deleted_count


def main():
    # -------------------------- 适配Shell脚本参数逻辑 --------------------------
    if len(sys.argv) != 5:
        print("📋 用法（适配Shell工作流）：python 5_pic_mismatch_check.py <input_dir> <output_dir> <level> <subject>")
        print("示例：python 5_pic_mismatch_check.py /data/output /data/output2 高考 文综")
        print("说明：input_dir=前序JSONL所在目录，output_dir=图片文件夹所在目录（自动处理冗余图片，无需确认）")
        sys.exit(1)

    # 提取Shell传递的参数
    input_dir = sys.argv[1]    # 前序4_transform_to_平台_sub.py的输出目录
    output_dir = sys.argv[2]   # 图片合并目录所在目录（含combine_image子目录）
    # batch = sys.argv[3]
    level = sys.argv[3]        # 兼容Shell参数（如"高考"）
    subject = sys.argv[4]      # 兼容Shell参数（如"文综"）

    # -------------------------- 自动推导文件路径 --------------------------
    # 1. 推导平台格式JSONL路径
    jsonl_filename = f"select-{level}{subject}-to平台.json"
    jsonl_path = os.path.join(input_dir, jsonl_filename)

    # 2. 推导图片合并目录路径（combine_image）
    image_folder = os.path.join(output_dir, "combine_image")

    # 3. 获取combine_image的上上一层目录，用于存放日志
    grandparent_dir = os.path.dirname(os.path.dirname(image_folder))
    log_filename = f"pic_mismatch_log_{level}{subject}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_path = os.path.join(grandparent_dir, log_filename)

    # -------------------------- 核心执行逻辑 --------------------------
    try:
        # 1. 提取PIC去重值
        unique_pics = extract_unique_pics_from_jsonl(jsonl_path)
        if not unique_pics:
            print(f"\n⚠️ 警告：未提取到任何有效PIC，程序终止")
            return

        # 2. 扫描物理图片
        image_filenames, image_path_map = scan_image_folder(image_folder)

        # 3. 计算不匹配项
        pic_missing, image_unreferenced = calculate_mismatch(unique_pics, image_filenames)

        # 4. 命令行输出结果
        print(f"\n" + "="*120)
        print(f"                content['PIC']与物理图片比对结果（{level}{subject}）")
        print("="*120)
        print(f"📊 核心统计：")
        print(f"   • PIC去重总数：{len(unique_pics)} | 物理图片总数：{len(image_filenames)} | 匹配数：{len(unique_pics & image_filenames)}")
        print(f"   • PIC覆盖率：{((len(unique_pics) - len(pic_missing)) / len(unique_pics) * 100):.2f}%")
        
        print(f"\n❌ PIC存在但图片缺失（共{len(pic_missing)}个，需补充）：")
        if pic_missing:
            for idx, pic in enumerate(pic_missing, 1):
                print(f"     {idx:3d}. {pic}")
        else:
            print(f"     （无缺失，PIC全部匹配）")

        print(f"\n⚠️ 图片存在但PIC未提及（共{len(image_unreferenced)}个，将强制清理）：")  # 提示改为“强制清理”
        if image_unreferenced:
            for idx, img in enumerate(image_unreferenced[:10], 1):
                print(f"     {idx:3d}. {img}")
            if len(image_unreferenced) > 10:
                print(f"     ... 省略 {len(image_unreferenced)-10} 个文件")
        else:
            print(f"     （无冗余，所有图片均在PIC中提及）")
        print("="*120)

        # 5. 生成比对日志
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"PIC与图片比对日志（{level}{subject}）\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"JSONL文件路径：{jsonl_path}\n")
            f.write(f"图片文件夹路径：{image_folder}\n")
            f.write(f"回收站路径：{os.path.join(grandparent_dir, 'recycle_bin_pic')}\n")
            f.write("="*60 + "\n")
            f.write(f"核心统计：\n")
            f.write(f"   • PIC去重总数：{len(unique_pics)}\n")
            f.write(f"   • 物理图片总数：{len(image_filenames)}\n")
            f.write(f"   • 匹配数：{len(unique_pics & image_filenames)}\n")
            f.write(f"   • PIC覆盖率：{((len(unique_pics) - len(pic_missing)) / len(unique_pics) * 100):.2f}%\n")
            f.write("="*60 + "\n")
            f.write(f"PIC存在但图片缺失（{len(pic_missing)}个）：\n")
            f.write("\n".join(pic_missing) + "\n")
            f.write("="*60 + "\n")
            f.write(f"图片存在但PIC未提及（{len(image_unreferenced)}个，已强制删除）：\n")  # 日志标记“已强制删除”
            f.write("\n".join(image_unreferenced) + "\n")

        print(f"\n📄 比对日志已保存至：{log_path}")

        # 6. 强制删除未被引用的图片（无需确认）
        if image_unreferenced:
            delete_unreferenced_images(image_unreferenced, image_path_map, image_folder, log_path)

    except Exception as e:
        print(f"\n❌ 程序执行失败：{str(e)}")
        # 记录错误日志
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"程序执行失败：{str(e)}\n")
            f.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    main()