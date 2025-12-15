#!/usr/bin/env python3
import os
import zipfile
import argparse
from pathlib import Path

def compress(input_path, output_path):
    try:
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        if not input_path.exists():
            raise ValueError(f"输入路径不存在: {input_path}")

        # 处理输出路径为目录的情况
        if output_path.is_dir():
            output_path = output_path / f"{input_path.name}.zip"

        # 创建输出目录
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            if input_path.is_file():
                zipf.write(input_path, arcname=input_path.name)
            elif input_path.is_dir():
                for root, dirs, files in os.walk(input_path):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(input_path.parent)
                        zipf.write(file_path, arcname=arcname)
                    # 处理空目录
                    if not dirs and not files:
                        arcname = Path(root).relative_to(input_path.parent)
                        zipf.writestr(str(arcname) + "/", b'')

        print(f"压缩成功！输出文件: {output_path}")
        return 0
    except Exception as e:
        print(f"错误: {str(e)}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="文件/目录压缩工具")
   # 设置输入路径
    input_path = "/DL_data_new/ftpdata/wjcui/code/切题链路合并/9.8可提交-35/3_ocr_res_9.8可提交-35/高中英语"
    
    # 自动生成输出路径（输出到当前目录，使用输入目录名+.zip）
    output_dir = "/DL_data_new/ftpdata/wjcui/code/解压缩/"  # 指定输出目录
    output_path = Path(output_dir) / f"{Path(input_path).name}.zip"
    
    exit_code = compress(input_path, output_path)
    exit(exit_code)
