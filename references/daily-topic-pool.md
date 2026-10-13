# 每日可挑选的任务池

仅当用户明确要求完整网格组合、多候选池或晨间准备时进入此模式。历史 `daily_pool.enabled` 配置本身不再触发此流程；普通每日三题按 `evidence-led-selection.md` 执行。组合上限和每组目标读配置；不把其他账号固定成8×8，也不按乘积模板批量吐同一命题。

## 每次先更新判断所需上下文

读取当前认可定位/网格、预算、近30天作品命题、近14天案例、选择与拒绝反馈、最新指标评论及其缺口、最新已保存日计划和活跃已选作品。人生与对标只读声明scope。记录实际读取范围；元数据不是完整案例、累计互动不是因果。新增作品、拒绝、入口失败、来源事件变化是重审受影响题的触发器。

配置benchmark_demand时读取其collection_path与signals_path及research/operations/source-health.json：本人评论和对标评论证据分开，按video_id/comment_id追溯。新增问题、审读任务或来源状态变化触发受影响组合重审；只更新采集检查时间不触发无意义改题。原候选source-snapshot保留历史，当前连通状态不能反向改写原证明。

先看未过期储备和缺口，再补近期原始线索。最新资讯经当前激活 topic-radar 的 daily-sources 契约采集。新闻要变成有用任务；纯发布、训练或作者高级技术无观众入口时可保留观察，不占实用待选目标。没有相关新闻不硬凑热点。

逐组合判断关系，提出不同输入/场景/成果/证据的独立题，逐条语义去重。已拒命题不能只换标题复提；既有命题更新复用稳定ID。全池可浏览，今日少量优先项是编辑判断，需要说明为什么今天值得先测；不要用关键词或模型置信度假装准确率。组合达标和今日优先项只计未过期且待选的test_first/record_candidate；observe保留浏览，单列储备数量，不补足实用题目标。达不到目标的格子明确列缺口，保留partial，不为凑数将观察题升成待测或换标题补题。

## 持久化与状态

`scripts/daily_pool.py --help` 提供 validate、publish、project、decide。workspace 必须采用已声明 moonlit.py/topic_store 作品与选题合同。程序负责字段、证据引用、精确命题防重、幂等、用户状态、索引与覆盖投影，Agent负责需求、组合、作者讲法和语义去重。

输入为候选数组及 source-snapshot；候选包括 daily_pool、title/core_thesis、user_task/input/steps/output/verification、grid_pair、tool_entry、prep_minutes、author_work_ids/author_basis、demand_basis、source_ids/source_urls、why_now/timeliness、generated_at/checked_at/expires_at、recording_status、dedup_review、daily_rank。具体CLI入参和格式从 --help 及实现读取，不猜参数。工具入口 planned/unknown 分别保持先测/观察；record_candidate 需有通过的 test_evidence。来源引用可追溯不等于事实自动证明。

生成/审读卡按 [七模型拆解](04-topic-template.md)：全池先补读者处境、原问题或假设、当前做法、主要收获、价值诊断及缺口；今日入围、用户展开或准备确认的详情再补五个入口、承诺对应、阅读/分享理由和复盘假设。新增content_brief与topic_analysis同题存进candidate；公共投影为contentBrief/topicAnalysis。程序仅透传，不以字段齐全自动判语义合格。旧卡可为null，按当前使用范围补齐，不重建ID、不刷新原生成时间、不影响已选/拒绝状态；缺拆解不冒充完整卡或删除真实旧储备。

同一topics.json里的多条更新必须在同一份当前文档中合并，保留其他题和用户状态。publish返回更新数后仍逐题读回本轮改动、原生成时间、身份及今日排序，不能只凭总数判定补证已经落盘。

source-snapshot 记录实际来源状态、读取范围、事件日、核对时间、当期线索与上下文摘要。晨间 state 保存实际更新、覆盖、缺格、上下文指纹与少量优先ID。completed 只说明写入过程完成，不意味着所有来源成功、所有格子满或全部题通过实测。

推荐仍归 topics/YYYY/YYYY-MM-DD/topics.json，索引归topics/index.json。后台仅投影与调用当前锁定 CLI；不另建可编辑候选库。用户明确选择才调用原 topics-pick 属主，可选direction原话保留于选择记录与作品source-topic；重复选复用作品且不改原方向，新方向走作品调研修订入口。用户授权确认后调研时按 [已确认选题调研](picked-topic-research.md) 处理；拒绝保存实际理由并退出待选。读取详情不是选择。

按来源时效和内容变化设置合理失效日。旧题不因为今日运行而刷新 generated_at；未复查不改 checked_at，复用来源保留原核对时间。过期/已选/拒绝不计待选覆盖。更新失败或部分完成保持实际状态，旧储备继续带原日期可浏览。

## 调度与可视化

使用宿主正式自动化，先查重更新已有任务；用户希望的准备时点、数据回流与研究开始时间读使用方配置。可将数据回流和选题更新分开以便独立恢复。首次手动初始化不算首次无人值守运行；调度配置与实际运行回执分别呈现。失去账号/来源权限时只停该路，其他带日期证据可以继续用。

每次推荐展示实际候选池、选格计数、当天优先项、输入与成果、操作计划、作者材料、费用/入口待测、来源状态和更新日期。原框架图不能替代真正候选；来源失败不能隐去。选择/拒绝后读回实际台账，详情随格子/筛选改变保持一致。无变化时保持安静，仅有新结果、失败或需用户处理事项才通知。
