# 贡献指南

感谢你改进 AIOps OJ Platform。

## 开发检查

需要 Python 3.10 或更新版本。

```bash
python -m unittest discover -s tests -v
node scripts/check-frontend-modules.js
```

前端源码位于 `static/app/`，直接以浏览器原生 ES Modules 运行，没有 bundle 生成步骤。

## 题目材料

公开仓库只提交可公开的 demo case。私有比赛题、隐藏答案、真实云主机、kubeconfig、API key、
SSH key、数据库、截图和运行状态不要提交到公开仓库。

提交前请运行测试，并检查 `git status` 与 `git diff`。
