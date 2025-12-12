import os
import re

def rename_folders(base_path):
    """
    批量重命名文件夹，保留学年级和学科名称部分
    
    Args:
        base_path (str): 包含需要重命名的子文件夹的根目录路径
    """
    # 检查基础路径是否存在
    if not os.path.exists(base_path):
        print(f"错误：路径 {base_path} 不存在")
        return
    
    # 遍历基础路径下的所有文件夹
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        
        # 只处理文件夹
        if os.path.isdir(folder_path):
            # 使用正则表达式提取年级和学科名称（初中/高中 + 学科）
            # 匹配模式：1104-单模交付数据-169本_初中历史-28_教辅 提取 初中历史
            match = re.search(r'([初高][中][^_-]+?)-\d+_', folder_name)
            
            if match:
                # 提取年级和学科名称
                grade_subject_name = match.group(1)
                
                # 构造新文件夹名称
                new_folder_path = os.path.join(base_path, grade_subject_name)
                
                # 检查目标文件夹是否已存在
                if os.path.exists(new_folder_path):
                    print(f"警告：文件夹 {grade_subject_name} 已存在，跳过 {folder_name}")
                    continue
                
                # 重命名文件夹
                try:
                    os.rename(folder_path, new_folder_path)
                    print(f"成功重命名: {folder_name} -> {grade_subject_name}")
                except Exception as e:
                    print(f"重命名失败 {folder_name}: {str(e)}")
            else:
                print(f"无法从文件夹名 {folder_name} 中提取年级和学科信息")

if __name__ == "__main__":
    # 在这里设置你的输入路径
    input_path = "/DL_data_new/ftpdata/wjcui/code/教辅/1031-单模交付数据-267本/10_final_llm_filter_1031-单模交付数据-267本/available"
    
    # 调用重命名函数
    rename_folders(input_path)