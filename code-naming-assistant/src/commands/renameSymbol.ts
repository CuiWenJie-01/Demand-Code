import * as vscode from 'vscode';
import { OllamaClient } from '../providers/ollamaClient';
import { NamingScene, SCENE_LABELS, buildPrompt } from '../utils/prompts';
import { cleanModelOutput, formatByCase } from '../providers/namingFormatter';
import { detectSceneFromContext } from '../providers/sceneDetector';

export async function renameSymbolCommand(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showErrorMessage('请先打开一个文件');
        return;
    }

    const document = editor.document;
    const selection = editor.selection;
    const selectedText = document.getText(selection).trim();

    if (!selectedText) {
        vscode.window.showErrorMessage('请先选中要重命名的代码符号');
        return;
    }

    const config = vscode.workspace.getConfiguration('codeNamingAssistant');
    const ollamaUrl = config.get<string>('ollamaUrl', 'http://localhost:11434');
    const model = config.get<string>('model', 'gemma3:4b-it-qat');

    const client = new OllamaClient({ url: ollamaUrl, model });

    const isConnected = await client.checkConnection();
    if (!isConnected) {
        vscode.window.showErrorMessage('无法连接到 Ollama 服务。请确认 Ollama 已启动且模型已下载。');
        return;
    }

    const autoScene = detectSceneFromContext();

    const sceneOptions: { label: string; scene: NamingScene; picked?: boolean }[] = [
        { label: '$(symbol-variable) 变量名 (snake_case)', scene: 'variable' },
        { label: '$(symbol-method) 函数/方法名 (snake_case)', scene: 'function' },
        { label: '$(symbol-class) 类名 (PascalCase)', scene: 'class' },
        { label: '$(symbol-constant) 常量名 (UPPER_SNAKE_CASE)', scene: 'constant' },
    ];

    const defaultIndex = sceneOptions.findIndex(opt => opt.scene === autoScene);
    if (defaultIndex >= 0) {
        sceneOptions[defaultIndex].picked = true;
    }

    const pick = await vscode.window.showQuickPick(
        sceneOptions.map(opt => opt.label),
        {
            placeHolder: '选择命名场景（已根据上下文自动推荐）',
        }
    );

    if (!pick) {
        return;
    }

    const selectedScene = sceneOptions.find(opt => opt.label === pick)?.scene;
    if (!selectedScene) {
        return;
    }

    const input = await vscode.window.showInputBox({
        prompt: `当前选中的符号：${selectedText}`,
        placeHolder: '输入中文描述来生成新名称，或留空使用当前文本',
        value: selectedText,
    });

    if (input === undefined) {
        return;
    }

    const textToTranslate = input.trim() || selectedText;

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: `正在生成${SCENE_LABELS[selectedScene]}...`,
            cancellable: false,
        },
        async () => {
            try {
                const prompt = buildPrompt(selectedScene, textToTranslate, textToTranslate);
                const rawResult = await client.generate(prompt);
                const cleanedResult = cleanModelOutput(rawResult);

                let finalResult = cleanedResult;
                switch (selectedScene) {
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

                const confirm = await vscode.window.showWarningMessage(
                    `确认替换？\n从：${selectedText}\n到：${finalResult}`,
                    { modal: true },
                    '确认',
                    '取消'
                );

                if (confirm === '确认') {
                    await editor.edit(editBuilder => {
                        editBuilder.replace(selection, finalResult);
                    });
                    vscode.window.showInformationMessage(`已替换为：${finalResult}`);
                }
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                vscode.window.showErrorMessage(`生成失败: ${message}`);
            }
        }
    );
}
