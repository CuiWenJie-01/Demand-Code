batch='1119中考文科补源'
# level='初中'    
# subject='英语only_q'    
intent='上平台'
source_type='中高考真题'  # 控制URL提取脚本选择的关键变量

# 输入输出目录定义
input_dir=/DL_data_new/ftpdata/jjhu32/code/切题链路合并/${batch}/13_data_spilt_$batch
output_dir=/DL_data_new/ftpdata/jjhu32/code/切题链路合并/${batch}/14_select_check_$batch
output_dir2=/DL_data_new/ftpdata/jjhu32/code/切题链路合并/${batch}/14_select_check_$batch/${batch}_${intent}

# 确保主输出目录存在
mkdir -p "$output_dir" "$output_dir2"

# 数据抽取（逻辑不变）
python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/select_数据-全量抽.py "$input_dir" "$output_dir" "$batch" 

# 路径复制：根据source_type选择调用的脚本
if [ "$source_type" = "教辅ocr切题" ]; then
    # 当source_type为"教辅ocr切题"时，调用1_select_url2.py
    python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/select_url2.py "$output_dir" "$output_dir" "$batch"
else
    # 其他情况，调用原1_select_url.py
    python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/select_url.py "$output_dir" "$output_dir" "$batch"
fi

# 图片复制（逻辑不变）
if [ "$source_type" = "教辅ocr切题" ]; then
    # 当source_type为"教辅ocr切题"时，调用2_cp_txt2file.py
    python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/cp_txt2file2.py "$output_dir" "$output_dir" 
else
    # 其他情况，调用原2_cp_txt2file.py
    python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/cp_txt2file.py "$output_dir" "$output_dir" 
fi

# 图片平铺（逻辑不变）
python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/combine_png.py "$output_dir" "$output_dir2"

# json格式转换（逻辑不变）
python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/transform_to_平台_sub.py "$output_dir" "$output_dir2" "$batch"

# 额外脚本调用（逻辑不变）
python /DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools_check/select_null_image.py "$output_dir2" "$output_dir2" "$batch"

echo =================完成==================