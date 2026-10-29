"""Public shared-metric inputs and expected observations, not renderer execution."""
import struct

def cases():
 lines=[];values=[];labels=[]
 def emit(s):lines.append(' '+s)
 def ck(expr,value):emit('MmCheck('+expr+','+str(value)+')');values.append(value);labels.append(expr)
 emit('mmMixed[0]=65 : mmMixed[1]=10 : mmMixed[2]=32 : mmMixed[3]=127 : mmMixed[4]=31 : mmMixed[5]=255 : mmMixed[6]=0')
 ck('Neon_TextWidth(0,0)',0);ck('Neon_TextWidth(0,@mmEmpty[0])',0);ck('Neon_LineHeight(0)',0)
 ck('NeonFontUse(@mmBits[0],8,12,32,32)',0)
 for font in range(4):emit(f'NeonFontSetup({font},{font+1},{font%2})')
 for font in (-1,0,1,2,3,4,99):
  scale=font+1 if 0<=font<=3 else 1
  ck(f'Neon_LineHeight({font})',12*scale);ck(f'Neon_TextWidth({font},@mmMixed[0])',24*scale)
  ck(f'Neon_CharWidth({font})',8*scale);ck(f'NeonBitmapLineHeight({font})',12*scale)
 emit('NeonFontSetup(1,0,0)');ck('Neon_LineHeight(1)',12);emit('NeonFontSetup(1,2,1)')
 ck('NeonMeasureBackendInstall(@MmWidth,@MmHeight)',15);ck('NeonMeasureBackendActive()',0)
 ck('MmInstallDraw()',0);ck('NeonMeasureBackendInstall(@MmWidth,@MmHeight)',0)
 emit('mmWidthRc=77 : mmHeightRc=27 : mmRevision=neon_fontRevision')
 ck('Neon_TextWidth(2,0)',0);ck('mmWidths',0)
 ck('Neon_TextWidth(2,@mmMixed[0])',77);ck('mmWidths',1);ck('mmFont',2);ck('MmSame(mmTextPointer,@mmMixed[0])',1)
 ck('Neon_LineHeight(2)',27);ck('mmHeights',1);ck('mmFont',2)
 for rc,expected in [(0,0),(-1,72),(-9,72),(4096,4096)]:
  emit('mmWidthRc='+str(rc));ck('Neon_TextWidth(2,@mmMixed[0])',expected)
 ck('mmWidths',5)
 for rc,expected in [(0,36),(-1,36),(-9,36),(1,1)]:
  emit('mmHeightRc='+str(rc));ck('Neon_LineHeight(2)',expected)
 ck('mmHeights',5);ck('MmSame(neon_fontRevision,mmRevision)',1);ck('Neon_Error()',15)
 ck('NeonMeasureBackendInstall(0,@MmHeight)',15);ck('NeonMeasureBackendActive()',1)
 emit('mmWidthRc=19');ck('Neon_TextWidth(2,@mmMixed[0])',19);ck('mmWidths',6)
 ck('NeonMeasureBackendInstall(0,0)',0);ck('NeonMeasureBackendActive()',0)
 ck('Neon_TextWidth(2,@mmMixed[0])',72);ck('Neon_LineHeight(2)',36);ck('mmWidths',6);ck('mmHeights',5)
 ck('NeonMeasureBackendInstall(@MmWidth,@MmHeight)',0);ck('MmInstallDraw()',0);ck('NeonMeasureBackendActive()',0)
 ck('Neon_TextWidth(2,@mmMixed[0])',72);ck('Neon_LineHeight(2)',36)
 emit('NeonDrawBackendClear()');ck('NeonDrawBackendActive()',0)
 emit('For i=0 To 4099 : mmLong[i]=65 : Next : mmLong[4100]=0')
 ck('Neon_TextWidth(0,@mmLong[0])',4097*8)
 emit('mmLong[4096]=0');ck('Neon_TextWidth(0,@mmLong[0])',4096*8)
 emit('mmLong[0]=0');ck('Neon_TextWidth(0,@mmLong[0])',0)
 ck('MmSame(neon_fontRevision,mmRevision)',1);ck('Neon_Error()',15)
 assert len(values)*16+64<4096
 return '\n'.join(lines),values,labels

def expected_report(chip=2711,unbounded_width=False):
 _,values,labels=cases();failed=[]
 if unbounded_width:
  failed=[i for i,(name,v) in enumerate(zip(labels,values)) if name=='Neon_TextWidth(0,@mmLong[0])' and v==4097*8]
  assert len(failed)==1;values=[4100*8 if i in failed else v for i,v in enumerate(values)]
 raw=struct.pack('<8q',0x4e4d5450,len(failed),chip,len(values),len(failed),1,0,0x50544d4e)
 raw+=b''.join(struct.pack('<2q',i+1,v) for i,v in enumerate(values))
 return raw+bytes(4096-len(raw))
