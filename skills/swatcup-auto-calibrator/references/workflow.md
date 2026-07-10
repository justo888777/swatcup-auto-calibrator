# Workflow / 工作流程

## English

Use this workflow for SWAT-CUP SUFI2 projects when the user wants calibration without GUI clicking.

1. Start with a clean project copy. Keep the original project readable and write experiments into a separate folder.
2. Check `SUFI2.IN/par_inf.txt` to identify the active parameter set and bounds.
3. Check `SUFI2.IN/observed_rch.txt` to identify stations and variables.
4. Run a single reproduction using a known `model.in` before sampling.
5. Run small sampling first, usually 10 to 50 runs, to verify that metrics and outputs are parsed correctly.
6. Increase to larger sampling only after outputs and objective metrics are plausible.
7. For paper-ready work, split observed files by calibration and validation periods and evaluate both periods explicitly.
8. For SWAT-CUP GUI 95PPU, generate `par_val.txt` with `plan`, then run the full SWAT-CUP workflow in the GUI if needed.

## 中文

当用户希望跳过 SWAT-CUP 图形界面进行 SUFI2 率定时，按下面流程执行。

1. 先复制一份干净工程，原始工程尽量只读，测试结果写到单独目录。
2. 检查 `SUFI2.IN/par_inf.txt`，确认参与率定的参数和范围。
3. 检查 `SUFI2.IN/observed_rch.txt`，确认站点、变量和观测长度。
4. 用已知 `model.in` 先做单次复现，确认输出指标能被正确读取。
5. 先做 10 到 50 次小样本测试，确认 SWAT 输出、SUFI2 提取和评价指标没有异常。
6. 小样本正常后，再扩大到几百或几千次采样。
7. 论文场景要把率定期和验证期观测文件分开，分别计算指标。
8. 如果需要 SWAT-CUP 软件中的 95PPU，用 `plan` 生成 `par_val.txt`，再放入 GUI 工程运行。
