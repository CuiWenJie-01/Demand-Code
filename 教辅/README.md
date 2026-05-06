# 教辅数据处理工具集

本目录包含用于教辅图书数据处理的 Python 工具脚本，主要面向大模型训练数据的预处理、质检与格式化工作流。

## 目录结构

```
教辅/
├── tools/              # 主处理流程工具
│   ├── handle/         # 分阶段处理脚本
│   ├── 1_tidan_ocr_edu.py
│   ├── 4_model_res_qa_process_edu.py
│   ├── 5_qa_dedup_optim_edu.py
│   ├── 6_llm_filter_tidan_edu.py
│   ├── data_filter_fuc_edu.py
│   ├── data_to_model_check.py
│   └── ...
├── tools_check/        # 质检与上平台工具
│   ├── select_url.py
│   ├── select_null_image.py
│   ├── combine_png.py
│   ├── cp_txt2file.py
│   └── ...
├── other/              # 其他辅助工具
│   ├── FileTransferTool.py   # 高速文件复制/移动工具
│   ├── compress.py           # 文件压缩工具
│   ├── batch_unzip.py        # 批量解压工具
│   └── delete_path.py        # 批量删除工具
└── 1128-单模文件提交-239本/  # 原始教辅图片数据（示例批次）
```

## 核心功能

### 1. 主处理流程 (tools/)

面向 LLM 训练数据的端到端处理流水线：

- **OCR 提单** (`1_tidan_ocr_edu.py`): 将教辅图片打包并生成 OCR 工单
- **QA 提取** (`4_model_res_qa_process_edu.py`): 从 OCR 结果中提取问答对
- **去重优化** (`5_qa_dedup_optim_edu.py`): 对 QA 结果进行去重与优化
- **数据过滤** (`data_filter_fuc_edu.py`): 按学科规则过滤低质量数据（支持英语、政治、历史、语文等）
- **上平台准备** (`data_to_model_check.py`): 将处理结果转换为平台提交格式

### 2. 质检工具 (tools_check/)

- **URL 抽取** (`select_url.py`): 从结果中抽取图片 URL
- **空图检测** (`select_null_image.py`): 检测无效或空白图片
- **图片合并** (`combine_png.py`): 按规则合并题目与答案图片
- **文件整理** (`cp_txt2file.py`): 按文本清单复制/整理文件

### 3. 辅助工具 (other/)

- **FileTransferTool.py**: 多线程高速文件复制/移动，支持进度显示
- **compress.py**: 目录压缩工具
- **batch_unzip.py**: 批量解压工具

## 处理流程

```
Step 0: 数据抽取 → Step 1: OCR 提单 → Step 2: OCR 结果处理
→ Step 3: 生成提单文件 → Step 4: QA 提取 → Step 5: 去重优化
→ Step 6: 可用性检查 → Step 7: 重命名 → Step 8: 上平台
```

详见 `tools/handle/教辅处理流程.md`

## 环境依赖

- Python 3.8+
- jieba
- tqdm
- PyYAML

## 使用说明

1. 将原始教辅图片按批次放入对应目录
2. 修改各脚本中的 `batch` 和 `root` 参数
3. 按阶段顺序执行 `handle/` 目录下的编号脚本
4. 使用 `tools_check/` 中的工具进行质量检查

## 注意事项

- 原始图片数据体积较大，已加入 `.gitignore`，请勿提交到 Git
- 各脚本中的绝对路径需根据实际环境修改
- 处理过程中会生成大量中间 JSON 文件，注意磁盘空间
