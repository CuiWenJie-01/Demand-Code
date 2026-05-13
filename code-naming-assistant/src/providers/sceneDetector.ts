import * as vscode from 'vscode';
import { NamingScene } from '../utils/prompts';

export function detectSceneFromContext(): NamingScene {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        return 'variable';
    }

    const document = editor.document;
    const selection = editor.selection;
    const lineText = document.lineAt(selection.start.line).text;
    const selectedText = document.getText(selection).trim();

    if (lineText.match(/^\s*class\s+\w*/)) {
        return 'class';
    }
    if (lineText.match(/^\s*def\s+\w*/)) {
        return 'function';
    }
    if (lineText.match(/^\s*[A-Z_][A-Z0-9_]*\s*=/)) {
        return 'constant';
    }
    if (selectedText && selectedText.match(/^[A-Z][a-zA-Z0-9]*$/)) {
        return 'class';
    }
    if (selectedText && selectedText.match(/^[a-z_][a-z0-9_]*\(/)) {
        return 'function';
    }

    return 'variable';
}

export function detectSceneFromFileName(fileName: string): NamingScene {
    if (fileName.endsWith('.py')) {
        return 'file';
    }
    return 'file';
}

export function detectSceneFromUri(uri: vscode.Uri): 'file' | 'directory' | 'project' {
    const stat = vscode.workspace.fs.stat(uri);
    try {
        const fs = require('fs');
        const statSync = fs.statSync(uri.fsPath);
        if (statSync.isDirectory()) {
            const parent = vscode.Uri.joinPath(uri, '..');
            const isWorkspaceRoot = vscode.workspace.workspaceFolders?.some(
                wf => wf.uri.fsPath === uri.fsPath
            );
            if (isWorkspaceRoot) {
                return 'project';
            }
            return 'directory';
        }
        return 'file';
    } catch {
        return 'file';
    }
}
