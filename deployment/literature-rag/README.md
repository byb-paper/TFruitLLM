# TropicalfruitLLM 全主题文献 QA + RAG

该目录把 13 个物种的 PubMed 文献清单纳入统一证据层。它补充了原有的代谢物、KG 和 OMICS 数据，但不替代这些数据。

## 覆盖主题

主题规则位于 `topic_taxonomy.json`，目前包括遗传育种、转录组、代谢物、蛋白与酶、表观遗传、发育成熟、采后、病虫害、非生物胁迫、栽培生理、繁殖与组织培养、食品加工、营养药理、微生物组、生态进化、表型计算、多组学、感官、过敏与食用安全、生物材料环境利用、分析检测等。

所有文献记录都会进入 RAG。没有命中主题规则的记录保存为 `other_unclassified`，并写入审计报告，避免静默丢失。该类记录不会自动生成训练 QA，以免把无关检索结果训练进模型。

## 构建

```bash
cd /work/home/acuckjum5f/fruit/literature-rag
LITERATURE_ROOT=/work/home/acuckjum5f/fruit/literature \
OUT=/work/home/acuckjum5f/fruit/literature-rag/output \
bash build_and_audit.sh \
  /work/home/acuckjum5f/fruit/13.sft_v16/data/sft_tpm.jsonl
```

输出：

- `literature_rag.sqlite`：问答时在线检索的全文证据库。
- `literature_qa.jsonl`：按“物种 × 主题”生成的可追溯 QA，可选择性加入下一轮 SFT。
- `literature_topic_audit.json`：各物种和主题覆盖数、未分类率及示例。

## 部署

把脚本与 `literature_rag.sqlite` 放到模型目录的 `/root/models/rag/`，启动命令为：

```bash
TP_SIZE=2 bash /root/models/rag/start_tfruitllm_literature_rag.sh
```

公网仍使用原 OpenAI 兼容接口：

```text
POST /v1/chat/completions
```

## 证据边界

文献清单大多只有题名、PMID 和 DOI。题名只能证明存在相关研究，不能支持具体表达倍数、基因功能或处理效应。若需要回答实验结果，应继续导入摘要、全文、转录组矩阵或结构化 KG。审计统计表示当前语料覆盖，不表示已经穷尽全部文献或全部代谢物。
