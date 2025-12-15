#!/bin/bash
# 批次信息
batch='1202-单模文件提交-437本'
# date='1114' # 现在需要修改为当前日期
date=$(date +%m%d)   # 自动获取当前日期，格式为月日(例如1127)
source_step1='教辅QA' # 第一步的数据来源（筛选合格数据/中高考真题/竞赛/教辅QA）
source_step2='教辅' # 第二步的数据来源（教辅/竞赛/真题/模拟题）
root='/DL_data_new/ftpdata/wjcui/code/教辅'
name='崔文杰'
model='doubao-seed-1-6-thinking-250715-多模'  # gemini2.5-pro-多模、doubao-seed-1-6-thinking-250715-多模

echo "=================开始执行完整流程=================="

# ==================== Step 1: 执行 0_cp.sh 的功能 ====================
echo "=================Step 1: 处理源文件=================="

# 基础路径定义
png_target_dir="$root/$batch/0_raw_png_$batch"  # 统一目标输出路径

# 根据source_step1自动设置路径和处理脚本
if [ "$source_step1" = "竞赛" ]; then
    # 竞赛类配置
    png_source_dir="/DL_data_new/自动化切题/原始数据/$source_step1/$batch"
    png_cut_dir="$root/$batch/$batch-待转换png文件"
    python_script="/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/0_1_cp_2png_race.py"
    script_args="$png_source_dir $png_cut_dir $png_target_dir $batch"
elif [ "$source_step1" = "筛选合格数据" ] || [ "$source_step1" = "中高考真题" ]; then
    # 筛选合格数据和中高考真题配置
    png_source_dir="/DL_data_new/自动化切题/原始数据/$source_step1/$batch/$batch"
    png_cut_dir="$root/$batch/$batch-png"
    python_script="/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/0_1_cp_2png.py"
    script_args="$png_source_dir $png_cut_dir $png_target_dir $batch"
elif [ "$source_step1" = "教辅QA" ]; then
    # 教辅QA配置（仅传递输入和输出路径两个参数）
    png_source_dir="/DL_data_new/自动化切题/原始数据/$source_step1/正式交付数据/图片包/$batch"
    python_script="/DL_data_new/ftpdata/wjcui/code/教辅/tools/0_1_cp_png.py"
    script_args="$png_source_dir $png_target_dir $batch"  
else
    echo "错误：source_step1值不支持，只能是'竞赛'、'筛选合格数据'、'中高考真题'或'教辅QA'"
    exit 1
fi

echo "当前批次: $batch"
echo "数据来源: $source_step1"
echo "源文件目录: $png_source_dir"
echo "目标存储目录: $png_target_dir"

# 创建目标目录
mkdir -p "$png_target_dir"

# 执行处理操作
echo "开始处理PNG文件..."
python "$python_script" $script_args

# 执行结果判断
if [ $? -eq 0 ]; then
    echo "Step 1 处理完毕"

    # 如果是竞赛类型，额外执行统计脚本
    if [ "$source_step1" = "竞赛" ]; then
        echo "统计源的题目套数和转换后的题目套数"
        python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/count_paper_sets.py" "$png_source_dir" "$png_target_dir" "$root" "$batch"
        # 检查统计脚本是否成功
        if [ $? -ne 0 ]; then
            echo "统计脚本执行失败"
            exit 1
        fi
    fi
else
    echo "Step 1 处理过程出现错误"
    exit 1
fi

# ==================== Step 2: 执行 1_tidan_zip.sh 的功能 ====================
echo "=================Step 2: 生成提单文件=================="

# 创建该批次的工程结构
echo "=================初始化工程结构=================="
mkdir -p "$root/$batch/2_model_res_ocr_$batch"
mkdir -p "$root/$batch/5_model_res_qa_$batch"
mkdir -p "$root/$batch/9_model_res_filter_$batch"

echo "=================生成提单文件=================="
# 根据source_step2选择对应的脚本
if [ "$source_step2" = "教辅" ]; then
    # 教辅QA场景使用专用脚本
    python /DL_data_new/ftpdata/wjcui/code/教辅/tools/1_tidan_ocr_edu.py "$root" "$batch" "$date" "$name" "$model" "$source_step2"
else
    # 其他场景使用原脚本
    python /DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/1_tidan_ocr.py "$root" "$batch" "$date" "$name" "$model" "$source_step2"
fi

# 检查执行结果
if [ $? -eq 0 ]; then
    echo "Step 2 处理完毕"
    echo "=================所有步骤执行完成=================="
else
    echo "Step 2 处理过程出现错误"
    exit 1
fi