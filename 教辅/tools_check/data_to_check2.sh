batch='1128-单模文件提交-239本'
intent='一检'
source_type='教辅QA'  # 控制URL提取脚本选择的关键变量，教辅QA或者中高考真题
root='/DL_data_new/ftpdata/wjcui/code/教辅'

# 自动获取level和subject
data_split_dir="$root/$batch/13_data_spilt_$batch"
if [ ! -d "$data_split_dir" ]; then
    echo "错误: 目录 $data_split_dir 不存在"
    exit 1
fi

# 获取匹配的子目录
sub_dirs=($(find "$data_split_dir" -maxdepth 1 -type d -name "${batch}_*"))
if [ ${#sub_dirs[@]} -eq 0 ]; then
    echo "错误: 在 $data_split_dir 中未找到匹配的子目录"
    exit 1
elif [ ${#sub_dirs[@]} -gt 1 ]; then
    echo "警告: 找到多个匹配的子目录，使用第一个:"
    for dir in "${sub_dirs[@]}"; do
        echo "  $dir"
    done
fi

# 提取level和subject
full_sub_dir=$(basename "${sub_dirs[0]}")
prefix="${batch}_"
if [[ $full_sub_dir == $prefix* ]]; then
    # 去掉前缀
    remaining=${full_sub_dir#$prefix}
    # 提取level和subject
    if [[ $remaining == 高中* ]]; then
        level="高中"
        subject=${remaining#高中}
    elif [[ $remaining == 初中* ]]; then
        level="初中"
        subject=${remaining#初中}
    else
        # 尝试通过常见教育阶段关键词判断
        if [[ $remaining == 小学* ]]; then
            level="小学"
            subject=${remaining#小学}
        else
            # 默认处理方式，假设第一个部分是level，其余是subject
            level=$(echo "$remaining" | cut -d'_' -f1)
            subject=$(echo "$remaining" | cut -d'_' -f2-)
        fi
    fi
else
    echo "错误: 子目录名称格式不符合预期"
    exit 1
fi

# 输入输出目录定义,input_dir写到available下面的科目子文件夹
input_dir=$root/$batch/13_data_spilt_$batch/${batch}_${level}${subject}
output_dir=$root/$batch/14_select_check_$batch
output_dir2=$root/$batch/14_select_check_$batch/${batch}_${level}${subject}_${intent}

# 确保主输出目录存在
mkdir -p "$output_dir" "$output_dir2"

# 数据抽取（逻辑不变）
python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/0_select_数据-全量抽.py "$input_dir" "$output_dir" "$level" "$subject"

# 路径复制：根据source_type选择调用的脚本
if [ "$source_type" = "教辅QA" ]; then
    # 当source_type为"教辅QA"时，调用1_select_url2.py
    python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/1_select_url2.py "$output_dir" "$output_dir" "$level" "$subject"
else
    # 其他情况，调用原1_select_url.py
    python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/1_select_url.py "$output_dir" "$output_dir" "$level" "$subject"
fi

# 图片复制（逻辑不变）
if [ "$source_type" = "教辅QA" ]; then
    # 当source_type为"教辅QA"时，调用2_cp_txt2file.py
    python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/2_cp_txt2file2.py "$output_dir" "$output_dir" 
else
    # 其他情况，调用原2_cp_txt2file.py
    python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/2_cp_txt2file.py "$output_dir" "$output_dir" 
fi

# 图片平铺（逻辑不变）
python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/3_combine_png.py "$output_dir" "$output_dir2"

# json格式转换（逻辑不变）
python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/4_transform_to_平台_sub.py "$output_dir" "$output_dir2" "$level" "$subject"

# 额外脚本调用（逻辑不变）
python /DL_data_new/ftpdata/wjcui/code/教辅/tools_check/select_null_image2.py "$output_dir2" "$output_dir2" "$level" "$subject"

# 新增功能：统计JSON文件中的数据行数
json_file="$output_dir2/select-${level}${subject}-to平台.json"
count_file="$output_dir2/data_count.txt"

if [ -f "$json_file" ]; then
    # 统计JSON文件行数
    line_count=$(wc -l < "$json_file")
    echo "数据行数: $line_count" > "$count_file"
    echo "已统计JSON文件行数并保存到: $count_file"
else
    echo "警告: JSON文件不存在: $json_file"
fi

echo =================完成==================