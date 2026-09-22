# cmux common pitfalls

Each of these bit a real session. They are recorded here so the next one does
not repeat them.

- **`list-workspaces` is window-scoped.** It shows only the workspaces in the
  *current* cmux window. After spawning, a fresh workspace can land in a
  different window and look as though it disappeared. Sanity-check with `cmux
  list-windows` (`workspaces=N` per window) and pass `--window <uuid>` to list a
  specific one. `cmux move-workspace-to-window --workspace workspace:N --window
  <uuid>` consolidates them.

- **`spawn-workspace.sh --new-window` can print a window-handle error after a
  successful spawn.** Where the output includes a ready workspace id, verify
  before acting: `cmux list-workspaces`, `cmux list-panes --workspace
  workspace:N`, `cmux list-pane-surfaces --workspace workspace:N`, then `cmux
  capture-pane --workspace workspace:N --surface surface:N --lines 80`. If the
  pane is live, continue from that workspace id and leave the other windows
  alone.

- **`read-screen | tail -25` can mislead.** The visible terminal buffer can hold
  input-area text *below* the most recent activity, so a tail-25 cut shows the
  original prompt sitting in the input box and misses live tool calls scrolled
  just above it. When checking whether a workspace is idle, use `tail -40` or no
  tail at all. Better still, read the worker's own output file rather than infer
  state from a screen.

- **Multi-workspace coordination.** When dispatching parallel workspaces that
  touch the same files, brief each one explicitly: *"Coordinate with
  workspace:X - do not touch &lt;files&gt;."* This prevents commit collisions on
  shared branches.

- **`--workspace` is a flag, never a positional argument, and the positional
  form misfires silently.** `cmux send workspace:N "text"` sends the text to the
  *current* workspace, with `workspace:N` swallowed into the message body, so
  the relay lands on the wrong agent - often your own surface. `cmux send-key
  workspace:N Enter` errors with `invalid_params: Unknown key`, because
  `workspace:N` is parsed as the key name. Always write the flag: `cmux send
  --workspace workspace:N "text"` then `cmux send-key --workspace workspace:N
  Enter`. Verify from the reply: both commands echo `OK surface:S workspace:N`,
  so confirm that `workspace:N` is your intended target before trusting the
  send. Key casing is a red herring - `Enter` and `enter` both work, and the
  flag is the whole bug. Handoff notes that write the positional form propagate
  the error, so fix them at the source.

- **`cmux send` of a multi-line prompt to an agent TUI gets stuck.** The TUI
  treats each newline as multi-line edit input, so a following `send-key Enter`
  adds another newline instead of submitting. Two correct paths: for a new
  workspace, bake the prompt into the launch command with `spawn-workspace.sh
  --prompt-file`; for mid-flight redirection, write the brief to a temp file and
  send a single line, `Read /tmp/brief.md and execute its instructions.` A
  single-line `cmux send` submits cleanly.

- **`spawn-workspace.sh` can rename the wrong workspace.** cmux
  alias-deprecation notices (`cmux: 'new-workspace' is now an alias...`) land in
  the `2>&1` stream and break positional UUID parsing, so the rename targets the
  *current* workspace instead of the new one. The helper runs cmux with
  `CMUX_QUIET=1` and extracts the ref by pattern (`grep -oE
  'workspace:[0-9]+'`) rather than by field position. After any spawn, confirm
  `cmux list-workspaces` shows the *new* workspace carrying the intended name
  and your own name unchanged.

- **`cmux current-workspace` drifts across windows after spawn cascades.** After
  several `new-workspace` and `close-workspace` cycles it can return a workspace
  id in a different window from where you actually are. Capture your own
  workspace id once at session start and reselect explicitly with `cmux
  select-workspace --workspace workspace:N`. Do not chain off repeated
  `current-workspace` queries.

- **Committing on a shared working tree.** Parallel sessions in one checkout
  share a git index and working tree, so another session's work can be sitting
  staged mid-flight. Before committing, run `git status` to spot parallel staged
  or modified files, and commit with an explicit file pathspec - `git commit -m
  '...' -- path/a path/b` - never `git add -A` or a bare commit, which sweep in
  the other session's half-done work. Note that `git commit -- <dir>` implicitly
  stages tracked modifications anywhere under that directory, so list explicit
  files rather than broad directories. For a rename, include both the old and
  the new path so the move is recorded. Do not `git reset` paths you did not
  stage: that disrupts the other session's index. Better than any of this: give
  each agent its own worktree with `spawn-workspace.sh --worktree`.

- **Verify a spawned worker's "actions taken" claims against the files.** Do not
  trust the deliverable. Spawned agents over-report completion: a worker's
  summary says three edits were applied when it made one. After a worker that
  mutates shared state finishes, **grep the target files for each claimed edit**
  before relaying success or closing the workspace. The "actions taken" section
  is a list to verify, and not a receipt. A worker may also report a canonical
  script "absent from this checkout" and hand-improvise the result - confirm the
  real tool path and re-run it properly rather than accept the improvisation.

- **Watch a worker's deliverable with a background until-loop, and not a nested
  detached job.** For one clean notification when a long workspace finishes, arm
  a background shell that exits when the deliverable file goes stable - size
  unchanged across two checks, above a floor - capped so it reports back to
  re-arm if the work is still running:

  ```bash
  prev=-1; stable=0; n=0
  while [ $n -lt 18 ]; do
    if [ -f "$F" ]; then
      cur=$(wc -c <"$F" 2>/dev/null || echo 0)
      if [ "$cur" -eq "$prev" ] && [ "$cur" -gt 800 ]; then
        stable=$((stable+1)); [ $stable -ge 2 ] && { echo DONE; exit 0; }
      else stable=0; fi
      prev=$cur
    fi
    n=$((n+1)); sleep 30
  done
  echo STILL-RUNNING; exit 2
  ```

  Do NOT nest a `nohup ... &` inside the background call. The outer call returns
  immediately and the detached child is untracked, so the completion
  notification never fires. The until-loop itself must be the background
  command.

- **cmux composers silently swallow the user's typed messages.** This is
  frequent enough to treat as a main channel: on one day, six of six typed
  instructions reached their worker only by relay. An emptied composer is not
  proof of delivery, and space-then-Enter does not flush it. Every tick, read
  each active workspace's composer line - anything sitting there may be an
  undelivered instruction. Read `orchestrator/SKILL.md` before relaying one:
  the harness also writes its own proposed text into composers, and the two
  render identically.

- **`--workspace` fails with `No focused surface` when a browser pane holds
  focus.** Both `cmux send` and `cmux read-screen` fail this way, so any
  workspace showing a rendered page reads as dead to a naive call while the
  agent is alive and working. Target the terminal surface instead: `cmux
  read-screen --surface surface:N`, and the same for `send`. Get the surface
  from `cmux list-pane-surfaces --workspace workspace:N`.

- **Count with `wc -l`, never `grep -c ... || echo 0`.** That idiom prints `0`
  twice when there are no matches, so a guard comparing its output against `0`
  fires on an empty result. A file-change watcher built this way emitted a false
  conflict alert, and the latch it then set would have suppressed a real one
  silently for the rest of the session. Use `... | wc -l | tr -d ' '`, and test
  any new guard against both an empty result and a planted positive before
  arming it.

- **zsh does not word-split an unquoted variable.** A `for` loop over multi-line
  command output runs once, over the whole blob, and a script that works in bash
  silently does nothing in zsh. Use `while IFS= read -r line; do ... done <<<
  "$out"` instead. Suspect the instrument first when a poller reports nothing
  while a direct check finds plenty.
