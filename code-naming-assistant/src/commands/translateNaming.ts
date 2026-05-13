import * as vscode from 'vscode';
import { OllamaClient } from '../providers/ollamaClient';
import { NamingScene, SCENE_LABELS, buildPrompt } from '../utils/prompts';
import { cleanModelOutput, formatByCase, NamingCase } from '../providers/namingFormatter';

export async function translateNamingCommand(context: vscode.ExtensionContext): Promise<void> {
    const config = vscode.workspace.getConfiguration('codeNamingAssistant');
    const ollamaUrl = config.get<string>('ollamaUrl', 'http://localhost:11434');
    const model = config.get<string>('model', 'gemma3:4b-it-qat');
    const defaultScene = config.get<string>('defaultScene', 'auto');

    const client = new OllamaClient({ url: ollamaUrl, model });

    const isConnected = await client.checkConnection();
    if (!isConnected) {
        const action = await vscode.window.showErrorMessage(
            '无法连接到 Ollama 服务。请确认：\n1. Ollama 已安装\n2. 已运行 ollama serve\n3. 模型已下载',
            '打开设置', '查看文档'
        );
        if (action === '打开设置') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'codeNamingAssistant');
        }
        return;
    }

    const input = await vscode.window.showInputBox({
        prompt: '请输入中文描述（如：第三章线性神经网络）',
        placeHolder: '支持直接粘贴中文，或输入已有英文进行格式化',
    });

    if (!input || input.trim().length === 0) {
        return;
    }

    const sceneOptions: { label: string; scene: NamingScene }[] = [
        { label: '$(file-directory) 项目名 (kebab-case)', scene: 'project' },
        { label: '$(folder) 目录/文件夹名 (snake_case)', scene: 'directory' },
        { label: '$(file-code) 文件名 (snake_case.py)', scene: 'file' },
        { label: '$(symbol-variable) 变量名 (snake_case)', scene: 'variable' },
        { label: '$(symbol-method) 函数/方法名 (snake_case)', scene: 'function' },
        { label: '$(symbol-class) 类名 (PascalCase)', scene: 'class' },
        { label: '$(symbol-constant) 常量名 (UPPER_SNAKE_CASE)', scene: 'constant' },
    ];

    let selectedScene: NamingScene | undefined;

    if (defaultScene !== 'auto') {
        selectedScene = defaultScene as NamingScene;
    } else {
        const pick = await vscode.window.showQuickPick(
            sceneOptions.map(opt => opt.label),
            {
                placeHolder: '选择命名场景',
            }
        );
        if (!pick) {
            return;
        }
        selectedScene = sceneOptions.find(opt => opt.label === pick)?.scene;
    }

    if (!selectedScene) {
        return;
    }

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: `正在生成 ${SCENE_LABELS[selectedScene]}...`,
            cancellable: false,
        },
        async () => {
            try {
                const prompt = buildPrompt(selectedScene!, input.trim());
                const rawResult = await client.generate(prompt);
                const cleanedResult = cleanModelOutput(rawResult);

                let finalResult = cleanedResult;
                switch (selectedScene) {
                    case 'project':
                        finalResult = formatByCase(cleanedResult, 'kebab');
                        break;
                    case 'directory':
                    case 'file':
                    case 'variable':
                    case 'function':
                        finalResult = formatByCase(cleanedResult, 'snake');
                        break;
                    case 'class':
                        finalResult = formatByCase(cleanedResult, 'pascal');
                        break;
                    case 'constant':
                        finalResult = formatByCase(cleanedResult, 'upper_snake');
                        break;
                }

                const copyAction = await vscode.window.showInformationMessage(
                    `生成结果：${finalResult}`,
                    { modal: false },
                    '复制到剪贴板',
                    '插入到编辑器',
                    '重新生成'
                );

                if (copyAction === '复制到剪贴板') {
                    await vscode.env.clipboard.writeText(finalResult);
                    vscode.window.showInformationMessage('已复制到剪贴板');
                } else if (copyAction === '插入到编辑器') {
                    const editor = vscode.window.activeTextEditor;
                    if (editor) {
                        editor.edit(editBuilder => {
                            const selection = editor.selection;
                            editBuilder.replace(selection, finalResult);
                        });
                    }
                } else if (copyAction === '重新生成') {
                    await translateNamingCommand(context);
                }
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                vscode.window.showErrorMessage(`生成失败: ${message}`);
            }
        }
    );
}
