# Code Naming Assistant

智能代码命名助手 —— 基于本地 Ollama 大模型，将中文描述翻译成符合工程规范的英文命名。

## 功能特性

- 7 种命名场景：项目名、目录名、文件名、变量名、函数名、类名、常量名
- 智能场景识别：根据代码上下文自动推荐命名类型
- 右键重命名：支持文件/文件夹/代码符号一键重命名
- 完全本地运行：基于 Ollama，无需联网，保护隐私
- 符合工程规范：自动应用 kebab-case / snake_case / PascalCase / UPPER_SNAKE_CASE
- 缩写白名单：自动使用 nn, acc, eval, utils 等常用缩写

## 安装要求

1. 安装 [Ollama](https://ollama.com/)
2. 下载推荐模型（选一个即可）：
   ```bash
   # 最推荐：Google Gemma3 4B QAT 版本，翻译质量好且速度快
   ollama pull gemma3:4b-it-qat

   # 或阿里 Qwen2.5 7B，中文理解更强
   ollama pull qwen2.5:7b

   # 或你已有的翻译模型
   ollama pull translategemma:4b
   ```
3. 启动 Ollama 服务：
   ```bash
   ollama serve
   ```

## 安装插件

### 方式一：本地安装（开发调试）

1. 打开 VSCode
2. 按 `Ctrl+Shift+P`，输入 `Extensions: Install from VSIX...`
3. 或者按 `F5` 直接在新窗口中调试运行

### 方式二：命令行打包安装

```bash
# 打包成 vsix
npx vsce package

# 在 VSCode 中安装
# Ctrl+Shift+P -> Extensions: Install from VSIX...
```

## 使用方法

### 1. 智能命名翻译（快捷键）

- 按 `Alt + Shift + T`（Mac: `Cmd + Shift + T`）
- 输入中文描述，如：`第三章线性神经网络`
- 选择命名场景（项目/目录/文件/变量/函数/类/常量）
- 插件调用 Ollama 生成符合规范的英文命名
- 可选择：复制到剪贴板 / 插入到编辑器 / 重新生成

### 2. 右键重命名文件/文件夹

- 在资源管理器中右键点击文件或文件夹
- 选择 **"重命名为规范英文"**
- 输入中文描述（或留空使用当前名称翻译）
- 确认后即可重命名

### 3. 右键重命名代码符号

- 在编辑器中选中代码中的变量/函数/类名
- 右键选择 **"重命名符号为规范英文"**
- 插件会根据上下文自动推荐命名场景
- 输入中文描述（或留空使用当前文本）
- 确认后替换

## 配置项

在 VSCode 设置中搜索 `codeNamingAssistant`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `codeNamingAssistant.ollamaUrl` | `http://localhost:11434` | Ollama 服务地址 |
| `codeNamingAssistant.model` | `gemma3:4b-it-qat` | 使用的模型名称 |
| `codeNamingAssistant.defaultScene` | `auto` | 默认命名场景（auto 为每次询问） |

## 命名规范速查

| 元素 | 风格 | 示例 |
|------|------|------|
| 项目 | kebab-case | `my-awesome-project` |
| 目录 | snake_case | `01_data_prep`, `02_models` |
| 文件 | snake_case.py | `train_model.py`, `config.yaml` |
| 变量 | snake_case | `total_loss`, `is_training` |
| 函数 | snake_case | `compute_average()`, `save_model()` |
| 类 | PascalCase | `LinearRegression`, `DataLoader` |
| 常量 | UPPER_SNAKE_CASE | `MAX_ITERATIONS`, `DEFAULT_LR` |

## 示例

| 中文描述 | 场景 | 输出 |
|----------|------|------|
| 第三章线性神经网络 | 目录 | `03_linear_nn` |
| 向量化加速 | 文件 | `vectorized.py` 或 `accel.py` |
| 计算平均损失 | 函数 | `compute_avg_loss` |
| 是否正在训练 | 变量 | `is_training` |
| 线性回归模型 | 类 | `LinearRegression` |
| 最大迭代次数 | 常量 | `MAX_ITERATIONS` |

## 常见问题

**Q: 提示无法连接到 Ollama？**
A: 请确认：
1. Ollama 已安装
2. 已运行 `ollama serve`
3. 模型已下载（`ollama list` 查看）
4. 端口 11434 未被占用

**Q: 生成的名字不符合预期？**
A: 可以在设置中切换模型，或在输入时提供更精确的描述。也可以点击"重新生成"获取不同结果。

**Q: 支持其他编程语言吗？**
A: 目前主要针对 Python 命名规范优化，但 kebab-case / snake_case / PascalCase 等通用规范适用于大多数语言。

## License

MIT
