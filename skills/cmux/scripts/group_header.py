#!/usr/bin/env python3
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

PREFIX = 'cmux.group-header/v1/'


def uuid(value):
    return str(UUID(value)).upper()


def cmux(*args, as_json=True):
    flags = ['--json', '--id-format', 'both'] if as_json else []
    result = subprocess.run(['cmux', *flags, *args], capture_output=True, text=True,
                            timeout=15, env=dict(os.environ, CMUX_QUIET='1'))
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or 'cmux failed')
    return json.loads(result.stdout) if as_json else result.stdout


def inventory(window=None):
    windows = cmux('list-windows') if window is None else [{'id': uuid(window)}]
    if not isinstance(windows, list):
        raise ValueError('invalid window inventory')
    rows = []
    for item in windows:
        wid = uuid(item['id'])
        listing = cmux('list-workspaces', '--window', wid)
        if uuid(listing['window_id']) != wid or not isinstance(listing['workspaces'], list):
            raise ValueError('invalid workspace inventory')
        for row in listing['workspaces']:
            rows.append(dict(row, id=uuid(row['id']), window_id=wid))
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate workspace identity')
    return rows


def resolve(workspace, window=None):
    rows = inventory(window)
    matches = [r for r in rows if workspace.lower() in (r['id'].lower(), r.get('ref', '').lower())
               or workspace == r.get('title')]
    if len(matches) != 1:
        raise ValueError('workspace must identify one live UUID')
    return matches[0], rows


def groups(window, rows=None):
    data = cmux('workspace-group', 'list', '--window', window)
    if uuid(data['window_id']) != window or not isinstance(data['groups'], list):
        raise ValueError('invalid group inventory')
    known = {r['id'] for r in rows if r['window_id'] == window} if rows is not None else None
    seen, group_ids, result = set(), set(), []
    for row in data['groups']:
        gid = uuid(row['id'])
        members = [uuid(m) for m in row['member_workspace_ids']]
        anchor = uuid(row['anchor_workspace_id'])
        if (gid in group_ids or len(set(members)) != len(members) or anchor not in members
                or seen.intersection(members) or (known is not None and not set(members).issubset(known))):
            raise ValueError('inconsistent group membership')
        seen.update(members)
        group_ids.add(gid)
        result.append(dict(row, id=gid, member_workspace_ids=members, anchor_workspace_id=anchor))
    return result


def before_close(workspace, window=None):
    target, rows = resolve(workspace, window)
    window = target['window_id']
    group_rows = groups(window, rows)
    group = next((g for g in group_rows if target['id'] in g['member_workspace_ids']), None)
    description = target.get('description') or ''
    marked = False
    if description.startswith(PREFIX):
        parts = description[len(PREFIX):].split('/')
        if len(parts) == 2:
            try:
                uuid(parts[0])
                uuid(parts[1])
                marked = True
            except ValueError:
                pass
    retained = marked or (group is not None and group['anchor_workspace_id'] == target['id'])
    result = dict(state='retained-header' if retained else 'ready', workspace=target['id'],
                  window=window, ref=target.get('ref'), title=target.get('title'),
                  group=group['id'] if group else None, header=group['anchor_workspace_id'] if group else None)
    if retained:
        result['reason'] = 'Reserved header or current anchor. Retain this workspace.'
        if group:
            result['repair_command'] = f'python3 {Path(__file__).resolve()} ensure --group {group["id"]} --window {window}'
    return result


def require_close(workspace, window=None):
    result = before_close(workspace, window)
    if result['state'] == 'retained-header':
        raise ValueError(result['reason'] + ' ' + result.get('repair_command', ''))
    return result


def ensure(workspace=None, window=None, group=None, dry_run=False):
    if workspace:
        target, rows = resolve(uuid(workspace), window)
        window = target['window_id']
        matches = [g for g in groups(window) if target['id'] in g['member_workspace_ids']]
        if not matches:
            return dict(state='ungrouped', workspace=target['id'], window=window, group=None, header=None)
        group = matches[0]['id']
    else:
        window, group = uuid(window), uuid(group)
    marker = PREFIX + window + '/' + group

    def snapshot():
        rows = inventory(window)
        matches = [g for g in groups(window, rows) if g['id'] == group]
        if len(matches) != 1:
            raise ValueError('group no longer exists')
        current = matches[0]
        if workspace and uuid(workspace) not in current['member_workspace_ids']:
            raise ValueError('caller moved out of the group')
        candidates = [r for r in rows if (r.get('description') or '').lower() == marker.lower()]
        if len(candidates) > 1:
            raise ValueError('duplicate managed header descriptions')
        header = candidates[0] if candidates else None
        if header:
            if header['id'] not in current['member_workspace_ids']:
                raise ValueError('managed header moved out of its group')
            if any(value for key, value in header.items()
                   if any(word in key.lower() for word in ('agent', 'conversation', 'resume', 'submitted'))):
                raise ValueError('managed header contains agent or conversation state')
        return current, header

    def apply():
        current, header = snapshot()
        original = set(current['member_workspace_ids'])
        result = dict(state='ready', window=window, group=group,
                      workspace=uuid(workspace) if workspace else None,
                      header=header['id'] if header else None)
        if header and header['id'] == current['anchor_workspace_id']:
            return result
        if dry_run:
            return dict(result, state='planned')
        focus = cmux('identify')['focused']
        if not header:
            failure = None
            try:
                cmux('new-workspace', '--window', window, '--group', group,
                     '--name', 'Group header', '--description', marker,
                     '--command', '/bin/zsh -f', '--focus', 'false', as_json=False)
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                failure = error
            current, header = snapshot()
            if header is None:
                raise ValueError(f'Header creation unresolved; retry ensure to discover it. {failure or "No marker found"}')
        if not original.issubset(current['member_workspace_ids']):
            raise ValueError('group membership changed during creation')
        cmux('workspace-group', 'set-anchor', '--group', group, '--workspace', header['id'],
             '--window', window, as_json=False)
        current, verified = snapshot()
        if (verified is None or current['anchor_workspace_id'] != header['id']
                or not original.issubset(current['member_workspace_ids'])):
            raise ValueError('header or original members failed verification')
        if cmux('identify')['focused'] != focus:
            raise ValueError('focus changed during header repair; inspect selection')
        return dict(result, state='repaired', header=header['id'])

    if dry_run:
        return apply()
    state = Path(os.environ.get('CMUX_GROUP_HEADER_STATE_DIR',
                                str(Path.home()/'.local/state/cmux/group-headers')))
    state.mkdir(parents=True, exist_ok=True)
    with (state/f'{window}-{group}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return apply()


def main():
    parser = argparse.ArgumentParser(description='Reserve permanent plain-shell group headers and guard closure.')
    parser.add_argument('operation', choices=['ensure', 'before-close'])
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--workspace', help='Live workspace UUID; before-close also accepts a ref or exact name')
    scope.add_argument('--group', help='Group UUID, requires --window')
    parser.add_argument('--window', help='Owning window UUID')
    parser.add_argument('--dry-run', action='store_true', help='Read inventory and report without changes')
    parser.add_argument('--json', action='store_true', help='Emit one JSON result')
    args = parser.parse_args()
    if (args.group and not args.window) or (args.operation == 'before-close' and not args.workspace):
        parser.error('--group requires --window and is supported only by ensure')
    try:
        result = (before_close(args.workspace, args.window) if args.operation == 'before-close'
                  else ensure(args.workspace, args.window, args.group, args.dry_run))
        code = 1 if result['state'] == 'retained-header' else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        result, code = dict(state='error', reason=str(error)), 1
    print(json.dumps(result) if args.json else ' '.join(str(v) for v in result.values() if v is not None))
    return code


if __name__ == '__main__':
    sys.exit(main())
