batch='1106-单模交付数据-234本'
root='/DL_data_new/ftpdata/wjcui/code/教辅'
source_type='教辅ocr切题'  # 控制URL提取脚本选择的关键变量
intent='一检'

# 输入输出目录定义
input_dir=${root}/${batch}/16_model_res_check_$batch
output_dir=${root}/${batch}/17_model_res_spilt_$batch

# 确保主输出目录存在
mkdir -p "$output_dir" 

python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/check_res_split.py" "$input_dir" "$output_dir" 

# 路径复制：根据source_type选择调用的脚本
if [ "$source_type" = "教辅ocr切题" ]; then
    # 当source_type为"教辅ocr切题"时，调用1_select_url2.py
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/select_url2.py" "$output_dir"
else
    # 其他情况，调用原1_select_url.py
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/select_url.py" "$output_dir"
fi

# 图片复制（逻辑不变）
if [ "$source_type" = "教辅ocr切题" ]; then
    # 当source_type为"教辅ocr切题"时，调用2_cp_txt2file.py
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/cp_txt2file2.py" "$output_dir" 
else
    # 其他情况，调用原2_cp_txt2file.py
    python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/cp_txt2file.py" "$output_dir" 
fi

# 图片平铺（逻辑不变）
python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/combine_png.py" "$output_dir" "$intent"

# json格式转换（逻辑不变）
python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/model_check_res_transform2.py" "$output_dir" "$intent"

python "/DL_data_new/ftpdata/clguo4/code/wenke_tools/tools/select_null_image.py" "$output_dir" "$intent"