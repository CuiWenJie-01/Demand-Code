import os
import fitz  # PyMuPDF
import re
from tqdm import tqdm


def extract_toc_and_split_pdf(input_pdf_path, output_dir):
    """
    根据PDF目录拆分PDF文件为每个章节单独的PDF文件，并按章节编号组织到子文件夹中

    Args:
        input_pdf_path: 输入PDF文件路径
        output_dir: 输出目录路径
    """
    # 打开PDF文档
    doc = fitz.open(input_pdf_path)

    # 获取目录（TOC）
    toc = doc.get_toc()

    if not toc:
        print("PDF中没有找到目录信息")
        doc.close()
        return

    print(f"找到 {len(toc)} 个目录项")

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 统计成功生成的章节数量
    successful_chapters = 0

    # 遍历目录项并拆分PDF
    for i, (level, title, page_num) in enumerate(tqdm(toc, desc="处理章节")):
        # 清理标题作为文件名
        clean_title = re.sub(r'[<>:"/\\|?*]', '_', title)
        clean_title = clean_title[:50]  # 限制文件名长度

        # 提取章节编号，用于创建子文件夹
        chapter_number_match = re.match(r'^(\d+\.?\d*)', title)
        chapter_number = chapter_number_match.group(1) if chapter_number_match else str(i + 1)

        # 获取主章节编号（如1.1和1.2都属于1）
        main_chapter = chapter_number.split('.')[0]

        # 创建子文件夹路径
        subfolder_path = os.path.join(output_dir, main_chapter)
        os.makedirs(subfolder_path, exist_ok=True)

        # 确定章节起始页和结束页码（PDF页码从1开始）
        start_page = page_num - 1  # 转换为0基索引

        # 确定章节结束页码
        if i < len(toc) - 1:
            # 当前章节结束页是下一个章节的开始页的前一页
            next_page_num = toc[i + 1][2]
            end_page = next_page_num - 1
        else:
            # 最后一章到文档末尾
            end_page = doc.page_count

        # 转换为0基索引
        end_page_index = min(end_page - 1, doc.page_count - 1)

        # 确保页面范围有效
        if start_page > end_page_index or start_page < 0:
            print(f"跳过无效章节: {title} (第{page_num}页)")
            continue

        # 计算实际页数
        page_count = end_page_index - start_page + 1
        if page_count <= 0:
            print(f"跳过空章节: {title} (第{page_num}页)")
            continue

        # 创建新文档保存当前章节
        chapter_doc = fitz.open()

        # 使用批量复制提高效率
        chapter_doc.insert_pdf(doc, from_page=start_page, to_page=end_page_index)

        # 检查是否有页面要保存
        if chapter_doc.page_count > 0:
            # 保存章节PDF到对应的子文件夹
            chapter_path = os.path.join(subfolder_path, f"{i + 1:02d}_{clean_title}.pdf")
            chapter_doc.save(chapter_path)
            print(f"已保存章节: {chapter_path} (第{start_page + 1}页 - 第{end_page_index + 1}页)")
            successful_chapters += 1
        else:
            print(f"跳过空章节: {title} (无有效页面)")

        chapter_doc.close()

    # 在关闭文档前获取统计信息
    total_chapters = len(toc)
    doc.close()
    print(f"拆分完成！共生成 {successful_chapters} 个章节PDF文件")


def main():
    # 在这里设置输入和输出路径
    input_pdf_path = r"D:\书库\托马斯微积分第15版.pdf"  # 输入PDF文件路径
    output_dir = r"D:\书库\data"  # 输出目录路径

    # 检查输入文件是否存在
    if not os.path.exists(input_pdf_path):
        print(f"错误：找不到输入文件 {input_pdf_path}")
        return

    # 执行拆分
    extract_toc_and_split_pdf(input_pdf_path, output_dir)


if __name__ == "__main__":
    main()
