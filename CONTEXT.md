# Cortensor OpenMinion Verifier

基于 `OpenMinion 0.1` Python SDK 构建的多源可验证声明审计、冗余推理共识裁决与 SDK 模块实测上下文。

## Language

**Claim Dossier**:
待审计的原始事实声明与配套公开上下文档案，包含目标命题、来源快照与预期裁决域。
_Avoid_: 普通聊天提示, 交易订单

**Redundant Verifier Pass**:
由相互独立提示或视角（如佐证者与质疑者）对同一 `Claim Dossier` 分别执行的只读取证与结构化推理轮次。
_Avoid_: 单次问答, 并发重试

**Consensus Verdict**:
汇总多轮 `Redundant Verifier Pass` 结论、证据一致性与分歧点后形成的结构化最终判定（支持、反驳或存疑）。
_Avoid_: 自由文本回复, 随机投票

**Approval-Gated Publication**:
在将 `Consensus Verdict` 对外归档或移交下游发布前，必须经过策略确认暂停或操作者回调授权的安全发布边界。
_Avoid_: 自动发送, 静默写入

**Building Block Probe**:
针对 `OpenMinion` 核心原语逐项执行的确定性行为验证与开发者体验诊断用例，用于生成参赛实测反馈报告。
_Avoid_: 单元测试集, 冒烟脚本
