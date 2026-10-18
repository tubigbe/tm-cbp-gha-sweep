# 2026-10-18 全量 ku↔GHA 逐位一致性核对（A 基线对照 + B 归档恢复）

操作：仿真机器人（唯一动手侧）。仓库 `tubigbe/tm-cbp-gha-sweep`（公开），`tm_cbp_sim` 本体未动。
本报告与 `scripts/verify_ku_vs_gha.py` 一起提交，任何人可复算。

## 0. 结论

**2835 项逐条字段比对，0 处不一致。** 首次在 105 条全量上证明：GHA runner 产出的数字与
ku 侧 AGENTS.md §10.1 基线原始 stdout **逐位相同**（此前只有两条 sample 的冒烟 gate）。
因此以后 GHA 产出的数字可以直接与 §10.1 的 ku 基线比较，不需要再怀疑平台差异。

- ku §10.1 基线：105 条平均 TM MPKI **13.415416**（文档值 13.4154）
- GHA A 对照跑：105 条平均 TM MPKI **13.415416**（逐条逐位相同）
- GHA B（iso-area B 49/53/T=10）归档：105 条平均 **12.851065**，即相对 A **−4.206%**
  （与早前报告的 −4.21% 全量结论一致）

## 1. 这次为什么需要恢复

两条 2026-10-18 全量 run（触发 commit `a4ac176`）的 **shard 全部/大部分成功，collect 失败**，
数据一直没坏，坏在 collect 的最后一步：

| run | 结果 | collect 死因 |
|---|---|---|
| A 对照 `39142060478`（`fullset_baseA.yml`） | 7 片全 success | **exit 2**：`pack_logs.py` 已成功打包 105 份（日志原文 `pack_logs: 105 log(s) == 105 run row(s)`），紧接着的诊断行 `ls -la ... \| head -5` 在 `set -o pipefail` 下收到 SIGPIPE，`ls` 退出码 2，step 失败 ⇒ commit 被跳过 |
| B 重跑 `39142060395`（`fullset_isoB.yml`） | shard 5（compress）failure，其余 6 片 success | **exit 1**：`pack_logs: expected 105 log(s), got 97 - incomplete collect`——这是**正确的硬失败**，compress 片在开跑 36–52 秒即被 Google Drive 下载抖动打死，8 条 trace 从未跑 |

原始失败日志已归档：`recovery_logs/a_collect_job.log`、`recovery_logs/b_collect_failed.log`。

## 2. 恢复方式（零 shard 重跑）

用 `actions/download-artifact@v4` 的 `run-id` + workflow 自带 `GITHUB_TOKEN`
跨 run 取回 artifact，再用 `scripts/recover_collect.py` 打包，**没有重跑任何 shard**：

- A：从 run `39142060478` 的 7 个 artifact（`baseA-0..6`）恢复 → `baseA_results/`
  （105 份 `.log.gz` + `SHA256SUMS` + `ALL.csv` 13 列 + `INVENTORY.txt`）
- B：从 **2026-10-16 那次完整的 B 全量 run**（`head_sha 69e3e6d`）的 7 个 artifact（`isoB-0..6`）恢复
  → `isoB_results/`（105 份 `.log.gz` + `SHA256SUMS` + `ALL.csv` 13 列 + `INVENTORY.txt`）。
  那是未经改动的 B 证据，比 10-18 重跑更早、且完整。

CSV 的两列 `instructions` 与 `GShare wrong` 旧 CSV 里没有，由恢复出的原始 stdout 重建：
`scripts/rebuild_csv_from_logs.py --results-dir <dir>`。

## 3. 核对项与结果（`scripts/verify_ku_vs_gha.py`）

| 检查 | 含义 | 规模 | 结果 |
|---|---|---|---|
| Q0-A / Q0-B | 每份 CSV 的数值 vs 它自己那次 run 的原始 stdout | 105×8 ×2 | 0 不一致 |
| **Q1** | **GHA A 对照跑 vs ku §10.1 原始 stdout（同变体、105 条全量）** | **105×5** | **0 不一致** |
| Q2 | `isoB_results` 归档 vs 10-16 已提交 CSV 快照（**恢复保真**，不是第二次平台跑） | 105×4 | 0 不一致 |
| Q3 | A vs B 逐条 `instructions` / `GShare wrong`（污染门） | 105×2 | 0 不一致 |

Q1 的 5 个字段：`TM MPKI`、`TM right`、`GShare MPKI`、`GShare wrong`、`instructions`。
其中 `GShare wrong`、`instructions` 是这次新拿回来的两列——以前 CSV 里根本没有，所以
"变体之间逐位一致"这条以前只能核 4 列，现在能核全。

## 4. 复算命令

```bash
# 在 ku 上
cd /data/tm_gha_sweep && git pull --ff-only
python3 scripts/verify_ku_vs_gha.py
# 预期末行：ALL CHECKS BIT-IDENTICAL (2835 field comparisons, 0 mismatch)

# 从原始日志重建 CSV（可复算）
python3 scripts/rebuild_csv_from_logs.py --results-dir baseA_results
python3 scripts/rebuild_csv_from_logs.py --results-dir isoB_results

# 校验日志完整性（SHA256SUMS 存的是未压缩内容的 sha256）
cd baseA_results/logs
while read -r sha size name; do
  got=$(gzip -dc "$name" | sha256sum | cut -d' ' -f1)
  [ "$got" = "$sha" ] && echo "OK   $name" || echo "FAIL $name"
done < SHA256SUMS
```

SHA256SUMS 每行格式：`<未压缩内容的sha256>  <未压缩字节数>  <文件名>`。

## 5. 边界（不要过度解读）

- Q1 证明的是**平台一致性**（同一份 A 源码在 GHA 与 ku 逐位相同），不是 B 变体本身的新结论。
- Q2 用的是 10-16 那次 run 自己的 artifact 与它已提交的 CSV 对比，属**恢复保真性**检查；
  它不是"10-18 再跑一次 B 与 10-16 对比"。10-18 B 重跑的 6 个成功片仍在 artifact（10-30 到期），
  需要时可同样零重跑恢复，目前没有必要。
- 本次没有重跑任何 trace，也没有改 `tm_cbp_sim` 里的任何文件。

## 6. 遗留修复

`collect` 里已去掉 `ls | head` 这类在 `set -o pipefail` 下会因 SIGPIPE 误杀 step 的诊断行，
改为 `find | wc -l` 与 `du -sh`（commit `a74b73d`，`[skip ci]`）。其他 5 个 workflow 的 collect
同样修正。`recover_collect.yml` / `recover_b.yml` 保留为以后的"只重收、不重跑"通道。
