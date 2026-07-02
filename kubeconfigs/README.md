# Kubeconfig 管理

## 权限分离

靶场提供两种 kubeconfig：

| 类型 | 文件名格式 | 用途 | 权限 |
|---|---|---|---|
| 只读 | `{server-role}-readonly.kubeconfig` | AI Agent 诊断用 | get/list/watch pods, deployments, events |
| 注入 | `{server-role}-injector.kubeconfig` | 出题系统注入故障 | 只读 + patch deployments + Chaos Mesh CRD |

## 部署时自动生成

deploy.sh 的 `08-generate-access` 会按服务器角色创建 ServiceAccount 并生成对应的 kubeconfig 文件。

生成的文件放在 `generated/` 目录（已被 .gitignore 忽略），同时生成 `{server-role}-chaos-dashboard.token` 用于登录 Chaos Dashboard。

## RBAC 模板

- `templates/readonly-clusterrole.yaml` — 只读 ClusterRole + ServiceAccount
- `templates/injector-clusterrole.yaml` — 注入权限 ClusterRole + ServiceAccount（含 Chaos Mesh）

- `templates/chaos-dashboard-clusterrole.yaml` — Chaos Dashboard 登录 token 对应的 ServiceAccount
