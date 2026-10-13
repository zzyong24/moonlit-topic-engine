# 人生上下文、九宫格与可录选题匹配

当用户明确要求联动人生地图/九宫格/兴趣/对标或做持续选题库时使用。普通日常三题默认读 `evidence-led-selection.md`，不因历史网格配置而触发本流程。来源发现仍归 moonlit-topic-radar；此处负责按任务选择上下文、理解材料与匹配。账号偏好、来源启用、预算与九宫格中心留在使用方配置，不固化到 Skill。

## 两种召回，各自有边界

1. **外部线索召回**：按受众任务和主题簇，生成各来源适用的公开查询，再分近期、近期仍有用、常青/本人现场三个窗口。AI 主线、当前实践、更广人生兴趣可以并行。新来源不默认都已可访问；事实核验回到原作者/官方，访问不足留缺口。具体查询规划归雷达的 `scripts/plan_recall.py`。
2. **本人上下文召回**：先读当期配置、账号快照和近期作品，再只召回明确项目中的相关 life_map/topic_grid 卡，记录项目、卡ID、版本、来源、遗漏。历史背景文档是材料索引，不自动升级成人格、当前偏好或成熟能力。对一个入围题只扩展相关的经历、原项目和结构卡；不把全部人生史送给外部检索/评分服务。

当前程序负责明确范围、全条目预算、版本与引用校验；对“这段经历为什么相关”的语义判断由当前 Agent 完成。没有执行语义审读的条目保留 unreviewed；不能把词频、相同标签或人工加权叫语义理解准确率。

## 九宫格如何联动

先区分网格角色。用户要“观众兴趣/场景 × 行业方法”的双九宫格时读取 [paired-grids.md](paired-grids.md)；下方中心＋外围角度是一种已有框架，不能混称同一种方法。作者 life_map 与作者兴趣只提供讲法和材料，不自动代表观众需求。

中心是当前想帮助观众完成的具体任务；外围八个角度可替换、可留空。对入围线索找一个最有材料的格子，不逐题展开八条。记录 `memory_links: [{project_key, context_id, version, slot}]` 和核心命题；四象限负责内容目标，格子负责角度，两者不是同一种分类。

候选的唯一权威记录在使用方 topics；用户选择后关联 works。记忆端只保留选题ID/路径、状态、版本与下一步引用，不成为第二个可编辑选题库。写回沿用记忆端的乐观版本保护，冲突读回重审，不覆盖新状态；不全局注册召回或恢复已暂停的聊天批量采集。

人生事件中的背景/选择/行动/结果、当时感受、后来理解、能力假设分开。作者提议与尚未确认的兴趣可用于探索，不能作为亲历事实写稿。更广人生内容有明确来源和观众收益时可以入选，不因没有 AI 关键词排除。

## 匹配与制作队列

语义审查每题回答：我为什么关注、观众得到什么、我凭什么讲、怎么在预算内取得可见证据、相对既有内容有什么实质新意、可留什么价值。对标只选择可迁移的段落功能/问题入口，注明实际阅读范围；不挪用别人的经历作为作者依据。指标旧快照不充当今日账号状态。

`scripts/personalize_topics.py` 提供两步：

```text
python3 <engine>/scripts/personalize_topics.py context --workspace <作品工作区> --config <个人选题配置.json> --date YYYY-MM-DD --memory-export <本轮按需召回.json> --output <外部运行目录/context.json>
python3 <engine>/scripts/personalize_topics.py rank --context <context.json> --input <候选.json> --reviews <Agent语义审读.json> --count 3 --output <本轮匹配.json>
```

context 不执行网络读取，只接收显式导出；默认不加载文档全文，仅哈希和带归属摘要、近期元数据。先用受众任务审读相关原文，再填 reviews。引用的 context_hash 变了必须重审。评论、价格、功能与事实时效分别核验，不以 hash 代替事实真伪。

review 必填 candidate_id、context_hash、reviewer、checked_at、evidence_ids、core_thesis、fit_decision（relevant/explore/mismatch/unknown）、duplicate_status、evidence_state、六维 dimensions（value 0–5 与 reason）、production_plan。生产计划包含具体 task、steps、visible_result、done_when、opening、format、prep_minutes、access_ready。ready 还必须 facts_checked=true 和 author_basis_evidence_ids，指向本人真实材料/项目记录；对标或九宫格提议不能证明一手结果。人生地图的 memory_links 用真实 event_id，九宫格用外围 slot。

实用任务账号另需 paired-grids 的 audience_review。fit_decision 包括作者/任务相关性，不能替代观众门槛审读；production_plan.access_ready 是作者能测试，viewer_entry 是观众能操作。未知保持观察，入口待测保持先测，fail 不进短名单。没有此配置时不强制把人生叙事或解释改成操作教程。

队列含义：

- record_candidate：已有足够本人依据与明确录制方案，预算内；仍是待选题，不是成片通过或用户认可。
- test_first：有预算内的具体可执行测试，结果尚未产生；先做小样，不提前写成功故事。
- deep_build：有明确计划，但超出本轮预算，进入中期项目储备。
- observe：权限、材料、时间或关键条件尚不清楚，下一步补最小缺口。
- skip：人群任务不合适或命题真正重复。不能只换标题重新推荐。
- existing_pool：同一命题已在近期候选池，引用已有topic_id并刷新其审读；不因为更换来源或标题重复创建候选。

六维辅助分与四象限百分制、JEV 分分别标注，不合并成“爆款指数”。权重是初始编辑实验设置，不是已学习到的用户人格。去重未完成最高79；语义审查为 substantive_update 时须指明新证据。程序只阻止已知相同命题及字段冲突；全文去重仍需人工/Agent逐项审读。

## 如何持续，而非无限刷标题

每次选题运行按实际条件更新：来源状态与日期、可录/需测/中期库存、用户 pick/不感兴趣/太难/重复的原因、实测结果、作品去向及发布后的反馈。选择结果与平台表现分开；不给未发布题补效果数字。优先从“真实项目有了新结果、旧题有了新证据、评论提出新任务”补池，外部热点只是其中一路。

用户给出具体反馈后，可运行 `personalize_topics.py feedback --workspace <工作区> --topic-id <已登记ID> --outcome can_explain|not_interested|too_hard|duplicate|test_completed|needs_material|audience_mismatch|entry_unavailable --reason <用户实际反馈> --date YYYY-MM-DD`，追加到 topics/selection-feedback.jsonl。只记录用户实际评价，不替用户表示兴趣或凭执行成功生成正反馈；该命令不改定位/权重、不登记发布结果。下一轮 context 读取最近50条，缺失时明确尚无学习样本。已拒同命题不能换标题重推；实质更新须附 changed_evidence 并重新核对人群任务。

先小批运行：来源查询上限、入围深挖数量、每主题最多入选数由配置决定，定期检查未被覆盖的主题/来源和时间窗。用户没请求定时运行时只保存策略与入口，不创建日更自动化。先验证接续和引用正确，再用实际接受率、实测完成率、重复误报/漏报、本人觉得能讲的比例校准；结构测试不宣称召回准确率。
