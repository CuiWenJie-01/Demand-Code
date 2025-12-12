#!/bin/bash
# 批次信息
batch='1110-单模文件提交-332本'
level='高中'         # 注意与13下的文件名对应
subject='语文'  # qa和仅q分开打包，subject记得改   #注意与13下的文件名对应【英语、政治、道德与法治、历史、语文、文综、地理、信息科技】
intent='上平台'
source_type='教辅QA'  # 控制URL提取脚本选择的关键变量，教辅QA或者中高考真题
root='/DL_data_new/ftpdata/wjcui/code/教辅'

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

echo =================完成==================

# 以下为注释的压缩逻辑，如需启用可删除注释符号
# cd "/DMXCC/DL_Data/ftpdata/jjhu32/中高考process/ocr效果测试/${batch}" || exit
# zip_name="胡佳驹_${batch}_全学科_gemini2.5pro多模_jjhu32_认知基础-SFT数据建设.zip"
# zip -qr "$zip_name" "./1_tidan_ocr_${batch}"

# cd "/DMXCC/DL_Data/ftpdata/jjhu32/中高考process/ocr效果测试/${batch}/1_tidan_ocr_${batch}" || exit
# for folder in */; do
#     # 确保只处理目录，并去掉尾部的 '/'
#     if [[ -d "$folder" ]]; then
#         folder_name=$(basename "$folder")

#         # 生成压缩文件名，例如：batch-folder_name.zip
#         zip_name="胡佳驹_${folder_name}_gemini2.5pro多模_jjhu32_认知基础-SFT数据建设.zip"
#         # 检查压缩文件是否已经存在
#         if [[ ! -e "$zip_name" ]]; then
#             # 压缩文件夹
#             echo "正在压缩压缩文件: $zip_name"
#             zip -qr "$zip_name" "$folder"
#             echo "压缩完成"
#             # 使用 ls -lh 显示压缩文件的大小
#             ls -lh "$zip_name"
#         else
#             echo "压缩文件已存在，跳过: $zip_name"
#             ls -lh "$zip_name"
#         fi     
#     fi
# done