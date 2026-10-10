# Automatic conversation titles

cmux can generate short workspace and tab titles from agent conversations.
Manual titles block automatic naming.

## Codex workspaces keep directory titles

A local check on cmux 0.65.0 (108), commit `dda24fbd2`, with Codex CLI
0.162.1 found enabled auto-naming and installed Stop hooks but no generated
title. The isolated Codex naming process copied the user configuration into
a temporary home and downloaded plugin repositories during startup.
Selecting Claude produced an automatic title.

1. Confirm the Claude CLI is installed and signed in. Read the live setting:

   ```bash
   cmux rpc workspace.set_auto_title '{"probe":true}'
   ```

2. Back up `~/.config/cmux/cmux.json` to a timestamped `.bak` file. Preserve
   its existing fields and comments. Set these fields in its `automation` object:

   ```json
   "workspaceAutoNaming": true,
   "autoNamingAgent": "claude"
   ```

   Claude uses its account to generate short titles across supported agent
   sessions. Apply the setting on each affected Mac. Installing this skill
   supplies the instructions; it leaves the local application settings to you.

3. Validate and reload:

   ```bash
   cmux config check
   cmux reload-config
   cmux rpc workspace.set_auto_title '{"probe":true}'
   ```

   The live probe must report `enabled: true` and `summarizer_agent: "claude"`.

4. Complete one ordinary Codex turn in a workspace with an automatic title.
   Confirm the new title with `cmux workspace list`. The session record in
   `~/.cmuxterm/codex-hook-sessions.json` should have `autoNameLastTitle` and
   `autoNameLastNamedAt`. Allow the 180-second cooldown after a previous attempt.

The installed Codex Stop handler can dispatch naming internally. Inspect
its generated script before adding another auto-name hook.

## Version limits and rollback

cmux 0.64.22 passed `web_search=false`, which newer Codex versions reject.
Its Claude naming command also passed an invalid empty MCP configuration.
The workaround above was verified on 0.65.0; check the installed version
before applying it to an older build. Version 0.65.0 supplies the supported
`web_search="disabled"` and `{"mcpServers":{}}` values.

Restore the configuration backup and run `cmux reload-config` to roll back.
To restore agent-specific title generation, set `autoNamingAgent` to `auto`
and verify a completed Codex turn first.

Sources: [cmux naming invocation](https://github.com/manaflow-ai/cmux/blob/dda24fbd2/CLI/CMUXCLI%2BAutoNamingDispatch.swift),
[argument builders](https://github.com/manaflow-ai/cmux/blob/dda24fbd2/CLI/CMUXCLI%2BAutoNaming.swift),
and [setting schema](https://github.com/manaflow-ai/cmux/blob/dda24fbd2/web/data/cmux.schema.json).
