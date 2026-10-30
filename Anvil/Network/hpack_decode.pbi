; Bounded HPACK decoder, independently implemented from RFC 7541 sections 4-6.
; https://www.rfc-editor.org/rfc/rfc7541.html
; Caller owns dynamic-table and field buffers. A complete, bounded field block
; is supplied to Begin; Next yields one field at a time, preserving table state.
; Output spans are opaque bytes, valid until Next. HTTP field rules are separate.
XIncludeFile "Anvil/Network/byte_order.pbi"
XIncludeFile "Anvil/Network/hpack_tables.pbi"
#HPACK_ARGUMENT=-3210
#HPACK_COMPRESSION=-3211
#HPACK_LIMIT=-3212
Structure HpackDecoder
 storage.i
 capacity.i
 maximum.i
 allowed.i
 required.i
 used.i
 size.i
 entries.i
 input.i
 bytes.i
 cursor.i
 output.i
 outputCapacity.i
 listLimit.i
 listSize.i
 fields.i
 updates.i
 active.i
 error.i
 name.i
 nameLength.i
 value.i
 valueLength.i
 sensitive.i
 stage.i
 insert.i
 pendingName.i
 stringEnd.i
 stringHuffman.i
 stringDestination.i
 stringCapacity.i
 stringWritten.i
 stringNode.i
 stringTail.i
 stringTailBits.i
EndStructure
Procedure.i hpFail(*d.HpackDecoder,error.i)
 *d\error=error : ProcedureReturn error
EndProcedure
Procedure.i HpackInit(*d.HpackDecoder,storage.i,capacity.i)
 Define i.i
 If *d=0 Or storage=0 Or capacity<4096 Or capacity>16384 : ProcedureReturn #HPACK_ARGUMENT : EndIf
 For i=0 To SizeOf(HpackDecoder)-1 : PokeA(*d+i,0) : Next
 *d\storage=storage : *d\capacity=capacity : *d\maximum=4096 : *d\allowed=4096 : *d\required=-1
 HpackTablesInit()
 ProcedureReturn 0
EndProcedure
; Call after the local SETTINGS change becomes effective, between field blocks.
; Preserve a pending minimum even if another update raises the final allowance.
Procedure.i HpackSetLimit(*d.HpackDecoder,maximum.i)
 If *d=0 : ProcedureReturn #HPACK_ARGUMENT : EndIf
 If *d\error<>0 : ProcedureReturn *d\error : EndIf
 If *d\active<>0 Or maximum<0 Or maximum>*d\capacity : ProcedureReturn hpFail(*d,#HPACK_ARGUMENT) : EndIf
 *d\allowed=maximum
 If *d\maximum>maximum
  If *d\required<0 Or maximum<*d\required : *d\required=maximum : EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i HpackBegin(*d.HpackDecoder,input.i,bytes.i,output.i,capacity.i,listLimit.i)
 If *d=0 : ProcedureReturn #HPACK_ARGUMENT : EndIf
 If *d\error<>0 : ProcedureReturn *d\error : EndIf
 If *d\active<>0 Or *d\storage=0 Or *d\capacity<4096 Or hpTablesReady=0 : ProcedureReturn hpFail(*d,#HPACK_ARGUMENT) : EndIf
 If bytes<0 Or bytes>65536 Or (bytes>0 And input=0) Or output=0 Or capacity<1 Or capacity>32768 Or listLimit<1 Or listLimit>65536 : ProcedureReturn hpFail(*d,#HPACK_ARGUMENT) : EndIf
 If input<output+capacity And output<input+bytes : ProcedureReturn hpFail(*d,#HPACK_ARGUMENT) : EndIf
 If input<*d\storage+*d\capacity And *d\storage<input+bytes : ProcedureReturn hpFail(*d,#HPACK_ARGUMENT) : EndIf
 If output<*d\storage+*d\capacity And *d\storage<output+capacity : ProcedureReturn hpFail(*d,#HPACK_ARGUMENT) : EndIf
 *d\input=input : *d\bytes=bytes : *d\cursor=0 : *d\output=output : *d\outputCapacity=capacity
 *d\listLimit=listLimit : *d\listSize=0 : *d\fields=0 : *d\updates=0 : *d\active=1 : *d\stage=0
 *d\name=0 : *d\value=0 : *d\nameLength=0 : *d\valueLength=0
 ProcedureReturn 0
EndProcedure
; At most five continuation octets; values are limited to signed-31-bit range.
Procedure.i hpInteger(*d.HpackDecoder,prefix.i)
 Define mask.i,value.i,shift.i,c.i,part.i
 If *d\cursor>=*d\bytes : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
 mask=(1<<prefix)-1 : value=PeekA(*d\input+*d\cursor) & mask : *d\cursor=*d\cursor+1
 If value<mask : ProcedureReturn value : EndIf
 shift=0
 While shift<=28
  If *d\cursor>=*d\bytes : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
  c=PeekA(*d\input+*d\cursor) : *d\cursor=*d\cursor+1 : part=c & 127
  If part>(($7FFFFFFF-value)>>shift) : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
  value=value+(part<<shift)
  If (c & 128)=0 : ProcedureReturn value : EndIf
  shift=shift+7
 Wend
 ProcedureReturn hpFail(*d,#HPACK_COMPRESSION)
EndProcedure
Procedure.i hpStringBegin(*d.HpackDecoder,destination.i,capacity.i)
 Define encoded.i
 If *d\cursor>=*d\bytes : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
 *d\stringHuffman=PeekA(*d\input+*d\cursor) & 128
 encoded=hpInteger(*d,7) : If encoded<0 : ProcedureReturn encoded : EndIf
 If encoded>*d\bytes-*d\cursor : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
 If *d\stringHuffman=0 And encoded>capacity : ProcedureReturn hpFail(*d,#HPACK_LIMIT) : EndIf
 *d\stringEnd=*d\cursor+encoded : *d\stringDestination=destination : *d\stringCapacity=capacity
 *d\stringWritten=0 : *d\stringNode=0 : *d\stringTail=0 : *d\stringTailBits=0
 ProcedureReturn 0
EndProcedure
; 0 complete, 2 more work, negative fatal. At most 128 input octets per call.
Procedure.i hpStringStep(*d.HpackDecoder)
 Define stop.i,c.i,bit.i,nextNode.i
 stop=*d\cursor+128 : If stop>*d\stringEnd : stop=*d\stringEnd : EndIf
 While *d\cursor<stop
  c=PeekA(*d\input+*d\cursor) : *d\cursor=*d\cursor+1
  If *d\stringHuffman=0
   PokeA(*d\stringDestination+*d\stringWritten,c) : *d\stringWritten=*d\stringWritten+1
  Else
   For bit=7 To 0 Step -1
    nextNode=hpHuff[*d\stringNode*2+((c>>bit)&1)]
    *d\stringTail=(*d\stringTail<<1)|((c>>bit)&1) : *d\stringTailBits=*d\stringTailBits+1
    If nextNode<0
     If nextNode=-257 : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
     If *d\stringWritten>=*d\stringCapacity : ProcedureReturn hpFail(*d,#HPACK_LIMIT) : EndIf
     PokeA(*d\stringDestination+*d\stringWritten,-nextNode-1) : *d\stringWritten=*d\stringWritten+1
     *d\stringNode=0 : *d\stringTail=0 : *d\stringTailBits=0
    Else
     *d\stringNode=nextNode
    EndIf
   Next
  EndIf
 Wend
 If *d\cursor<*d\stringEnd : ProcedureReturn 2 : EndIf
 If *d\stringNode<>0
  If *d\stringTailBits>7 Or *d\stringTail<>(1<<*d\stringTailBits)-1 : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
 EndIf
 ProcedureReturn 0
EndProcedure
Procedure.i hpLookup(*d.HpackDecoder,index.i)
 Define p.i,i.i,n.i,v.i
 If index<1 Or index>61+*d\entries : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
 If index<=61
  *d\name=hpName[index] : *d\nameLength=hpNameLength[index]
  *d\value=hpValue[index] : *d\valueLength=hpValueLength[index]
  ProcedureReturn 0
 EndIf
 p=*d\storage
 For i=62 To index-1 : p=p+4+NetReadBE16(p)+NetReadBE16(p+2) : Next
 n=NetReadBE16(p) : v=NetReadBE16(p+2)
 *d\name=p+4 : *d\nameLength=n : *d\value=p+4+n : *d\valueLength=v
 ProcedureReturn 0
EndProcedure
Procedure hpTrim(*d.HpackDecoder,target.i)
 Define p.i,count.i,size.i,n.i,v.i
 If *d\size<=target : ProcedureReturn : EndIf
 p=0 : count=0 : size=0
 While count<*d\entries
  n=NetReadBE16(*d\storage+p) : v=NetReadBE16(*d\storage+p+2)
  If n+v+32>target-size : Break : EndIf
  size=size+n+v+32 : p=p+n+v+4 : count=count+1
 Wend
 *d\size=size : *d\used=p : *d\entries=count
EndProcedure
Procedure hpInsert(*d.HpackDecoder)
 Define cost.i,space.i,i.i
 cost=*d\nameLength+*d\valueLength+32
 If cost>*d\maximum : hpTrim(*d,0) : ProcedureReturn : EndIf
 hpTrim(*d,*d\maximum-cost)
 space=cost-28
 For i=*d\used-1 To 0 Step -1 : PokeA(*d\storage+i+space,PeekA(*d\storage+i)) : Next
 NetWriteBE16(*d\storage,*d\nameLength) : NetWriteBE16(*d\storage+2,*d\valueLength)
 For i=0 To *d\nameLength-1 : PokeA(*d\storage+4+i,PeekA(*d\name+i)) : Next
 For i=0 To *d\valueLength-1 : PokeA(*d\storage+4+*d\nameLength+i,PeekA(*d\value+i)) : Next
 *d\used=*d\used+space : *d\size=*d\size+cost : *d\entries=*d\entries+1
EndProcedure
; 1 field, 2 more bounded work, 0 block complete, negative latched fatal error.
; No partially decoded field is emitted. A name is copied before table eviction.
Procedure.i HpackNext(*d.HpackDecoder)
 Define c.i,index.i,rc.i,n.i,v.i,i.i,cost.i
 If *d=0 : ProcedureReturn #HPACK_ARGUMENT : EndIf
 If *d\error<>0 : ProcedureReturn *d\error : EndIf
 If *d\active=0 : ProcedureReturn 0 : EndIf
 If *d\stage=0
  If *d\cursor>=*d\bytes
   If *d\required>=0 : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
   *d\active=0 : ProcedureReturn 0
  EndIf
  c=PeekA(*d\input+*d\cursor)
  If (c & $E0)=$20
   If *d\fields<>0 Or *d\updates>=2 : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
   n=hpInteger(*d,5) : If n<0 : ProcedureReturn n : EndIf
   If n>*d\allowed : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
   If *d\required>=0 And n>*d\required : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
   *d\required=-1 : *d\maximum=n : *d\updates=*d\updates+1 : hpTrim(*d,n)
   ProcedureReturn 2
  EndIf
  If *d\required>=0 : ProcedureReturn hpFail(*d,#HPACK_COMPRESSION) : EndIf
  *d\insert=0 : *d\sensitive=0
  If (c & 128)<>0
   index=hpInteger(*d,7) : If index<0 : ProcedureReturn index : EndIf
   rc=hpLookup(*d,index) : If rc<>0 : ProcedureReturn rc : EndIf
   n=*d\nameLength : v=*d\valueLength
   If n+v>*d\outputCapacity : ProcedureReturn hpFail(*d,#HPACK_LIMIT) : EndIf
   For i=0 To n-1 : PokeA(*d\output+i,PeekA(*d\name+i)) : Next
   For i=0 To v-1 : PokeA(*d\output+n+i,PeekA(*d\value+i)) : Next
   *d\pendingName=n : *d\stringWritten=v : *d\stage=5
  Else
   If (c & 64)<>0
    *d\insert=1 : index=hpInteger(*d,6)
   Else
    *d\sensitive=(c & 16)>>4 : index=hpInteger(*d,4)
   EndIf
   If index<0 : ProcedureReturn index : EndIf
   If index=0
    rc=hpStringBegin(*d,*d\output,*d\outputCapacity) : If rc<>0 : ProcedureReturn rc : EndIf
    *d\stage=1
   Else
    rc=hpLookup(*d,index) : If rc<>0 : ProcedureReturn rc : EndIf
    n=*d\nameLength : If n>*d\outputCapacity : ProcedureReturn hpFail(*d,#HPACK_LIMIT) : EndIf
    For i=0 To n-1 : PokeA(*d\output+i,PeekA(*d\name+i)) : Next
    *d\pendingName=n : *d\stage=2
   EndIf
  EndIf
 EndIf
 If *d\stage=1
  rc=hpStringStep(*d) : If rc<>0 : ProcedureReturn rc : EndIf
  *d\pendingName=*d\stringWritten : *d\stage=2
  ProcedureReturn 2
 EndIf
 If *d\stage=2
  rc=hpStringBegin(*d,*d\output+*d\pendingName,*d\outputCapacity-*d\pendingName)
  If rc<>0 : ProcedureReturn rc : EndIf
  *d\stage=3
 EndIf
 If *d\stage=3
  rc=hpStringStep(*d) : If rc<>0 : ProcedureReturn rc : EndIf
  *d\stage=5
 EndIf
 n=*d\pendingName : v=*d\stringWritten : cost=n+v+32
 If cost>*d\listLimit-*d\listSize : ProcedureReturn hpFail(*d,#HPACK_LIMIT) : EndIf
 *d\listSize=*d\listSize+cost : *d\fields=*d\fields+1
 *d\name=*d\output : *d\nameLength=n : *d\value=*d\output+n : *d\valueLength=v
 If *d\insert<>0 : hpInsert(*d) : EndIf
 *d\stage=0 : ProcedureReturn 1
EndProcedure
