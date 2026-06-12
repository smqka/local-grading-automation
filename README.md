# 试卷批改工具

一个面向数学老师的网页端 AI 批阅辅助工具。当前产品路线坚持“老师确认型辅助批阅”：不保存爱探究账号密码，不自动提交分数，不调用爱探究私有接口。

当前版本实现本地 AI 建议评分闭环。网页端负责老师主动授权的窗口捕获、答案区域框选、裁剪预览和结果展示；Python 评分 API 只接收裁剪后的学生答案区域图片，返回结构化“建议分”，不读取或提交爱探究数据。

## 功能边界

- 网页工作台由 `server/index.js` 提供，默认访问 `http://localhost:5173`。
- 评分 API 由 `grading_api` 提供，默认监听 `127.0.0.1:8765`。
- 前端调用同源 `/api/grade-answer`，由 Node 代理到 Python `/api/grade`。
- API key 只从服务端环境变量读取，不进入前端代码。
- 请求图片只在内存中处理，服务端不落盘保存。
- 返回建议分、扣分点、置信度和人工复核提示。
- 低置信度或非法模型输出会强制标记为人工复核。
- 不自动点击、不自动填分、不调用爱探究私有接口。

## 本地启动

先启动评分 API：

```powershell
python -m grading_api.server
```

如果系统 `python` 不可用，可以使用 Codex 桌面内置 Python 路径启动：

```powershell
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m grading_api.server
```

再启动网页端：

```powershell
node server/index.js
```

打开：

```text
http://localhost:5173
```

使用流程：

1. 点击“开始捕获”，在浏览器弹窗里选择爱探究窗口。
2. 在预览画面中拖拽框选学生答案区域。
3. 检查裁剪图，确认不含姓名、班级或学号。
4. 填写满分，标准答案和给分规则可手动输入，也可选择图片作为参考材料。
5. 点击“获取建议分”，查看建议分、扣分点、置信度和复核提示。
6. 老师自行在爱探究中确认并手动录入分数。

## 评分 API 配置

复制 `.env.example` 为本地 `.env`，填入服务端环境变量。`.env` 已被 `.gitignore` 忽略。

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-4.1"
```

可选项：

- `PORT`：网页端口，默认 `5173`
- `OPENAI_BASE_URL`：默认 `https://api.openai.com/v1`
- `GRADING_API_HOST`：默认 `127.0.0.1`
- `GRADING_API_PORT`：默认 `8765`
- `GRADING_API_URL`：Node 代理访问的评分 API 地址，默认由 host/port 拼出
- `GRADING_API_TOKEN`：设置后请求必须带 `X-Grading-Api-Token`
- `GRADING_MAX_IMAGE_BYTES`：默认 `5242880`
- `GRADING_ALLOWED_ORIGINS`：逗号分隔的前端来源白名单
- `GRADING_PROXY_MAX_BODY_BYTES`：Node 代理请求体限制，默认 `25165824`

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

```powershell
Invoke-RestMethod http://127.0.0.1:5173/api/health
```

## 请求示例

```json
{
  "image": "data:image/png;base64,...",
  "max_score": 6,
  "standard_answer": "x = 2",
  "standard_answer_image": null,
  "grading_rules": "写出正确方程得 2 分；化简过程正确得 2 分；最终答案正确得 2 分。",
  "grading_rules_image": null,
  "deduction_rules": "过程正确但计算小错最多给 4 分；空白给 0 分。",
  "allow_equivalent_answers": true,
  "score_by_steps": true,
  "score_precision": "0.5",
  "question_id": "sample-q1",
  "rule_version": "v1"
}
```

`standard_answer` 和 `grading_rules` 可以留空，但对应的 `standard_answer_image` 或 `grading_rules_image` 必须提供。参考图片只支持 PNG、JPEG 和 WebP，且同样只在内存中处理。

响应示例：

```json
{
  "suggested_score": 5.5,
  "max_score": 6.0,
  "confidence": 0.93,
  "needs_review": false,
  "review_reason": "",
  "deduction_points": ["最终化简有轻微缺失"],
  "student_answer_summary": "学生列式正确，过程基本完整。",
  "uncertain_factors": [],
  "model": "gpt-4.1",
  "prompt_version": "grading-api-v1",
  "rule_version": "v1",
  "question_id": "sample-q1"
}
```

## 测试

```powershell
python -m unittest discover -s tests
```

## 文档

设计和合规指导见：

- `docs/auto-grading-guide/README.md`
