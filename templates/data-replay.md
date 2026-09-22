# 复盘记录

当前可用，按已有后台记录或用户数据执行，不要求先接齐所有平台。

必填：work_id、topic_id、platform、observation_start、observation_end、quadrant、main_task、CTA、evidence_path。

可选数值：views、likes、favorites、comments、follows、asset_uses、qualified_requests、scope_discussions、quotes、orders、adoption_feedback。缺值用null，且记录分母/统计定义；成交、试听、咨询不能混为同一种转化。

决策字段：keep / revise / collect_evidence / pause，原因、下一轮动作、决策来源。记录用户自述与后台计数的区别，不从一次表现推断因果。

口径和回写步骤见 ../references/07-data-loop.md。
