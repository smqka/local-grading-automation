# 本地阅卷自动化工具

一个可本地运行的 AI 阅卷辅助工具。它通过浏览器窗口捕获和答案区域裁剪，把当前学生答案发送给视觉模型获取建议分；当置信度达到阈值时，可通过本机坐标点击自动选择分数。仓库同时包含一个 Codex Skill，方便基于现有代码改造成其他本地阅卷流程。

## 适用场景

- 阅卷系统没有开放 API，但教师可以在电脑端打开批阅页面。
- 同一道题连续批改，答案区域和分数按钮位置相对稳定。
- 标准答案、给分规则可以由教师手动输入和确认。
- 希望用置信度阈值控制“自动打分 / 等待审核 / 自动跳过”。

不适合：

- 需要绕过登录、验证码、风控或平台权限。
- 需要静默读取第三方系统数据。
- 答案区域、分数按钮位置频繁变化且无法稳定框选。
- 未获得授权就处理含身份信息或敏感信息的学生材料。

## 两种使用方式

### 普通用户：直接运行工具

1. 安装 Node.js 20+ 和 Python 3.10+。
2. 复制 `.env.example` 为 `.env`，填入模型 API 配置。
3. 启动本地工具：

```powershell
scripts\start-local-tool.cmd
```

4. 打开：

```text
http://127.0.0.1:5175
```

5. 在网页里填写题号、满分、标准答案和给分规则。
6. 点击“开始捕获”，选择阅卷系统窗口，并框选学生答案区域。
7. 记录各分值按钮坐标。
8. 设置置信度阈值，以及低于阈值时“等待审核”或“自动跳过”。
9. 点击“开始批卷”。

### Codex 用户：基于 Skill 改造

Skill 位于：

```text
skill/local-grading-automation
```

可以让 Codex 使用该 skill 理解项目结构、自动化状态机、模型图片输入、鼠标坐标点击和常见排查路径，例如：

```text
Use $local-grading-automation to adapt this grading assistant to my local grading system.
```

## 自动批卷流程

工具遵循事件驱动流程：

1. 刷新当前裁剪截图。
2. 发起模型评分请求。
3. 等待当前请求返回。
4. 根据置信度和模型复核标记决策：
   - 达到阈值：点击对应分数按钮。
   - 低于阈值且选择等待审核：暂停。
   - 低于阈值且选择自动跳过：点击跳过坐标。
5. 等阅卷系统翻页完成后，再刷新下一份截图。

模型未返回前不会点击。暂停或重新继续后，旧请求即使返回也不会触发点击，避免上一份结果点到下一份。

## 配置

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

常用变量：

- `OPENAI_API_KEY`：OpenAI 或兼容接口密钥。
- `OPENAI_BASE_URL`：OpenAI 兼容接口地址，默认 `https://api.openai.com/v1`。
- `OPENAI_MODEL`：支持图片输入的模型名。
- `PORT`：网页端口，默认 `5175`。
- `GRADING_API_HOST` / `GRADING_API_PORT`：本地评分 API 地址，默认 `127.0.0.1:8765`。
- `GRADING_IMAGE_URL_MODE`：当网关不支持 base64 图片时，可选 `imgbb`、`litterbox`、`uguu`、`tmpfiles`。

`.env` 不应提交到 Git。

## 图片和模型接口

默认流程优先发送单张裁剪答案图。若模型网关不支持 `data:image/...;base64,...`，可以配置图片转 URL 上传器。开启图片 URL 模式后，裁剪图会先上传到第三方或自有文件服务，再把 URL 发给模型。

建议优先使用支持 base64 图片输入的官方或可信模型接口；在正式场景中，若必须使用图片 URL，优先配置自有对象存储和短期有效链接。

## 本机自动点击

浏览器不能直接控制外部阅卷系统窗口的鼠标，因此自动点击由本机 Python API 调用 Windows 鼠标接口完成。

安全边界：

- 默认只监听 `127.0.0.1`。
- 只有用户显式启用自动点击后才会执行。
- 坐标由用户手动记录。
- 高置信度自动打分只点击分数按钮；如果阅卷系统点分后自动翻页，不再额外点击下一份。
- 自动跳过仅在用户选择“低于阈值自动跳过”时使用跳过坐标。

## 项目结构

```text
web/                 前端工作台：截图、裁剪、规则输入、坐标记录和自动批卷控制
server/              Node 本地网页服务和 API 代理
grading_api/         Python 评分 API、模型调用、图片上传适配和鼠标自动化接口
tests/               Python 单元测试
scripts/             Windows 本地启动脚本
shared/              API 契约草案
docs/                通用设计、合规和试运行文档
skill/               Codex Skill，用于二次开发和维护
```

## 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:5175/api/health
```

## 测试

```powershell
npm.cmd run check
python -m unittest discover -s tests
```

如果系统 `python` 不可用，可以设置：

```powershell
$env:PYTHON_EXE="C:\Path\To\python.exe"
scripts\start-local-tool.cmd
```

## 公开发布前检查

- 不提交 `.env`。
- 不提交 `logs/`。
- 不提交真实学生答案图片或阅卷系统截图。
- 不提交 API key、ImgBB key、中转站私有地址。
- 不在文档中写私人本机路径。
- 确认 `.env.example` 只包含占位符。

## 许可

本项目采用 MIT License。你可以自由使用、修改和分发，但需要保留版权声明和许可证文本。
