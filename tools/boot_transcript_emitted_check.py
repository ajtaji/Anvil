from __future__ import annotations
import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import tcp_multiif_emitted_check as emitted

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "Anvil" / "Core" / "boot_transcript.pbi"
FIXTURE = ROOT / "RaspberryPi4" / "Tests" / "boot_transcript_emitted_gate.pi4"

def fixture(core: str) -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    marker = "; @@PRODUCTION_BOOT_TRANSCRIPT@@"
    if text.count(marker) != 1:
        raise SystemExit("boot transcript gate: fixture marker drifted")
    return text.replace(marker, core)

def build(pmfc: Path, work: Path, text: str, stem: str) -> Path:
    staged = work / pmfc.name
    if not staged.exists(): shutil.copy2(pmfc, staged)
    if (ROOT / "Boards").is_dir() and not (work / "Boards").exists(): shutil.copytree(ROOT / "Boards", work / "Boards")
    src = work / f"{stem}.pi4"; src.write_text(text, encoding="utf-8", newline="\n")
    image = work / f"{stem}.img"
    run = subprocess.run([str(staged), str(src), "-t", "pi4", "--load-addr", hex(emitted.LOAD), "--stack-addr", hex(emitted.STACK), "--entry-returns", "-o", str(image), "-s"], cwd=ROOT, env={**os.environ, "PMF_ROOT": str(ROOT)}, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if run.returncode or "pmfc: OK" not in run.stdout:
        raise SystemExit(f"boot transcript gate: {stem} compile failed\n{run.stdout}")
    return image

def mutate_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1: raise SystemExit(f"boot transcript gate: {label} site count {text.count(old)}")
    return text.replace(old, new, 1)

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--pmfc",default=os.environ.get("PMFC")); p.add_argument("--interp",default=os.environ.get("PMF_A64_INTERP")); a=p.parse_args()
    pmfc=emitted.required_path(a.pmfc,"PMFC"); interp=emitted.required_path(a.interp,"PMF_A64_INTERP"); a64=emitted.load_interpreter(interp)
    core=CORE.read_text(encoding="utf-8")
    mutations=(
        ("missing store", "  gBootTranscript[gBootTranscriptCount] = c & $FF", "  ; store removed"),
        ("missing overflow count", "    gBootTranscriptLost = gBootTranscriptLost + 1", "    ; overflow count removed"),
        ("stop clears retained prefix", "  gBootTranscriptActive = 0\n  ProcedureReturn gBootTranscriptCount", "  gBootTranscriptActive = 0\n  gBootTranscriptCount = 0\n  ProcedureReturn gBootTranscriptCount"),
        ("replay drops the last byte", "  If index < 0 Or index >= gBootTranscriptCount", "  If index < 0 Or index >= gBootTranscriptCount - 1"),
        ("start keeps the previous epoch's overflow", "  gBootTranscriptLost = 0\n  gBootTranscriptActive = 0", "  gBootTranscriptActive = 0"),
    )
    with tempfile.TemporaryDirectory(prefix="anvil-boot-transcript-") as td:
        work=Path(td); result,steps=emitted.execute(a64,build(pmfc,work,fixture(core),"boot_transcript_gate"))
        if result: print(f"boot_transcript_emitted_check: FAIL assertion {result} after {steps:,} A64 instructions"); return 1
        killed=[]
        for i,(label,old,new) in enumerate(mutations,1):
            mutant=mutate_once(core,old,new,label); r,used=emitted.execute(a64,build(pmfc,work,fixture(mutant),f"boot_transcript_mutant_{i}"))
            if r==0: print(f"boot_transcript_emitted_check: FAIL {label} mutant survived"); return 1
            killed.append(f"{label}:{r}")
    print(f"boot_transcript_emitted_check: PASS - 18 assertions, {steps:,} A64 instructions; 5 mutants rejected ({', '.join(killed)})")
    return 0
if __name__ == "__main__": sys.exit(main())
