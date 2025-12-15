import os
import shutil
import subprocess
import logging
import concurrent.futures  # 新增并行处理支持

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 预留的删除路径列表
DELETE_PATHS = [
    "/DMXZYB1/ftpdata/wjcui/Test/教辅/1128-单模文件提交-239本/崔文杰_1128-单模文件提交-239本_doubao-seed-1-6-thinking-250715-多模_认知基础-SFT"
]

def delete_path(path):
    """
    删除指定路径的文件或文件夹（保持原子操作）
    
    Args:
        path (str): 要删除的文件或文件夹路径
    """
    if not os.path.exists(path):
        logger.warning(f"路径不存在: {path}")
        return False
    
    try:
        if os.path.isfile(path):
            os.remove(path)
            logger.info(f"成功删除文件: {path}")
        elif os.path.isdir(path):
            # 使用系统级命令加速大目录删除
            subprocess.run(['rm', '-rf', path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"成功删除文件夹: {path}")
        else:
            logger.warning(f"未知的文件类型: {path}")
            return False
        return True
    except Exception as e:
        logger.error(f"删除失败 {path}: {str(e)}")
        return False

def main():
    """
    主函数，使用进程池并行删除所有预设路径
    """
    if not DELETE_PATHS:
        logger.info("没有设置要删除的路径，请在DELETE_PATHS中添加路径")
        return
    
    logger.info(f"开始并行删除 {len(DELETE_PATHS)} 个项目...")
    success_count = 0
    
    # 创建与CPU核心数匹配的进程池
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # 提交所有删除任务并获取结果迭代器
        results = executor.map(delete_path, DELETE_PATHS)
        
        # 统计成功数量
        for result in results:
            if result:
                success_count += 1
    
    logger.info(f"并行删除完成，成功 {success_count}/{len(DELETE_PATHS)} 个项目")

if __name__ == "__main__":
    print("警告：此程序将永久删除文件和文件夹！")
    print("并行删除将同时处理多个路径，速度更快但无法中断单个任务")
    print("请确保已在DELETE_PATHS变量中正确配置要删除的路径。")
    confirm = input("确认执行并行删除操作？(输入 'y' 确认): ")
    
    if confirm.lower() == 'y':
        main()
    else:
        print("操作已取消")