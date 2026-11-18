# T2.4 端到端冒烟记录

运行时间 2026-11-18。所有数字由 `baselines/out/*.json` 汇总，汇总脚本见文末命令。

## 一、跑通范围

| 项 | 值 |
|---|---|
| 问句 | 120 条（5 算子 × 3 问句类型 × 8） |
| 系统 | B1 朴素 RAG、B2 图检索、B3 LightRAG |
| 图版本 | G_v1 + 5 个算子变体 = 6 份 |
| 实际执行 | B1 × 1（固定语料，不随图变）、B2 × 6、B3_proxy × 6 |
| 输出文件 | 13 份，共 1560 条问答 |
| B3 真实系统 | **未运行**，见第五节 |

B1 只跑一次是设计使然：它的语料是固定快照，不读图，图变了它也不会变——这正是它作为“空对照”的意义。

## 二、答案完整性

| 系统 | 文件数 | 非空答案 | 空答案 |
|---|---|---|---|
| B1 | 1 | 120/120 | 0 |
| B2 | 6 | 707/720 | 13 |
| B3_proxy | 6 | 707/720 | 13 |

13 条空答案全部可解释，不是崩溃：

- `b2_restrict_rel` / `b3_proxy_restrict_rel` 各 9 条：包括 `add_inst-referral-02`（朱鹭航空）、`refine_type-referral-02/03` 等。这些主体的枢纽机场全是普通机场，RESTRICT 之后确实没有可回答的对象。**空答案与 G_v2 的应然答案（空集）一致**，是正确行为。
- `b2_merge_entity` / `b3_proxy_merge_entity` 各 1 条：`merge_entity-referral-01` 问「中华航空」的枢纽机场。MERGE 后实体只剩规范名「华航集团」，`中华航空` 退化为别名；以字符串前缀匹配三元组的阅读器找不到 `中华航空的枢纽机场是…`，于是空。这是一次**由表面标签变化引发的假翻转**，正是 MERGE 算子想暴露的失败模式。

## 三、时延（本地 CPU，单进程 Python）

| 系统 | p50 | p95 | max | 120 题总耗时 |
|---|---|---|---|---|
| B1 | 0.7 ms | 1.1 ms | 1.6 ms | 0.09 s |
| B2 | 0.1 ms | 0.6 ms | 3.9 ms | 0.03–0.04 s |
| B3_proxy | 1.0 ms | 1.7 ms | 5.3 ms | 0.13 s |

这些是**检索与拼装**的时延，不含 LLM 推理，因此不能当作线上时延报告。它们的用途是确认管线没有性能陷阱：120 题全跑在 0.2 秒内，预算可以全部花在模型调用上。

## 四、token 与成本回算

token 由字符数 / 1.5 估算（中文混合文本的经验值），不是 tokenizer 实测。

| 系统 | 输入 token | 输出 token | 每次全量输入均值/题 |
|---|---|---|---|
| B1（1 次） | 22,430 | 698 | 187 |
| B2（6 次） | 1,362,938 | 1,632 | 1,893 |
| B3_proxy（6 次） | 1,489,519 | 1,632 | 2,077 |
| **合计** | **2,874,887** | **3,962** | — |

按 qwen-plus 档位假设（输入 ¥0.0008/千 token，输出 ¥0.002/千 token；价格随官方调整，仅作量级估算）：

- 输入成本 ≈ 2.30 元
- 输出成本 ≈ 0.008 元
- **一轮完整扫描（13 次运行）≈ 2.31 元**

预算回算（任务书上限 100–150 元）：

| 预算 | 可跑完整扫描 | 对应问答量 |
|---|---|---|
| 100 元 | 43 轮 | 67,080 条 |
| 150 元 | 65 轮 | 101,400 条 |

上表输出 token 极低，是因为占位阅读器只吐几个字。换成真实 LLM 后，按每题 40–60 个输出 token 估算，一轮增加约 0.12–0.19 元，**总量仍在 2.5 元左右**，预算结论不变：成本瓶颈不在生成，而在 2-hop 上下文（B2/B3 每题约 1.9–2.1k 输入 token）。若要进一步省钱，优先裁 2-hop 邻居数，而不是裁问句数。

## 五、B3 的诚实状态

`baselines/out/b3_status.json` 记录：

- `lightrag` 包未安装；
- 环境里没有任何 LLM key（`OPENAI_API_KEY` / `DASHSCOPE_API_KEY` / `QWEN_API_KEY` / `LLM_API_KEY`）；
- 因此 `available: false`，**本轮没有任何真实 LightRAG 数字**。

为了让三列对照不至于缺席，`b3_lightrag.py --proxy` 跑了一个明确标注的本地替身：低层取 B1 的 top-k 文本块，高层取 B2 的 2-hop 三元组，再走同一个阅读器。输出文件名一律带 `proxy`，`meta.warning` 写明 “local hybrid stand-in, NOT real LightRAG”。**它不能替代真实 LightRAG 的实验结论。**

## 六、与应然标签的对照（仅作管线证据）

`eval/score.py` 把每个系统的 v1 答案与变体答案做比较，再和求解器标签交叉。完整表见 `eval/scores.md`，摘要：

| 系统 | 算子 | FR | FFR | MFR |
|---|---|---|---|---|
| B1 | 全部 | 0.000 | 0.000 | 1.000（有应然翻转的格子） |
| B2 | RESTRICT_REL | 0.250 | 0.000 | 0.455 |
| B2 | MERGE_ENTITY | 0.042 | 0.071 | 1.000 |
| B2 | 其余三个 | 0.000 | 0.000 | 1.000 |
| B3_proxy | 与 B2 基本一致 | — | — | — |

**这组数字不能当作“基线鲁棒性”结论**，原因有三：

1. 计数题在占位阅读器下没有聚合能力，一律答 0，v1/v2 都不变 → 计数格子的 FR 恒为 0，与检索是否移动无关。
2. 全称题靠关键词“并非/没有”判断，倾向答“是”；SPLIT 后应然答案恰好翻成“是”，于是 SPLIT 全称的 acc_v2 反而升到 0.83–1.0。这是蒙对，不是能力。
3. B2 的 RESTRICT 指称 4/4 翻转、零假翻，说明**检索层确实感知到了边删除**；但 MERGE 的 1 次假翻来自标签规范化，属于真实的系统行为，可以保留为案例。

真正可用于论文的 FR/FFR/MFR 需要真实 LLM 阅读器。接口已经留好：三个脚本的 `answer()` 都把拼好的 context 交给同一个 `read_answer`，替换成 API 调用即可，其余流程不动。

## 七、偏差与未完成项

| 项 | 状态 | 影响 |
|---|---|---|
| 真实 LLM 作答 | 未跑（无 key） | 三系统准确率、FR/FFR/MFR 仅有占位值 |
| 真实 LightRAG | 未跑（无包、无 key） | 第三列用明确标注的 proxy 顶替 |
| token 计数 | 字符估算 | 成本误差约 ±20% |
| 时延 | 本地 CPU、无 LLM | 不代表线上端到端时延 |
| 计数题基线 | 无聚合器 | 该格子的基线数字只有连通性意义 |
| KGE 漂移基线 | 未跑（无 PyTorch 环境） | 任务书可选项，未纳入本轮 |

## 八、复现命令

```bash
cd /d/repro/schema_change
python baselines/b1_naive.py
python baselines/b2_graph.py
for op in add_inst refine_type restrict_rel merge_entity split_concept; do
  python baselines/b2_graph.py --graph ops/graphs/$op.json --out baselines/out/b2_$op.json
done
python baselines/b3_lightrag.py            # 写 b3_status.json
python baselines/b3_lightrag.py --proxy    # 写 b3_proxy_v1.json
for op in add_inst refine_type restrict_rel merge_entity split_concept; do
  python baselines/b3_lightrag.py --proxy --graph ops/graphs/$op.json --out baselines/out/b3_proxy_$op.json
done
python eval/score.py
```
