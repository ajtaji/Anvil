"""Run production CPU glyph/scroll procedures with real host RAM, no board."""
import argparse,pathlib,re,tempfile,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--purebasic',required=True);args=p.parse_args()
source=(root/'RaspberryPi3/Lib/framebuffer.pbi').read_text()
parts=[]
for name in ('Pi3FbPack','Pi3FbPixel','Pi3FbChar','Pi3FbNewline','Pi3FbLine'):
 parts.append(re.search(r'(?ms)^Procedure[^\n]*\b'+name+r'\(.*?^EndProcedure',source).group())
prefix='''OpenConsole()
Global pi3_fb.i,pi3_fb_pitch.i,pi3_fb_size.i,pi3_fb_column.i,pi3_fb_row.i,pi3_fb_pixel_order.i
Procedure Pi3MailboxBarrier()
EndProcedure
'''
checks='''
Define x.i,y.i,p.i
pi3_fb_pitch=2568 : pi3_fb_size=pi3_fb_pitch*480
pi3_fb=AllocateMemory(pi3_fb_size+16)
For y=0 To 479
 For x=0 To 639 : PokeL(pi3_fb+y*pi3_fb_pitch+x*4,y+1) : Next
 PokeQ(pi3_fb+y*pi3_fb_pitch+2560,$1122334455667788)
Next
PokeQ(pi3_fb+pi3_fb_size,$1234567890ABCDEF)
pi3_fb_row=19 : Pi3FbNewline()
If pi3_fb_row<>19 Or pi3_fb_column<>0 : End 1 : EndIf
For y=0 To 479
 For x=0 To 639
  If y<456
   If PeekL(pi3_fb+y*pi3_fb_pitch+x*4)<>y+25 : End 2 : EndIf
  Else
   If PeekL(pi3_fb+y*pi3_fb_pitch+x*4)<>$180C08 : End 3 : EndIf
  EndIf
 Next
 If PeekQ(pi3_fb+y*pi3_fb_pitch+2560)<>$1122334455667788 : End 4 : EndIf
Next
If PeekQ(pi3_fb+pi3_fb_size)<>$1234567890ABCDEF : End 5 : EndIf
If AnvilTextGlyph(65)<>$699F999 Or AnvilTextGlyph(126)<>$05A0000 : End 6 : EndIf
FillMemory(pi3_fb,pi3_fb_size,0)
Pi3FbChar(65,0,0)
If PeekL(pi3_fb)<>0 Or PeekL(pi3_fb+3*4)<>$F0E0C0 : End 7 : EndIf
If PeekL(pi3_fb+9*pi3_fb_pitch)<>$F0E0C0 : End 8 : EndIf
pi3_fb_row=0 : pi3_fb_column=41
Define text.s="AA"
Pi3FbLine(@text)
If pi3_fb_row<>2 Or pi3_fb_column<>0 : End 9 : EndIf
PrintN("PASS: full480row scroll pixels+padding+endguard, ASCII glyph/scaling and line wrapping")
'''
# PureBasic string literals are UTF-16 by default; byte span explicitly ASCII.
checks=checks.replace('Define text.s="AA"','Define text.i=AllocateMemory(3)\nPokeA(text,65) : PokeA(text+1,65)').replace('Pi3FbLine(@text)','Pi3FbLine(text)')
with tempfile.TemporaryDirectory(prefix='pi3-console-') as tmp:
 src=pathlib.Path(tmp)/'gate.pb';exe=pathlib.Path(tmp)/'gate.exe'
 src.write_text(prefix+(root/'Anvil/Graphics/text_glyph.pbi').read_text()+'\n'+'\n'.join(parts)+checks)
 r=subprocess.run([args.purebasic,str(src),'/EXE',str(exe)],capture_output=True,text=True)
 if r.returncode:raise SystemExit(r.stdout+r.stderr)
 r=subprocess.run([str(exe)],capture_output=True,text=True)
 print(r.stdout);raise SystemExit(r.returncode)
