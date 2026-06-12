# 自动批阅工具指导文档

版本日期：2026-06-12

本文件夹用于指导“数学试卷自动批阅辅助工具”的设计、开发、验证和上线。当前目标是先做网页端自动化辅助，而不是直接接入爱探究私有接口，也不是直接全自动提交分数。

## 项目定位

工具定位为“老师确认型 AI 批阅助手”：

- 老师仍然是最终评分人。
- 工具只在老师授权后读取当前屏幕中的答题区域。
- 工具根据老师输入的标准答案、满分和给分规则输出建议分。
- 第一版不保存爱探究账号密码，不绕过登录，不抓取非公开接口，不自动提交最终分数。

## 当前推荐路线

1. 网页端 MVP：老师在电脑微信或网页端打开爱探究，另开浏览器访问本工具，通过浏览器屏幕捕获读取爱探究窗口。
2. AI 辅助评分：只截取“学生答案区域”，上传给后端评分，返回建议分、扣分点和置信度。
3. 人工确认：老师在爱探究中手动录入分数。
4. 试点验证：用已批改样本对比 AI 建议分和老师真实分数。
5. 可控升级：只有当准确率、时效和合规条件达标后，才考虑“一键填分”或官方 API 接入。

## 文档索引

- [01-product-roadmap.md](./01-product-roadmap.md)：分阶段产品计划和每阶段准入条件。
- [02-compliance-security.md](./02-compliance-security.md)：合规、安全、隐私和账号边界。
- [03-web-automation-design.md](./03-web-automation-design.md)：网页端自动化技术设计。
- [04-ai-grading-policy.md](./04-ai-grading-policy.md)：AI 评分策略、人机协作和质量门槛。
- [05-validation-release-checklist.md](./05-validation-release-checklist.md)：测试、试点、发布和回滚清单。

## 明确不做的事

- 不把 API 密钥写进前端代码。
- 不把学生姓名、班级、学号等身份信息作为默认上传内容。
- 不保存老师的爱探究账号密码。
- 不绕过验证码、风控、权限校验或平台限制。
- 不通过逆向接口批量抓取或提交数据作为正式方案。
- 不在第一版自动提交分数。
- 不用学生答题图片训练模型，除非另行取得清晰授权并完成合规评估。

## 参考资料

上线前需要重新核对最新版本：

- 国家法律法规数据库：《中华人民共和国个人信息保护法》  
  https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3YjY0NzJhMzAxN2I2NTZjYzIwNDAwNDQ=
- 国家法律法规数据库：《中华人民共和国数据安全法》  
  https://flk.npc.gov.cn/detail2.html?ZmY4MDgxODE3OWY1ZTA4MDAxNzlmODg1YzdlNzAzOTI=
- 国家网信办：《生成式人工智能服务管理暂行办法》  
  https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm
- MDN：`getDisplayMedia()`  
  https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia
- W3C：Screen Capture  
  https://www.w3.org/TR/screen-capture/
