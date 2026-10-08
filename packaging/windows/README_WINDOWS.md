# AI 阅卷助手：Windows 10/11 独立安装版 V1.1

本目录是 `smqka/local-grading-automation` 的 V1.1 升级包，保留原有网页操作界面、Node 本地网页服务、Python 评分与鼠标点击功能。

## 最终使用者（不需要开发环境）

1. 在另一台 **64 位 Windows 10/11** 电脑双击 `AI阅卷助手_Setup_1.1.0_x64.exe`。
2. 按向导安装，创建桌面快捷方式。
3. 双击 **AI阅卷助手**。
4. 首次启动填写：支持图片的模型名称、HTTPS 接口地址、API Key；网络模式默认「自动读取系统代理」。
5. 软件自动启动两个本地服务，自动打开 `http://127.0.0.1:5175`。
6. 在浏览器内进行窗口捕获、答案区域框选与坐标配置。关闭 **AI阅卷助手** 控制窗口会结束由其启动的两个后台服务。

不需要安装 Python、Conda、Node.js、npm、PyInstaller 或 Inno Setup。**联网调用视觉模型仍需要网络和可用的 API Key**。浏览器仍需支持屏幕捕获授权；建议使用 Edge / Chrome。

首次启动的 API Key 经 Windows 当前用户 DPAPI 加密，保存在 `%LOCALAPPDATA%\LocalGradingAutomation\config.json`，只可由相应用户凭据解密。密钥不写入安装目录，也不会写入日志。用户配置在卸载后保留。

服务端口固定：网页 `127.0.0.1:5175`，API `127.0.0.1:8765`。如果端口被占用，启动器会显示错误，不会终止其他进程。

## V1.1 新增的代理配置

- **自动读取系统代理（默认）**：优先按 Windows 静态代理配置解析当前 API 地址；没有静态代理时尝试 PAC/WPAD（如果设置了）；若无法得到结果，再使用当前进程已有的代理环境变量，最后直连。仅修改本软件两个后台子进程的网络环境变量，不修改 Windows 用户的全局代理环境变量。
- **直连**：强制忽略 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY，不经代理请求模型。
- **手动代理**：输入 `http://127.0.0.1:7897` 等当前设备实际 HTTP 代理地址和端口。其他电脑不一定是 7897；需要按该电脑实际设置填写。
- **测试网络连接**：使用 Windows 的 curl.exe GET `/models`（不携带 API Key、不会消耗模型费用）。HTTP 401/403 表示服务器可达，不代表 API Key 或图片识别能力已验证。保存后运行软件、使用模拟答案进行图片评分才能验证完整功能。
- 旧 V1.0 配置 `config.json` 可直接读取（缺少网络字段时默认为自动），API Key 仍使用 Windows DPAPI 加密存储。升级安装不应删除用户配置。

**限制：** 需要目标电脑确实有可用网络或代理；PAC/WPAD 依赖 Windows WinHTTP 执行，复杂脚本/策略可能需要手动配置。不会自动开启、安装或提供 VPN。Python / Node 后台的出口代理配置相同，本地 `127.0.0.1` 通信不走代理。

## 如何得到安装包（推荐，不需要在个人电脑安装构建环境）

1. 将**本改造包内所有文件按相同目录结构合并到原始 GitHub 仓库根目录**。不要把 `grading_installer_overlay` 文件夹整体多套一层。
2. 将新增文件 `git add`、`git commit`、`git push` 上传到你有权限的仓库。仓库管理员也可以用 GitHub 网页上传。
3. 打开 GitHub 仓库 **Actions** → **Build Windows Installer** → **Run workflow**，选择 `main` 分支。
4. 构建成功后打开该次运行页面的 **Artifacts**，下载 `AI阅卷助手-Windows-x64-Setup`。
5. 解压下载到的 Actions 产物，找到 `AI阅卷助手_Setup_1.1.0_x64.exe`，发给需要安装软件的 Windows 用户。

GitHub Actions 的构建机负责准备 Python / Node / Inno Setup，最后将运行环境封装在安装程序里。普通使用者不需要这些组件。GitHub Actions 产物会根据仓库权限和保留周期清理，建议下载备份，发布正式版可上传至 GitHub Releases。

## 本地制作安装包（仅构建者需要环境）

构建者在 Windows x64 安装：Python 3.12、Node.js 22、Inno Setup 6；然后在原始仓库根目录运行：

```powershell
python -m pip install "pyinstaller>=6.10,<7"
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1
```

安装包输出在 `dist\installer\`，独立程序运行文件位于 `dist\windows-stage\`。不需要 npm install，因为原始仓库目前没有第三方 npm 包。

## 设计说明

- `api_entry.py`：冻结原项目 `grading_api.server.main`，没有重写评分算法。
- `launcher.py`：Tk 桌面控制程序；首次设置、DPAPI 保存 API Key、启动健康检查、自动打开浏览器、退出时关闭其两个子进程。
- `build.ps1`：打包 Python API 和启动器；拷贝原生 Node.exe 以及原前端、服务端静态资源。
- `LocalGradingAutomation.iss`：Inno Setup 单用户安装器，默认安装到本地用户目录、创建快捷方式。
- `.github/workflows/build-windows-installer.yml`：云端 Windows 构建 + 测试 + 上传 exe。

## 重要提醒

- 软件仅在 `127.0.0.1` 本机监听，不会连接或代理到校内网络的其他设备；远程模型 API 仍通过 HTTPS 请求调用。
- 无数字签名的安装包可能受到 Windows SmartScreen 的“未知发布者”提示，不应承诺完全不弹安全提示。如需正式分发建议代码签名。
- 自动点击的坐标会受到系统缩放、窗口布局和双屏排列影响。正式批卷前需使用测试账号和测试题逐项验证。
- 不会绕过教师登录、平台权限或浏览器的窗口捕获确认。不要在无授权情况下处理学生敏感材料。
- 在第三方图片上传模式下，学生答案图片可能被上传到第三方平台；默认并未启用该模式。
- 若安装后未启动，点击启动器里的 **查看日志**，检查 `%LOCALAPPDATA%\LocalGradingAutomation\logs`。
- 单独打开 `http://127.0.0.1:5175` 只能看到网页，必须保持桌面控制窗口运行才能维持后台服务。

## 安装版升级说明

同一个 AppId 会让 V1.1 安装到 V1.0 的默认安装目录；建议先关闭旧版控制窗口再安装。升级后打开「模型与网络配置」并点击「测试网络连接」，返回 401/403 也是连接成功的正常表现。随后再进行模拟图片评分测试。

## 尚未完成的验证

本增量包是在非 Windows 环境中生成的，已进行 Python 静态检查和代理逻辑单元测试，但**尚未在真实 Windows 机器上运行 PyInstaller、Inno Setup、窗口捕获和鼠标自动点击端到端验收**。通过 GitHub Actions 可以执行首次 Windows 打包，随后应在干净的 Windows 10/11 电脑进行实际安装测试。
