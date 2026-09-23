from __future__ import annotations
import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "Anvil" / "Core" / "settings.pbi"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "settings_wifi_revision_emitted_gate.pi4"

def source(settings: str) -> str:
    template = FIXTURE.read_text(encoding="utf-8")
    marker = "; @@PRODUCTION_SETTINGS@@"
    if template.count(marker) != 1:
        raise SystemExit("settings wifi revision gate: fixture marker is not unique")
    return template.replace(marker, settings)

def build(compiler: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / compiler.name
    if not staged.exists(): shutil.copy2(compiler, staged)
    if (ROOT / "Boards").is_dir() and not (work / "Boards").exists(): shutil.copytree(ROOT / "Boards", work / "Boards")
    probe = work / f"{stem}.pi4"; probe.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    run = subprocess.run([str(staged), "--compile", str(probe), "-t", "pi4", "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK), "--entry-returns", "-o", str(image), "-s"], cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)}, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout: raise SystemExit(f"settings wifi revision gate: {stem} compile failed\n{run.stdout}")
    return image

def mutate_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1: raise SystemExit(f"settings wifi revision gate: {label} site count {text.count(old)}")
    return text.replace(old, new, 1)

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--compiler",default=os.environ.get("PMF_COMPILER")); p.add_argument("--interp",default=os.environ.get("PMF_A64_INTERP")); a=p.parse_args()
    compiler=emitted.required_path(a.compiler,"PMF_COMPILER"); interp=emitted.required_path(a.interp,"PMF_A64_INTERP"); a64=emitted.load_interpreter(interp)
    settings=SETTINGS.read_text(encoding="utf-8"); exact=source(settings)
    mutations=(
      ("PMK misclassification", 'If *key = 0 : ProcedureReturn 0 : EndIf', 'If *key = 0 : ProcedureReturn 0 : EndIf\n  If set_Contains(*key, "pmk.secret") <> 0 : ProcedureReturn 1 : EndIf'),
      ("identical setter", 'If same = 0 And set_WifiSelectionKey(@set_wantKey[0]) <> 0', 'If set_WifiSelectionKey(@set_wantKey[0]) <> 0'),
      ("parse coalescing", '  set_WifiBatchBegin()\n  SettingsReset()', '  SettingsReset()'),
      ("partial batch close", '      set_loadState = 2\n      set_WifiBatchEnd()', '      set_loadState = 2'),
      ("discard misclassification", 'Procedure SettingsDiscardLoad()\n  If set_loadState = 2', 'Procedure SettingsDiscardLoad()\n  set_WifiChanged()\n  If set_loadState = 2'),
      ("no-file reset ownership", '      set_WifiBatchBegin()\n      SettingsReset()\n      set_WifiBatchEnd()', '      set_WifiBatchBegin()\n      ; no-file credential reset removed\n      set_WifiBatchEnd()'),
    )
    with tempfile.TemporaryDirectory(prefix="anvil-settings-wifi-revision-") as td:
      work=Path(td); result,steps=emitted.execute(a64,build(compiler,work,exact,"settings_wifi_revision_gate"))
      if result: print(f"settings_wifi_revision_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions"); return 1
      mutant_steps=0
      for i,(label,old,new) in enumerate(mutations,1):
        m=mutate_once(settings,old,new,label); result,used=emitted.execute(a64,build(compiler,work,source(m),f"settings_wifi_revision_mutant_{i}")); mutant_steps+=used
        if result==0: print(f"settings_wifi_revision_emitted_check: FAIL {label} mutant survived"); return 1
    print(f"settings_wifi_revision_emitted_check: PASS - 20 assertions, {steps:,} A64 instructions; {len(mutations)} assertion-failing mutants rejected ({mutant_steps:,} mutant instructions)")
    return 0
if __name__ == "__main__": sys.exit(main())
