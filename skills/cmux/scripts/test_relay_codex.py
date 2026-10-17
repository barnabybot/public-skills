#!/usr/bin/env python3
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('relay_codex', Path(__file__).with_name('relay-codex.py'))
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)
W = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
S = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
P = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
T = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
OTHER = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hooks = {'sessions': {T: {'sessionId': T, 'workspaceId': W.upper(),
                      'surfaceId': S.upper(), 'pid': 1234, 'pidStartSeconds': 1700000000}}}
        self.panes = {'workspace_ref': 'workspace:1', 'panes': [{'id': P}]}
        self.surfaces = {'workspace_ref': 'workspace:1', 'surfaces': [
            {'id': S.upper(), 'ref': 'surface:2', 'type': 'terminal'}]}
        self.binding = {'workspace_ref': 'workspace:1', 'surface_ref': 'surface:2',
                        'resume_binding': {'kind': 'codex', 'execution_location': 'local',
                                           'checkpoint_id': T}}
        executable = Path(self.temp.name, 'codex-target')
        executable.write_text('fixture')
        executable.chmod(0o700)
        self.executable = str(executable)
        self.binding['resume_binding']['launch_command'] = {
            'executable_path': self.executable, 'arguments': [self.executable], 'environment': None}
        self.hooks['sessions'][T]['launchCommand'] = {
            'executablePath': self.executable, 'arguments': [self.executable], 'environment': None}
        self.calls = []
        self.queue_error = None
        self.second_binding = None
        self.binding_reads = 0
        self.ps_start = time.strftime('%a %b %d %H:%M:%S %Y', time.gmtime(1700000000))

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        if command[1:2] == ['queue']:
            self.assertEqual(command[0], self.executable)
            if self.queue_error:
                raise self.queue_error
            return subprocess.CompletedProcess(command, 0, 'accepted', '')
        if command[0] == 'ps':
            return subprocess.CompletedProcess(command, 0, self.ps_start, '')
        if 'list-panes' in command:
            self.assertEqual(command[-2:], ['--workspace', W])
            data = self.panes
        elif 'list-pane-surfaces' in command:
            self.assertEqual(command[-4:], ['--workspace', W, '--pane', P])
            data = self.surfaces
        else:
            self.assertEqual(command, ['cmux', '--json', 'surface', 'resume', 'show', '--surface', S])
            self.binding_reads += 1
            data = self.second_binding if self.binding_reads > 1 and self.second_binding else self.binding
        return subprocess.CompletedProcess(command, 0, json.dumps(data), '')

    def invoke(self, *extra, message='hello', from_file=False):
        Path(self.temp.name, 'codex-hook-sessions.json').write_text(json.dumps(self.hooks))
        args = ['--workspace', W, '--surface', S, '--json']
        if from_file:
            file = Path(self.temp.name, 'message.txt')
            file.write_bytes(message.encode('utf-8'))
            args += ['--message-file', str(file)]
        else:
            args += ['--message', message]
        out = io.StringIO()
        with patch.dict(os.environ, {'CMUX_AGENT_HOOK_STATE_DIR': self.temp.name}), \
             patch.object(relay.subprocess, 'run', side_effect=self.run_command), \
             contextlib.redirect_stdout(out):
            code = relay.main(args + list(extra))
        return code, json.loads(out.getvalue())

    def assert_failed(self):
        code, result = self.invoke()
        self.assertEqual((code, result['status']), (1, 'failed'))
        self.assertFalse(any(cmd[1:2] == ['queue'] for cmd in self.calls))

    def test_exact_message_bytes_and_single_queue(self):
        for file in (False, True):
            with self.subTest(file=file):
                self.calls.clear()
                message = 'line one\r\n香港 "quotes" \'single\' $(whoami)\n\n'
                code, result = self.invoke(message=message, from_file=file)
                self.assertEqual(code, 0)
                self.assertEqual(result['queue_receipt'], 'accepted')
                self.assertEqual((result['status'], result['received']), ('queued', False))
                self.assertEqual([c for c in self.calls if c[1:2] == ['queue']],
                                 [[self.executable, 'queue', '--thread', T, '--message', message]])
                self.assertFalse(any('send' in c or 'send-key' in c for c in self.calls))

    def test_global_dock_is_outside_workspace(self):
        self.panes['panes'].append({'id': OTHER, 'dock_scope': 'global', 'surface_count': 0})
        code, result = self.invoke('--dry-run')
        self.assertEqual((code, result['status']), (0, 'planned'))

    def test_missing_conflicting_or_unusable_executable(self):
        launch = self.binding['resume_binding']['launch_command']
        for path in (None, 'codex', '/missing/codex', self.executable.upper()):
            with self.subTest(path=path):
                launch['executable_path'] = path
                self.assert_failed()
        launch['executable_path'] = self.executable
        Path(self.executable).chmod(0o600)
        self.assert_failed()

    def test_remote_and_no_daemon_arguments_refused(self):
        launches = [self.binding['resume_binding']['launch_command'],
                    self.hooks['sessions'][T]['launchCommand']]
        for launch in launches:
            for flag in ('--remote', '--remote=ws://host', '--no-daemon'):
                with self.subTest(flag=flag):
                    launch['arguments'] = [self.executable, flag]
                    self.assert_failed()
            launch['arguments'] = [self.executable]

    def test_remote_binding_fields_refused(self):
        for field in ('remote_pty_session_id', 'remote_surface_id', 'remote_workspace_id'):
            self.binding['resume_binding'][field] = OTHER
            self.assert_failed()
            self.binding['resume_binding'][field] = None

    def test_incompatible_launch_environment_refused(self):
        sources = [self.binding['resume_binding'], self.binding['resume_binding']['launch_command'],
                   self.hooks['sessions'][T]['launchCommand']]
        for source in sources:
            for key in ('CODEX_HOME', 'CODEX_REMOTE_ENDPOINT', 'CODEX_APP_SERVER_WS_URL'):
                with self.subTest(key=key):
                    source['environment'] = {key: '/incompatible/endpoint'}
                    self.assert_failed()
            source['environment'] = None

    def test_matching_launch_environment_allowed(self):
        self.binding['resume_binding']['launch_command']['environment'] = {'CODEX_HOME': '/same/home'}
        with patch.dict(os.environ, {'CODEX_HOME': '/same/home'}):
            code, result = self.invoke('--dry-run')
        self.assertEqual((code, result['status']), (0, 'planned'))

    def test_dry_run(self):
        code, result = self.invoke('--dry-run')
        self.assertEqual((code, result['status']), (0, 'planned'))
        self.assertFalse(any(c[1:2] == ['queue'] for c in self.calls))

    def test_missing_binding(self):
        self.binding['resume_binding'] = None
        self.assert_failed()

    def test_non_codex_or_remote(self):
        for field, value in [('kind', 'claude'), ('execution_location', 'remote')]:
            with self.subTest(field=field):
                previous = self.binding['resume_binding'][field]
                self.binding['resume_binding'][field] = value
                self.assert_failed()
                self.binding['resume_binding'][field] = previous

    def test_wrong_surface_or_workspace(self):
        for field, value in [('surface_ref', 'surface:99'), ('workspace_ref', 'workspace:99')]:
            with self.subTest(field=field):
                previous = self.binding[field]
                self.binding[field] = value
                self.assert_failed()
                self.binding[field] = previous

    def test_missing_or_nonterminal_surface(self):
        self.surfaces['surfaces'][0]['type'] = 'browser'
        self.assert_failed()
        self.surfaces['surfaces'] = []
        self.assert_failed()

    def test_missing_conflicting_or_duplicate_hook(self):
        original = copy.deepcopy(self.hooks)
        for change in ('missing', 'conflict', 'duplicate', 'map_key'):
            with self.subTest(change=change):
                self.hooks = copy.deepcopy(original)
                if change == 'missing':
                    self.hooks['sessions'] = {}
                elif change == 'conflict':
                    self.hooks['sessions'][T]['sessionId'] = OTHER
                elif change == 'duplicate':
                    self.hooks['sessions'][OTHER] = copy.deepcopy(self.hooks['sessions'][T])
                else:
                    self.hooks['sessions'][OTHER] = self.hooks['sessions'].pop(T)
                self.assert_failed()

    def test_stale_pid(self):
        self.ps_start = ''
        self.assert_failed()

    def test_reused_pid(self):
        self.hooks['sessions'][T]['pidStartSeconds'] += 10
        self.assert_failed()

    def test_changed_binding_before_queue(self):
        self.second_binding = copy.deepcopy(self.binding)
        self.second_binding['resume_binding']['checkpoint_id'] = OTHER
        self.assert_failed()
        self.assertEqual(self.binding_reads, 2)

    def test_queue_timeout_is_uncertain_and_never_retried(self):
        self.queue_error = subprocess.TimeoutExpired(['codex', 'queue'], 30)
        code, result = self.invoke()
        self.assertEqual((code, result['status']), (1, 'uncertain'))
        self.assertEqual(len([c for c in self.calls if c[1:2] == ['queue']]), 1)
        self.assertFalse(result['received'])

    def test_queue_failure(self):
        self.queue_error = subprocess.CalledProcessError(1, ['codex', 'queue'], stderr='unavailable')
        code, result = self.invoke()
        self.assertEqual((code, result['status']), (1, 'failed'))
        self.assertEqual(len([c for c in self.calls if c[1:2] == ['queue']]), 1)

    def test_rejects_non_uuid_invocation(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            relay.main(['--workspace', 'workspace:1', '--surface', S, '--message', 'hello'])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
