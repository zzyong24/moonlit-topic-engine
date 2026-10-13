# 复盘记录

当前可用，按已有后台记录或用户数据执行，不要求先接齐所有平台。

必填：work_id、topic_id、platform、observation_start、observation_end、quadrant、main_task、CTA、evidence_path。

可选数值：views、likes、favorites、comments、follows、asset_uses、qualified_requests、scope_discussions、quotes、orders、adoption_feedback。缺值用null，且记录分母/统计定义；成交、试听、咨询不能混为同一种转化。

决策字段：keep / revise / collect_evidence / pause，原因、下一轮动作、决策来源。记录用户自述与后台计数的区别，不从一次表现推断因果。

选题卡回读：原topic_analysis及review_plan、实际采用hook_id/标题和内容版本、承诺是否改变、实际主目标与信号。五个未采用标题只保留备选，不分配虚构表现。历史缺预设写unknown，不倒填计划。

诊断分别记录：吸引人的问题、提供价值的材料、可再试的表达及各自观察证据/解释假设。下轮写一个主要changed_factor、保留因素、实际差异与下一次查看条件；数据不足时优先collect_evidence，不凭低点赞判断完播或正文质量。

口径和回写步骤见 ../references/07-data-loop.md。

科学运营补充：account_id、publication_id、published_at、captured_at、实际发布年龄、目标窗口与容差、来源与统计定义、真实分子/分母、累计/区间、样本数、可比范围、混杂因素、数据新鲜度、评论完整性、制作耗时。实验记hypothesis、primary_metric、changed_factor、comparison_scope、check_at、stop_or_expand_condition；观察结论与因果假设分开。
