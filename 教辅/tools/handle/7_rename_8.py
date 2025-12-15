#!/bin/bash

# 集成处理脚本，按照以下顺序执行：
# 1. 二轮过滤处理 (原7_filter_zip.sh)
# 2. 文件夹重命名 (原rename_folder.py)  
# 3. 数据合并与去重 (原8_compare_similarity.sh)
1
# 配置参数
batch='1110-单模文件提交-332本'
root='/DL_data_new/ftpdata/wjcui/code/教辅'
source='教辅QA'
onlyq='False'

# echo "=========================================="
# echo "开始执行集成处理流程..."
# echo "=========================================="

# 第一步：执行二轮过滤处理 (原7_filter_zip.sh的功能)
echo "=================Step 1: 二轮过滤处理=================="
# 根据source值选择对应的过滤脚本
if [ "$source" = "教辅QA" ]; then
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/7_llm_filter_edu.py" "$root" "$batch"
else
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/7_llm_filter.py" "$root" "$batch"
fi

avail_path="$root/$batch/10_final_llm_filter_$batch/available"
unavail_path="$root/$batch/10_final_llm_filter_$batch/unavailable"

python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/count_qa_num.py" "$avail_path"
python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/count_qa_num.py" "$unavail_path"

# 检查第一步是否成功执行
if [ ! -d "$avail_path" ]; then
    echo "错误: 第一步执行失败，目录 $avail_path 不存在"
    exit 1
fi

# 第二步：执行文件夹重命名 (原rename_folder.py的功能)
echo "=================Step 2: 文件夹重命名=================="
# 使用Python脚本进行文件夹重命名
python << EOF
import os
import re

def rename_folders(base_path):
    """
    批量重命名文件夹，保留学年级和学科名称部分
    """
    # 检查基础路径是否存在
    if not os.path.exists(base_path):
        print(f"错误：路径 {base_path} 不存在")
        return False
    
    renamed_count = 0
    # 遍历基础路径下的所有文件夹
    for folder_name in os.listdir(base_path):
        folder_path = os.path.join(base_path, folder_name)
        
        # 只处理文件夹
        if os.path.isdir(folder_path):
            # 使用正则表达式提取年级和学科名称（初中/高中 + 学科）
            # 匹配模式：1104-单模交付数据-169本_初中历史-28_教辅 提取 初中历史
            # 同时匹配：1104-单模文件提交-400本_初中历史_教辅 提取 初中历史
            match = re.search(r'([初高][中][^_-]+?)(?:-\d+_|_)', folder_name)
            
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
                    renamed_count += 1
                except Exception as e:
                    print(f"重命名失败 {folder_name}: {str(e)}")
            else:
                print(f"无法从文件夹名 {folder_name} 中提取年级和学科信息")
    
    print(f"总共重命名了 {renamed_count} 个文件夹")
    return True

# 设置输入路径
input_path = "$avail_path"

# 调用重命名函数
success = rename_folders(input_path)
if not success:
    exit(1)
EOF

# 检查第二步是否成功执行
if [ $? -ne 0 ]; then
    echo "错误: 第二步执行失败"
    exit 1
fi

# 第三步：执行数据合并与去重 (原8_compare_similarity.sh的功能)
echo "=================Step 3: 数据合并与去重=================="
# 设置相关变量
base_dir="$root"
available_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available"

# 检查available目录是否存在
if [ ! -d "$available_dir" ]; then
    echo "错误: 目录 $available_dir 不存在"
    exit 1
fi

# 获取available目录下的所有子目录
subdirs=($(ls -1 "$available_dir"))

# 存储所有找到的level和subject组合
level_subject_pairs=()

# 从子目录名中提取level和subject
for dir in "${subdirs[@]}"; do
    # 匹配模式如："初中历史"、"高中语文"等
    if [[ $dir =~ ^(初中|高中|竞赛)(.+)$ ]]; then
        level=${BASH_REMATCH[1]}
        subject=${BASH_REMATCH[2]}
        level_subject_pairs+=("$level:$subject")
        echo "发现目录: $dir -> level=$level, subject=$subject"
    fi
done

# 如果没有找到匹配的目录，则报错退出
if [ ${#level_subject_pairs[@]} -eq 0 ]; then
    echo "错误: 在 $available_dir 目录下未找到符合格式(初中/高中/竞赛+科目)的子目录"
    echo "可用的子目录:"
    for dir in "${subdirs[@]}"; do
        echo "  - $dir"
    done
    exit 1
fi

echo "共发现 ${#level_subject_pairs[@]} 个有效的level-subject组合"

# 处理每个level-subject组合
for pair in "${level_subject_pairs[@]}"; do
    IFS=':' read -r level subject <<< "$pair"
    
    # 区分input_dir用的subject和其他地方用的subject
    if [ "$subject" = "道德与法治" ]; then
        input_subject="道德与法治"  # input_dir中专用
        processed_subject="政治"    # 其他所有地方用
    else
        input_subject="$subject"    # 非道德与法治时，两者一致
        processed_subject="$subject"
    fi

    if [[ "$subject" == "英语-辅学类" || "$subject" == "英语-刷题类" ]]; then
        txt_b_path="/DL_data_new/自动化切题/交付数据/good/0实时更新的去重路径（质检未过批次需要手动删除）/英语.txt"
    elif [[ "$subject" == "语文-辅学类" || "$subject" == "语文-刷题以" ]]; then
        txt_b_path="/DL_data_new/自动化切题/交付数据/good/0实时更新的去重路径（质检未过批次需要手动删除）/语文.txt"
    else
        txt_b_path="/DL_data_new/自动化切题/交付数据/good/0实时更新的去重路径（质检未过批次需要手动删除）/${processed_subject}.txt" # 以这个路径下的txt为准
    fi

    # 创建目录（确保目录存在）
    mkdir -p "${base_dir}/${batch}/11_data_combine_${batch}"
    mkdir -p "${base_dir}/${batch}/12_compare_similarity_${batch}"
    mkdir -p "${base_dir}/${batch}/13_data_spilt_${batch}"

    # 根据source和onlyq生成input_dir（仅这里用input_subject）
    if [ "$onlyq" = "True" ]; then
        if [ "$source" = "教辅QA" ] || [ "$source" = "模拟题" ]; then
            input_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available/${batch}_${level}${input_subject}_教辅only_q"
        elif [ "$source" = "竞赛" ]; then
            input_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available/${batch}_${level}${input_subject}_竞赛only_q"
        elif [ "$source" = "中高考真题" ]; then
            input_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available/${batch}_${level}${input_subject}_真题only_q"
        fi
        # 输出文件用processed_subject
        output_file="${base_dir}/${batch}/11_data_combine_${batch}/${batch}_${level}${processed_subject}only_q.json"
        file_a_path="$output_file"
    else
        if [ "$source" = "教辅QA" ] || [ "$source" = "模拟题" ]; then
            input_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available/${level}${input_subject}"
        elif [ "$source" = "中高考真题" ]; then
            input_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available/${batch}_${level}${input_subject}_真题"
        elif [ "$source" = "竞赛" ]; then
            input_dir="${base_dir}/${batch}/10_final_llm_filter_${batch}/available/${batch}_${level}${input_subject}_竞赛"
        fi
        # 输出文件用processed_subject
        output_file="${base_dir}/${batch}/11_data_combine_${batch}/${batch}_${level}${processed_subject}.json"
        file_a_path="$output_file"
    fi

    echo "=================step.0 合并源文件=================="
    echo "当前输入目录: $input_dir"  # 这里显示的是含input_subject的路径
    echo "当前输出文件: $output_file"  # 这里显示的是含processed_subject的路径
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/combine_data.py" "$input_dir" "$output_file" 

    output_dir="${base_dir}/${batch}/12_compare_similarity_${batch}"

    echo "=================step.1 去重=================="
    echo "待去重文件路径: $file_a_path"  # 含processed_subject
    python "/DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools/compare_json_similarity.py" "$file_a_path" "$txt_b_path" "$output_dir"
    echo '去重完毕······'

    file_spilt_path="${base_dir}/${batch}/12_compare_similarity_${batch}"
    output_spilt_dir="${base_dir}/${batch}/13_data_spilt_${batch}"

    echo "=================step.2 分离=================="
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/data_spilt.py" "$file_spilt_path" "$output_spilt_dir"
done

echo "=========================================="
echo "7_rename_8处理流程执行完成！"
echo "=========================================="