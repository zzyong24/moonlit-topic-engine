# 研究状态与内容交接

## 存放与来源

工作区研究目录保存 research-config.json：scope_id、selection_file、ledger_file、账号配置/历史台账来源、筛选参数、approved_at/source、证据索引。字段允许为空并标unknown；找不到时先检查当前会话与已有报告，不擅自改变认可范围。不得保存密钥、Cookie或授权凭据。

业务事实与当前价格从用户资料读取；周更数量、优先服务、报价试验记录 proposed/approved/testing/validated/retired 及依据，不因助手建议或一次认可研究清单就升级为长期战略。配置在用户工作区，Skill源码不包含用户数据。

## 每条记录的独立维度

- identity：platform、account、work_id；源ID不因标题修改而变化。
- source：captured_at、public_url、evidence_path、页码/抓取范围、likes及统计口径。
- selection：scope_id、included、rule、rank、median；与fit分开。
- content：metadata_only / text_available / text_unusable；全文来源与授权范围单独保留。
- analysis：unreviewed / summarized / structure_reviewed；reviewed_at、reviewer、摘要路径。
- visual：not_viewed / sampled / reviewed；采样范围。文字分析不得升级视觉状态。
- fit：unreviewed / core / expression_only / mismatch；说明理由。
- commercial：self_report / visible_entry / transaction_evidence / hypothesis / unknown，可多项；关联证据。
- job：status、task_id、key_fingerprint、attempt_history；与analysis独立，正文成功不代表分析完成。

未知不是0，待分析不是失败。报告数字从同一scope台账统计，不从多个日期的叙述拼接。覆盖率分母分别注明账号数、入选视频、正文可用、已审数量。

## 选题到制作的最小交接

`topic_id → 账号/受众任务 → Q1-Q4 → 唯一内容任务 → 命题 → 来源及核验日 → 结构卡ID → 一手证据或测试计划 → 去重范围/结论 → 可选CTA及入口就绪状态 → 承接假设 → 验证指标 → 状态`。

选题可以有planned证据；脚本定稿要求结论对应真实证据，计划不能改写为亲历。用户批准制作后才创建作品ID，topic_id映射到work_id，不用平台发布记录新建作品。

## 复盘

记录发布后观测窗口、平台、分母与指标：观看/收藏/关注、资产实际使用、有效场景提交、范围讨论、报价、成交、采用反馈。商业转化不得用互动替代；缺数留空。每次提出继续、改角度、补证据或暂停的决策及原因，回写同一作品记录，下一轮选题先读这些决策。

## 既有台账字段适配

读取历史平铺台账时显式映射：`existing_status → job.status`，`content_state → content`，`review_state → analysis`，`visual_state → visual`，`fit_state → fit`；中文analysis_status、fit等保留为显示说明，不拿它们覆盖规范状态。`scope_id`是当前范围键。缺少来源、commercial或job细节时记unknown/未提供，不能从succeeded推导。原task_id及key_fingerprint必要时从关联的视频记录读取，当前研究CSV不承担任务调度。新消费者先执行这一映射，不按字段名猜测进度。


内容简报content_brief先于象限与结构：具体人和处境、关切及其依据/假设、预期观众变化、材料支持关系、未知与分歧、帮助范围及不足、表达方式。定义见 moonlit-business-copywriter/references/content-first-principles.md。CTA允许null，纠错与确定结论不是必填要求。
