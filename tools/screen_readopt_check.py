#!/usr/bin/env python3
"""Focused source gate for the DSI re-adoption / pending / abandon contract.

Structural only: it reads source and proves the ORDER of the three things that
cannot be got wrong on a scanning panel - validate before the display list is
changed, believe the switch only when DISPLACT names the new list, and commit
software geometry only after that. The emitted proof is
tools/screen_readopt_emitted_check.py; the restoration proof is
tools/screen_restore_emitted_check.py.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
H = (ROOT / 'RaspberryPi4/Lib/hvs.pi4').read_text(encoding='utf-8')
S = (ROOT / 'RaspberryPi4/Board/screen_source.pi4').read_text(encoding='utf-8')
C = (ROOT / 'RaspberryPi4/Board/screen_cmd.pi4').read_text(encoding='utf-8')


def proc(src, name):
    m = re.search(rf'(?ms)^Procedure(?:\.i)? {name}\([^\n]*\).*?^EndProcedure\s*$', src)
    if not m:
        raise AssertionError('missing ' + name)
    return m.group(0)


begin = proc(S, 'ScrDsiReadoptBegin')
resolve = proc(S, 'ScrDsiReadoptResolve')
abandon = proc(S, 'ScrDsiReadoptAbandon')
flip = proc(H, 'HvsFlipBegin')
poll = proc(H, 'HvsFlipResolve')
give_up = proc(H, 'HvsFlipAbandon')
service = proc(C, 'ScreenDsiReadoptService')
rebuild = proc(C, 'ScreenRebuildAtGeometry')

# The tuple is accepted BEFORE the hardware is asked for anything, so the
# post-confirm install cannot acquire a new external failure.
assert 'DisplayAdoptValidate' in begin and begin.index('DisplayAdoptValidate') < begin.index('HvsFlipBegin')
# The switch is believed only when the hardware says so, and the software
# geometry is committed only after that.
assert 'HvsFlipResolve()' in resolve and resolve.index('HvsFlipResolve()') < resolve.index('DisplayAdopt(')
assert 'gScrRot = gScrReadoptRot' in resolve and resolve.index('DisplayAdopt(') < resolve.index('gScrRot =')
# Two immutable slots, and the request is a write to DISPLIST0.
assert '#HVS_DLIST_SECOND' in flip and 'HvsWr(#SCALER_DISPLIST0_OFF, at)' in flip
assert 'HvsDlistActive() <> hvs_flip_at' in poll and 'hvs_flip_pending = 0' in poll

# GIVING UP IS NOT A CANCELLATION. DISPLIST has been written and the block
# may latch the staged slot later, so the staged slot is rewritten to say
# what the ACTIVE one says rather than the request being forgotten - and
# DISPLIST is NOT pointed back, which would be a second request racing the
# first.
assert 'HvsWriteDlistFor(hvs_flip_at, hvs_fb, hvs_w, hvs_h, hvs_hflip, hvs_vflip)' in give_up
assert 'HvsWr(' not in give_up
assert 'HvsFlipAbandon()' in abandon and 'gScrReadoptPending = 0' in abandon
# The software geometry was never changed while pending, so there is nothing
# in the abandon path to put back.
assert 'gScrRot =' not in abandon and 'DisplayAdopt(' not in abandon

# The console is rebuilt only after the requested list is ACTIVE, and the
# rebuild is the shared composition tail rather than a second copy of it.
assert service.index('ScrDsiReadoptResolve()') < service.index('ScreenRebuildAtGeometry()')
assert 'ConGridInit(' in rebuild and 'ScrPresentAll()' in rebuild
assert rebuild.index('ConGridInit(') < rebuild.index('BootTranscriptCount()')

# Nothing on this path repeats panel power, a reset, an initialization, the
# DSI host, the pixel valve or an allocation.
for forbidden in ('DsiPanel', 'DsiHost', 'PvUp(', 'PvDown(', 'HvsUp(', 'DisplayInit(', 'I2c'):
    assert forbidden not in begin + resolve + abandon + service + rebuild, forbidden

mutants = [
    begin.replace('DisplayAdoptValidate(fb, lw * 4, lw, lh, 32)', '0', 1),
    flip.replace('#HVS_DLIST_SECOND', '#HVS_DLIST_FIRST', 1),
    poll.replace('HvsDlistActive() <> hvs_flip_at', '0', 1),
    resolve.replace('gScrRot = gScrReadoptRot', 'gScrRot = 0', 1),
    give_up.replace('HvsWriteDlistFor(hvs_flip_at, hvs_fb, hvs_w, hvs_h, hvs_hflip, hvs_vflip)',
                    'HvsWr(#SCALER_DISPLIST0_OFF, hvs_dlist_at)', 1),
]
assert len(set(mutants)) == 5
print('screen_readopt_check: PASS - preflight, two immutable slots, pending readback, '
      'commit order, abandon-is-not-cancel and the forbidden-call boundary')
