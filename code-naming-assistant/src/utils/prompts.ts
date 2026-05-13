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
    project: `项目名（Project）
- 风格：kebab-case，全小写，单词间用短横线"-"分隔
- 长度：2~4个单词，不超过30字符
- 示例：deep-learning-exercises, my-nn-lab, chinese-news-classifier`,

    directory: `目录/文件夹名（Directory）
- 风格：snake_case，全小写，单词间用下划线"_"分隔
- 序号：数字用两位（01_, 02_），不要无意义的单词如chapter
- 特殊目录：common, utils, config, scripts, data, tests
- 示例：01_data_prep, 02_models, 03_training, common, tests`,

    file: `文件名（File）
- Python文件：snake_case.py，全小写+下划线，无冗余前缀
- 其他文件（JSON, YAML, Markdown）：全小写 + "-"或"_"，保持一致
- 常见后缀：train.py, model.py, losses.py, utils.py, config.yaml
- 一个文件只做一件事：文件名应精准反映其内容，但不重复上层目录名
- 示例：
  不推荐：chapter3_linear_neural_network/vectorized_acceleration.py
  推荐：ch03_linear_nn/vectorized.py 或 ch03_linear_nn/accel.py`,

    variable: `变量名（Variable）
- 风格：snake_case，全小写，下划线分隔
- 长度：短作用域可短名（i, j, x）；长作用域用描述性单词
- 避免匈牙利命名：不用str_name, int_count
- 布尔变量：用is_, has_, can_前缀
- 示例：total_loss = 0.0, is_training = True, student_names = ["Alice", "Bob"]`,

    function: `函数/方法名（Function / Method）
- 风格：snake_case，动词开头 + 名词
- 行为明确：get_, set_, compute_, save_, load_, parse_, format_
- 布尔函数：is_valid(), has_error()
- 示例：def compute_average(data): ..., def save_model(path): ..., def is_empty(): ...`,

    class: `类名（Class）
- 风格：PascalCase，首字母大写，无下划线
- 名词，避免动词
- 示例：LinearRegression, DataLoader, NeuralNetwork`,

    constant: `常量名（Constant）
- 风格：UPPER_SNAKE_CASE，全大写，下划线分隔
- 示例：MAX_ITERATIONS = 1000, DEFAULT_LEARNING_RATE = 0.01`,
};

const ABBREVIATION_LIST = `neural network → nn, linear → lin, feature → feat, vectorized → vec,
acceleration/accelerate → accel, implementation/implement → impl,
utility/utilities → utils, configuration/configure → config,
example → demo, evaluation/evaluate → eval, training → train,
test/testing → test, validation/validate → val, maximum → max, minimum → min,
number → num, information → info, application → app, database → db,
image → img, temporary/temp → tmp, argument/arguments → arg/args,
parameter/parameters → param/params, object → obj, string → str,
integer → int, boolean → bool, array → arr, dictionary → dict,
function → func, variable → var, error → err, exception → exc,
message → msg, response → resp, request → req, library → lib,
document → doc, directory → dir, source → src, destination → dst,
input → in, output → out, reference → ref, identifier → id,
index → idx, count → cnt, current → curr, previous → prev,
initialize/initial → init`;

export function buildPrompt(scene: NamingScene, chineseText: string): string {
    const sceneRule = SCENE_RULES[scene];
    return `你是一位专业的代码命名顾问。请将以下中文描述翻译成符合软件工程规范的英文命名。

【命名场景】：${SCENE_LABELS[scene]}

【命名规范】：
${sceneRule}

【缩写白名单】（优先使用，让名字更简洁）：
${ABBREVIATION_LIST}

【通用否定原则】：
- 不要直译，要符合代码命名习惯
- 避免过长的名字，优先使用缩写白名单
- 去除无意义的词如chapter, my, temp, test_final_final
- 不要混用风格：如myVariable_name
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
