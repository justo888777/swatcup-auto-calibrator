# Native GUI delivery

## Bake direct-only inputs

After accepting direct edits, make the project root the verified state and copy the same touched input files into `Backup/` and `DirectBase/` with `sync_baked_inputs.py`. Do this only for the explicitly accepted files. Re-run the best model after synchronization.

Keep GUI-active parameters to syntax and extensions proven to work with the project's native `Swat_Edit.exe`. Arrays in `.sol`, monthly WUS fields, and reservoir controls may work in the direct runner while failing in native Swat_Edit; bake them when native support is uncertain.

## Preserve the native launch path

- Use the project's original `SUFI2_Pre.bat`, `SUFI2_Run.bat`, and `SUFI2_Post.bat` unchanged when possible.
- Keep `Echo/`; some native projects fail without it.
- Keep `par_inf.txt` and `SUFI2_swEdit.def` in Windows CRLF. Old Fortran readers can reject LF-only control files.
- Ensure declared parameter/simulation counts match the actual parameter rows, every `par_val.txt` row width, run IDs, and the `SUFI2_swEdit.def` interval.
- Preserve the actual SWAT and SUFI2 executables used by the working source project.

## Multi-row smoke test

Make a separate full copy of the formal project. Configure a small multi-row plan whose size is chosen for the current task, then run the native BAT sequence in an interactive terminal. The first Pre/SWAT run can be slow, especially after changing reservoir record modes; allow a realistic cold-start interval.

The smoke test passes only when:

- Pre completes and applies every smoke-plan parameter row;
- Run completes the configured number of SWAT simulations;
- every observed `FLOW_OUT_*` file contains exactly the configured number of blocks with the full observed length;
- Post produces its objective/goal and 95PPU outputs;
- the first run reproduces the baked best model within expected numeric precision.

Archive the smoke receipt outside the formal `SUFI2.OUT/`. Restore the user-requested formal simulation count and matching plan, then leave formal `SUFI2.OUT/` empty. Run `native_gui_check.py --strict` as the final release-boundary check.

Pass `--expected-formal-runs`, the smoke output, and the verified best process-series CSV. Static checks verify non-empty native executables and file shapes; they supplement but never replace actually executing the original BAT sequence.
