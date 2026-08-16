# SWAT-CUP 自动率定工具

[English](README.md) | 简体中文

面向多站点 SWAT-CUP/SUFI2 工程的无图形界面自动率定与过程诊断工具。

它可以直接复现 `model.in`，在相互隔离的工程副本中进行参数采样，计算各站点 R2、NSE、KGE、PBIAS 及水文过程指标，并准备能够继续使用 SWAT-CUP GUI 和原生 BAT 文件运行的正式工程。

## 1.1.0 版本更新

本版本将原有的无 GUI 运行器扩展为完整的率定、诊断和 GUI 工程交付工作流：

- 新增多站点过程诊断，包括相关系数、log-NSE、月尺度气候态、最佳时滞、洪峰偏移、洪峰捕获率、低流量比例和模拟零流量比例。
- 保存每次模拟的完整过程线，并基于有效样本构建逐站点 95PPU 包络。
- 根据当前工程的 `fig.fig` 审计站点上下游关系、记录输入、WUS 用水以及本地或上游水库。
- 支持 `.wus` 和 `.res` 联合调参，并对水库参数施加温和的物理约束。
- 水库目标库容、最小/最大出流和取水量均按月份调整，不会将原有季节过程压成全年固定值。
- 支持不同站点权重以及逐站点 NSE/KGE 准入阈值。
- 记录失败模拟并按最大尝试次数补充采样，使要求的样本数代表成功完成的模拟数。
- 新增固定输入同步、原生 GUI 工程检查和 BAT 冒烟测试验证。

1.1.0 移除了针对特定流域编写的 `sediment` 和 `hhb_flow` 评分模式。普通率定可使用带站点权重的 `kge`，需要兼顾过程形态时使用 `multisite_timeseries`。

## 安全原则

SWAT 和 SUFI2 会写入固定文件名，因此不能在同一个工程目录中并发运行多个模拟。并行率定时，每个 worker 必须拥有一份完整且相互隔离的工程副本。

必须遵守以下原则：

- 保留用户原始工程，所有试验在完整副本中执行。
- 参数采样前先复现一组已知 `model.in`；若结果不一致，应先检查基准文件、可执行文件和观测配置。
- 根据当前工程的 `fig.fig` 推导站点依赖关系，不能沿用其他流域的分区或上下游关系。
- 仅率定真正位于测站本地或上游、能够影响该测站的水库；同子流域但位于测站下游的水库会被排除。
- 各站点分别得到的最优参数不能直接拼接，必须通过一次全模型联合复现后才能接受。
- 已知正确的点源、取水、水库调度和记录输入不能作为任意拟合参数。
- 当 Swat_Edit 无法修改 `.sol`、`.wus` 或 `.res` 参数时，应将接受的固定值同步到工程根目录、`Backup/` 和存在的 `DirectBase/`。
- GUI 正式工程应保留原始 BAT 文件、`Echo/` 和 Windows CRLF 控制文件，并在交付前清空正式 `SUFI2.OUT/`。

## 环境要求

- Python 3.10 或更高版本。
- Windows SWAT-CUP SUFI2 工程。
- 工程中包含 `swat.exe`、`SUFI2_extract_rch.exe`、`SUFI2.IN/`，以及 `DirectBase/` 或 `Backup/`。
- NumPy 和 Pillow 仅用于绘制 95PPU 图。

安装基础工具：

```powershell
git clone https://github.com/justo888777/swatcup-auto-calibrator.git
cd swatcup-auto-calibrator
python -m pip install -e .
```

同时安装 95PPU 绘图依赖：

```powershell
python -m pip install -e ".[ppu]"
```

安装后的命令为 `swatcup-auto`。Codex Skill 中也包含独立运行器：

```text
skills/swatcup-auto-calibrator/scripts/swatcup_auto_runner.py
```

## 推荐工作流

1. 检查 `SUFI2.IN`、`fig.fig`、可执行文件、BAT 文件、`Backup/`、`DirectBase/`、`Echo/`、观测数据块长度和现有输出。
2. 使用 `audit_structure.py` 检查测站拓扑、依赖分区、WUS 数量和单位、上游水库以及记录输入。
3. 使用 `single` 复现当前最佳模型，保存逐站点指标和过程线。
4. 先运行少量试验，依据单次运行耗时和成功率确定 worker 数量与最大尝试次数。
5. 在独立 worker 中运行要求数量的成功样本，并使用 `--series-dir` 保存过程线。
6. 综合检查站点阈值、总目标函数、时序、log-NSE、偏差、洪峰、低流量和错误零流量。
7. 使用完整成功样本构建 95PPU。若观测洪峰长期位于合理宽度的包络之外，应优先检查结构和输入数据，而不是盲目缩小参数范围。
8. 仅保留有明确响应且具有物理意义的参数，并复现选定的全模型组合。
9. 同步直接修改的固定输入，生成下一轮 GUI `par_val.txt`，再执行 GUI 工程检查和原生 BAT 冒烟测试。

## 快速开始

### 1. 审计拓扑与结构输入

```powershell
python skills/swatcup-auto-calibrator/scripts/audit_structure.py `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --out-dir ".\results\structure"
```

审计内容包括站点上下游关系、相关水库、WUS 月取水量、记录输入文件及可能位于测站下游的设施。

### 2. 复现已知最佳参数

```powershell
swatcup-auto single `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --model-in ".\best_model.in"
```

只有复现结果与原结果一致后，才能继续采样寻优。

### 3. 多 worker 小样本率定

以下示例要求得到 200 次成功模拟，最多允许尝试 240 次：

```powershell
swatcup-auto sample `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --runs 200 `
  --max-attempts 240 `
  --workers 4 `
  --refresh-workers `
  --center-model-in ".\best_model.in" `
  --scale 0.15 `
  --score-mode multisite_timeseries `
  --variable-weights "FLOW_OUT_17=2,FLOW_OUT_60=2" `
  --series-dir ".\results\series" `
  --out-csv ".\results\round1.csv"
```

可使用 `--min-station-nse` 和 `--min-station-kge` 要求每个观测数据块都达到最低阈值。若没有候选方案满足全部阈值，工具不会输出误导性的最佳 `model.in`。

## 95PPU 与过程诊断

使用完整的成功模拟过程线构建逐站点 95PPU：

```powershell
python skills/swatcup-auto-calibrator/scripts/build_95ppu.py `
  --observed "D:\Projects\HHB\Project.Sufi2.SwatCup\SUFI2.IN\observed_rch.txt" `
  --final-series-csv ".\results\series\run_42_series.csv" `
  --ensemble-dir ".\results\series" `
  --results-csv ".\results\round1.csv" `
  --expected-samples 200 `
  --out-dir ".\results\95ppu"
```

`--expected-samples` 会检查实际加载的完整样本数量，防止将不完整或失败模拟混入 95PPU。

## 水库与 WUS 联合调参

首先检查能够影响指定测站的水库：

```powershell
swatcup-auto reservoir-scope `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --stations "17,60"
```

需要单独生成水库参数范围时：

```powershell
swatcup-auto reservoir-scope `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --stations "17,60" `
  --out-par-inf ".\results\reservoir_par_inf.txt" `
  --runs 200
```

水库参数约束包括：

- `RES_RR`、`NDTARGR`、`EVRSV` 和 `RES_K` 在当前值附近温和调整。
- `STARG(month)` 按当前月份目标库容分别调整，保留季节变化。
- `WURESN(month)` 只调整原来存在取水的月份。
- `OFLOWMN(month)` 和 `OFLOWMX(month)` 分月调整，并保证生成范围不会破坏最小出流与最大出流的顺序。
- 默认不率定 `IRESCO` 等水库运行模式，除非有明确的调度依据。

WUS 参数使用相同的月份语法，例如：

```text
v__WURCH(7).wus________17
```

调整 WUS 前必须确认当前工程中的用水单位、实际取水记录和回归水设置。结构输入不应仅为提高统计指标而失去物理意义。

## 生成下一轮 GUI 参数方案

以接受的最佳参数为中心生成 1000 次 GUI 样本，并将精确中心放在第1行：

```powershell
swatcup-auto plan `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --runs 1000 `
  --center-model-in ".\results\round1.best_model.in" `
  --scale 0.10 `
  --out-par-val ".\results\par_val_1000.txt"
```

只有 Swat_Edit 已确认支持的参数才应放入 GUI `par_inf.txt`。不支持的 `.sol`、`.wus` 或 `.res` 参数应固定写入基础输入文件。

## 同步固定输入

先使用 `--dry-run` 检查将要同步的文件：

```powershell
python skills/swatcup-auto-calibrator/scripts/sync_baked_inputs.py `
  --project "D:\Projects\HHB\Delivery.Sufi2.SwatCup" `
  --model-in ".\results\round1.best_model.in" `
  --dry-run
```

确认范围正确后执行同步：

```powershell
python skills/swatcup-auto-calibrator/scripts/sync_baked_inputs.py `
  --project "D:\Projects\HHB\Delivery.Sufi2.SwatCup" `
  --model-in ".\results\round1.best_model.in"
```

默认同步到 `Backup/`，若工程存在 `DirectBase/` 则同时同步。也可以通过 `--destinations` 明确指定目录。

## GUI 工程交付检查

在原生 Pre/Run/Post BAT 冒烟测试完成后检查正式工程：

```powershell
python skills/swatcup-auto-calibrator/scripts/native_gui_check.py `
  --project "D:\Projects\HHB\Delivery.Sufi2.SwatCup" `
  --source-project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --expected-formal-runs 1000 `
  --smoke-out ".\results\smoke\SUFI2.OUT" `
  --smoke-runs 3 `
  --require-empty-out `
  --strict
```

检查内容包括：

- `par_inf.txt` 声明的参数数和模拟数是否与实际内容一致。
- `par_val.txt` 是否包含连续且完整的样本行。
- `SUFI2_swEdit.def` 是否与正式样本数一致。
- 原生 BAT 文件是否与来源工程一致。
- BAT 引用的可执行文件是否存在且非空。
- 控制文件是否保持 Windows CRLF。
- 冒烟测试输出的站点、样本数和过程长度是否完整。
- 第1个 GUI 样本是否能够复现已确认的最佳过程线。

## Codex Skill

仓库包含可安装的 Codex Skill：

```text
skills/swatcup-auto-calibrator/
```

该 Skill 会要求代理保留来源工程、从拓扑推导率定范围、同时检查统计指标与过程线、对 WUS/水库参数施加物理约束，并在交付前完成全模型复现和原生 GUI 验证。

## 已知边界

- 默认模型程序名为 `swat.exe`，提取程序名为 `SUFI2_extract_rch.exe`。
- 工具不包含 SWAT 或 SWAT-CUP 可执行文件及其许可证。
- 自动率定不能替代对降水、观测流量、取水、水库调度和点源数据的质量检查。
- 较高的综合 KGE 不能掩盖单站点负 NSE、错误洪峰时序、虚假零流量或明显水量偏差。

## 许可证

MIT。SWAT 与 SWAT-CUP 可执行文件及许可证不包含在本仓库中。
