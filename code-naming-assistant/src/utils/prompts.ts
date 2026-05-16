export type NamingScene = 'project' | 'directory' | 'file' | 'variable' | 'function' | 'class' | 'constant';

export const SCENE_LABELS: Record<NamingScene, string> = {
    project: '项目名',
    directory: '目录/文件夹名',
    file: '文件名',
    variable: '变量名',
    function: '函数/方法名',
    class: '类名',
    constant: '常量名',
};

const SCENE_RULES: Record<NamingScene, string> = {
    project: `项目层级 (Project Root)
- 风格：全小写，使用中划线"-"分隔（Kebab-case）
- 模板：[类别]-[核心名]-[可选：版本]
- 课程/学习类示例：dsa-notes, dl-practice, cs-basics
- 工具/平台类示例：data-pipeline, model-server, image-nas
- 重构示例：chapter3_linear_neural_network → ch03-linear-nets`,

    directory: `目录/文件夹层级 (Folders/Packages)
- 风格：全小写，snake_case（下划线"_"分隔）
- 模板：[序号]_[模块名] 或 [功能名]
- 序号处理规则（非常重要）：
  * 只处理开头的整数部分，补零到两位（如 3→03, 4→04）
  * 小数部分保持原样（如 3.2 保持 .2, 4.2 保持 .2）
  * 最终格式：03.2_xxx, 04.2_xxx, 03_xxx
  * 不要给序号添加额外层级数字
- 逻辑分层：data/, models/, utils/, scripts/, docs/
- 章节分层：01_linear_reg/, 02_logistic_reg/, 03_mlp/
- 示例：
  "3.2. 线性回归的从零开始实现" → "03.2_lin_reg_impl"
  "4. 多层感知机" → "04_mlp"
  "神经网络" → "nn"`,

    file: `文件层级 (Files)
- 风格：Python 统一用 snake_case；C++ 常用 snake_case 或 PascalCase
- 模板：[核心对象]_[主要动作].[后缀]
- 核心准则：既然文件夹已经说明了上下文，文件名就要去重
- 示例：
  不推荐：chapter3_linear_neural_network/vectorized_acceleration.py
  推荐：ch03-linear-nets/vec_bench.py 或 ch03-linear-nets/vec_perf.py
  逻辑：vec (向量化), perf (性能), bench (基准测试)`,

    variable: `变量 (Variable)
- 风格：snake_case，具体名词
- 长度：短作用域可使用数学符号或常用缩写（x, y, w, b, lr, bs）；长作用域用描述性单词
- 避免匈牙利命名：不用str_name, int_count
- 示例：input_ids, learning_rate`,

    function: `函数 (Function)
- 风格：snake_case，动词+名词
- 行为明确：get_, set_, compute_, save_, load_, parse_, format_
- 布尔函数：is_valid(), has_error()
- 示例：get_batch(), train_epoch()`,

    class: `类 (Class)
- 风格：PascalCase，抽象名词
- 示例：LinearNet, DataLoader`,

    constant: `常量 (Constant)
- 风格：SCREAMING_SNAKE_CASE，全大写
- 示例：MAX_EPOCHS, BATCH_SIZE`,
};

const ABBREVIATION_LIST = `implementation (实现) → impl → linear_impl.py
optimization (优化) → opt → memory_opt.py
configuration (配置) → config/cfg → model_cfg.json
utilities (工具类) → utils → path_utils.py
distributed (分布式) → dist → dist_train.py
comparison/test (对比) → bench/eval → speed_bench.py
requirement (需求/依赖) → reqs → requirements.txt
neural network → nn
linear → lin
feature → feat
vectorized → vec
acceleration/accelerate → accel
evaluation/evaluate → eval
training → train
test/testing → test
validation/validate → val
maximum → max
minimum → min
number → num
information → info
application → app
database → db
image → img
temporary/temp → tmp
argument/arguments → arg/args
parameter/parameters → param/params
object → obj
string → str
integer → int
boolean → bool
array → arr
dictionary → dict
function → func
variable → var
error → err
exception → exc
message → msg
response → resp
request → req
library → lib
document → doc
directory → dir
source → src
destination → dst
input → in
output → out
reference → ref
identifier → id
index → idx
count → cnt
current → curr
previous → prev
initialize/initial → init`;

export function buildPrompt(scene: NamingScene, chineseText: string): string {
    const sceneRule = SCENE_RULES[scene];
    return `你是一位专业的代码命名顾问，追求既能"一眼看懂"又能"短小精悍"的命名风格。请将以下中文描述翻译成符合软件工程规范的英文命名。

【命名场景】：${SCENE_LABELS[scene]}

【命名规范】：
${sceneRule}

【精简词库对照表】（优先使用，避免冗长）：
${ABBREVIATION_LIST}

【命名哲学】：
- 文件夹提供语境：既然在 ch03-linear-nets 目录下，文件就不再需要重复 linear
- 文件名提供功能：让人一眼看出这个文件是用来做 bench (测试) 还是 impl (实现)
- 变量名提供含义：代码内部尽量用 x, y, w, b 等数学符号或 lr, bs 等常用缩写

【通用否定原则】：
- 不要直译，要符合代码命名习惯
- 避免过长的名字，优先使用精简词库
- 去除无意义的词如 chapter, my, temp, test_final_final
- 不要混用风格：如 myVariable_name
- 不要中文/拼音
- 模块私有/内部使用加单下划线前缀：_internal_helper, _private_var
- 若名称与Python内置函数冲突，加尾随下划线：class_, input_

【要求】：
1. 只返回最终的英文命名，不要任何解释、说明、注释
2. 如果输入已经是英文，直接按当前场景的规范格式化
3. 确保输出严格符合上述命名规范的风格
4. 输出必须是纯文本，不要加引号、代码块或其他格式

【中文描述】：
${chineseText}

【输出】：`;
}
