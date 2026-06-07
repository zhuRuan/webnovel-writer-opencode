# 初始化收集对象（内部数据模型）

```json
{
  "project": {
    "title": "",
    "genre": "",
    "target_words": 0,
    "target_chapters": 0,
    "one_liner": "",
    "core_conflict": "",
    "target_reader": "",
    "platform": ""
  },
  "protagonist": {
    "name": "",
    "desire": "",
    "flaw": "",
    "archetype": "",
    "structure": "单主角"
  },
  "relationship": {
    "heroine_config": "",
    "heroine_names": [],
    "heroine_role": "",
    "co_protagonists": [],
    "co_protagonist_roles": [],
    "antagonist_tiers": {},
    "antagonist_level": "",
    "antagonist_mirror": ""
  },
  "golden_finger": {
    "type": "",
    "name": "",
    "style": "",
    "visibility": "",
    "irreversible_cost": "",
    "growth_rhythm": ""
  },
  "world": {
    "scale": "",
    "factions": "",
    "power_system_type": "",
    "social_class": "",
    "resource_distribution": "",
    "currency_system": "",
    "currency_exchange": "",
    "sect_hierarchy": "",
    "cultivation_chain": "",
    "cultivation_subtiers": ""
  },
  "constraints": {
    "anti_trope": "",
    "hard_constraints": [],
    "core_selling_points": [],
    "opening_hook": ""
  }
}
```

## 字段说明

### project（项目基本信息）
- `title` — 书名（可先给工作名）
- `genre` — 题材（支持 A+B 复合题材）
- `target_words` — 目标总字数
- `target_chapters` — 目标总章数
- `one_liner` — 一句话故事
- `core_conflict` — 核心冲突
- `target_reader` — 目标读者
- `platform` — 发布平台

### protagonist（主角）
- `name` — 姓名
- `desire` — 欲望（想要什么）
- `flaw` — 缺陷（会害他付代价的缺陷）
- `archetype` — 原型标签（成长型/复仇型/天才流等）
- `structure` — 结构（单主角/多主角）

### relationship（关系与反派）
- `heroine_config` — 感情线配置（无/单女主/多女主）
- `heroine_names` — 女主姓名列表
- `heroine_role` — 女主角色定位
- `co_protagonists` — 多主角姓名列表
- `co_protagonist_roles` — 多主角分工
- `antagonist_tiers` — 反派分层（小/中/大）
- `antagonist_level` — 反派级别
- `antagonist_mirror` — 镜像对抗一句话

### golden_finger（金手指）
- `type` — 类型（可为"无金手指"）
- `name` — 名称/系统名
- `style` — 风格（硬核/诙谐/黑暗/克制等）
- `visibility` — 可见度（谁知道）
- `irreversible_cost` — 不可逆代价
- `growth_rhythm` — 成长节奏（慢热/中速/快节奏）

### world（世界观）
- `scale` — 世界规模（单城/多域/大陆/多界）
- `factions` — 势力格局
- `power_system_type` — 力量体系类型
- `social_class` — 社会阶层
- `resource_distribution` — 资源分配
- `currency_system` — 货币体系
- `currency_exchange` — 货币兑换规则
- `sect_hierarchy` — 宗门/组织层级
- `cultivation_chain` — 境界链
- `cultivation_subtiers` — 小境界

### constraints（创意约束）
- `anti_trope` — 反套路规则
- `hard_constraints` — 硬约束列表
- `core_selling_points` — 核心卖点列表
- `opening_hook` — 开篇钩子
