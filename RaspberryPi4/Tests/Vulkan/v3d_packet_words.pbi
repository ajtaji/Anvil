; SPDX-License-Identifier: MIT
; CPU-only exact packet bytes, partial overflow, first errors and record guards.
Global Dim NpwStorage.q[128]
Global Dim NpwPattern.a[16]
Procedure.i NpwRun()
  Protected base.i,buffer.i,row.i,n.i,width.i,align.i,remain.i,state.i,value.i,j.i,written.i,expected.i,errors.i,rc.i,kind.i,count.i,attrs.i,record.i,bytes.i,packetBytes.i
  For j=0 To 16383 Step 8 : PokeI($E1C00000+j,0) : Next
  PokeI($E1C00000,$56505731) : PokeI($E1C00008,1)
  buffer=@NpwStorage[0]
  For kind=0 To 1
    width=2+kind*2
    For align=0 To 3
      For remain=0 To 5
        For state=0 To 2
          For j=0 To 767 : PokeA(buffer+j,$A5) : Next
          base=buffer+16+align
          rc=V3dClBegin(base,256+8+remain) : v3d_clPos=8
          If state=1 : v3d_clOpen=0 : EndIf
          If state=2 : v3d_clErr=27 : EndIf
          value=$89ABCDEF
          If (align+remain)%3=1 : value=-1 : EndIf
          If (align+remain)%3=2 : value=$100000001 : EndIf
          If width=2
            NpwPattern[0]=107 : NpwPattern[1]=value & $FF : NpwPattern[2]=(value >> 8) & $FF
            NpwPattern[3]=$34 : NpwPattern[4]=$12 : NpwPattern[5]=$78 : NpwPattern[6]=$56 : NpwPattern[7]=$BC : NpwPattern[8]=$9A
            packetBytes=9 : V3dClClipWindow(value,$1234,$5678,$9ABC)
          Else
            NpwPattern[0]=104
            For j=0 To 3 : NpwPattern[j+1]=(value >> (j*8)) & $FF : Next
            packetBytes=5 : V3dClPointSize(value)
          EndIf
          written=packetBytes : If remain<written : written=remain : EndIf
          If state<>0 : written=0 : EndIf
          errors=0
          For j=0 To 767
            expected=$A5
            If j>=24+align And j<24+align+written : expected=NpwPattern[j-24-align] : EndIf
            If PeekA(buffer+j)<>expected : errors=errors+1 : EndIf
          Next
          row=$E1C00080+n*80
          PokeI(row,width) : PokeI(row+8,align) : PokeI(row+16,remain) : PokeI(row+24,state)
          PokeI(row+32,rc) : PokeI(row+40,v3d_clPos) : PokeI(row+48,v3d_clErr) : PokeI(row+56,errors)
          For j=0 To 15 : PokeA(row+64+j,PeekA(base+8+j)) : Next
          n=n+1
        Next
      Next
    Next
  Next
  ; Full public 16-bit-field packet at every destination alignment.
  For align=0 To 3
    For j=0 To 767 : PokeA(buffer+j,$A5) : Next
    base=buffer+16+align : rc=V3dClBegin(base,256+17) : v3d_clPos=8
    NpwPattern[0]=107 : NpwPattern[1]=$EF : NpwPattern[2]=$CD : NpwPattern[3]=$34 : NpwPattern[4]=$12
    NpwPattern[5]=$78 : NpwPattern[6]=$56 : NpwPattern[7]=$BC : NpwPattern[8]=$9A
    V3dClClipWindow($89ABCDEF,$1234,$5678,$9ABC)
    errors=0
    For j=0 To 767
      expected=$A5
      If j>=24+align And j<33+align : expected=NpwPattern[j-24-align] : EndIf
      If PeekA(buffer+j)<>expected : errors=errors+1 : EndIf
    Next
    row=$E1C00080+n*80
    PokeI(row,100) : PokeI(row+8,align) : PokeI(row+16,9)
    PokeI(row+32,rc) : PokeI(row+40,v3d_clPos) : PokeI(row+48,v3d_clErr) : PokeI(row+56,errors)
    For j=0 To 15 : PokeA(row+64+j,PeekA(base+8+j)) : Next
    n=n+1
  Next
  ; Every zeroed byte, including partial-stage records; invalid requests
  ; must leave all storage unchanged. The raw 608-byte image includes guards.
  For count=0 To 5
    For j=0 To 767 : PokeA(buffer+j,$A5) : Next
    base=buffer+63 : base=base-(base%32)
    attrs=1
    If count=1 : attrs=3 : EndIf
    If count=2 : attrs=31 : EndIf
    If count=3 : attrs=0 : EndIf
    If count=4 : attrs=32 : EndIf
    If count=5 : base=base+1 : EndIf
    rc=V3dShaderRecordBegin(base,attrs)
    If count=0 : V3dShaderRecordDefaults($12345678) : EndIf
    row=$E1C02EC0+count*640
    PokeI(row,attrs) : PokeI(row+8,base-buffer) : PokeI(row+16,rc) : PokeI(row+24,v3d_shrecOk)
    For j=0 To 607 : PokeA(row+32+j,PeekA(buffer+j)) : Next
  Next
  PokeI($E1C00010,n) : PokeI($E1C00018,6)
  ProcedureReturn 0
EndProcedure
