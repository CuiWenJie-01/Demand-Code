import os
from pathlib import Path
import zipfile

# =============== 配置区 ===============
# ✅ 路径列表文件（每行一个路径）
PATHS_FILE = "/DL_data_new/ftpdata/wjcui/code/other/unzip_paths.txt"

# ✅ 解压目标根目录（ZIP 内容将直接解压到这里）
TARGET_ROOT = "/DL_data_new/自动化切题/原始数据/教辅QA/正式交付数据/图片包"
# =============== 配置结束 ===============


def extract_zip_simple(zip_path, extract_to):
    """
    简单解压：将 zip 文件直接解压到指定目录
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_to)
        print(f"✅ 成功解压: {zip_path.name}")
        return True
    except Exception as e:
        print(f"❌ 解压失败: {zip_path.name} - {str(e)}")
        return False


def main():
    paths_file = Path(PATHS_FILE)
    target_root = Path(TARGET_ROOT)
    target_root.mkdir(parents=True, exist_ok=True)  # 确保目标根目录存在

    # 检查路径文件是否存在
    if not paths_file.exists():
        print(f"❌ 错误：文件不存在: {paths_file}")
        return

    # 读取所有 ZIP 路径
    with open(paths_file, 'r', encoding='utf-8') as f:
        raw_lines = f.readlines()

    zip_paths = []
    for line in raw_lines:
        cleaned = line.strip().strip('"\'').strip()
        if cleaned:
            zip_paths.append(Path(cleaned))

    if not zip_paths:
        print("❌ 未读取到有效路径")
        return

    success_count = 0
    fail_count = 0

    # 逐个解压
    for zip_path in zip_paths:
        if not zip_path.exists():
            print(f"❌ 文件不存在: {zip_path}")
            fail_count += 1
            continue

        # ✅ 直接解压到目标根目录（不再创建 zip_path.stem 这一层）
        extract_to = target_root

        # （可选）检查是否已存在同名目录（以 zip 文件名 stem 为参考）
        potential_dir = extract_to / zip_path.stem
        if potential_dir.exists() and any(potential_dir.iterdir()):
            print(f"⏭️  已存在，跳过: {potential_dir.name}/")
            continue

        print(f"📦 正在解压: {zip_path.name}")
        if extract_zip_simple(zip_path, extract_to):
            success_count += 1
        else:
            fail_count += 1

    # 打印总结
    print("\n" + "=" * 50)
    print(f"✅ 解压完成！成功: {success_count}, 失败: {fail_count}")
    print(f"📁 所有文件已解压至: {target_root}/")


if __name__ == "__main__":
    main()