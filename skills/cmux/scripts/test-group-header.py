#!/usr/bin/env python3
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).parent
W, G, A, B, H = [str(i) * 8 + '-' + str(i) * 4 + '-' + str(i) * 4 + '-' + str(i) * 4 + '-' + str(i) * 12 for i in range(1, 6)]
MARKER = f'cmux.group-header/v1/{W}/{G}'
STUB = r'''#!/usr/bin/env python3
import fcntl, json, os, sys
from pathlib import Path
p = Path(os.environ['STATE'])
with p.with_suffix('.lock').open('w') as lock:
 fcntl.flock(lock, fcntl.LOCK_EX)
 s = json.loads(p.read_text())
 args = sys.argv[1:]
 s['calls'].append(args)
 if '--json' in args:
  args = args[3:]
 cmd = args[0]
 def arg(key): return args[args.index(key)+1]
 out, rc = 'OK', 0
 if cmd == 'list-windows': out = [{'id':s['window']}]
 elif cmd == 'identify': out = {'focused':{'workspace_id':s['selected'], 'window_id':s['window']}}
 elif cmd == 'list-workspaces':
  s['inventories'] = s.get('inventories',0)+1
  if s.get('rebind_on_second_inventory') and s['inventories'] == 2:
   s['workspaces'][1]['id'] = s['header']
   s['group']['member_workspace_ids'][1] = s['header']
  if s.get('anchor_on_second_inventory') and s['inventories'] == 2:
   s['group']['anchor_workspace_id'] = s['workspaces'][1]['id']
  if '--json' in sys.argv: out = {'window_id':s['window'], 'workspaces':s['workspaces']}
  else: out = '\n'.join('  '+w['ref']+'  '+w['title'] for w in s['workspaces'])
 elif cmd == 'workspace-group' and args[1] == 'list':
  if s.get('inventory_failure'): out, rc = 'inventory failed', 1
  else: out = {'window_id':s['window'], 'groups':[s['group']]}
 elif cmd == 'workspace-group' and args[1] == 'set-anchor':
  if s.get('promotion_failure'): out, rc = 'promotion failed', 1
  else: s['group']['anchor_workspace_id'] = arg('--workspace')
 elif cmd == 'new-workspace':
  assert arg('--focus') == 'false'
  w = {'id':s['header'], 'ref':'workspace:3', 'title':'Group header', 'description':arg('--description')}
  s['workspaces'].append(w)
  s['group']['member_workspace_ids'].append(w['id'])
  out = 'OK workspace:3'
  if s.get('create_response_failure'): out, rc = 'connection lost after creation', 1
 elif cmd == 'close-workspace':
  target = arg('--workspace')
  found = next(w for w in s['workspaces'] if target in (w['id'],w['ref']))
  s['workspaces'].remove(found)
  s['group']['member_workspace_ids'].remove(found['id'])
  if s['group']['anchor_workspace_id'] == found['id']:
   s['group']['anchor_workspace_id'] = s['group']['member_workspace_ids'][0] if s['group']['member_workspace_ids'] else None
 else: out, rc = 'unsupported '+str(args), 1
 p.write_text(json.dumps(s))
 print(json.dumps(out) if isinstance(out,(dict,list)) else out)
 sys.exit(rc)
'''

class Headers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cmux = self.root/'cmux'
        cmux.write_text(STUB)
        cmux.chmod(0o755)
        self.state = self.root/'state.json'
        self.state.write_text(json.dumps({'window':W,'header':H,'selected':B,'calls':[],
            'workspaces':[{'id':A,'ref':'workspace:1','title':'Agent','description':''}, {'id':B,'ref':'workspace:2','title':'Successor','description':''}],
            'group':{'id':G,'name':'Project','is_collapsed':False,'anchor_workspace_id':A,'anchor_workspace_is_generated':False,'anchor_workspace_provenance':'user','member_workspace_ids':[A,B]}}))
        self.note = self.root/'note.md'
        self.note.write_text('---\nstatus: in-progress\nworkspace_id: "workspace:1"\nworkspace_name: "Agent"\n---\n')
        self.env = dict(os.environ, PATH=f'{self.root}:{os.environ["PATH"]}',STATE=str(self.state),CMUX_SESSIONS_DIR=str(self.root),CMUX_GROUP_HEADER_STATE_DIR=str(self.root/'locks'))
    def read(self): return json.loads(self.state.read_text())
    def change(self, **values):
        s = self.read(); s.update(values); self.state.write_text(json.dumps(s))
    def run_header(self, *args):
        return subprocess.run(['python3',str(HERE/'group_header.py'),*args,'--json'],env=self.env,text=True,capture_output=True)
    def ensure(self): return self.run_header('ensure','--workspace',A)
    def test_anchor_close_preserves_note_and_members(self):
        before = self.note.read_bytes()
        p = subprocess.run(['bash',str(HERE/'close-workspace.sh'),'workspace:1'],env=self.env,text=True,capture_output=True)
        self.assertNotEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.note.read_bytes(),before)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])
        self.assertEqual(self.read()['group']['anchor_workspace_id'],A)
    def test_ensure_then_close_leaves_header_and_successor(self):
        p = self.ensure(); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p = subprocess.run(['bash',str(HERE/'close-workspace.sh'),'workspace:1'],env=self.env,text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        s = self.read()
        self.assertEqual(s['group']['anchor_workspace_id'],H)
        self.assertEqual(s['group']['member_workspace_ids'],[B,H])
        self.assertEqual(s['selected'],B)
        self.assertIn('status: done',self.note.read_text())
        self.assertIn(['close-workspace','--workspace',A],s['calls'])
    def test_repeat_and_concurrent_ensure_create_one_header(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _:self.ensure(),range(2)))
        for p in results: self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.ensure().returncode,0)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B,H])
        self.assertEqual(self.read()['group']['anchor_workspace_id'],H)
    def test_retry_discovers_created_shell_after_failed_promotion(self):
        self.change(promotion_failure=True)
        self.assertNotEqual(self.ensure().returncode,0)
        self.change(promotion_failure=False)
        p = self.ensure(); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B,H])
    def test_uncertain_create_response_reconciles_marker(self):
        self.change(create_response_failure=True)
        p = self.ensure(); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B,H])
    def test_marked_child_is_retained(self):
        s = self.read(); s['workspaces'][1]['description'] = MARKER; self.change(workspaces=s['workspaces'])
        p = self.run_header('before-close','--workspace',B)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout)['state'],'retained-header')
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])
    def test_native_generated_anchor_with_unknown_process_is_preserved_as_child(self):
        s = self.read()
        s['group'].update(anchor_workspace_is_generated=True,anchor_workspace_provenance='generated')
        self.change(group=s['group'])
        p = self.ensure(); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(self.read()['group']['anchor_workspace_id'],H)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B,H])
    def test_managed_header_with_conversation_state_stops_ensure(self):
        s = self.read()
        s['workspaces'][0].update(description=MARKER,latest_submitted_message='Start work')
        self.change(workspaces=s['workspaces'])
        p = self.ensure()
        self.assertNotEqual(p.returncode,0)
        self.assertIn('conversation',p.stdout)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])
    def test_duplicate_markers_stop_ensure(self):
        s = self.read()
        for row in s['workspaces']: row['description'] = MARKER
        self.change(workspaces=s['workspaces'])
        self.assertNotEqual(self.ensure().returncode,0)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])
    def test_second_close_guard_retains_promoted_child_and_note(self):
        self.note.write_text(self.note.read_text().replace('workspace:1','workspace:2').replace('Agent','Successor'))
        before = self.note.read_bytes()
        self.change(anchor_on_second_inventory=True)
        p = subprocess.run(['bash',str(HERE/'close-workspace.sh'),'workspace:2'],env=self.env,text=True,capture_output=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.note.read_bytes(),before)
        self.assertEqual(self.read()['group']['anchor_workspace_id'],B)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])
    def test_reused_ref_does_not_close_replacement(self):
        self.change(rebind_on_second_inventory=True)
        p = subprocess.run(['bash',str(HERE/'close-workspace.sh'),'workspace:2'],env=self.env,text=True,capture_output=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,H])
        self.assertFalse(any(call[0]=='close-workspace' for call in self.read()['calls']))
    def test_sole_managed_header_survives_close(self):
        p = self.ensure(); self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        s = self.read()
        s['workspaces'] = [row for row in s['workspaces'] if row['id'] == H]
        s['group']['member_workspace_ids'] = [H]
        self.change(workspaces=s['workspaces'],group=s['group'])
        p = subprocess.run(['bash',str(HERE/'close-workspace.sh'),'workspace:3'],env=self.env,text=True,capture_output=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.read()['group']['anchor_workspace_id'],H)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[H])
    def test_wrong_window_and_missing_anchor_fail_without_changes(self):
        p = self.run_header('ensure','--workspace',A,'--window',G)
        self.assertNotEqual(p.returncode,0)
        s = self.read(); s['group']['anchor_workspace_id'] = H; self.change(group=s['group'])
        self.assertNotEqual(self.ensure().returncode,0)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])
    def test_inventory_failure_and_dry_run_do_not_mutate(self):
        p = self.run_header('ensure','--workspace',A,'--dry-run')
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.assertEqual(json.loads(p.stdout)['state'],'planned')
        self.assertFalse((self.root/'locks').exists())
        self.change(inventory_failure=True)
        self.assertNotEqual(self.ensure().returncode,0)
        self.assertEqual(self.read()['group']['member_workspace_ids'],[A,B])

if __name__ == '__main__': unittest.main(verbosity=2)
