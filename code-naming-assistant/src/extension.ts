import * as vscode from 'vscode';
import { translateNamingCommand } from './commands/translateNaming';
import { renameFileCommand } from './commands/renameFile';
import { renameSymbolCommand } from './commands/renameSymbol';

export function activate(context: vscode.ExtensionContext) {
    const translateDisposable = vscode.commands.registerCommand(
        'codeNamingAssistant.translateNaming',
        () => translateNamingCommand(context)
    );

    const renameFileDisposable = vscode.commands.registerCommand(
        'codeNamingAssistant.renameFile',
        (uri: vscode.Uri) => {
            if (!uri) {
                vscode.window.showErrorMessage('请从资源管理器中右键选择文件或文件夹');
                return;
            }
            renameFileCommand(uri);
        }
    );

    const renameSymbolDisposable = vscode.commands.registerCommand(
        'codeNamingAssistant.renameSymbol',
        () => renameSymbolCommand()
    );

    context.subscriptions.push(translateDisposable);
    context.subscriptions.push(renameFileDisposable);
    context.subscriptions.push(renameSymbolDisposable);

    vscode.window.showInformationMessage('Code Naming Assistant 已激活！使用 Alt+Shift+T 快速命名翻译。');
}

export function deactivate() {}
