; Versioned handoff owned by Anvil/Kernel/Zentaji/startup.zen.
; r1=device table, r2=boot source, r3=context, r4..r15=0; SP/EVEC are owned.
; The context lives in the loaded image and remains valid for the monitor's life.
#ZEN_BOOT_MAGIC = $4E455A4C49564E41
#ZEN_BOOT_BYTES = 128
#ZEN_BOOT_TABLE = 24
#ZEN_BOOT_SOURCE = 32
#ZEN_BOOT_RAM = 40
#ZEN_BOOT_LOADER_SP = 48
#ZEN_BOOT_STACK_BOTTOM = 56
#ZEN_BOOT_STACK_TOP = 64
#ZEN_BOOT_VECTORS = 72
#ZEN_BOOT_ENTRY = 80
#ZEN_BOOT_STATUS = 88
#ZEN_BOOT_LOAD = 96
#ZEN_BOOT_IMAGE_END = 104
#ZEN_BOOT_STACK_BYTES = 112
#ZEN_BOOT_PAYLOAD_CALL = 120

Procedure.i ZentajiBootContextValid(context.i)
  Protected ram.i,top.i,bottom.i,first.i,last.i,vec.i,version.i,call.i
  ram=PeekQ($FFFF000000010018)
  If context<0 Or (context&15)<>0 Or ram<$200000 Or context>ram-$100000-#ZEN_BOOT_BYTES : ProcedureReturn 0 : EndIf
  version=PeekQ(context+8)
  If PeekQ(context)<>#ZEN_BOOT_MAGIC Or (version<>1 And version<>2) Or PeekQ(context+16)<>#ZEN_BOOT_BYTES : ProcedureReturn 0 : EndIf
  If PeekQ(context+#ZEN_BOOT_TABLE)<>$FFFF000000010000 Or PeekQ(context+#ZEN_BOOT_RAM)<>ram Or PeekQ(context+#ZEN_BOOT_STATUS)<>0 : ProcedureReturn 0 : EndIf
  top=(ram&-16)-$100000 : bottom=top-PeekQ(context+#ZEN_BOOT_STACK_BYTES)
  first=PeekQ(context+#ZEN_BOOT_LOAD) : last=PeekQ(context+#ZEN_BOOT_IMAGE_END) : vec=PeekQ(context+#ZEN_BOOT_VECTORS)
  If PeekQ(context+#ZEN_BOOT_SOURCE)<>PeekA($FFFF000000010023) : ProcedureReturn 0 : EndIf
  If PeekQ(context+#ZEN_BOOT_STACK_BYTES)<16384 Or PeekQ(context+#ZEN_BOOT_STACK_BYTES)>1048576 : ProcedureReturn 0 : EndIf
  If PeekQ(context+#ZEN_BOOT_STACK_TOP)<>top Or PeekQ(context+#ZEN_BOOT_STACK_BOTTOM)<>bottom Or (bottom&15)<>0 : ProcedureReturn 0 : EndIf
  If first<0 Or first>=last Or last>bottom Or context<first Or context+128>last : ProcedureReturn 0 : EndIf
  If vec<first Or (vec&4095)<>0 Or vec>last-4096 : ProcedureReturn 0 : EndIf
  If PeekQ(context+#ZEN_BOOT_ENTRY)<first Or PeekQ(context+#ZEN_BOOT_ENTRY)>=vec Or (PeekQ(context+#ZEN_BOOT_ENTRY)&7)<>0 : ProcedureReturn 0 : EndIf
  call=PeekQ(context+#ZEN_BOOT_PAYLOAD_CALL)
  If version=1
    If call<>0 : ProcedureReturn 0 : EndIf
  Else
    If (call&7)<>0 Or call<vec+4096 Or call>=context : ProcedureReturn 0 : EndIf
  EndIf
  ProcedureReturn 1
EndProcedure
