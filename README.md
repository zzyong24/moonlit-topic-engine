![选题引擎：找到值得讲、也有依据讲的那一题](assets/readme/hero.png)

# 月明·选题引擎

结合定位、研究和真实任务，选出值得做的内容角度，并把证据和下一步测试写进选题卡。

## 你会得到什么

- 按请求数量提供的候选选题和优先顺序
- 受众任务、核心收益、切口与论证方向
- 来源、去重范围、证据缺口及测试动作

## 试着这样说

```text
用 moonlit-topic-engine。根据我的定位和已有研究给我三个选题。说明为什么适合现在做、观众得到什么、还缺哪些证据。
```

## 安装与首次使用

将本仓库的完整目录交给支持本地 Skill 的 Agent 安装，保留 `SKILL.md` 与随附资源。已有同名版本时先检查差异；使用版本锁的工作区沿用自身升级机制。

让 Agent 安装：

```text
请安装这个 Skill：https://github.com/zzyong24/moonlit-topic-engine
```

也可通过 Skills CLI 安装：

```bash
npx skills add zzyong24/moonlit-topic-engine
```

## 配置与依赖

需要当前定位、近期内容台账和材料。判断原则依赖 moonlit-business-copywriter，评分规则依赖 moonlit-topic-radar，研究交接使用 moonlit-benchmark-research。可选 JEV 匹配脚本需 typesafe-ai 与 TYPESAFE_API_KEY。

## 数据与使用边界

模型匹配会向配置的 TypeSafe 服务发送候选和定位信息；研究请求交给所选来源。评分是排序参考，不是爆款概率。此 Skill 停在选题和必要大纲，不自动创建作品或全平台成稿。

## 配套 Skill

[benchmark-research](https://github.com/zzyong24/moonlit-benchmark-research) · [business-copywriter](https://github.com/zzyong24/moonlit-business-copywriter) · [topic-radar](https://github.com/zzyong24/moonlit-topic-radar)

## 详细说明

执行流程与资源导航见 [SKILL.md](SKILL.md)。安装检查不代表真实业务验收；需要外部服务、账号登录或付费生成的步骤，应在使用者自己的环境中验证。

---

月明水清深 · `moonlit-topic-engine`

首图为 AI 生成的品牌概念插画，不是工具截图或执行结果。
