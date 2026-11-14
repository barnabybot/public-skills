import os
from datetime import date
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


HELPER = Path(__file__).with_name('spawn-workspace.sh')


class SpawnLaunchTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.home() / 'Scratch' / date.today().isoformat()
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.env = dict(os.environ, PATH=f'{self.directory}:{os.environ["PATH"]}',
                        SPAWN_PYTHON=sys.executable, TEST_DIR=str(self.directory),
                        CMUX_AGENT_LAUNCH_KIND='claude')
        resolver = self.directory / 'resolve.py'
        resolver.write_text('''import os, shlex
agent = os.environ['TEST_AGENT']
model = 'fixture-model'
values = dict(ROUTE_AGENT=agent, ROUTE_MODEL=model, ROUTE_MODEL_ID=model,
              ROUTE_DISPLAY=model, ROUTE_EFFORT='high', ROUTE_LEGACY_NOTE='',
              ROUTE_LINE='route: fixture')
for key, value in values.items():
    print(f'{key}={shlex.quote(value)}')
''')
        self.env['ROUTING_RESOLVER'] = str(resolver)
        self.write_executable('cmux', '''#!/bin/bash
case "$1" in
  new-workspace)
    if [[ "$2" == --help ]]; then echo legacy; exit; fi
    while [[ $# -gt 0 ]]; do
      if [[ "$1" == --command ]]; then printf '%s' "$2" > "$TEST_DIR/command"; break; fi
      shift
    done
    echo 'OK workspace:99'
    ;;
  current-workspace) echo workspace:1 ;;
  read-screen)
    printf 'read\\n' >> "$TEST_DIR/reads"
    printf '%s' "$TEST_SCREEN"
    ;;
  send-key) printf '%s\\n' "${@: -1}" >> "$TEST_DIR/keys" ;;
esac
''')
        self.write_executable('sleep', '#!/bin/bash\nexit 0\n')

    def write_executable(self, name, contents):
        path = self.directory / name
        path.write_text(contents)
        path.chmod(0o755)

    def launch(self, agent, screen, prompt=True):
        for name in ('keys', 'command', 'reads'):
            (self.directory / name).unlink(missing_ok=True)
        self.env.update(TEST_AGENT=agent, TEST_SCREEN=screen)
        args = [str(HELPER), 'launch-fixture', '--model', 'fixture', '--effort', 'high',
                '--cwd', str(self.directory), '--no-session']
        if prompt:
            args += ['--prompt', 'Execute the fixture task.']
        result = subprocess.run(args, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tokens = shlex.split((self.directory / 'command').read_text())
        for token in tokens:
            if token.startswith('Read the file at /tmp/spawn-prompt.'):
                prompt_path = Path(token.split(' in full.')[0].removeprefix('Read the file at '))
                self.addCleanup(prompt_path.unlink, missing_ok=True)
        keys = self.directory / 'keys'
        reads = self.directory / 'reads'
        self.reads = reads.read_text().splitlines() if reads.exists() else []
        return tokens[tokens.index('exec') + 1:], keys.read_text().splitlines() if keys.exists() else []

    def test_claude_prompt_preserves_brief_without_trust_input(self):
        command, keys = self.launch('claude', 'Do you trust this folder?')
        self.assertEqual(command[:6], ['claude', '--dangerously-skip-permissions',
                                     '--model', 'fixture-model', '--effort', 'high'])
        self.assertEqual(len(command), 7)
        self.assertTrue(command[6].startswith('Read the file at /tmp/spawn-prompt.'))
        self.assertEqual(keys, [])
        self.assertEqual(self.reads, [])

    def test_claude_selected_no(self):
        command, keys = self.launch('claude', 'Do you trust this folder?\n> 1. No, exit\n  2. Yes, I trust this folder', False)
        self.assertEqual(command, ['claude', '--dangerously-skip-permissions', '--model',
                                   'fixture-model', '--effort', 'high'])
        self.assertEqual(keys, [])
        self.assertEqual(self.reads, [])

    def test_claude_selected_yes(self):
        for marker in ('>', '❯'):
            with self.subTest(marker=marker):
                _, keys = self.launch('claude', f'Do you trust this folder?\n{marker} 1. Yes, I trust this folder\n  2. No, exit', False)
                self.assertEqual(keys, [])
                self.assertEqual(self.reads, [])

    def test_unrecognised_yes_no_chrome_does_not_send_down(self):
        screens = (
            'Do you trust this folder?\n  1. Yes, I trust this folder\n  2. No, exit',
            'Do you trust this folder?\n* Yes, I trust this folder\n  No, exit',
            'Do you trust this folder?\n→ Yes\n  No',
        )
        for screen in screens:
            with self.subTest(screen=screen):
                _, keys = self.launch('claude', screen, False)
                self.assertNotIn('Down', keys)
                self.assertEqual(keys, [])
                self.assertEqual(self.reads, [])

    def test_python_selection(self):
        names = ['/opt/homebrew/bin/python3.12', '/opt/homebrew/bin/python3', 'python3', 'explicit-python']
        log = self.directory / 'python-calls'
        functions = []
        for name in names:
            functions.append(f'''{name}() {{
  if [[ "$1" == -c && "$2" == 'import yaml' ]]; then
    printf '%s\\n' 'probe {name}' >> {shlex.quote(str(log))}
    return 0
  fi
  printf '%s\\n' 'run {name}' >> {shlex.quote(str(log))}
  {shlex.quote(sys.executable)} "$@"
}}
''')
        startup = self.directory / 'bash-env'
        startup.write_text('\n'.join(functions))
        self.env['BASH_ENV'] = str(startup)
        for override, expected in ((None, 'python3'), ('explicit-python', 'explicit-python')):
            with self.subTest(override=override):
                log.unlink(missing_ok=True)
                self.env.pop('SPAWN_PYTHON', None)
                if override:
                    self.env['SPAWN_PYTHON'] = override
                self.launch('claude', 'ready', False)
                self.assertEqual(log.read_text().splitlines(), [f'run {expected}'])


if __name__ == '__main__':
    unittest.main()
