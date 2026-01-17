# Git 使用说明（本项目）

本仓库用于管理 `d:\dhga\server` 的服务脚本、监控系统与前端页面代码。推荐的最小工作流如下。

## 1) 初始化（已完成）

如果你是第一次在这个目录启用 Git：

```powershell
cd d:\dhga\server
git init -b main
```

本仓库已添加：

- `.gitignore`：忽略日志、数据库、虚拟环境等本地运行产物
- `.gitattributes`：规范常见文件的换行符（Windows/脚本兼容）
- `.editorconfig`：基础编辑器格式约定

## 2) 关联远端（GitHub / Gitee / GitLab）

```powershell
git remote add origin <YOUR_REMOTE_URL>
git remote -v
```

## 3) 首次提交

```powershell
git add .
git commit -m "Initial commit"
git push -u origin main
```

## 4) 日常开发建议

- 新功能：`git checkout -b feat/<name>` → 开发 → push → PR/MR
- 修复：`git checkout -b fix/<name>` → 开发 → push → PR/MR
- 发布：打 tag（可选）`git tag -a v0.1.0 -m "v0.1.0"; git push --tags`

## 5) 注意事项

- 不要把密钥提交进 Git（`.env` 已默认忽略）
- `logs/`、`ops/monitor/data/`、`*.db` 等运行时产物已默认忽略

