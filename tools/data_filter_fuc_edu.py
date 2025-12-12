import re
import jieba
from functools import lru_cache


class DataFilter:
    def __init__(self):
        # 需要检查的字段
        self.CHECK_FIELDS1 = (
            "题目背景知识",
            "题目内容",
            "对应答案",
        )
        self.CHECK_FIELDS2 = (
            "背景知识是否含图",
            "题目是否含图",
            "答案是否含图"
        )
        self.CHECK_FIELDS3 = (
            "背景知识是否含下划线",
            "题目是否含下划线",
            "题目是否含下划线"
        )
        self.CHECK_FIELDS4 = (
            "背景知识是否含表",
            "题目是否含表",
            "答案是否含表"
        )
        
        # 编译正则表达式以提高性能
        self.option_pattern = re.compile(
            r'(?:[Aa][\.:：．、]|[Bb][\.:：．、]|[Cc][\.:：．、]|[Dd][\.:：．、])|'
            r'(?:[Aa][\s]*[\u4e00-\u9fa5]|[Bb][\s]*[\u4e00-\u9fa5]|[Cc][\s]*[\u4e00-\u9fa5]|[Dd][\s]*[\u4e00-\u9fa5])|'
            r'(?:[Aa][\s]*[^\w\s]|[Bb][\s]*[^\w\s]|[Cc][\s]*[^\w\s]|[Dd][\s]*[^\w\s])',
            re.IGNORECASE
        )
        
        # 全角转半角映射表
        self.full_to_half_map = str.maketrans(
            'ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ',
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        )
        
        # 要剔除的"无效答案"内容
        self.INVALID_ANSWERS = {"", "略", "未找到对应答案", "答案不完整", "无"}
        
        # 要剔除的"无效题目"内容
        self.INVALID_QUESTION = {"未找到对应题目", "题目不完整", "无选项数据", "未识别到任何完整题目", "无", ""}
        
        # 听力题关键词
        self.LISTEN_KEYWORDS = {"材料", "对话", "短文"}
        
        # 图片相关关键词
        self.IMAGE_KEYWORDS = ('如图', '下图')
        
        # 特殊下划线关键词
        self.UNDERLINE_KEYWORDS = ('加点', '波浪线')

    @lru_cache(maxsize=1000)
    def _normalize_answer(self, ans):
        """标准化答案文本"""
        if not isinstance(ans, str):
            return ""
        # 标准化答案：移除空格、逗号、顿号等分隔符并转为半角大写
        normalized_ans = re.sub(r'[\s,、，]+', '', ans.strip())
        normalized_ans = normalized_ans.translate(self.full_to_half_map).upper()
        return normalized_ans

    def is_pure_letter_answer(self, ans):
        """检查答案是否是纯字母选项（支持全角和半角的A-Z字母），支持多选题格式"""
        # 处理空答案或非字符串类型
        if not ans:
            return False
            
        normalized_ans = self._normalize_answer(ans)
        
        # 检查是否只包含A-Z的字母（至少1个，最多不限制数量但需去重）
        if not re.fullmatch(r'[A-Z]+', normalized_ans):
            return False
            
        # 检查字母是否重复（多选题选项不应重复）
        if len(normalized_ans) != len(set(normalized_ans)):
            return False
            
        return True

    def _check_single_entry(self, entry, check_func, field_name=None, check_value=None):
        """检查单题型条目"""
        if "sub_qa" in entry:
            return False
            
        if field_name:
            value = entry.get(field_name, "")
            return check_value(value) if check_value else check_func(value)
        else:
            # 对所有CHECK_FIELDS1中的字段执行检查
            for field in self.CHECK_FIELDS1:
                value = entry.get(field, "")
                if check_func(field, value):
                    return True
            return False

    def _check_multi_entry(self, entry, check_func, field_name=None, check_value=None):
        """检查多题型条目"""
        sub_qa = entry.get("sub_qa")
        if not isinstance(sub_qa, list):
            return False
            
        for sub in sub_qa:
            if field_name:
                value = sub.get(field_name, "")
                if check_value(value) if check_value else check_func(value):
                    return True
            else:
                # 对所有CHECK_FIELDS1中的字段执行检查
                for field in self.CHECK_FIELDS1:
                    value = sub.get(field, "")
                    if check_func(field, value):
                        return True
        return False

    def is_emptyA(self, entry):
        """检查是否存在无效答案"""
        def check_answer_field(field, value):
            return field == "对应答案" and value in self.INVALID_ANSWERS
            
        # 单题型检查
        if self._check_single_entry(entry, check_answer_field):
            return (True, '答案缺失')
            
        # 多题型检查
        if self._check_multi_entry(entry, check_answer_field):
            return (True, '答案缺失')
            
        return False

    def is_emptyQ(self, entry):
        """检查是否存在无效题目"""
        def check_question_field(field, value):
            return field == "题目内容" and value in self.INVALID_QUESTION
            
        # 单题型检查
        if self._check_single_entry(entry, check_question_field):
            return (True, '题目缺失')
            
        # 多题型检查
        if self._check_multi_entry(entry, check_question_field):
            return (True, '题目缺失')
            
        return False

    def is_litsen(self, entry):
        """检查是否为听力题"""
        # 检查背景知识
        bg_knowledge = entry.get("题目背景知识")
        if bg_knowledge and isinstance(bg_knowledge, str):
            if "听" in bg_knowledge and any(item in bg_knowledge for item in self.LISTEN_KEYWORDS):
                return (True, '听力题')
        
        def check_listen_field(field, value):
            return (field == "题目内容" and 
                   isinstance(value, str) and 
                   "听" in value and 
                   any(item in value for item in self.LISTEN_KEYWORDS))
        
        # 单题型检查
        if self._check_single_entry(entry, check_listen_field):
            return (True, '听力题')
            
        # 多题型检查
        if self._check_multi_entry(entry, check_listen_field):
            return (True, '听力题')
            
        return False

    def is_relevant_pic(self, entry):
        """检查是否包含图片"""
        # 检查整个entry是否有图片标记
        entry_str = str(entry)
        if '<picture>' in entry_str or '<fig>' in entry_str:
            return (True, '图片多模题')
            
        # 检查背景知识是否含图
        if entry.get("背景知识是否含图", "") == "是":
            return (True, '图片多模题')
        
        def check_image_in_fields(field, value):
            # 检查是否明确标注含图
            if field in self.CHECK_FIELDS2 and value == "是":
                return True
                
            # 检查是否包含图片关键词
            if isinstance(value, str) and any(key in value for key in self.IMAGE_KEYWORDS):
                return True
                
            return False
        
        # 单题型检查
        if self._check_single_entry(entry, check_image_in_fields):
            return (True, '图片多模题')
            
        # 多题型检查
        if self._check_multi_entry(entry, check_image_in_fields):
            return (True, '图片多模题')
            
        return False

    def is_relevant_table(self, entry):
        """检查是否包含表格"""
        # 检查背景知识是否含表
        if entry.get("背景知识是否含表", "") == "是":
            return (True, '题目含表')
        
        def check_table_field(field, value):
            return field in self.CHECK_FIELDS4 and value == "是"
        
        # 单题型检查
        if self._check_single_entry(entry, check_table_field):
            return (True, '题目含表')
            
        # 多题型检查
        if self._check_multi_entry(entry, check_table_field):
            return (True, '题目含表')
            
        return False

    def is_relevant_line_strict(self, entry):
        """严格检查是否包含下划线"""
        # 检查背景知识是否含下划线
        if entry.get("背景知识是否含下划线", "") == "是":
            return (True, '特殊下划线')
        
        def check_underline_strict_field(field, value):
            # 检查是否明确标注含下划线
            if field in self.CHECK_FIELDS3 and value == "是":
                return True
                
            return False
        
        def check_underline_keywords(entry_data):
            """检查特殊关键词"""
            answer = entry_data.get("对应答案", "") or ""
            content = entry_data.get("题目内容", "") or ""
            return any(keyword in (answer + content) for keyword in self.UNDERLINE_KEYWORDS)
        
        # 单题型检查
        if self._check_single_entry(entry, check_underline_strict_field):
            return (True, '特殊下划线')
            
        # 检查关键词
        if not ("sub_qa" in entry) and check_underline_keywords(entry):
            return (True, '特殊下划线')
            
        # 多题型检查
        if self._check_multi_entry(entry, check_underline_strict_field):
            return (True, '特殊下划线')
            
        # 检查子题关键词
        sub_qa = entry.get("sub_qa")
        if isinstance(sub_qa, list):
            for sub in sub_qa:
                if check_underline_keywords(sub):
                    return (True, '特殊下划线')
                    
        return False

    def is_relevant_line_lenient(self, entry):
        """宽松检查是否包含下划线"""
        def check_underline_keywords(entry_data):
            """检查特殊关键词"""
            answer = entry_data.get("对应答案", "") or ""
            content = entry_data.get("题目内容", "") or ""
            combined_text = str(answer) + str(content)
            return any(keyword in combined_text for keyword in self.UNDERLINE_KEYWORDS)
        
        # 单题型检查
        if not ("sub_qa" in entry) and check_underline_keywords(entry):
            return (True, '特殊下划线')
            
        # 多题型检查
        sub_qa = entry.get("sub_qa")
        if isinstance(sub_qa, list):
            for sub in sub_qa:
                if check_underline_keywords(sub):
                    return (True, '特殊下划线')
                    
        return False

    def has_complete_options(self, question_content):
        """检查题目内容中是否包含完整的ABCD选项"""
        if not isinstance(question_content, str):
            return False
            
        # 使用预编译的正则表达式检测选项
        found_options = set()
        for match in self.option_pattern.finditer(question_content):
            option_char = match.group()[0].upper()
            found_options.add(option_char)
            
        # 确保找到所有基本选项（A-D）
        return found_options.issuperset({'A', 'B', 'C', 'D'})

    def option_not_complete(self, entry):
        """检查选项是否完整"""
        def check_option_completeness(entry_data):
            answer = entry_data.get("对应答案", "") or ""
            content = entry_data.get("题目内容", "") or ""
            return (self.is_pure_letter_answer(answer) and 
                   not self.has_complete_options(content))
        
        # 单题型检查
        if not ("sub_qa" in entry) and check_option_completeness(entry):
            return (True, '选项不全')
            
        # 多题型检查
        sub_qa = entry.get("sub_qa")
        if isinstance(sub_qa, list):
            for sub in sub_qa:
                if check_option_completeness(sub):
                    return (True, '选项不全')
                    
        return False

    def is_too_short(self, entry, th_length=20):
        """检查题目是否过短"""
        # 单题型
        if "sub_qa" not in entry:
            value = entry.get("题目内容")
            if value is None:
                value = ""
            if len(jieba.lcut(str(value))) < th_length:
                return (True, '题目过短')
        
        # 多题型
        if isinstance(entry.get("sub_qa"), list):
            value_bg = entry.get("题目背景知识")
            if value_bg is None:
                value_bg = ""
            else:
                value_bg = str(value_bg)

            for sub in entry["sub_qa"]:
                value = sub.get("题目内容")
                if value is None:
                    value = ""
                else:
                    value = str(value)

                total_tokens = len(jieba.lcut(value_bg) + jieba.lcut(value))
                if total_tokens < (1.5 * th_length):
                    return (True, '题目过短')
        
        return False

    def check_english(self, record):
        """英语数据检查"""
        functions = [
            (self.is_relevant_pic, None),
            (self.is_emptyQ, None),
            (self.is_litsen, None),
            (self.is_too_short, 20),
            (self.is_emptyA, None),
        ]

        result = False
        for func, param in functions:
            if param is not None:
                result = func(record, param)
            else:
                result = func(record)
            if result is not False:
                break
        return result

    def check_politics(self, record):
        """政治数据检查"""
        functions = [
            (self.is_relevant_pic, None),
            (self.is_emptyQ, None),
            (self.is_emptyA, None),
        ]

        result = False
        for func, param in functions:
            result = func(record)
            if result is not False:
                break
        return result

    def check_history(self, record):
        """历史数据检查"""
        functions = [
            (self.is_relevant_pic, None),
            (self.is_emptyQ, None),
            (self.is_relevant_table, None),
            (self.is_relevant_line_strict, None),
            (self.is_emptyA, None),
        ]

        result = False
        for func, param in functions:
            result = func(record)
            if result is not False:
                break
        return result

    def check_chinese(self, record):
        """语文数据检查"""
        functions = [
            (self.is_relevant_pic, None),
            (self.is_emptyQ, None),
            (self.is_relevant_table, None),
            (self.is_relevant_line_lenient, None),
            (self.option_not_complete, None),
            (self.is_too_short, 10),
            (self.is_emptyA, None),
        ]

        result = False
        for func, param in functions:
            if param is not None:
                result = func(record, param)
            else:
                result = func(record)
            if result is not False:
                break
        return result