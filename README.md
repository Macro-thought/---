# 研究数据集存档

RAG / 知识图谱方向研究用的原始数据，从一个本地工作目录里整理出来，单独存放以免和代码混在一起。

整理日期：2026-11-16。数据来自公开渠道，均为原样存档，未做二次加工（`wiki_zh` 下几个 json 是从分片里抽出来的派生文件）。

## 目录

| 路径 | 体积 | 内容 |
|---|---|---|
| `_datasets/rot_kg.zip` | 34 MB | RotatE 官方仓库 + WN18RR 数据包，TransE / RotatE 复现用 |
| `_datasets/musique/musique_dev.jsonl` | 29 MB | MuSiQue dev 集，早期 schema 算子原型的输入 |
| `_datasets/wiki_zh/` | 38 MB（见下） | 中文维基抽出的标题表、正文与匹配结果 |
| `_datasets/papers/` | 1.4 MB | TransE (2013)、ConvE (2018)、RotatE (2019) 三篇方法/基线原文 |
| `_datasets/web/` | 592 KB | 网页存档：CCKS 会议页、一个相关页面 |

`_datasets/wiki_zh/` 里：

- `titles.json` — 1,384,748 条中文维基条目标题
- `texts.json` — 394 篇正文，键为条目标题
- `texts_clean.json` — 同上，做过去噪
- `match.json` / `match2.json` — 标题与正文的匹配结果

## 6 个 parquet 分片：走 Releases，不进 git

`wiki_zh/train-00000-of-00006.parquet` ~ `train-00005`，合计 1.64 GB，单文件 121–560 MB，**超过 GitHub 单文件 100 MB 的硬限制**，普通 git 推不上去（服务端直接拒收，不是配置问题）。

这 6 个文件放在本仓的 Release 附件里（附件单文件上限 2 GB，免费，不占 git 历史）：

**下载地址**：https://github.com/Starry985666/---/releases/tag/v1-parquet

| 文件 | 体积 | SHA-256（前 16 位） |
|---|---|---|
| `train-00000-of-00006.parquet` | 559 MB | `853ddf4a138c792a` |
| `train-00001-of-00006.parquet` | 251 MB | `038b08e5aae38b5a` |
| `train-00002-of-00006.parquet` | 120 MB | `ec8f6c0dd1418b8f` |
| `train-00003-of-00006.parquet` | 249 MB | `4884e4933fa91f46` |
| `train-00004-of-00006.parquet` | 244 MB | `415a5cd235a359a0` |
| `train-00005-of-00006.parquet` | 214 MB | `803ae27118b1daf9` |

下载后放回 `_datasets/wiki_zh/`，与 `titles.json` 同级即可。校验：

```bash
cd _datasets/wiki_zh && sha256sum train-*.parquet   # 对照上表前 16 位
```

**校验口径**：用这批分片重新抽取，标题数应与 `titles.json` 的 1,384,748 条一致；版本不同会有出入，以实际抽出的 `texts.json` 是否覆盖所需条目为准。

## 许可与出处

- `wiki_zh/` — 来自中文维基百科快照，文本按 CC BY-SA 授权，转载需署名并以相同方式共享
- `musique/` — MuSiQue 数据集，CC BY 4.0
- `rot_kg.zip` — RotatE 官方代码（MIT）与其附带的 WN18RR 数据包
- `papers/` — 三篇论文的版权归原作者/出版方，此处仅作个人研究存档，非商业分发

## 用法

数据目录结构即仓库结构，脚本按相对路径读：

```python
from pathlib import Path
DATA = Path("_datasets")
MUSIQUE = DATA / "musique" / "musique_dev.jsonl"
```
