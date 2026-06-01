# Code Naming Assistant

智能代码命名助手 —— 基于本地 Ollama 大模型，将中文描述翻译成符合工程规范的英文命名。

[![VSCode Marketplace](https://img.shields.io/visual-studio-marketplace/v/cuiwj.code-naming-assistant?style=for-the-badge&logo=visualstudiocode)](https://marketplace.visualstudio.com/items?itemName=cuiwj.code-naming-assistant)
[![Installs](https://img.shields.io/visual-studio-marketplace/i/cuiwj.code-naming-assistant?style=for-the-badge)](https://marketplace.visualstudio.com/items?itemName=cuiwj.code-naming-assistant)
[![Downloads](https://img.shields.io/visual-studio-marketplace/d/cuiwj.code-naming-assistant?style=for-the-badge)](https://marketplace.visualstudio.com/items?itemName=cuiwj.code-naming-assistant)
[![Rating](https://img.shields.io/visual-studio-marketplace/r/cuiwj.code-naming-assistant?style=for-the-badge)](https://marketplace.visualstudio.com/items?itemName=cuiwj.code-naming-assistant)

## ✨ 功能特性

- **7 种命名场景**：项目名、目录名、文件名、变量名、函数名、类名、常量名
- **智能场景识别**：根据代码上下文自动推荐命名类型
- **一键重命名**：支持文件/文件夹/代码符号快速重命名
- **完全本地运行**：基于 Ollama，无需联网，保护隐私
- **工程规范自动应用**：自动转换 kebab-case / snake_case / PascalCase / UPPER_SNAKE_CASE
- **智能缩写优化**：自动使用 nn, acc, eval, utils 等常用缩写

## 🚀 快速开始

### 前置要求

1. 安装 [Ollama](https://ollama.com/)
2. 下载推荐模型：
   ```bash
   # 推荐：Google Gemma3 4B QAT（翻译质量好且速度快）
   ollama pull gemma3:4b-it-qat
   
   # 或阿里 Qwen2.5 7B（中文理解更强）
   ollama pull qwen2.5:7b
   ```
3. 启动 Ollama 服务：
   ```bash
   ollama serve
   ```

### 安装插件

在 VS Code 扩展市场搜索 **Code Naming Assistant** 即可安装。

## 🎯 使用方法

### 1. 智能命名翻译（快捷键）

- 按 `Alt + Shift + T`（Mac: `Cmd + Shift + T`）
- 输入中文描述，如：`第三章线性神经网络`
- 选择命名场景
- 插件生成符合规范的英文命名

### 2. 右键重命名文件/文件夹

- 在资源管理器中右键点击文件或文件夹
- 选择 **"重命名为规范英文"**
- 输入中文描述（或留空使用当前名称）

### 3. 右键重命名代码符号

- 在编辑器中选中变量/函数/类名
- 右键选择 **"重命名符号为规范英文"**
- 插件自动推荐命名场景

## ⚙️ 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `codeNamingAssistant.ollamaUrl` | `http://localhost:11434` | Ollama 服务地址 |
| `codeNamingAssistant.model` | `gemma3:4b-it-qat` | 使用的模型名称 |
| `codeNamingAssistant.defaultScene` | `auto` | 默认命名场景 |

## 📋 命名规范

| 元素 | 风格 | 示例 |
|------|------|------|
| 项目 | kebab-case | `my-awesome-project` |
| 目录 | snake_case | `01_data_prep`, `02_models` |
| 文件 | snake_case.py | `train_model.py` |
| 变量 | snake_case | `total_loss`, `is_training` |
| 函数 | snake_case | `compute_average()` |
| 类 | PascalCase | `LinearRegression` |
| 常量 | UPPER_SNAKE_CASE | `MAX_ITERATIONS` |

## 🌟 转换示例

| 中文描述 | 场景 | 输出 |
|----------|------|------|
| 第三章线性神经网络 | 目录 | `03_linear_nn` |
| 向量化加速 | 文件 | `vectorized.py` |
| 计算平均损失 | 函数 | `compute_avg_loss` |
| 是否正在训练 | 变量 | `is_training` |
| 线性回归模型 | 类 | `LinearRegression` |
| 最大迭代次数 | 常量 | `MAX_ITERATIONS` |

## ❓ 常见问题

**Q: 提示无法连接到 Ollama？**
A: 请确认 Ollama 已安装、已运行 `ollama serve`、模型已下载、端口 11434 未被占用。

**Q: 生成的名字不符合预期？**
A: 可以切换模型，或提供更精确的描述，也可以点击"重新生成"获取不同结果。

## 📄 许可证

MIT License

---

**Made with ❤️** for developers who care about clean code.