#!/usr/bin/env python3
"""Read-only query recovery faults; no board or emulator is used by these checks."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import board_run as br

class FakeConsole:
 def __init__(self,answer='ok\npmf> ',fail=False,prompt=True):
  self.addr=('192.0.2.1',5555);self.name='test';self.answer=answer;self.fail=fail;self.prompt=prompt;self.closed=False;self.calls=[];self.transcript=['initial\n'];self.accepted_datagrams=[]
 def command(self,line,seconds):
  self.calls.append(line);self.transcript.append(line+'\n')
  if self.fail:raise br.CommandTimeout(line,seconds,5,1,True)
  self.accepted_datagrams.append(self.answer.encode());self.transcript.append(self.answer);return self.answer
 def at_prompt(self,timeout):self.calls.append('prompt');return self.prompt
 def close(self):self.closed=True

class RecoveryChecks(unittest.TestCase):
 def test_exact_read_only_allowlist(self):
  for line in ['boot mem 1000000 shot','net recv 1000000 10','deadman 15','shot','shot arm','shot disarm','screen vulkan','version\nboot','shot status ']:
   c=FakeConsole()
   with self.assertRaises(ValueError):br.read_only_command_with_recovery(c,line,1)
   self.assertEqual(c.calls,[])
 def test_no_timeout_no_replacement(self):
  for line in ['version','map','shot status']:
   c=FakeConsole()
   with patch.object(br,'NetConsole') as factory:
    got,answer,detail=br.read_only_command_with_recovery(c,line,1)
   self.assertIs(got,c);self.assertEqual(answer,c.answer);self.assertIsNone(detail);factory.assert_not_called();self.assertFalse(c.closed)
 def test_fresh_retry_and_journal(self):
  old=FakeConsole(fail=True);fresh=FakeConsole()
  with tempfile.TemporaryDirectory() as td:
   journal=br.RunJournal(Path(td),'run',{},old);journal.step('map')
   with patch.object(br,'NetConsole',return_value=fresh):got,answer,detail=br.read_only_command_with_recovery(old,'shot status',1)
   self.assertIs(got,fresh);self.assertTrue(old.closed);self.assertFalse(fresh.closed);self.assertEqual(fresh.calls,['prompt','shot status']);self.assertEqual(detail['first_received_bytes'],5)
   journal.console=got;journal.step('capture baseline');text=(Path(td)/'run.txt').read_text();self.assertEqual(text.count('retrying once on a fresh console'),1);self.assertIn('shot status',text)
 def test_status_snapshot_keeps_callers_connection(self):
  old=FakeConsole(fail=True);fresh=FakeConsole()
  with patch.object(br,'NetConsole',return_value=fresh):got,answer,detail=br.read_only_command_with_recovery(old,'shot status',1,preserve_console=True)
  self.assertIs(got,old);self.assertFalse(old.closed);self.assertTrue(fresh.closed);self.assertEqual(answer,fresh.answer);self.assertIn(fresh.answer,old.transcript);self.assertEqual(old.accepted_datagrams,fresh.accepted_datagrams)
 def test_failed_prompt_does_not_resend(self):
  old=FakeConsole(fail=True);fresh=FakeConsole(prompt=False)
  with patch.object(br,'NetConsole',return_value=fresh),self.assertRaises(br.StreamError):br.read_only_command_with_recovery(old,'shot status',1)
  self.assertEqual(fresh.calls,['prompt']);self.assertTrue(fresh.closed);self.assertFalse(old.closed)
 def test_retry_timeout_is_terminal(self):
  old=FakeConsole(fail=True);fresh=FakeConsole(fail=True)
  with patch.object(br,'NetConsole',return_value=fresh) as factory,self.assertRaises(br.StreamError):br.read_only_command_with_recovery(old,'shot status',1)
  self.assertEqual(factory.call_count,1);self.assertEqual(fresh.calls,['prompt','shot status']);self.assertTrue(fresh.closed)
 def test_socket_creation_failure_preserves_original(self):
  old=FakeConsole(fail=True)
  with patch.object(br,'NetConsole',side_effect=OSError('no socket')),self.assertRaises(br.StreamError):br.read_only_command_with_recovery(old,'shot status',1)
  self.assertFalse(old.closed)

if __name__=='__main__':unittest.main()
