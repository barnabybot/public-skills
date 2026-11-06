# Open browser pages in one pane

Apply the [browser defaults](../SKILL.md#browser-sessions) to every browser page opened through cmux or orchestrator.

1. Run `cmux identify --json`. Capture the caller's workspace, window and terminal pane. Use `CMUX_WORKSPACE_ID` when present and confirm that it matches the caller. The selected workspace can belong to another task.
2. Inspect `cmux list-panes` and `cmux list-pane-surfaces` in that workspace. Reuse its existing right-hand browser pane. Preserve the user's existing layout and tabs.
3. If the browser pane is absent, focus the terminal pane and create one browser pane to its right. The default split is 50/50. Substitute the captured identities for the sample refs:

```bash
cmux focus-pane --pane pane:T --workspace workspace:N --window window:W
cmux new-pane --type browser --direction right --workspace workspace:N --window window:W --url 'https://example.com' --focus true
```

Read `pane_ref` and `surface_ref` from the result. Use the returned browser pane for each later page:

```bash
cmux new-surface --type browser --pane pane:M --workspace workspace:N --window window:W --url 'https://example.org' --focus true
```

4. For local HTML, pass an absolute `file://` URL and encode spaces as `%20`:

```bash
cmux new-surface --type browser --pane pane:M --workspace workspace:N --window window:W --url 'file:///absolute/path/report%20name.html' --focus true
```

5. Verify placement with `cmux tree --workspace workspace:N --window window:W --json`. Confirm the first split is about `0.5` and each browser tab belongs to the same browser pane. Check every new page using its returned surface:

```bash
cmux browser --surface surface:S wait --load-state complete --timeout-ms 10000
cmux browser --surface surface:S get title
cmux browser --surface surface:S get url
```

Confirm the expected title and URL before reporting completion. If the workspace is hidden, `--focus true` can leave it hidden. Select the captured workspace when the user asks to see the result, then confirm the intended tab is visible.
