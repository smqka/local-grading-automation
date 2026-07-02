# 本地阅卷自动化设计文档

本目录记录通用本地阅卷自动化工具的产品、合规、安全、自动化和试运行建议。它不绑定任何具体阅卷平台。

## 项目定位

工具定位为“本机运行、教师可控、AI 辅助”的阅卷自动化工具：

- 用户主动捕获本机阅卷窗口。
- 用户手动输入并确认标准答案和给分规则。
- 模型只针对当前裁剪答案图给出建议分和置信度。
- 自动点击仅在用户启用后执行。
- 低置信度结果按用户设置等待审核或自动跳过。

## 推荐路线

1. 手动建议分：先验证截图、模型、给分规则和结果结构。
2. 坐标辅助点击：记录分值按钮坐标，高置信度时点击分数。
3. 半自动循环：模型返回后决策，翻页完成后自动刷新截图。
4. 稳定性验证：用脱敏样本对比 AI 建议分和人工分。
5. 场景化改造：针对不同阅卷系统调整坐标记录、翻页延迟和截图区域。

## 文档索引

- [01-product-roadmap.md](./01-product-roadmap.md)：分阶段路线。
- [02-compliance-security.md](./02-compliance-security.md)：隐私、安全和账号边界。
- [03-web-automation-design.md](./03-web-automation-design.md)：截图和自动点击设计。
- [04-ai-grading-policy.md](./04-ai-grading-policy.md)：AI 评分策略。
- [05-validation-release-checklist.md](./05-validation-release-checklist.md)：验证和发布清单。
