import os
import shutil
import time
from pathlib import Path
from tqdm import tqdm
import threading
from concurrent.futures import ThreadPoolExecutor
import argparse

# 删除原来的路径定义，因为现在使用交互式输入
# SOURCE_PATH = "/DL_data_new/ftpdata/wjcui/code/Test"  # 源路径，例如: "/DMXCC-code/DL_Data/ftpdata/jjhu32/data"
# DEST_PATH = "/DMXZYB1/ftpdata/wjcui"    # 目标路径，例如: "/DMXCC-code/DL_Data/output_platform_data"

# 复制配置参数
BUFFER_SIZE = 64 * 1024  # 64KB 缓冲区
MAX_WORKERS = 4          # 最大线程数
CHUNK_SIZE = 10 * 1024 * 1024  # 10MB 分块大小用于大文件

class FastCopy:
    def __init__(self, source, destination, max_workers=4, buffer_size=64*1024, chunk_size=10*1024*1024):
        self.source = Path(source)
        self.destination = Path(destination)
        self.max_workers = max_workers
        self.buffer_size = buffer_size
        self.chunk_size = chunk_size
        self.total_files = 0
        self.total_size = 0
        self.copied_size = 0
        self.progress_lock = threading.Lock()
        
    def calculate_total(self):
        """计算总文件数和总大小"""
        print("正在扫描文件...")
        self.total_files = 0
        self.total_size = 0
        
        if self.source.is_file():
            self.total_files = 1
            self.total_size = self.source.stat().st_size
        else:
            # 使用os.walk遍历所有文件
            for root, dirs, files in os.walk(self.source):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        self.total_size += file_path.stat().st_size
                        self.total_files += 1
                    except (OSError, FileNotFoundError):
                        pass
                        
        print(f"总共需要处理 {self.total_files} 个文件, 总大小: {self.format_bytes(self.total_size)}")
    
    def format_bytes(self, bytes_num):
        """格式化字节数为可读格式"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_num < 1024.0:
                return f"{bytes_num:.2f} {unit}"
            bytes_num /= 1024.0
        return f"{bytes_num:.2f} PB"
    
    def copy_file_with_progress(self, src_file, dst_file):
        """带进度跟踪的文件复制"""
        try:
            # 确保目标目录存在
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            
            file_size = src_file.stat().st_size
            
            # 对于小文件直接复制
            if file_size <= self.chunk_size:
                shutil.copy2(src_file, dst_file)
                with self.progress_lock:
                    self.copied_size += file_size
            else:
                # 对于大文件分块复制并显示进度
                with open(src_file, 'rb') as fsrc, open(dst_file, 'wb') as fdst:
                    copied = 0
                    while copied < file_size:
                        chunk = fsrc.read(min(self.chunk_size, file_size - copied))
                        if not chunk:
                            break
                        fdst.write(chunk)
                        copied += len(chunk)
                        with self.progress_lock:
                            self.copied_size += len(chunk)
                
            # 保持元数据
            shutil.copystat(src_file, dst_file)
            return True
        except Exception as e:
            print(f"复制文件 {src_file} 时出错: {e}")
            return False
    
    def move_file_with_progress(self, src_file, dst_file):
        """带进度跟踪的文件移动"""
        try:
            # 确保目标目录存在
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            
            file_size = src_file.stat().st_size
            
            # 对于小文件直接移动
            if file_size <= self.chunk_size:
                shutil.move(str(src_file), str(dst_file))
                with self.progress_lock:
                    self.copied_size += file_size
            else:
                # 对于大文件先复制再删除
                success = self.copy_file_with_progress(src_file, dst_file)
                if success:
                    src_file.unlink()  # 删除原文件
                return success
                
            return True
        except Exception as e:
            print(f"移动文件 {src_file} 时出错: {e}")
            return False
    
    def copy_single_file(self, src_file, dst_file):
        """复制单个文件"""
        return self.copy_file_with_progress(src_file, dst_file)
    
    def move_single_file(self, src_file, dst_file):
        """移动单个文件"""
        return self.move_file_with_progress(src_file, dst_file)
    
    def copy_directory(self):
        """复制整个目录"""
        # 计算要复制的文件总数和总大小
        self.calculate_total()
        
        # 创建目标根目录
        if self.source.is_file():
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            files_to_copy = [(self.source, self.destination)]
        else:
            # 保留源文件夹结构，创建同名的目标文件夹
            # 例如源是 ".../试题包/1"，目标是 ".../Test"，则最终结果应该是 ".../Test/1"
            target_root_dir = self.destination / self.source.name
            target_root_dir.mkdir(parents=True, exist_ok=True)
            files_to_copy = []
            for root, dirs, files in os.walk(self.source):
                for file in files:
                    src_file = Path(root) / file
                    # 计算相对于源根目录的路径
                    rel_path = src_file.relative_to(self.source)
                    # 构建目标文件路径
                    dst_file = target_root_dir / rel_path
                    files_to_copy.append((src_file, dst_file))
        
        # 使用tqdm显示整体进度
        start_time = time.time()
        with tqdm(total=self.total_size, unit='B', unit_scale=True, desc="复制进度") as pbar:
            # 使用线程池并发复制文件
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for src_file, dst_file in files_to_copy:
                    future = executor.submit(self.copy_single_file, src_file, dst_file)
                    future.add_done_callback(lambda f: pbar.update(self.get_last_file_size()))
                    futures.append(future)
                
                # 等待所有任务完成
                for future in futures:
                    future.result()
        
        elapsed_time = time.time() - start_time
        print(f"\n复制完成! 耗时: {elapsed_time:.2f} 秒")
        print(f"平均速度: {self.format_bytes(self.total_size/elapsed_time)}/s")
    
    def move_directory(self):
        """移动整个目录"""
        # 计算要移动的文件总数和总大小
        self.calculate_total()
        
        # 创建目标根目录
        if self.source.is_file():
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            files_to_move = [(self.source, self.destination)]
        else:
            # 保留源文件夹结构，创建同名的目标文件夹
            target_root_dir = self.destination / self.source.name
            target_root_dir.mkdir(parents=True, exist_ok=True)
            files_to_move = []
            for root, dirs, files in os.walk(self.source):
                for file in files:
                    src_file = Path(root) / file
                    # 计算相对于源根目录的路径
                    rel_path = src_file.relative_to(self.source)
                    # 构建目标文件路径
                    dst_file = target_root_dir / rel_path
                    files_to_move.append((src_file, dst_file))
        
        # 使用tqdm显示整体进度
        start_time = time.time()
        with tqdm(total=self.total_size, unit='B', unit_scale=True, desc="移动进度") as pbar:
            # 使用线程池并发移动文件
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for src_file, dst_file in files_to_move:
                    future = executor.submit(self.move_single_file, src_file, dst_file)
                    future.add_done_callback(lambda f: pbar.update(self.get_last_file_size()))
                    futures.append(future)
                
                # 等待所有任务完成
                for future in futures:
                    future.result()
        
        # 如果是目录移动，删除源目录
        if self.source.is_dir():
            try:
                shutil.rmtree(self.source)
            except Exception as e:
                print(f"删除源目录 {self.source} 时出错: {e}")
        
        elapsed_time = time.time() - start_time
        print(f"\n移动完成! 耗时: {elapsed_time:.2f} 秒")
        print(f"平均速度: {self.format_bytes(self.total_size/elapsed_time)}/s")
    
    def get_last_file_size(self):
        """获取上一个复制完成的文件大小（简化实现）"""
        # 在实际应用中，可能需要更精确的方法来跟踪每个文件的大小
        # 这里我们返回一个估计值
        return self.chunk_size
    
    def run_copy(self):
        """运行复制任务"""
        if not self.source.exists():
            print(f"源路径不存在: {self.source}")
            return
        
        print(f"开始从 '{self.source}' 复制到 '{self.destination}'")
        
        try:
            if self.source.is_file():
                print("检测到单个文件复制")
                self.calculate_total()
                start_time = time.time()
                
                with tqdm(total=self.total_size, unit='B', unit_scale=True, desc="复制进度") as pbar:
                    self.copy_file_with_progress(self.source, self.destination)
                    pbar.update(self.total_size)
                
                elapsed_time = time.time() - start_time
                print(f"\n复制完成! 耗时: {elapsed_time:.2f} 秒")
                print(f"平均速度: {self.format_bytes(self.total_size/elapsed_time)}/s")
            else:
                print("检测到目录复制")
                self.copy_directory()
        except KeyboardInterrupt:
            print("\n用户中断了复制操作")
        except Exception as e:
            print(f"复制过程中发生错误: {e}")
    
    def run_move(self):
        """运行移动任务"""
        if not self.source.exists():
            print(f"源路径不存在: {self.source}")
            return
        
        print(f"开始从 '{self.source}' 移动到 '{self.destination}'")
        
        try:
            if self.source.is_file():
                print("检测到单个文件移动")
                self.calculate_total()
                start_time = time.time()
                
                with tqdm(total=self.total_size, unit='B', unit_scale=True, desc="移动进度") as pbar:
                    self.move_file_with_progress(self.source, self.destination)
                    pbar.update(self.total_size)
                
                elapsed_time = time.time() - start_time
                print(f"\n移动完成! 耗时: {elapsed_time:.2f} 秒")
                print(f"平均速度: {self.format_bytes(self.total_size/elapsed_time)}/s")
            else:
                print("检测到目录移动")
                self.move_directory()
        except KeyboardInterrupt:
            print("\n用户中断了移动操作")
        except Exception as e:
            print(f"移动过程中发生错误: {e}")

def get_user_input():
    """获取用户输入的源路径和目标路径"""
    print("=" * 50)
    print("欢迎使用文件快速复制/移动工具")
    print("=" * 50)
    
    while True:
        source = input("请输入源路径(SOURCE_PATH): ").strip()
        destination = input("请输入目标路径(DEST_PATH): ").strip()
        
        print(f"\n您输入的路径信息:")
        print(f"源路径: {source}")
        print(f"目标路径: {destination}")
        
        confirm = input("\n确认路径是否正确？(y/n): ").strip().lower()
        if confirm in ['y', 'yes', '是', '']:
            return source, destination
        else:
            print("请重新输入路径信息。\n")

def get_operation_choice():
    """获取用户操作选择"""
    print("\n请选择操作类型:")
    print("1: 复制")
    print("2: 移动")
    
    while True:
        choice = input("请输入选项 (1 或 2): ").strip()
        if choice in ['1', '2']:
            return choice
        else:
            print("无效选项，请输入 1 或 2")

def main():
    # 获取用户输入的路径
    source, destination = get_user_input()
    
    # 获取用户操作选择
    operation = get_operation_choice()
    
    if not source or not destination:
        print("源路径和目标路径不能为空!")
        return
    
    copier = FastCopy(source, destination, MAX_WORKERS, BUFFER_SIZE, CHUNK_SIZE)
    
    if operation == '1':
        copier.run_copy()
    elif operation == '2':
        copier.run_move()

if __name__ == "__main__":
    main()