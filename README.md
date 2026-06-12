# 试卷批改工具

一个面向数学老师的网页端 AI 批阅辅助工具。当前阶段只建设项目骨架和安全边界，目标是先做“老师确认型辅助批阅”，不保存爱探究账号密码，不自动提交分数。

## 当前阶段

分支：`chore/project-scaffold`

本阶段提供：

- 零依赖 Node 静态服务器。
- 基础网页壳子。
- 健康检查接口。
- 环境变量加载工具。
- 项目目录结构。

后续功能分支会继续实现：

- 浏览器窗口捕获。
- 学生答案区域裁剪。
- 后端 AI 评分接口。
- 建议分展示和人工复核流程。

## 本地启动

```powershell
node server/index.js
```

默认访问：

```text
http://localhost:5173
```

健康检查：

```text
http://localhost:5173/api/health
```

## 环境变量

复制 `.env.example` 为 `.env`，然后填入本地密钥：

```text
OPENAI_API_KEY=your_api_key_here
```

`.env` 已被 `.gitignore` 忽略，不能提交真实密钥。

## 文档

设计和合规指导见：

- `docs/auto-grading-guide/README.md`
