# Stall traces

Each dated file from 4 and 5 Oct 2026 is a false stall. `stall_check.py` judges
those seats active. `verified-stall.json` exits 1: idle input, a promise, and
silence after the 12-minute warm-up. `2026-10-11-read-then-hang.json` exits 1
as well: a promise, one read, then silence past the window. The read restarts
the silence clock, and the seat stalls once that silence elapses.

Drop the activity the old watcher missed, or pass `--warmup-minutes 0` on
the warm-up trace, and the same file becomes a stall. Seat ids are labels
for the trace. They name no person and no host.
