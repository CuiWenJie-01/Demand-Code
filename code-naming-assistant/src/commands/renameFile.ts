import * as vscode from 'vscode';
import * as path from 'path';
import { OllamaClient } from '../providers/ollamaClient';
import { NamingScene, SCENE_LABELS, buildPrompt } from '../utils/prompts';
import { cleanModelOutput, formatByCase } from '../providers/namingFormatter';

export async function renameFileCommand(uri: vscode.Uri): Promise<void> {
    const config = vscode.workspace.getConfiguration('codeNamingAssistant');
    const ollamaUrl = config.get<string>('ollamaUrl', 'http://localhost:11434');
    const model = config.get<string>('model', 'gemma3:4b-it-qat');

    const client = new OllamaClient({ url: ollamaUrl, model });

    const isConnected = await client.checkConnection();
    if (!isConnected) {
        vscode.window.showErrorMessage('无法连接到 Ollama 服务。请确认 Ollama 已启动且模型已下载。');
        return;
    }

    const fs = require('fs');
    const stats = fs.statSync(uri.fsPath);
    const isDirectory = stats.isDirectory();
    const oldName = path.basename(uri.fsPath);

    let scene: NamingScene;
    if (isDirectory) {
        const isWorkspaceRoot = vscode.workspace.workspaceFolders?.some(
            wf => wf.uri.fsPath === uri.fsPath
        );
        scene = isWorkspaceRoot ? 'project' : 'directory';
    } else {
        scene = 'file';
    }

    const input = await vscode.window.showInputBox({
        prompt: `当前${isDirectory ? '文件夹' : '文件'}名：${oldName}`,
        placeHolder: '输入中文描述来生成新名称，或直接留空使用当前名翻译',
        value: oldName,
    });

    if (input === undefined) {
        return;
    }

    const textToTranslate = input.trim() || oldName;

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: `正在生成${isDirectory ? '文件夹' : '文件'}名...`,
            cancellable: false,
        },
        async () => {
            try {
                const prompt = buildPrompt(scene, textToTranslate);
                const rawResult = await client.generate(prompt);
                const cleanedResult = cleanModelOutput(rawResult);

                let finalResult = cleanedResult;
                if (scene === 'project') {
                    finalResult = formatByCase(cleanedResult, 'kebab');
                } else if (scene === 'directory' || scene === 'file') {
                    finalResult = formatByCase(cleanedResult, 'snake');
                }

                if (!isDirectory && scene === 'file') {
                    const ext = path.extname(oldName);
                    if (ext && !finalResult.endsWith(ext)) {
                        finalResult = finalResult + ext;
                    }
                }

                const newUri = vscode.Uri.joinPath(uri, '..', finalResult);

                const confirm = await vscode.window.showWarningMessage(
                    `确认重命名？\n从：${oldName}\n到：${finalResult}`,
                    { modal: true },
                    '确认',
                    '取消'
                );

                if (confirm === '确认') {
                    await vscode.workspace.fs.rename(uri, newUri, { overwrite: false });
                    vscode.window.showInformationMessage(`已重命名为：${finalResult}`);
                }
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                vscode.window.showErrorMessage(`重命名失败: ${message}`);
            }
        }
    );
}
