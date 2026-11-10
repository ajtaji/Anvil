; Typed shader IR -> native Zentaji shader instructions.\n; SPDX-License-Identifier: MIT
; Requires vk_ir.pbi. This is a compiler, not a pixel renderer: the native GPU
; executes the published code on its isolated shader context. There is no CPU
; rasterisation or shader fallback. No Vulkan capability is enabled by this file.
; Encoding the machine ISA is required because the GPU accepts native entry
; addresses, while typed IR is passive data. This introduces no timing claim.
;
; ABI: r1 vertex index, r4 instance index, r3 pinned draw metadata. Metadata
; qwords 0/1 are push/UBO pointers; qwords 4..19 are vertex binding bases.
; r8..r10 are address temporaries, r16..r239 hold immutable scalar SSA lanes.
; r254 is the GPU return sentinel. v0 is clip position / fragment RGBA;
; v1..v15 carry vertex locations 0..14 into interpolated fragment inputs.
; Each lane is the exact float32 bit pattern, without host float conversion.
;
; Method: verify the complete typed module, resolve declared locations and
; block-member offsets, then emit straight-line instructions into private
; scratch. Composite operations alias immutable scalar registers. Actual
; arithmetic uses the machine's separately rounded float32 instructions.
; Only a completely accepted module publishes bytes. Register/code exhaustion
; and unsupported operations leave destination bytes unchanged.
;
; Instruction encodings follow tools/zentaji/opcodes.py R/I/M/B/V formats.
; LIQ is two words (instruction, exact bits). Loads address pinned input data.
; ADD/MUL compute vertex addresses from the invocation index and binding plan.
; VEXT reads interpolated input lanes; VINS publishes result lanes. JR r254
; returns to the GPU. Every emitted instruction group below states its purpose.
XIncludeFile "Anvil/Graphics/Vulkan/vk_ir.pbi"
#AVK_ZEN_SHADER_CODE_BYTES=65536
#AVK_ZEN_SHADER_ERR_ARGS=-23701
#AVK_ZEN_SHADER_ERR_IR=-23702
#AVK_ZEN_SHADER_ERR_UNSUPPORTED=-23703
#AVK_ZEN_SHADER_ERR_SPACE=-23704
#AVK_ZEN_SHADER_ERR_LAYOUT=-23705
Structure AvkZenShaderAttribute Align #PB_Structure_AlignC
 location.i : binding.i : offset.i : stride.i : components.i : instanceRate.i
EndStructure
Structure AvkZenShaderTarget Align #PB_Structure_AlignC
 code.i : capacity.i : attributeCount.i : attributes.i
 invertY.i ; 1 adapts positive-height Vulkan viewport Y to native scanout Y
EndStructure
Structure AvkZenShaderResult Align #PB_Structure_AlignC
 codeBytes.i : registers.i : varyingCount.i
 pushBytes.i : uniformBytes.i : uniformBinding.i
EndStructure
Global Dim avkZsCode.q[#AVK_ZEN_SHADER_CODE_BYTES/8]
Global Dim avkZsReg.i[(#ANVIL_IR_MAX_ID+1)*4]
Global avkZsWords.i,avkZsNext.i,avkZsError.i,avkZsRoot.i,avkZsMember.i,avkZsVarying.i,avkZsPrimary.i
Global avkZsPushBytes.i,avkZsUniformBytes.i,avkZsUniformVariable.i,avkZsUniformBinding.i

Procedure.i avkZsFail(code.i)
 If avkZsError=0 : avkZsError=code : EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i avkZsEmit(word.q)
 If avkZsError<>0 : ProcedureReturn 0 : EndIf
 If avkZsWords>=#AVK_ZEN_SHADER_CODE_BYTES/8 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_SPACE) : EndIf
 avkZsCode[avkZsWords]=word : avkZsWords=avkZsWords+1
 ProcedureReturn 1
EndProcedure
Procedure.i avkZsAllocate()
 If avkZsNext>239 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_SPACE) : EndIf
 avkZsNext=avkZsNext+1 : ProcedureReturn avkZsNext-1
EndProcedure
Procedure avkZsLiteral(reg.i,bits.q)
 ; LIQ loads exact low float32 bits: no decimal conversion, NaN canonicalisation
 ; or intermediate precision is introduced by the shader compiler.
 avkZsEmit($34|(reg<<8)) : avkZsEmit(bits&$FFFFFFFF)
EndProcedure
Procedure avkZsLoad(op.i,reg.i,base.i,offset.i)
 ; M-format: data, base, zero index, zero writeback, signed byte displacement.
 avkZsEmit(op|(reg<<8)|(base<<16)|((offset&$FFFFFF)<<40))
EndProcedure
Procedure avkZsBinary(op.i,to.i,a.i,b.i)
 ; R-format, untransformed operands, no integer overflow traps; float32
 ; arithmetic opcodes carry their own precision and use the GPU reset FP mode.
 avkZsEmit(op|(to<<8)|(a<<16)|(b<<24))
EndProcedure
Procedure.i avkZsDecoration(*m.AvkIrModule,variable.i,member.i,kind.i)
 Protected *v.AvkIrVariable,*t.AvkIrType,*d.AvkIrDecoration,owner.i=variable,n.i
 If member>=0
  *v=avkIrFindVariable(*m,variable)
  If *v=0 : ProcedureReturn -1 : EndIf
  *t=avkIrFindType(*m,*v\pointerType)
  If *t=0 : ProcedureReturn -1 : EndIf
  owner=*t\pointeeType
 EndIf
 For n=0 To *m\decorationCount-1
  *d=avkIrDecorationAt(*m,n)
  If *d\sourceId=owner And *d\member=member And *d\kind=kind : ProcedureReturn *d\value : EndIf
 Next
 ProcedureReturn -1
EndProcedure
Procedure.i avkZsPointer(*m.AvkIrModule,id.i)
 Protected *v.AvkIrVariable,*n.AvkIrNode,*c.AvkIrConstant
 avkZsMember=-1 : *v=avkIrFindVariable(*m,id)
 If *v<>0 : avkZsRoot=id : ProcedureReturn *v : EndIf
 *n=avkIrFindNode(*m,id)
 If *n=0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
 If *n\kind<>#ANVIL_IR_OP_ACCESS_CHAIN : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
 *v=avkIrFindVariable(*m,*n\operand0) : *c=avkIrFindConstant(*m,*n\operand1)
 If *v=0 Or *c=0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
 avkZsRoot=*n\operand0 : avkZsMember=*c\word0
 ProcedureReturn *v
EndProcedure
Procedure.i avkZsConstantComponent(*c.AvkIrConstant,lane.i)
 Select lane
  Case 0 : ProcedureReturn *c\component0
  Case 1 : ProcedureReturn *c\component1
  Case 2 : ProcedureReturn *c\component2
  Case 3 : ProcedureReturn *c\component3
 EndSelect
 ProcedureReturn 0
EndProcedure
Procedure.i avkZsScalarConstant(*m.AvkIrModule,id.i)
 Protected *c.AvkIrConstant,reg.i
 If id<1 Or id>#ANVIL_IR_MAX_ID : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_IR) : EndIf
 If avkZsReg[id*4]<>0 : ProcedureReturn avkZsReg[id*4] : EndIf
 *c=avkIrFindConstant(*m,id)
 If *c=0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
 If *c\componentCount<>0 Or avkIrFloatLanes(*m,*c\typeId)<>1 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
 reg=avkZsAllocate() : avkZsLiteral(reg,*c\word0)
 avkZsReg[id*4]=reg
 ProcedureReturn reg
EndProcedure
Procedure.i avkZsValue(*m.AvkIrModule,id.i,lane.i)
 Protected *c.AvkIrConstant,count.i,reg.i,n.i,component.i
 If id<1 Or id>#ANVIL_IR_MAX_ID Or lane<0 Or lane>3 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_IR) : EndIf
 If avkZsReg[id*4+lane]<>0 : ProcedureReturn avkZsReg[id*4+lane] : EndIf
 *c=avkIrFindConstant(*m,id)
 If *c=0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
 count=avkIrFloatLanes(*m,*c\typeId)
 If count<1 Or lane>=count : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
 If *c\componentCount=0
  avkZsReg[id*4]=avkZsScalarConstant(*m,id)
 Else
  For n=0 To count-1
   component=avkZsConstantComponent(*c,n)
   avkZsReg[id*4+n]=avkZsScalarConstant(*m,component)
  Next
 EndIf
 ProcedureReturn avkZsReg[id*4+lane]
EndProcedure
Procedure.i avkZsInput(*m.AvkIrModule,*target.AvkZenShaderTarget,*node.AvkIrNode)
 Protected *v.AvkIrVariable,*a.AvkZenShaderAttribute,*found.AvkZenShaderAttribute
 Protected count.i,location.i,offset.i,n.i,reg.i,index.i
 *v=avkZsPointer(*m,*node\operand0)
 If *v=0 : ProcedureReturn 0 : EndIf
 count=avkIrFloatLanes(*m,*node\resultType)
 If count<1 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
 If *v\storageClass=#ANVIL_IR_STORAGE_INPUT
  location=avkZsDecoration(*m,avkZsRoot,avkZsMember,#ANVIL_IR_DEC_LOCATION)
  If location<0 Or location>14 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
  If *m\stage=#ANVIL_IR_STAGE_VERTEX
   For n=0 To *target\attributeCount-1
    *a=*target\attributes+n*SizeOf(AvkZenShaderAttribute)
    If *a\location=location : *found=*a : EndIf
   Next
   If *found=0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
   If *found\components<>count : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
   ; Fetch this binding's base from immutable draw metadata. Multiply the
   ; invocation's vertex/instance index by the declared stride, then add base.
   avkZsLoad($5E,8,3,32+*found\binding*8)
   avkZsLiteral(9,*found\stride)
   index=1 : If *found\instanceRate<>0 : index=4 : EndIf
   avkZsBinary($1D,9,index,9) : avkZsBinary($10,8,8,9)
   For n=0 To count-1
    reg=avkZsAllocate() : avkZsLoad($5C,reg,8,*found\offset+n*4)
    avkZsReg[*node\sourceId*4+n]=reg
   Next
  Else
   ; The GPU interpolates vertex location L in v(L+1). VEXT.f32 reads the
   ; exact lane bits into a scalar SSA register, without a float conversion.
   For n=0 To count-1
    reg=avkZsAllocate()
    avkZsEmit($D3|(reg<<8)|((location+1)<<16)|(n<<32)|(10<<40))
    avkZsReg[*node\sourceId*4+n]=reg
   Next
  EndIf
 ElseIf *v\storageClass=#ANVIL_IR_STORAGE_PUSH_CONSTANT Or *v\storageClass=#ANVIL_IR_STORAGE_UNIFORM
  If avkZsMember<0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
  offset=avkZsDecoration(*m,avkZsRoot,avkZsMember,#ANVIL_IR_DEC_OFFSET)
  If offset<0 Or offset>65520 Or (offset&3)<>0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
  ; qword 0 names the live push block, qword 1 the live uniform block.
  ; Their exact extents are validated by the submitting resource owner.
  index=0
  If *v\storageClass=#ANVIL_IR_STORAGE_UNIFORM
   index=8
   If avkZsUniformVariable<>0 And avkZsUniformVariable<>avkZsRoot : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
   avkZsUniformBinding=avkZsDecoration(*m,avkZsRoot,-1,#ANVIL_IR_DEC_BINDING)
   If avkZsUniformBinding<0 Or avkZsDecoration(*m,avkZsRoot,-1,#ANVIL_IR_DEC_DESCRIPTOR_SET)<>0 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
   avkZsUniformVariable=avkZsRoot
   If offset+count*4>avkZsUniformBytes : avkZsUniformBytes=offset+count*4 : EndIf
  Else
   If offset+count*4>avkZsPushBytes : avkZsPushBytes=offset+count*4 : EndIf
  EndIf
  avkZsLoad($5E,8,3,index)
  For n=0 To count-1
   reg=avkZsAllocate() : avkZsLoad($5C,reg,8,offset+n*4)
   avkZsReg[*node\sourceId*4+n]=reg
  Next
 Else
  ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED)
 EndIf
 ProcedureReturn Bool(avkZsError=0)
EndProcedure
Procedure.i avkZsOutput(*m.AvkIrModule,*node.AvkIrNode,invertY.i)
 Protected *v.AvkIrVariable,slot.i,location.i,builtin.i,count.i,n.i,reg.i
 *v=avkZsPointer(*m,*node\operand0)
 If *v=0 : ProcedureReturn 0 : EndIf
 If *v\storageClass<>#ANVIL_IR_STORAGE_OUTPUT : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
 count=avkIrFloatLanes(*m,avkIrValueType(*m,*node\operand1))
 If count<1 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED) : EndIf
 builtin=avkZsDecoration(*m,avkZsRoot,avkZsMember,#ANVIL_IR_DEC_BUILTIN)
 location=avkZsDecoration(*m,avkZsRoot,avkZsMember,#ANVIL_IR_DEC_LOCATION)
 If *m\stage=#ANVIL_IR_STAGE_VERTEX
  If builtin=#ANVIL_IR_BUILTIN_POSITION
   If count<>4 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
   slot=0 : avkZsPrimary=1
  Else
   If location<0 Or location>14 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
   slot=location+1 : If slot>avkZsVarying : avkZsVarying=slot : EndIf
  EndIf
 Else
  If location<>0 Or builtin<>-1 Or count<>4 : ProcedureReturn avkZsFail(#AVK_ZEN_SHADER_ERR_LAYOUT) : EndIf
  slot=0 : avkZsPrimary=1
 EndIf
 For n=0 To count-1
  reg=avkZsValue(*m,*node\operand1,n)
  If *m\stage=#ANVIL_IR_STAGE_VERTEX And slot=0 And n=1 And invertY<>0
   ; Native window Y is (1-y/w)*height/2; Vulkan with positive viewport
   ; height needs (1+y/w)*height/2. Flip only the published clip Y, keeping
   ; the SSA source immutable. FSGN.NEG.S toggles the float32 sign bit and
   ; preserves signed zero and NaN payloads; subtraction from zero does not.
   avkZsEmit($AE|(10<<8)|(reg<<16)|(1<<40)|(1<<56)) : reg=10
  EndIf
  ; VINS.f32 writes exactly one result lane. Remaining vector lanes stay
  ; zero from the GPU's per-invocation reset, never from stale shader state.
  avkZsEmit($D2|(slot<<8)|(reg<<16)|(n<<32)|(10<<40))
 Next
 ProcedureReturn Bool(avkZsError=0)
EndProcedure
Procedure.i AnvilVkZentajiShaderCompile(*m.AvkIrModule,*target.AvkZenShaderTarget,*out.AvkZenShaderResult)
 Protected n.i,k.i,lanes.i,a.i,b.i,reg.i,op.i,ram.i=PeekQ($FFFF000000010018)
 Protected *node.AvkIrNode,*attr.AvkZenShaderAttribute,*other.AvkZenShaderAttribute
 If *m=0 Or *target=0 Or *out=0 : ProcedureReturn #AVK_ZEN_SHADER_ERR_ARGS : EndIf
 If *target\invertY<>0 And *target\invertY<>1 : ProcedureReturn #AVK_ZEN_SHADER_ERR_ARGS : EndIf
 If *target\code<1 Or (*target\code&7)<>0 Or *target\capacity<8 Or *target\capacity>ram Or *target\code>ram-*target\capacity : ProcedureReturn #AVK_ZEN_SHADER_ERR_ARGS : EndIf
 If *target\code<@avkZsCode[0]+#AVK_ZEN_SHADER_CODE_BYTES+8 And *target\code+*target\capacity>@avkZsCode[0] : ProcedureReturn #AVK_ZEN_SHADER_ERR_ARGS : EndIf
 If *target\attributeCount<0 Or *target\attributeCount>16 Or (*target\attributeCount>0 And *target\attributes=0) : ProcedureReturn #AVK_ZEN_SHADER_ERR_ARGS : EndIf
 If AnvilVkIrVerify(*m)<>#ANVIL_IR_OK : ProcedureReturn #AVK_ZEN_SHADER_ERR_IR : EndIf
 For n=0 To *target\attributeCount-1
  *attr=*target\attributes+n*SizeOf(AvkZenShaderAttribute)
  If *attr\location<0 Or *attr\location>14 Or *attr\binding<0 Or *attr\binding>15 Or *attr\components<1 Or *attr\components>4 Or *attr\offset<0 Or *attr\stride<1 Or *attr\stride>65535 Or *attr\offset>*attr\stride-*attr\components*4 Or (*attr\instanceRate<>0 And *attr\instanceRate<>1) : ProcedureReturn #AVK_ZEN_SHADER_ERR_LAYOUT : EndIf
  For k=0 To n-1
   *other=*target\attributes+k*SizeOf(AvkZenShaderAttribute)
   If *other\location=*attr\location : ProcedureReturn #AVK_ZEN_SHADER_ERR_LAYOUT : EndIf
   If *other\binding=*attr\binding And (*other\stride<>*attr\stride Or *other\instanceRate<>*attr\instanceRate) : ProcedureReturn #AVK_ZEN_SHADER_ERR_LAYOUT : EndIf
  Next
 Next
 avkZsPushBytes=0 : avkZsUniformBytes=0 : avkZsUniformVariable=0 : avkZsUniformBinding=-1
 avkZsWords=0 : avkZsNext=16 : avkZsError=0 : avkZsVarying=0 : avkZsPrimary=0
 For n=0 To #ANVIL_IR_MAX_ID
  For k=0 To 3 : avkZsReg[n*4+k]=0 : Next
 Next
 For n=0 To *m\nodeCount-1
  *node=avkIrNodeAt(*m,n)
  Select *node\kind
   Case #ANVIL_IR_OP_LOAD
    avkZsInput(*m,*target,*node)
   Case #ANVIL_IR_OP_ACCESS_CHAIN
    ; Verified compile-time pointer provenance; emit no machine instruction.
   Case #ANVIL_IR_OP_COMPOSITE_EXTRACT
    avkZsReg[*node\sourceId*4]=avkZsValue(*m,*node\operand0,*node\literal0)
   Case #ANVIL_IR_OP_COMPOSITE_CONSTRUCT
    For k=0 To *node\operandCount-1 : avkZsReg[*node\sourceId*4+k]=avkZsValue(*m,avkIrOperand(*node,k),0) : Next
   Case #ANVIL_IR_OP_FADD,#ANVIL_IR_OP_FSUB,#ANVIL_IR_OP_FMUL
    lanes=avkIrFloatLanes(*m,*node\resultType)
    op=$A6 : If *node\kind=#ANVIL_IR_OP_FSUB : op=$A7 : EndIf
    If *node\kind=#ANVIL_IR_OP_FMUL : op=$A8 : EndIf
    For k=0 To lanes-1
     a=avkZsValue(*m,*node\operand0,k) : b=avkZsValue(*m,*node\operand1,k) : reg=avkZsAllocate()
     avkZsBinary(op,reg,a,b) : avkZsReg[*node\sourceId*4+k]=reg
    Next
   Case #ANVIL_IR_OP_STORE
    avkZsOutput(*m,*node,*target\invertY)
   Case #ANVIL_IR_OP_RETURN
    ; B-format JR uses ra in byte 1. The GPU owns the sentinel in r254.
    avkZsEmit($9C|(254<<8))
   Default
    avkZsFail(#AVK_ZEN_SHADER_ERR_UNSUPPORTED)
  EndSelect
  If avkZsError<>0 : ProcedureReturn avkZsError : EndIf
 Next
 If avkZsPrimary=0 : ProcedureReturn #AVK_ZEN_SHADER_ERR_LAYOUT : EndIf
 If avkZsWords>*target\capacity/8 : ProcedureReturn #AVK_ZEN_SHADER_ERR_SPACE : EndIf
 For n=0 To avkZsWords-1 : PokeQ(*target\code+n*8,avkZsCode[n]) : Next
 *out\pushBytes=avkZsPushBytes : *out\uniformBytes=avkZsUniformBytes : *out\uniformBinding=avkZsUniformBinding
 *out\codeBytes=avkZsWords*8 : *out\registers=avkZsNext-16 : *out\varyingCount=avkZsVarying
 ProcedureReturn 0
EndProcedure
