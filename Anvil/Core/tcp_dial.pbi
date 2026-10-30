; Kernel binding for the shared connection selector.
#TCP_DIAL_KERNEL=1
XIncludeFile "Anvil/Network/tcp_dial.pbi"
Procedure.i NetDialStart(*d.TcpDial,host.i,port.i)
 ProcedureReturn TcpDialStart(*d,host,port)
EndProcedure
