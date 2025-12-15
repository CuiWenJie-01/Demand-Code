batch='1128-单模文件提交-239本'
date=$(date +%m%d)   # 自动获取当前日期，格式为月日(例如1127)
root='/DL_data_new/ftpdata/wjcui/code/教辅'
name='崔文杰'
model='qwen3-vl-235b-a22b-thinking-多模'
# model2='qwen3-vl-235b-a22b-thinking-多模'

echo "=================开始处理=================="
mkdir -p "$root/$batch/14_select_check_${batch}"
mkdir -p "$root/$batch/15_data_to_check_tidan_${batch}"
mkdir -p "$root/$batch/16_model_res_check_${batch}"
mkdir -p "$root/$batch/16_model_res_check_${batch}"
# mkdir -p "$root/$batch/16_model_res_check_${batch}/$model2"


echo "=================路径定义=================="
input_dir="$root/$batch/13_data_spilt_${batch}"
output_dir="$root/$batch/14_select_check_${batch}"
output_dir2="$root/$batch/15_data_to_check_tidan_${batch}"
# output_dir3="$root/$batch/15_data_to_check_tidan_${batch}/$model2"

echo "=================自动化质检提单=================="
python "/DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools/select_数据-全量抽.py" "$input_dir" "$output_dir" "$batch" 
python "/DL_data_new/ftpdata/jjhu32/code/切题链路合并/tools/data_to_model_check3.py" "$output_dir" "$output_dir2" "$name" "$model" "$batch" "$root" "$date"