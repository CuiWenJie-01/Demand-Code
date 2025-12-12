import json
import os, sys
import logging
from collections import defaultdict
from tqdm import tqdm
from data_filter_fuc_edu import *
from rapidfuzz import process, fuzz
import hashlib


def check_dedup(text1, text2, ps_th=80, fs_th=80):
    """
    使用 rapidfuzz 进行文本相似度比较，提高去重效率
    """
    partial_similarity = fuzz.partial_ratio(text1, text2)  # 部分匹配比率
    full_similarity = fuzz.ratio(text1, text2)  # 完全匹配比率
    # 两个相似度任意一个超过阈值都判定重复
    return partial_similarity >= ps_th or full_similarity >= fs_th


def replace_with_none(lst, target):
    """
    将列表中所有等于指定元素的项替换为 None。
    """
    for i, item in enumerate(lst):
        if item == target:
            lst[i] = None
    return lst


def sanitize_record(record):
    """
    在写入前标准化 None 字段为空字符串
    """
    # 处理顶层字段
    if record.get("题目背景知识") is None:
        record["题目背景知识"] = ""
    
    # 处理 sub_qa 中的字段
    if "sub_qa" in record and isinstance(record["sub_qa"], list):
        for qa in record["sub_qa"]:
            if qa.get("题目编号") is None:
                qa["题目编号"] = ""
            if qa.get("题目内容") is None:
                qa["题目内容"] = ""
            if qa.get("对应答案") is None:
                qa["对应答案"] = ""
    else:
        # 单题型
        if record.get("题目编号") is None:
            record["题目编号"] = ""
        if record.get("题目内容") is None:
            record["题目内容"] = ""
        if record.get("对应答案") is None:
            record["对应答案"] = ""
    return record


class QuestionDeduplicator:
    """
    题目去重器，用于高效处理大量题目的去重工作
    """
    def __init__(self):
        self.record_list = []  # 具体记录
        self.final_dedup_record_index = []  # 决定最终记录是否写入去重文件
        self.q_list = []  # 所有题目信息，方便快速查重
        self.q_dict = defaultdict(lambda: defaultdict(list))  # 所有题目在record中对应的index
        self.record_index = -1
        self.data_filter = DataFilter()
        # 使用哈希表加速查找
        self.q_hash = {}  # 题目内容的hash值到题目列表索引的映射

    def _get_text_hash(self, text):
        """
        计算文本的hash值，用于快速筛选候选匹配项
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:8]

    def _find_similar_questions(self, q):
        """
        使用hash优化的方法寻找相似题目
        """
        # 如果q_list为空，直接返回None
        if not self.q_list:
            return None
            
        # 使用hash进行快速筛选
        q_hash = self._get_text_hash(q)
        candidates = []
        
        # 如果有相同的hash，则优先检查这些候选
        if q_hash in self.q_hash:
            for idx in self.q_hash[q_hash]:
                candidates.append((self.q_list[idx], idx))
        
        # 如果候选较少，也加入一些相邻的题目作为候选
        if len(candidates) < 10 and len(self.q_list) > 0:
            # 添加最近的几个题目作为候选
            start_idx = max(0, len(self.q_list) - 10)
            for i in range(start_idx, len(self.q_list)):
                if i not in [idx for _, idx in candidates]:
                    candidates.append((self.q_list[i], i))
        
        # 如果仍然没有候选，则使用全部题目
        if not candidates:
            candidates = [(q_text, i) for i, q_text in enumerate(self.q_list)]
            
        # 使用rapidfuzz找出最佳匹配
        if candidates:
            candidate_texts = [text for text, _ in candidates]
            best_match = process.extractOne(q, candidate_texts)
            if best_match is not None:
                best_text, score, idx = best_match
                # 找到原始索引
                original_idx = candidates[idx][1]
                return best_text, original_idx
                
        return None

    def _process_shared_questions(self, record):
        """
        处理共享题干数据的去重
        """
        dedup_record_index_list = []

        # 遍历sub_qa中的所有题目检查是否有重复
        for sub_i, qa in enumerate(record['sub_qa']):
            q = qa['题目内容']

            # 查找相似题目
            match_result = self._find_similar_questions(q)
            if match_result is not None:
                best_match_text, best_match_idx = match_result
                is_dedup = check_dedup(q, best_match_text)
                dedup_record_index = self.q_dict[best_match_text]['record_index']

                for i in dedup_record_index:
                    if is_dedup and (i is not None):
                        dedup_record_index_list.append(i)

            # 更新题目列表和字典
            self.q_list.append(q)
            q_hash = self._get_text_hash(q)
            if q_hash not in self.q_hash:
                self.q_hash[q_hash] = []
            self.q_hash[q_hash].append(len(self.q_list) - 1)
            
            self.q_dict[q]['record_index'].append(self.record_index)
            self.q_dict[q]['sub_index'].append(sub_i)

        # 处理重复情况
        return self._handle_shared_duplicates(record, dedup_record_index_list)

    def _handle_shared_duplicates(self, record, dedup_record_index_list):
        """
        处理共享题目的重复情况
        """
        # 无重复
        if not dedup_record_index_list:
            self.final_dedup_record_index.append(self.record_index)
            return True

        # 有重复
        if len(set(dedup_record_index_list)) > 1:
            self.final_dedup_record_index.append(None)
            logging.info(f'==========与多个记录重复==========\n当前记录:{record}\n重复记录:{[self.record_list[i] for i in dedup_record_index_list]}')
            return True

        # 判断到底是留历史记录还是新记录
        history_record = self.record_list[dedup_record_index_list[0]]
        if 'sub_qa' in history_record:  # 历史记录为共享题干
            logging.info(f'共享题干-共享题干重复：\n{record}\n{history_record}')
            bg = record['题目背景知识']
            history_bg = history_record['题目背景知识']
            is_dedup = check_dedup(bg, history_bg)
            if is_dedup:  # 背景知识重复, 保留当前最新记录
                try:
                    self.final_dedup_record_index[dedup_record_index_list[0]] = None  # 删除历史记录
                except IndexError:
                    self.final_dedup_record_index.append(None)
                    logging.info(f'共享题干内部小问重复，可能有识别错误\n当前记录:{record}')
                    return True
                for history_qa in history_record['sub_qa']:
                    history_q = history_qa['题目内容']
                    self.q_dict[history_q]['record_index'] = replace_with_none(
                        self.q_dict[history_q]['record_index'], 
                        dedup_record_index_list[0]
                    )
                self.final_dedup_record_index.append(self.record_index)
                return True
            else:  # 背景信息不重复，认为两条记录不重复
                self.final_dedup_record_index.append(self.record_index)
                return True
        else:  # 历史记录为独立题干，没有背景信息，选择保留当前记录
            logging.info(f'共享题干-独立题干重复：\n{record}\n{history_record}')
            self.final_dedup_record_index[dedup_record_index_list[0]] = None  # 删除历史记录
            history_q = history_record['题目内容']
            self.q_dict[history_q]['record_index'] = replace_with_none(
                self.q_dict[history_q]['record_index'], 
                dedup_record_index_list[0]
            )
            self.final_dedup_record_index.append(self.record_index)
            return True

    def _process_single_question(self, record):
        """
        处理独立题干数据的去重
        """
        q = record['题目内容']
        
        # 查找相似题目
        match_result = self._find_similar_questions(q)
        if match_result is not None:
            best_match_text, best_match_idx = match_result
            is_dedup = check_dedup(q, best_match_text)
            dedup_record_index = self.q_dict[best_match_text]['record_index']
            unique_non_none_elements = {x for x in dedup_record_index if x is not None}
            
            # 判断是否一个best_match_text对应了多个记录
            if len(unique_non_none_elements) > 1:
                self.final_dedup_record_index.append(None)
                valid_dup_indices = [i for i in dedup_record_index if i is not None]
                logging.info(f'==========与多个记录重复==========\n当前记录:{record}\n重复记录:{[self.record_list[i] for i in valid_dup_indices]}')
                # 更新题目列表和字典
                self._update_question_data(q)
                return True

            if is_dedup and (len(unique_non_none_elements) > 0):  # 重复的情况
                i = unique_non_none_elements.pop()
                history_record = self.record_list[i]
                if 'sub_qa' in history_record:  # 历史记录为共享题干，保留历史记录
                    logging.info(f'独立题干-共享题干重复：\n{record}\n{history_record}')
                    # 更新题目列表和字典
                    self._update_question_data(q)
                    self.final_dedup_record_index.append(None)
                    return True
                else:  # 历史记录也为独立题干时，保留最新的
                    logging.info(f'独立题干-独立题干重复：\n{record}\n{history_record}')
                    self.final_dedup_record_index[i] = None
                    history_q = history_record['题目内容']
                    self.q_dict[history_q]['record_index'] = replace_with_none(
                        self.q_dict[history_q]['record_index'], 
                        i
                    )

        # 更新题目列表和字典
        self._update_question_data(q)
        self.final_dedup_record_index.append(self.record_index)
        return True

    def _update_question_data(self, q):
        """
        更新题目数据到列表和字典中
        """
        self.q_list.append(q)
        q_hash = self._get_text_hash(q)
        if q_hash not in self.q_hash:
            self.q_hash[q_hash] = []
        self.q_hash[q_hash].append(len(self.q_list) - 1)
        
        self.q_dict[q]['record_index'].append(self.record_index)
        self.q_dict[q]['sub_index'].append(None)

    def _filter_record(self, record):
        """
        对记录进行初步筛选
        """
        source_type = record['source_type']
        # 粗筛
        if '英语' in source_type:
            check_result = self.data_filter.check_english(record)
        elif '政治' in source_type or '道德与法治' in source_type:
            check_result = self.data_filter.check_politics(record)
        elif '历史' in source_type:
            check_result = self.data_filter.check_history(record)
        elif '语文' in source_type:
            check_result = self.data_filter.check_chinese(record)
        elif '文综' in source_type:
            check_result = self.data_filter.check_history(record)
        elif '雅思托福真题01' in source_type:
            check_result = self.data_filter.check_english(record)
        else:
            logging.error(f'source type错误！')
            self.final_dedup_record_index.append(None)
            record['err_type'] = '未知source_type'
            return False, record

        if check_result is not False:
            self.final_dedup_record_index.append(None)
            _, record['err_type'] = check_result
            return False, record

        return True, record

    def process_record(self, record):
        """
        处理单条记录
        """
        self.record_list.append(record)
        self.record_index += 1

        # 初步筛选
        passed_filter, processed_record = self._filter_record(record)
        if not passed_filter:
            return processed_record

        # 根据题型分别处理
        if 'sub_qa' in record:
            # 共享题干数据
            self._process_shared_questions(record)
        else:
            # 独立题干数据
            self._process_single_question(record)

        return record

    def write_results(self, output_file_path):
        """
        将去重后的结果写入文件
        """
        split_qa_num = 0
        with open(output_file_path, 'w', encoding='utf-8') as output_file:
            for index in self.final_dedup_record_index:
                if index is not None:
                    record = self.record_list[index]
                    # 标准化 None 字段为空字段
                    record = sanitize_record(record)

                    if "sub_qa" in record:
                        split_qa_num += len(record["sub_qa"])
                    else:
                        split_qa_num += 1
                    output_file.write(json.dumps(record, ensure_ascii=False) + '\n')
        
        return split_qa_num


def dedup_by_file(input_file_path, output_file_path, err_file_path):
    """
    对单个文件进行去重处理
    """
    deduplicator = QuestionDeduplicator()

    with open(input_file_path, 'r', encoding='utf-8') as input_file, \
         open(err_file_path, 'w', encoding='utf-8') as err_file:
        
        for line in input_file:
            record = json.loads(line)
            processed_record = deduplicator.process_record(record)
            
            # 如果记录被过滤掉，写入错误文件
            if processed_record is not record:
                err_file.write(json.dumps(processed_record, ensure_ascii=False) + '\n')

    total_num = len(deduplicator.final_dedup_record_index)
    count_none = len(list(filter(lambda x: x is None, deduplicator.final_dedup_record_index)))
    left_num = total_num - count_none
    split_qa_num = deduplicator.write_results(output_file_path)
    
    return total_num, count_none, left_num, split_qa_num


if __name__ == "__main__":
    # 请确保 Pasted_Text_1754376870865.txt 文件与脚本在同一目录下
    # 或者修改 input_jsonl_file 为文件的完整路径、
    # batch = '8.19重新传输文件-50'
    # batch = '8.18重新传输文件-22'
    root = sys.argv[1]
    batch = sys.argv[2]
    input_dir = rf"{root}/{batch}/6_extract_qa_{batch}" 
    output_dir = rf"{root}/{batch}/7_qa_filter_{batch}"
    # input_dir = rf"/yrfs2/ftpdata/zyzhou28/code/文科切题ocr多模/{batch}/5_qa_filter" 
    # output_dir = rf"/yrfs2/ftpdata/zyzhou28/code/文科切题ocr多模/{batch}/5_qa_filter_twice"
    os.makedirs(output_dir, exist_ok=True)
    err_log = f"{output_dir}/日志.log"
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=err_log,
        filemode='w'
    )

    sub_folders = [d for d in os.listdir(input_dir)
                   if os.path.isdir(os.path.join(input_dir, d))]
    if not sub_folders:
        print(f"在目录 {input_dir} 中未找到子文件夹")
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(f"找到 {len(sub_folders)} 个子文件夹，开始处理...")

    for sub_folder in sub_folders:
        subfolder_path = os.path.join(input_dir, sub_folder)
        output_subfolder = os.path.join(output_dir, sub_folder)
        os.makedirs(output_subfolder, exist_ok=True)
        os.makedirs(output_subfolder+'err', exist_ok=True)
        total_num_sub_folder, count_none_sub_folder, left_num_sub_folder, split_qa_sub_folder = 0, 0, 0, 0
        for filename in tqdm(os.listdir(subfolder_path)):
            if filename.endswith(".json"):
                input_file_path = os.path.join(subfolder_path, filename)
                output_file_path = os.path.join(output_subfolder, filename)
                err_file_path = os.path.join(output_subfolder+'err', f'err_{filename}')
                # print(f'正在处理{input_file_path}')
                total_num, count_none, left_num, split_qa_num = dedup_by_file(input_file_path, output_file_path, err_file_path)
                total_num_sub_folder += total_num
                count_none_sub_folder += count_none
                left_num_sub_folder += left_num
                split_qa_sub_folder += split_qa_num
        logging.info(f'批次{sub_folder}: 原始题量-{total_num_sub_folder} 筛除题量-{count_none_sub_folder} 留存题量-{left_num_sub_folder} 拆分题量-{split_qa_sub_folder}')
        print(f'批次{sub_folder}: 原始题量-{total_num_sub_folder} 筛除题量-{count_none_sub_folder} 留存题量-{left_num_sub_folder} 拆分题量-{split_qa_sub_folder}')