# R3 CIEDG 应用接入进度

- Issue：#24；分支：`research/r3-ciedg-application`，从稳定 `research/point1-integrated-method-v0` 建立。
- 已完成：读取 Issue、R3 报告/适配器/确定性 workflow、CIEDG 调用链；只读核验已授权资源为两个存储分区、69 份 EDF、两份统计 JSON 与非权威说明。
- 科学语义：数字事件可作显式计算标签；标签含义、Boundary、采集参考、参与者与诊断组尚未获权威确认。
- 固定方案：应用层配置 → 现有 IntentSpec/TaskSpec/ledger/preflight → 冻结 ContractGraphResidualPlanner → Registry/Executor；事件摘要与质量+功率两个独立任务。
- 固定选择：两个存储分区各按相对路径取前两份 EDF；结果先验不可见。
- 阶段 B/C 已完成：应用层结构化任务桥、私有输出限定 CLI、固定子集选择与独立切窗/PSD oracle；未修改冻结方法或原确定性流程。
- 当前验证：固定 4 份真实 EDF 均完成两项任务；14 项逐例检查全部通过，手动 Welch 最大绝对差约 `2.59e-26`，与原确定性频带输出最大绝对差 `0`。完整逐例记录仅在 Git 忽略的本地目录。
- 合成回归：新增 6 个测试通过；全量 `unittest` 227 项通过、12 项按资源/联网门槛跳过；`compileall` 通过。
- 已补齐：验证报告、ASD 资料缺口与公开/私有结果边界；待完成最终状态、提交/推送/Draft PR/CI/Issue 评论。
- Git 网络记录：本机 `git fetch`/`git push` HTTPS 连续连接重置或 443 超时；授权 GitHub 仓库接口已在同名远端分支建立等价阶段提交，不使用 force。保留本地提交；未来直连恢复需先核对两条 SHA 不同但文件等价的历史，再安全合并。
- Draft PR #25 已建立，base 为冻结研究分支；上一轮远端 HEAD `69a7866` 的 tree 与对应本地 tree `1dc180a` 完全一致。GitHub Actions `unit-tests` run `40079097685` 为 success；CI 未接触真实 R3。
