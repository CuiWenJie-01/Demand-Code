import yaml
from pathlib import Path
from typing import Optional, Dict, Any


class PromptLoader:
    """Prompt加载器，用于根据不同阶段和学科构建prompt"""

    # 定义特殊学科映射关系
    SPECIAL_SUBJECTS = {"地理", "信息科技", "信息技术"}
    CHINESE_SUBJECT = "语文"

    def __init__(self, config_path: str = "../prompts.yaml"):
        """
        初始化PromptLoader
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件 {config_path} 不存在")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def get_subject_config(self, subject: str) -> dict:
        """
        获取指定学科的配置
        
        Args:
            subject: 学科名称
            
        Returns:
            学科配置字典
            
        Raises:
            ValueError: 当学科未在配置中定义时
        """
        subjects = self.config.get("subjects", {})
        if subject not in subjects:
            raise ValueError(f"学科 '{subject}' 未在prompt配置中定义")
        return subjects[subject]

    def get_question_types(self, subject: str) -> str:
        """
        获取学科的问题类型
        
        Args:
            subject: 学科名称
            
        Returns:
            问题类型字符串
        """
        return self.get_subject_config(subject)["question_types"]

    def get_extract_qa_rules(self, subject: str) -> str:
        """
        获取学科的提取问答规则
        
        Args:
            subject: 学科名称
            
        Returns:
            提取问答规则字符串
        """
        rules = self.get_subject_config(subject).get("extract_qa_rules", "")
        return rules if rules is not None else ""

    def get_check_rules(self, subject: str) -> str:
        """
        获取学科的检查规则
        
        Args:
            subject: 学科名称
            
        Returns:
            检查规则字符串
        """
        rules = self.get_subject_config(subject).get("check_rules", "")
        return rules if rules is not None else ""

    def _build_ocr_prompt(self, workflow: str) -> str:
        """
        构建OCR阶段的prompt
        
        Args:
            workflow: 工作流程类型 ("中高考" 或 "教辅QA")
            
        Returns:
            OCR阶段的prompt字符串
        """
        ocr_prompts = self.config["prompts"]["1_ocr"]
        template_key = "template" if workflow == "中高考" else "template_edu"
        
        if template_key not in ocr_prompts:
            raise KeyError(f"OCR 配置中缺少 {template_key} 模板")
        return ocr_prompts[template_key]

    def _build_extract_qa_prompt(self, subject: str) -> str:
        """
        构建提取问答阶段的prompt
        
        Args:
            subject: 学科名称
            
        Returns:
            提取问答阶段的prompt字符串
        """
        question_types = self.get_question_types(subject)
        extract_qa_rules = self.get_extract_qa_rules(subject)
        template = self.config["prompts"]["2_extract_qa"]["template"]
        return template.format(
            subject=subject,
            question_types=question_types,
            extract_qa_rules=extract_qa_rules
        )

    def _build_check_availability_prompt(self, subject: str, query: str, answer: str) -> str:
        """
        构建可用性检查阶段的prompt
        
        Args:
            subject: 学科名称
            query: 查询内容
            answer: 答案内容
            
        Returns:
            可用性检查阶段的prompt字符串
        """
        question_types = self.get_question_types(subject)
        check_rules = self.get_check_rules(subject)
        
        # 根据学科选择模板
        if subject in self.SPECIAL_SUBJECTS:
            template = self.config["prompts"]["3_check_availability"]["template_special"]
        elif subject == self.CHINESE_SUBJECT:
            template = self.config["prompts"]["3_check_availability"]["template_chinese"]
        else:
            template = self.config["prompts"]["3_check_availability"]["template"]
            
        return template.format(
            subject=subject,
            question_types=question_types,
            check_rules=check_rules,
            query=query,
            answer=answer,
        )

    def _build_quality_check_prompt(self, stage: str, query: Optional[str] = None) -> str:
        """
        构建质检相关的prompt
        
        Args:
            stage: 质检阶段 ("质检单轮", "质检多轮-1", "质检多轮-2")
            query: 查询内容（可选）
            
        Returns:
            质检阶段的prompt字符串
        """
        if stage == "质检单轮":
            template = self.config["Prompt_check"]["template-单轮"]
            return template.format(query=query)
        elif stage == "质检多轮-1":
            template = self.config["Prompt_check"]["template-多轮1"]
            return template.format()
        elif stage == "质检多轮-2":
            if query is None:
                raise ValueError("质检多轮-2阶段需要提供query参数")
                
            template_key = "template-地理信息多轮2" if query in self.SPECIAL_SUBJECTS else "template-多轮2"
            template = self.config["Prompt_check"][template_key]
            return template.format(query=query)
        else:
            raise ValueError(f"不支持的质检阶段: {stage}")

    def build_prompt(
        self,
        stage: str,
        subject: str = None,
        query: str = None,
        answer: str = None,
        workflow: str = "中高考",
    ) -> str:
        """
        构建完整 prompt。
        
        Args:
            stage: 阶段 ('1_ocr', '2_extract_qa', '3_check_availability', '质检单轮', '质检多轮-1', '质检多轮-2')
            subject: 学科，用于 extract_qa 和 check_availability
            query: 查询内容，仅用于 check_availability 和 质检多轮阶段
            answer: 答案内容，仅用于 check_availability（answer 手动传入，如 "没有答案"）
            workflow: 工作流类型，仅用于 1_ocr 阶段，可选 "中高考" 或 "教辅QA"，默认 "中高考"
            
        Returns:
            构建好的prompt字符串
            
        Raises:
            ValueError: 当提供不支持的阶段或参数值时
            KeyError: 当配置缺失必要模板时
        """
        if stage == "1_ocr":
            if workflow not in ["中高考", "教辅QA"]:
                raise ValueError(f"不支持的 workflow: {workflow}，仅支持 '中高考' 或 '教辅QA'")
            return self._build_ocr_prompt(workflow)

        elif stage == "2_extract_qa":
            if subject is None:
                raise ValueError("extract_qa阶段必须提供subject参数")
            return self._build_extract_qa_prompt(subject)

        elif stage == "3_check_availability":
            if subject is None:
                raise ValueError("check_availability阶段必须提供subject参数")
            return self._build_check_availability_prompt(subject, query, answer)

        elif stage in ["质检单轮", "质检多轮-1", "质检多轮-2"]:
            return self._build_quality_check_prompt(stage, query)

        else:
            raise ValueError(f"不支持的阶段: {stage}")


# ================== 示例调用 ==================
if __name__ == "__main__":
    # 初始化加载器
    loader = PromptLoader("/DMXZYB1/ftpdata/wjcui/Test/code/prompts.yaml")

    # 模拟使用场景
    subject = "语文"
    q_text = "床前明月光的作者是谁？"

    # 如果没有答案，手动传入 "没有答案"
    a_text = "没有答案"

    # 构建第一阶段 prompt（ocr）
    # workflow: 仅用于 1_ocr 阶段，可选 "中高考" 或 "教辅QA"，默认 "中高考"
    prompt_1 = loader.build_prompt(stage="1_ocr", workflow="教辅QA")

    # 构建第二阶段 prompt（提qa）
    prompt_2 = loader.build_prompt(stage="2_extract_qa", subject=subject)
    
    # 构建第三阶段 prompt（可用性检查）
    prompt_3 = loader.build_prompt(
        stage="3_check_availability",
        subject=subject,
        query=q_text,
        answer=a_text
    )

    # 构建自动化质检 prompt（可用性检查）
    prompt_check1 = loader.build_prompt(stage="质检多轮-1")
    prompt_check2 = loader.build_prompt(stage="质检多轮-2", query=q_text)

    # print("=== 生成的 Prompt (OCR) ===")
    # print(prompt_1)
    # print("\n=== 生成的 Prompt (Extract QA) ===")
    # print(prompt_2)
    # print("\n=== 生成的 Prompt (Check Availability) ===")
    print(prompt_3)
    # print("\n=== 生成的 Prompt (自动化质检) ===")
    # print(prompt_check1)
    # print(prompt_check2)