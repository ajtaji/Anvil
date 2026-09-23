"""Execute the shared screen-connection action/result contract as A64."""
from __future__ import annotations
import argparse
from pathlib import Path
import tempfile
import pi3_framebuffer_contract_check as fb
import pathlib as _pmfpath
from pmf_compiler import resolve_compiler

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'RaspberryPi3/Tests/screen_connection_contract.pi3'
CTRL=0x06000000

def run(compiler:Path):
  a64=fb.load_interpreter()
  with tempfile.TemporaryDirectory(prefix='anvil-screen-connection-') as d:
    blob,symbols=fb.compile_image(compiler,Path(d),SOURCE,'screen-connection-contract')
  cpu=fb.make_machine(a64,blob,symbols,fb.FirmwareCase('valid'),el=3)
  steps=0
  def invoke(command,*args):
    nonlocal steps
    fb.write32(cpu,CTRL,command)
    for i,value in enumerate(args,1): cpu.store(CTRL+i*8,value&0xffffffffffffffff,8)
    value,count=fb.call(cpu,symbols,'Main',limit=100_000);steps+=count;return value
  def state(): return invoke(4)
  def generation(): return invoke(5)
  def next(now): return invoke(2,now)
  def complete(action,result,now): return invoke(3,action,result,now)

  # Inert until registration; invalid poll interval is clamped.
  assert state()==0 and next(0)==0
  assert invoke(1,1)==1 and state()==1 and generation()==0
  # Disable cannot discard a claimed or asynchronous pre-surface probe.
  assert next(0)==1 and invoke(7)==0
  assert complete(1,0,0)==1 and invoke(7)==0
  assert next(1)==1 and complete(1,3,1)==1 and state()==1
  assert invoke(7)==1 and state()==0
  assert invoke(1,1)==1
  # Claim is exclusive. Wrong-token completion cannot release it.
  assert next(0)==1 and next(0)==0
  assert complete(2,1,0)==0 and next(0)==0
  # Async probe PENDING is distinct from ABSENT and reacquires a new token.
  assert complete(1,0,0)==1 and state()==2
  assert next(1)==1 and complete(1,1,1)==1 and state()==3
  # Attach and redraw are independently pending; generation publishes once.
  assert next(1)==2 and complete(2,0,1)==1 and state()==3
  assert next(2)==2 and complete(2,1,2)==1 and state()==4
  assert next(2)==4 and complete(4,0,2)==1 and state()==4
  assert next(3)==4 and complete(4,1,3)==1 and state()==5 and generation()==1

  # One absent observation is not detach. A tight next tick does not create a
  # second sample: the poll gap must elapse before another probe token exists.
  assert next(1003)==1 and complete(1,3,1003)==1 and state()==5
  assert next(1003)==0 and next(1500)==0
  assert next(2003)==1 and complete(1,3,2003)==1 and state()==6
  # Detach can stay pending while the board quiesces DMA.
  assert next(2003)==3 and complete(3,0,2003)==1 and state()==6
  assert next(2004)==3 and complete(3,1,2004)==1 and state()==1

  # Reconnect requires a complete attach/redraw sequence and one generation.
  assert next(3004)==1 and complete(1,1,3004)==1
  assert next(3004)==2 and complete(2,1,3004)==1
  assert next(3004)==4 and complete(4,1,3004)==1
  assert state()==5 and generation()==2

  # Recoverable attach cancellation targets a quiescing detach then ABSENT.
  assert next(4004)==1 and complete(1,3,4004)==1
  assert next(5004)==1 and complete(1,3,5004)==1
  assert next(5004)==3 and complete(3,1,5004)==1 and state()==1
  assert next(6004)==1 and complete(1,1,6004)==1
  assert next(6004)==2 and complete(2,2,6004)==1 and state()==6
  assert next(6004)==3 and complete(3,1,6004)==1 and state()==1

  # An unknown positive probe result while attached must retain ownership and
  # require DETACH before quarantine. Register replacement and disable cannot
  # erase a live owner.
  assert next(7004)==1 and complete(1,1,7004)==1
  assert next(7004)==2 and complete(2,1,7004)==1
  assert next(7004)==4 and complete(4,1,7004)==1
  assert next(8004)==1 and complete(1,99,8004)==1 and state()==6
  assert invoke(1,1000)==0 and invoke(7)==0 and state()==6
  assert next(8004)==3 and complete(3,1,8004)==1 and state()==7
  assert invoke(7)==1 and state()==0

  # Fatal probe before ownership quarantines immediately and issues no action,
  # so disable is safe without a detach.
  assert invoke(1,1000)==1
  assert next(9004)==1 and complete(1,-9,9004)==1
  fatal_state,fatal_error=state(),invoke(6)&0xffffffffffffffff
  assert fatal_state==7 and fatal_error==((-9)&0xffffffffffffffff),(fatal_state,hex(fatal_error))
  assert next(0xffffffff)==0 and generation()==0
  assert invoke(7)==1 and state()==0 and next(0)==0

  # The board clock is a wrapping 32-bit millisecond counter.  A redraw just
  # before wrap must not cause an immediate poll, and must become due after a
  # full interval across the wrap boundary.
  assert invoke(1,1000)==1
  assert next(0xffffffe0)==1 and complete(1,1,0xffffffe0)==1
  assert next(0xffffffe0)==2 and complete(2,1,0xffffffe0)==1
  assert next(0xffffffe0)==4 and complete(4,1,0xffffffe0)==1
  assert next(0x20)==0
  assert next(0x3c8)==1
  return 82,steps

def main():
  p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);a=p.parse_args(); a.compiler = _pmfpath.Path(resolve_compiler(a.compiler)) if a.compiler else a.compiler
  if not a.compiler.is_file(): raise SystemExit(f'compiler not found: {a.compiler}')
  checks,steps=run(a.compiler.resolve())
  print(f'PASS: {checks} shared screen-connection assertions; {steps:,} emitted A64 instructions')
  print('  exclusive action token; wrong-token refusal; asynchronous probe pending')
  print('  timed two-sample detach and 32-bit wrap; pending DMA quiescence; reconnect generation')
  print('  recoverable attach cancellation; owned cleanup before quarantine; guarded disable/register')
if __name__=='__main__': main()
