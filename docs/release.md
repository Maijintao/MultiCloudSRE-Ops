# 发布说明

这个仓库当前已经是脱敏后的公开仓库，可以直接在当前目录中维护和推送。

## 日常维护流程

```bash
python -m unittest discover -s tests -v
node scripts/check-frontend-modules.js
git status
git add <changed-files>
git commit -m "<message>"
git push
```

提交前确认不要包含：

- `.env`
- `state/`
- `.private-release-backup/`
- `*.sqlite3`
- `__pycache__/`
- 私有比赛题
- 真实云主机地址
- kubeconfig、SSH key、API key 或其它凭据

## 首次公开发布

如果将来需要重新做一个无历史公开仓库，请从干净目录重新 `git init`，不要推送包含私有题库
或部署历史的旧 Git 仓库。发布前至少运行：

```bash
python -m unittest discover -s tests -v
node scripts/check-frontend-modules.js
```

仓库内的卫生测试会扫描常见泄漏，但发布前仍应人工检查 staged diff。
