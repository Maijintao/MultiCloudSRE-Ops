# 前端模块说明

前端是无依赖的浏览器原生 JavaScript 模块，不再使用生成的 `static/app.js` bundle。

- 源码目录：`static/app/`
- 模块入口：`static/app/main.js`
- HTML 入口：`static/index.html`
- 样式文件：`static/styles.css`

修改前端后运行：

```bash
node scripts/check-frontend-modules.js
```

该检查会阻止以下回退：

- `static/index.html` 加载旧的 `/static/app.js`。
- 源码重新使用 `window.OJApp` 全局注册表。
- ES Module import 缺少 `.js` 后缀。
- 使用内联 DOM 事件属性。

CI 会运行该脚本，确保前端仍然保持原生模块结构。
