; SPDX-License-Identifier: MIT
; Pure bounded caller-memory list. No renderer or device is owned here.
XIncludeFile "Anvil/Graphics/neon_particle_types.pbi"
Structure NeonParticleList Align #PB_Structure_AlignC
  data.i : bytes.i : capacity.i : count.i
EndStructure
Procedure.i NeonParticleListConfigure(*list.NeonParticleList,data.i,bytes.i,capacity.i)
  If *list=0 Or (*list & 7)<>0 Or data<1 Or (data & 3)<>0 Or capacity<1 Or capacity>#NEON_PARTICLE_MAX Or bytes<capacity*32 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  If data>$7FFFFFFFFFFFFFFF-bytes Or *list>$7FFFFFFFFFFFFFFF-32 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  If *list<data+bytes And data<*list+32 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  *list\data=data : *list\bytes=bytes : *list\capacity=capacity : *list\count=0
  ProcedureReturn 0
EndProcedure
Procedure.i NeonParticleListClear(*list.NeonParticleList)
  If *list=0 Or (*list & 7)<>0 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  If *list\data<1 Or *list\capacity<1 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  *list\count=0 : ProcedureReturn 0
EndProcedure
Procedure.i NeonParticleListAdd(*list.NeonParticleList,x.f,y.f,size.f,angle.f,r.f,g.f,b.f,a.f)
  Protected item.NeonParticleRecord,*out.NeonParticleRecord
  If *list=0 Or (*list & 7)<>0 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  If *list\data<1 Or (*list\data & 3)<>0 Or *list\capacity<1 Or *list\capacity>#NEON_PARTICLE_MAX Or *list\bytes<*list\capacity*32 Or *list\count<0 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  If *list\data>$7FFFFFFFFFFFFFFF-*list\bytes : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  If *list\count>=*list\capacity : ProcedureReturn #NEON_PARTICLE_ERR_CAPACITY : EndIf
  item\x=x : item\y=y : item\size=size : item\angle=angle : item\r=r : item\g=g : item\b=b : item\a=a
  If NeonParticleRecordValid(@item)=0 : ProcedureReturn #NEON_PARTICLE_ERR_ARGS : EndIf
  *out=*list\data+*list\count*32
  *out\x=x : *out\y=y : *out\size=size : *out\angle=angle : *out\r=r : *out\g=g : *out\b=b : *out\a=a
  *list\count=*list\count+1 : ProcedureReturn 0
EndProcedure
