<br />

# 升级补丁版本 (1.0.0 → 1.0.1)

npm version patch

# 升级小版本 (1.0.0 → 1.1.0)

npm version minor

# 升级大版本 (1.0.0 → 2.0.0)

npm version major

# 如果vsce 没有安装，需要用 npx 来运行，或者先全局安装。
`vsce` 没有安装，需要用 `npx` 来运行，或者先全局安装。

两种解决方式：

**方式 1：直接用 npx（推荐，不用安装）**
```bash
npx @vscode/vsce package
```

**方式 2：先全局安装 vsce**
```bash
npm install -g @vscode/vsce
vsce package
```

> 注意：新版包名是 `@vscode/vsce`，旧版叫 `vsce`。如果上面不行，试试 `npx vsce package`。

# 然后打包

vsce package
