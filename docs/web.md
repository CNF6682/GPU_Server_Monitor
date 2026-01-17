# 网页（Web）相关

本项目包含一个监控系统的静态前端页面，位置在 `ops/monitor/frontend/`。

## 1) 本地打开/运行

最简单方式：直接用浏览器打开 `ops/monitor/frontend/index.html`。

如果需要通过 HTTP 方式访问（推荐）：

```powershell
cd d:\dhga\server\ops\monitor\frontend
python -m http.server 8090
```

然后访问：`http://localhost:8090/`

## 2) 作为 Windows 服务运行（NSSM）

本仓库的服务框架支持用 `services/<name>/service.json` 定义服务。已提供一个示例配置：

- `services/monitor-frontend/service.json`

安装/启动示例（管理员 PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\svc\svc.ps1 install monitor-frontend
powershell -File .\ops\svc\svc.ps1 start monitor-frontend
```

## 3) 发布到网页（可选：GitHub Pages）

如果你希望把文档/页面发布成可访问的网站，常见做法是：

- 将仓库推到 GitHub
- 在仓库 Settings → Pages 中配置发布源（例如 `main` 分支的 `/docs`）

本仓库已提供 `docs/index.md` 作为一个简单入口页。

