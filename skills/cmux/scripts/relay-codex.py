#!/usr/bin/env python3
import argparse
import calendar
import json
import os
from pathlib import Path
import re
import subprocess
import time


def full_uuid(value):
    if not isinstance(value, str) or not re.fullmatch(
        r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value
    ):
        raise ValueError('Pass a full UUID; numeric refs and partial IDs are unsupported.')
    return value.lower()


def same_id(value, expected):
    return isinstance(value, str) and value.lower() == expected


def cmux_json(arguments):
    result = subprocess.run(['cmux', '--json'] + arguments, capture_output=True,
                            text=True, check=True, timeout=10)
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError('cmux returned an invalid object; inspect the target and retry.')
    return data


def identity(workspace, surface):
    panes = cmux_json(['--id-format', 'both', 'list-panes', '--workspace', workspace])
    workspace_ref = panes.get('workspace_ref')
    if not workspace_ref or ('workspace_id' in panes and
                             not same_id(panes['workspace_id'], workspace)):
        raise ValueError('Workspace identity is absent or conflicting; inspect cmux list-workspaces.')
    matches = []
    for pane in panes['panes']:
        if pane.get('dock_scope') == 'global':
            continue
        surfaces = cmux_json(['--id-format', 'both', 'list-pane-surfaces',
                              '--workspace', workspace, '--pane', full_uuid(pane['id'])])
        if surfaces.get('workspace_ref') != workspace_ref or (
            'workspace_id' in surfaces and not same_id(surfaces['workspace_id'], workspace)
        ):
            raise ValueError('Pane workspace changed; inspect the target before retrying.')
        matches.extend(row for row in surfaces['surfaces'] if same_id(row.get('id'), surface))
    if len(matches) != 1 or matches[0].get('type') != 'terminal':
        raise ValueError('Target must be one live terminal in the selected workspace; inspect its UUID.')
    surface_ref = matches[0].get('ref')
    native = cmux_json(['surface', 'resume', 'show', '--surface', surface])
    if not surface_ref or native.get('workspace_ref') != workspace_ref or native.get('surface_ref') != surface_ref:
        raise ValueError('Resume binding belongs to another target; inspect the selected surface.')
    binding = native.get('resume_binding')
    if not isinstance(binding, dict) or binding.get('kind') != 'codex' or binding.get('execution_location') != 'local':
        raise ValueError('Target needs a local Codex resume binding; inspect cmux surface resume show.')
    thread = full_uuid(binding.get('checkpoint_id'))
    state_dir = Path(os.environ.get('CMUX_AGENT_HOOK_STATE_DIR', str(Path.home() / '.cmuxterm')))
    sessions = json.loads((state_dir / 'codex-hook-sessions.json').read_text(encoding='utf-8'))['sessions']
    matches = [(key, row) for key, row in sessions.items()
               if same_id(row.get('workspaceId'), workspace) and same_id(row.get('surfaceId'), surface)]
    if len(matches) != 1:
        raise ValueError('Expected exactly one matching hook session; inspect codex-hook-sessions.json.')
    key, row = matches[0]
    if not same_id(key, thread) or not same_id(row.get('sessionId'), thread):
        raise ValueError('Hook session conflicts with the native binding; refresh the target session.')
    launch, hook_launch = binding.get('launch_command') or {}, row.get('launchCommand') or {}
    executable = launch.get('executable_path')
    if (not isinstance(executable, str) or not Path(executable).is_absolute() or
        executable != hook_launch.get('executablePath') or not Path(executable).is_file() or
        not os.access(executable, os.X_OK)):
        raise ValueError('Target executable is missing, conflicting or unavailable; refresh the launch binding.')
    if any(value is not None for key, value in binding.items() if key.startswith('remote_')):
        raise ValueError('Remote bindings are unsupported; select a default local daemon session.')
    for command in (launch, hook_launch):
        if any(arg in ('--remote', '--no-daemon') or arg.startswith('--remote=')
               for arg in command.get('arguments', [])):
            raise ValueError('Remote or no-daemon launch is unsupported; select a default local daemon session.')
    for source in (binding, launch, hook_launch):
        for key, value in (source.get('environment') or {}).items():
            if key == 'CODEX_HOME' or re.search(r'(ENDPOINT|URL|SOCKET|REMOTE|DAEMON)', key):
                expected = os.environ.get(key, str(Path.home() / '.codex') if key == 'CODEX_HOME' else None)
                if value != expected:
                    raise ValueError('Launch routing environment differs; use the same local daemon environment.')
    pid, started = row.get('pid'), row.get('pidStartSeconds')
    if type(pid) is not int or pid <= 0 or type(started) is not int or started <= 0:
        raise ValueError('Hook process generation is missing; refresh the target session.')
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], capture_output=True,
                            text=True, check=True, timeout=10,
                            env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'})
    actual_start = calendar.timegm(time.strptime(result.stdout.strip(), '%a %b %d %H:%M:%S %Y'))
    if actual_start != started:
        raise ValueError('Hook PID belongs to another process generation; refresh the target session.')
    return thread, pid, started, executable


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Queue one message to a verified local Codex thread without writing to its terminal.',
        epilog='Queue acceptance does not prove receipt. Timeouts are uncertain; inspect the thread before retrying.')
    parser.add_argument('--workspace', type=full_uuid, required=True, help='Full live cmux workspace UUID.')
    parser.add_argument('--surface', type=full_uuid, required=True, help='Full terminal surface UUID within that workspace.')
    message = parser.add_mutually_exclusive_group(required=True)
    message.add_argument('--message', help='Exact text to queue, including any newlines.')
    message.add_argument('--message-file', type=Path, help='UTF-8 file; preserves line endings and trailing newlines.')
    parser.add_argument('--dry-run', action='store_true', help='Validate identity and report planned; do not queue.')
    parser.add_argument('--json', action='store_true', help='Emit a JSON result with status and received=false.')
    args = parser.parse_args(argv)
    try:
        text = args.message_file.read_bytes().decode('utf-8') if args.message_file else args.message
        if not text or '\0' in text:
            parser.error('Pass a non-empty message without NUL bytes.')
    except (OSError, UnicodeError) as error:
        parser.error(f'Cannot read the UTF-8 message file: {error}')
    result = {'status': 'failed', 'workspace': args.workspace, 'surface': args.surface, 'received': False}
    queue_started = False
    try:
        target = identity(args.workspace, args.surface)
        result['thread'] = target[0]
        result['executable'] = target[3]
        if identity(args.workspace, args.surface) != target:
            raise ValueError('Target identity changed during verification; inspect it before retrying.')
        if args.dry_run:
            result['status'] = 'planned'
        else:
            queue_started = True
            queued = subprocess.run([target[3], 'queue', '--thread', target[0], '--message', text],
                                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    check=True, timeout=30)
            result['queue_receipt'] = queued.stdout
            result['status'] = 'queued'
    except subprocess.TimeoutExpired:
        result['status'] = 'uncertain' if queue_started else 'failed'
        result['error'] = ('Queue timed out and may have accepted the message; inspect the thread before retrying.'
                           if queue_started else 'Identity verification timed out; inspect cmux and the target process.')
    except subprocess.CalledProcessError as error:
        result['error'] = f'{error.cmd[0]} exited {error.returncode}; inspect the target and command availability before retrying.'
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result['error'] = f'Validation or command failed: {error}. Inspect the target and hook state before retrying.'
    print(json.dumps(result, ensure_ascii=False) if args.json else
          f"{result['status']}: {result.get('thread', args.surface)}; received=false" +
          (f"; {result['error']}" if 'error' in result else ''))
    return 0 if result['status'] in ('planned', 'queued') else 1


if __name__ == '__main__':
    raise SystemExit(main())
