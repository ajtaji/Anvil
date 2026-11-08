; Layout reporting uses only the shared range formatter and board memory seam.
Procedure CmdMap()
  PrintN("THE MEMORY MAP, AS THIS IMAGE MEASURES IT")
  PutMonitorMap()
  PrintNl()
  PrintN("Where a payload may go:")
  PutWindows()
  PrintN("  Nothing in this map is a constant this program was told. The")
  PrintN("  monitor's extent is the size of the image the firmware loaded, and")
  PrintN("  the low window begins above it, so both move when this program")
  PrintN("  does. There is no maximum size.")
  PrintN("ok")
EndProcedure
