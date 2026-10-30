"""Refuse a TLS working global missing from the serialized connection image."""
from pathlib import Path
import re

def check():
    root=Path(__file__).resolve().parents[1]
    context=(root/'Anvil/Crypto/tls13_context.pbi').read_text(encoding='utf8')
    save=context.split('Procedure.i Tls13ContextSave',1)[1].split('EndProcedure',1)[0]
    restore=context.split('Procedure.i Tls13ContextRestore',1)[1].split('EndProcedure',1)[0]
    constants={};rows=[];offset=0
    for file in ['tls13_record','tls13_hs','x509']:
        text=(root/f'Anvil/Crypto/{file}.pbi').read_text(encoding='utf8')
        constants.update({k:int(v) for k,v in re.findall(r'^#(\w+)\s*=\s*(\d+)\s*(?:;|$)',text,re.M)})
        for name,kind,array in re.findall(r'^Global (?:Dim )?(\w+)\.([ai])(?:\[([^]]+)\])?',text,re.M):
            if file=='x509' and not(name.startswith('X509Ee') or name=='xEePkey'):continue
            if name=='TlsCipherInstalled':continue
            n=(constants[array[1:]] if array.startswith('#') else int(array)) if array else 1
            size=n*(8 if kind=='i' else 1);offset=(offset+7)&~7
            if array:
                a=f'TlsCopy(dst+{offset},@{name}[0],{size})'
                b=f'TlsCopy(@{name}[0],src+{offset},{size})'
            else:a=f'PokeI(dst+{offset},{name})';b=f'{name}=PeekI(src+{offset})'
            assert save.count(a)==1 and restore.count(b)==1,name
            rows.append(name);offset+=size
    size=(offset+7)&~7
    assert f'#TLS13_CONTEXT_SIZE={size}' in context
    assert restore.count('Tls13RecInvalidateCipher()')==1
    assert 'TlsCipherInstalled=PeekI' not in restore
    assert 'Drbg' not in save and 'Drbg' not in restore
    client=(root/'Anvil/Core/tls_client.pbi').read_text(encoding='utf8')
    select=client.split('Procedure tlsc_Select',1)[1].split('EndProcedure',1)[0]
    fields=[name for name in re.findall(r'^Global (tlsc_\w+)\.i',client,re.M)
            if name not in {'tlsc_seeded','tlsc_slot','tlsc_cursor','tlsc_nextHandle'}]
    for i,name in enumerate(fields):
        assert f'tlsc_saved[base+{i}]={name}' in select,name
        assert f'{name}=tlsc_saved[base+{i}]' in select,name
    assert f'#TLSC_CONNECTIONS*{len(fields)}]' in client
    for name,limit in [('name','NAME_MAX'),('hs','HS_BUF'),('recv','RECV_BUF'),('tx','TX_BUF'),('in','IN_BUF'),('ring','RING')]:
        assert f'Global Dim tlsc_{name}.a[#TLSC_CONNECTIONS*#TLSC_{limit}]' in client
        for expression in re.findall(r'\btlsc_'+name+r'\[([^]]+)\]',client):
            base=f'tlsc_slot*#TLSC_{limit}'
            assert expression==base or expression.startswith(base+'+'),(name,expression)
    return {'state_fields':len(rows),'snapshot_bytes':size,'client_fields':len(fields),'isolated_large_buffers':6}

if __name__=='__main__':print(check())
