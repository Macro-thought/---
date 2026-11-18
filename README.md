# 受控扰动下的图推理结论翻转诊断

围绕 Wikidata 航空子图，构造五种模式演化算子（REFINE_TYPE、RESTRICT_REL、MERGE_ENTITY、SPLIT_CONCEPT，以及对照 ADD_INST），用确定性求解器自动生成「应然翻转」标签，诊断图检索 / GraphRAG 系统在知识图谱模式演化下的答案稳定性。

对应任务书：*Does Your Answer Survive the Schema Change? A Controlled Perturbation Study of Graph Reasoning under KG Evolution*（CCKS/CCL 短文方向）。

完整执行报告见 [REPORT.md](REPORT.md)。

## 核心数字

| 项 | 值 |
|---|---|
| 图规模 | 600 实体 / 1506 边（航空公司 185、机场 74、机型 81、城市 75） |
| 算子 | 4 个主算子 + 1 个对照，5 份变体图全部通过不变量检查 |
| 题库 | 120 题 = 5 算子 × 3 问句类型 × 8，全局无重复 |
| 应然矩阵 | 15 格与先验全部吻合（9 格 match、6 格 consistent） |
| 语料 | 600 篇，每篇 3–5 句，0 标签泄漏 |
| 可答性 | 120/120 |
| 基线冒烟 | 13 次运行 / 1560 条问答；一轮全量约 2.31 元（qwen-plus 档位估算） |

## 目录结构

```
data/            图数据（graph_v1.json、raw_graph.json、schema.json、add_instances.json）
                 data/raw/ 为 QLever 请求缓存，未纳入版本库
tools/           取数与建图脚本（qlever.py、fetch_raw.py、build_graph.py、dump_shapes.py）
ops/             算子实现、5 份变体图与 diff、不变量检查
labels/          确定性求解器、120 条标签、15 格矩阵、独立抽查
qa/              题库生成、可答性审计、20 题复核样张
corpus/          语料构建、600 篇文档、模板说明
baselines/       B1 朴素 RAG / B2 图检索 / B3 LightRAG（探测 + 本地 proxy）
eval/            答案翻转评分（FR / FFR / MFR）
logs/            决策日志、冒烟记录、抽查记录
REPORT.md        一阶段执行报告
```

## 快速开始

实验部分只依赖 Python 标准库（在 Python 3.14 上验证，3.10+ 应可运行）：

```bash
python ops/operators.py            # 生成 5 份变体图 + diff
python ops/invariant_check.py      # 不变量检查
python qa/generate_questions.py    # 120 题 + 标签 + 矩阵
python labels/spotcheck.py         # 独立抽查 3 条
python corpus/build_corpus.py      # 600 篇语料
python qa/answerability.py         # 可答性审计
python baselines/b1_naive.py
python baselines/b2_graph.py
python baselines/b3_lightrag.py            # 探测 LightRAG 可用性
python baselines/b3_lightrag.py --proxy    # 本地混合检索替身
python eval/score.py
```

从 Wikidata 重新取图才需要第三方依赖：

```bash
pip install -r requirements.txt
python tools/fetch_raw.py
python tools/build_graph.py
python tools/fetch_add.py
```

## 方法口径

**成员语义**：`members(T)` = 节点类型为 T，或 T 在 `type_path` 中，或 T 出现在 facet 属性（`p31_subtype` / `airport_class` / `aircraft_class`）里。祖先包含 + 叶子 facet。

**REFINE 与 SPLIT 的区别**是本研究的核心操纵变量：

- REFINE 保留父概念在 `type_path` 中，父类仍指称原集合 → 全部稳定。
- SPLIT 从 `type_path` 中移除父概念，父类实例集变空 → 全称题按经典空域语义翻真。

**标签来源**：求解器在 G_v1 与 G_op 上分别求值，答案不同即判 flip，无人工标注、无 κ。

## 应然矩阵

| 算子 | 指称 | 计数 | 全称 |
|---|---|---|---|
| ADD_INST | 0/8 | 0/8 | 0/8 |
| REFINE_TYPE | 0/8 | 0/8 | 0/8 |
| RESTRICT_REL | 4/8 | 4/8 | 3/8 |
| MERGE_ENTITY | 0/8 | 8/8 | 2/8 |
| SPLIT_CONCEPT | 0/8 | 4/8 | 8/8 |

## 已知限制

- 本机无 LLM API key，B1/B2/B3 使用**抽取式占位阅读器**，真实 FR/FFR/MFR 待 key 到位后运行；替换点为 `baselines/common.py:read_answer`。
- `lightrag` 未安装，B3 只有可用性探测 + 明确标注的本地 proxy，`baselines/out/b3_status.json` 记录原因。
- 无 PyTorch 环境，任务书可选的 KGE 漂移对照未执行。
- token 成本按字符数 / 1.5 估算，误差约 ±20%。

## 数据来源

图数据来自 Wikidata，经 `https://qlever.dev/api/wikidata` 抽取，种子为 P31/P279* Q46970 且 P17 属于中国、香港、澳门、台湾地区、日本、韩国。Wikidata 数据以 CC0 发布；本仓库中的节点 ID、标签与关系为派生数据。抽取时间与查询语句见 `tools/` 与 `data/graph_stats.json`。
