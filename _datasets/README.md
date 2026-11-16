# _datasets —— 从外部拉下来的原始数据

2026-11-16 整理。规矩：**这里只放"下载来的东西"，不放代码、不放跑出来的结果。**
代码留在原处，路径从这里指过去；新数据一律先落这里再被脚本读取。

| 目录 / 文件 | 原位置 | 体积 | 是什么 | 谁在用 |
|---|---|---|---|---|
| `rot_kg.zip` | `D:\repro\rot_kg.zip` | 34 MB | RotatE 官方仓库 + WN18RR 数据包（TransE/RotatE 复现用） | `复现笔记_RotatE_WN18RR.md`、`跑RotatE_WN18RR.cmd`、`跑TransE_WN18RR.cmd` |
| `musique/musique_dev.jsonl` | `D:\repro\musique_ops\` | 29 MB | MuSiQue dev 集，早期算子原型（`ops_pilot.py`）的输入 | `musique_ops/ops_pilot.py`（已改为读新路径） |
| `wiki_zh/` | `D:\repro\wiki_zh\` | 1.7 GB | 中文维基 HF parquet 分片 ×6（train-00000~00005）+ 抽取的 `titles.json`、`texts.json`、`texts_clean.json`、`match*.json` | 语料相关实验 |
| `papers/` | `D:\repro\papers\` | 1.4 MB | 三篇方法/基线原文 PDF：TransE (2013)、ConvE (2018)、RotatE (2019) | 复现笔记、论文引用 |
| `web/` | `D:\repro\_lit\` | 592 KB | 下载的网页存档：`ccks.html`（CCKS 会议页）、`s1.html` | 选题/档位判断 |

合计 1.8 GB。

## 没放进来、留在原地的

| 位置 | 为什么留下 |
|---|---|
| `repos/`（2.8 GB） | 是代码仓（LightRAG 等），不是数据 |
| `schema_change/data/` | 是从 Wikidata 现取的图，随项目走，且被 `build_graph.py`/`make_schema.py` 按相对路径读 |
| `musique_ops/*.json` | 是跑出来的中间产物，不是原始输入 |
| `count_probe/` | 脚本 + 它自己的结果混在一起，下次清理再说 |
| `results/`、`plan/`、`_wpspeed/` | 产出与文档，不是原始数据 |

## 引用约定

新脚本别写绝对路径，照这个来：

```python
from pathlib import Path
DATA = Path(__file__).resolve().parent.parent / "_datasets"   # 脚本在 D:\repro\<子目录>\ 时
MUSIQUE = DATA / "musique" / "musique_dev.jsonl"
```

## 变更记录

- **2026-11-16**：`wiki_zh`、`papers`、`_lit`、`rot_kg.zip`、`musique_dev.jsonl` 五项从 `D:\repro` 顶层与 `musique_ops\` 迁入本目录（同盘移动，未复制）。
  `_lit` 改名 `web`；`musique_dev.jsonl` 单独放进 `musique/`，与 `musique_ops\` 的代码产物分开。
  同步改了 `musique_ops/ops_pilot.py` 的 `MUSIQUE` 路径。全项目 grep 过，没有其他脚本硬编码这些路径。
