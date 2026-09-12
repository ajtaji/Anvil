"""Conservative source review gate, NOT a complete language/escape proof.

Reports explicit read-before-write and frame-address aliases passed to calls,
returned, or stored outside scalar locals. Calls are review boundaries: a
synchronous consumer may be safe. Unsupported control flow is reported, never
silently certified. Compiler-zeroed locals may intentionally read zero.
"""
import argparse,json,re
from pathlib import Path
import usb_frame_safety_check as old
TOKEN=re.compile(r'(?<![.#@])\b[a-z_]\w*\b',re.I)
DECL=re.compile(r'^(?:Define|Protected|Dim)\s+(.+)',re.I)
ASSIGN=re.compile(r'^\*?([a-z_]\w*)(?:\.\w+)?\s*=\s*(.*)$',re.I)

def statements(text):
 # Remove strings BEFORE comments/colon splitting. Keep original line numbers.
 for n,line in enumerate(text.splitlines(),1):
  line=re.sub(r'"(?:[^"\\]|\\.)*"','""',line).split(';',1)[0]
  for part in re.split(r'(?<!:):(?!:)',line):
   if part.strip():yield n,part.strip()

def analyze(text):
 findings=[];unknown=[];locals=set();written=set();aliases=set();branches=[];inside=False;asm=False;proc=''
 def report(n,kind,detail):findings.append((n,proc,kind,detail))
 for n,s in statements(text):
  m=old.PROC.match(s)
  if m:
   proc=m[1];inside=True;locals=set();written=set();aliases=set();branches=[]
   for p in m[2].split(','):
    k=re.match(r'\s*\*?(\w+)',p)
    if k:locals.add(k[1].lower());written.add(k[1].lower())
   continue
  if not inside:continue
  if s.lower()=='endprocedure':inside=False;continue
  if s.lower()=='asm':asm=True;unknown.append((n,proc,'inline ASM effects require review'));continue
  if s.lower()=='endasm':asm=False;continue
  if asm:continue
  low=s.lower()
  if re.match(r'^(select|case|default|endselect|goto|gosub|for|next|repeat|until|forever|break|continue)\b',low):
   unknown.append((n,proc,'unsupported control flow: '+s));written=set();continue
  if low.startswith('else'):
   if branches:
    entry,arm,kind=branches[-1];branches[-1]=(entry,set(written),kind);written=set(entry)
   continue
  if low in ('endif','wend'):
   if branches:
    entry,arm,kind=branches.pop();written=(written & arm) if arm is not None else written & entry
   else:unknown.append((n,proc,'unmatched control terminator'))
   continue
  m=DECL.match(s)
  if m:
   for item in m[1].split(','):
    k=re.match(r'\s*\*?(\w+)(?:\.\w+)?(.*)',item)
    if not k:continue
    name=k[1].lower();locals.add(name)
    if '[' in k[2]:unknown.append((n,proc,'array element initialization not tracked: '+name))
    if '=' in k[2]:
     expr=k[2].split('=',1)[1]
     for t in set(TOKEN.findall(expr.lower())) & locals - written:report(n,'read-before-write',t)
     written.add(name)
     if set(re.findall(r'@(\w+)',expr.lower()))&locals or set(TOKEN.findall(expr.lower()))&aliases:aliases.add(name)
   continue
  m=ASSIGN.match(s);rhs=m[2] if m else s;lhs=m[1].lower() if m else None
  tokens=set(TOKEN.findall(rhs.lower()));addresses=set(re.findall(r'@\*?(\w+)',rhs.lower()))&locals
  # Address taking itself is not a read of that local's value.
  for name in tokens & locals - written - addresses:report(n,'read-before-write',name)
  tainted=bool(addresses or tokens&aliases)
  if tainted:
   if old.CALL.search(rhs):report(n,'alias-call-review',rhs)
   if low.startswith('procedurereturn'):report(n,'alias-return',rhs)
   if m and lhs not in locals:report(n,'alias-nonlocal-store',s)
   if not m and re.match(r'^\w+\[',s):report(n,'alias-index-store',s)
  if m:
   if lhs in locals:written.add(lhs)
   if tainted:aliases.add(lhs)
   # Monotone aliases intentionally retain taint across branch overwrites.
  if re.match(r'^(if|while)\b',low):branches.append((set(written),None,low.split()[0]))
 return findings,unknown

def selftest():
 def check(body,kind):
  f,_=analyze('Procedure Test(flag.i)\n'+body+'\nEndProcedure');assert any(x[2]==kind for x in f),(body,f)
 check('Define x.i\nPrint(x)','read-before-write')
 check('Define x.i\nIf flag\nx=1\nEndIf\nPrint(x)','read-before-write')
 check('Define x.i\nWhile flag\nx=1\nWend\nPrint(x)','read-before-write')
 check('Define x.i,p.i,q.i\nx=0\np=@x\nq=p\nForward(q)','alias-call-review')
 check('Define x.i,p.i\nx=0\np=@x\nglobal_pointer=p','alias-nonlocal-store')
 check('Define x.i,p.i\np=@x\nProcedureReturn p','alias-return')
 f,u=analyze('Procedure Test(flag.i)\nDefine x.i\nIf flag\nx=1\nElse\nx=2\nEndIf\nPrint(x)\nEndProcedure');assert not f and not u,(f,u)
 print('PASS six negative controls and initialized-branch positive control')

def main():
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path);p.add_argument('--selftest',action='store_true');a=p.parse_args();selftest()
 if a.selftest:return 0
 # Syntactic direct-call closure, not dynamic dispatch or conditional include resolution.
 definitions={};duplicates=[]
 for folder in ('RaspberryPi4/Board','RaspberryPi4/Lib'):
  for path in (old.ROOT/folder).glob('*.pi4'):
   text=path.read_text(encoding='utf-8',errors='replace')
   for match in re.finditer(r'(?ims)^Procedure(?:\.\w+)?\s+(\w+)\s*\([^\n]*?\).*?\bEndProcedure\b',text):
    name=match[1].lower()
    if name in definitions:duplicates.append(name)
    definitions[name]=(str(path.relative_to(old.ROOT)),text[:match.start()].count('\n'),match[0])
 pending=['usbenumerate'];seen=set();missing=set();findings=[];unknown=[]
 while pending:
  name=pending.pop()
  if name in seen:continue
  seen.add(name)
  if name not in definitions:missing.add(name);continue
  path,offset,body=definitions[name];f,u=analyze(body)
  findings.extend((path,n+offset,proc,kind,detail) for n,proc,kind,detail in f)
  unknown.extend((path,n+offset,proc,why) for n,proc,why in u)
  for _,line in statements(body):pending.extend(x.lower() for x in old.CALL.findall(line) if x.lower()!=name and x.lower() not in ('if','elseif','and','or','while','until','not'))
 report={'scope':'syntactic UsbEnumerate direct-call closure only; missing callees include intrinsics and dynamic targets','procedures':len(seen-missing),'unresolved_callees':sorted(missing),'duplicate_definitions':duplicates,'review_findings':findings,'unmodeled':unknown}
 if a.report:a.report.write_text(json.dumps(report,indent=2)+'\n')
 print('REVIEW REQUIRED:',len(findings),'findings;',len(unknown),'unmodeled statements;',len(missing),'unresolved callees')
 return 2 if findings or unknown or missing or duplicates else 0
if __name__=='__main__':raise SystemExit(main())
