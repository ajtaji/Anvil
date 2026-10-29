; SPDX-License-Identifier: MIT
; Physical shared collision/geometry and resident raster application.
EnableFloatingPoint
XIncludeFile "Anvil/Graphics/neon_collision.pbi"
XIncludeFile "Anvil/Hal/neon_service_api.pbi"
XIncludeFile "Anvil/Graphics/neon_service_client.pbi"
XIncludeFile "Anvil/Graphics/neon_service_mapping.pbi"
Global ncpChecks.i,ncpFailure.i
Global Dim ncpA.a[96]
Global Dim ncpB.a[96]
Global Dim ncpRGBA.a[288]
Global Dim ncpScratch.q[128]
Global Dim ncpHull.NeonCollisionPoint[64]
Global Dim ncpPoly.NeonCollisionPoint[8]
Global Dim ncpTempHull.NeonCollisionPoint[64]
Global Dim ncpRows.a[16]
Global Dim ncpCurve.NeonCollisionPoint[21]
Global Dim ncpLines.f[80]
Global ncpMaskA.NeonCollisionMask,ncpMaskB.NeonCollisionMask,ncpTA.NeonCollisionTransform,ncpTB.NeonCollisionTransform,ncpHit.NeonCollisionPoint
Procedure NcpCheck(actual.i,expected.i)
  ncpChecks=ncpChecks+1
  If ncpChecks<=600 : PokeI(#NCP_REPORT+256+ncpChecks*16,actual) : PokeI(#NCP_REPORT+264+ncpChecks*16,expected) : EndIf
  If actual<>expected And ncpFailure=0 : ncpFailure=ncpChecks : EndIf
  PokeI(#NCP_REPORT+16,ncpFailure) : PokeI(#NCP_REPORT+24,ncpChecks)
EndProcedure
Procedure.i Main(services.i)
  Protected i.i,j.i,n.i,font.i,rc.i
  For i=0 To 16383 : PokeA(#NCP_REPORT+i,0) : Next
  PokeI(#NCP_REPORT,$4E435031) : PokeI(#NCP_REPORT+8,1)
  NcpCheck(NeonCollisionAABB(-11.0,-17.0,12.0,8.0,18.0,-8.0,6.0,14.0),0)
  NcpCheck(NeonCollisionAABB(-6.0,-19.0,19.0,11.0,6.0,6.0,15.0,18.0),0)
  NcpCheck(NeonCollisionAABB(-15.0,7.0,6.0,11.0,-7.0,-4.0,4.0,9.0),0)
  NcpCheck(NeonCollisionAABB(-8.0,11.0,0.0,6.0,-12.0,-4.0,3.0,0.0),0)
  NcpCheck(NeonCollisionAABB(-15.0,-20.0,13.0,7.0,-3.0,-1.0,16.0,14.0),0)
  NcpCheck(NeonCollisionAABB(20.0,-8.0,3.0,15.0,-1.0,-11.0,13.0,4.0),0)
  NcpCheck(NeonCollisionAABB(0.0,17.0,3.0,17.0,-14.0,4.0,16.0,18.0),1)
  NcpCheck(NeonCollisionAABB(4.0,20.0,0.0,2.0,7.0,20.0,2.0,18.0),0)
  NcpCheck(NeonCollisionAABB(-11.0,-18.0,5.0,4.0,12.0,1.0,1.0,8.0),0)
  NcpCheck(NeonCollisionAABB(19.0,-17.0,13.0,20.0,13.0,19.0,17.0,6.0),0)
  NcpCheck(NeonCollisionAABB(-19.0,10.0,12.0,14.0,-12.0,-5.0,1.0,17.0),1)
  NcpCheck(NeonCollisionAABB(-8.0,-3.0,16.0,6.0,9.0,20.0,15.0,18.0),0)
  NcpCheck(NeonCollisionAABB(14.0,0.0,14.0,1.0,4.0,5.0,5.0,1.0),0)
  NcpCheck(NeonCollisionAABB(-13.0,5.0,2.0,2.0,11.0,12.0,13.0,13.0),0)
  NcpCheck(NeonCollisionAABB(-20.0,-16.0,13.0,13.0,-6.0,13.0,9.0,2.0),0)
  NcpCheck(NeonCollisionAABB(10.0,-18.0,17.0,10.0,-2.0,-17.0,1.0,12.0),0)
  NcpCheck(NeonCollisionAABB(-6.0,-16.0,12.0,5.0,-6.0,-7.0,16.0,13.0),0)
  NcpCheck(NeonCollisionAABB(9.0,20.0,2.0,12.0,14.0,4.0,2.0,8.0),0)
  NcpCheck(NeonCollisionAABB(17.0,-18.0,12.0,4.0,-12.0,1.0,13.0,6.0),0)
  NcpCheck(NeonCollisionAABB(-10.0,-6.0,12.0,20.0,-7.0,0.0,3.0,15.0),1)
  NcpCheck(NeonCollisionAABB(-9.0,6.0,10.0,13.0,17.0,-20.0,11.0,20.0),0)
  NcpCheck(NeonCollisionAABB(-13.0,19.0,2.0,5.0,-14.0,-20.0,0.0,12.0),0)
  NcpCheck(NeonCollisionAABB(13.0,-3.0,10.0,5.0,-9.0,9.0,10.0,3.0),0)
  NcpCheck(NeonCollisionAABB(-17.0,-4.0,2.0,15.0,-9.0,11.0,9.0,11.0),0)
  NcpCheck(NeonCollisionAABB(4.0,19.0,12.0,10.0,-11.0,5.0,10.0,9.0),0)
  NcpCheck(NeonCollisionAABB(-15.0,4.0,8.0,1.0,-14.0,-19.0,13.0,0.0),0)
  NcpCheck(NeonCollisionAABB(-9.0,-14.0,20.0,3.0,-15.0,-14.0,0.0,6.0),0)
  NcpCheck(NeonCollisionAABB(-8.0,12.0,10.0,8.0,0.0,-2.0,14.0,8.0),0)
  NcpCheck(NeonCollisionAABB(10.0,20.0,8.0,10.0,9.0,7.0,15.0,12.0),0)
  NcpCheck(NeonCollisionAABB(-13.0,-12.0,15.0,16.0,20.0,-15.0,11.0,6.0),0)
  NcpCheck(NeonCollisionAABB(10.0,-18.0,9.0,9.0,7.0,-9.0,6.0,2.0),0)
  NcpCheck(NeonCollisionAABB(15.0,0.0,6.0,18.0,19.0,-7.0,13.0,2.0),0)
  NcpCheck(NeonCollisionAABB(-9.0,16.0,19.0,3.0,-18.0,5.0,12.0,10.0),0)
  NcpCheck(NeonCollisionAABB(12.0,-1.0,2.0,13.0,-1.0,7.0,8.0,6.0),0)
  NcpCheck(NeonCollisionAABB(17.0,19.0,9.0,15.0,11.0,9.0,18.0,13.0),1)
  NcpCheck(NeonCollisionAABB(-8.0,-19.0,9.0,10.0,-18.0,-10.0,19.0,6.0),1)
  NcpCheck(NeonCollisionAABB(8.0,16.0,5.0,11.0,-8.0,-19.0,11.0,2.0),0)
  NcpCheck(NeonCollisionAABB(2.0,-13.0,2.0,9.0,-19.0,8.0,19.0,15.0),0)
  NcpCheck(NeonCollisionAABB(-18.0,-1.0,19.0,15.0,4.0,0.0,17.0,4.0),0)
  NcpCheck(NeonCollisionAABB(-19.0,-2.0,15.0,4.0,-9.0,3.0,8.0,4.0),0)
  NcpCheck(NeonCollisionAABB(14.0,-8.0,20.0,5.0,14.0,4.0,2.0,11.0),0)
  NcpCheck(NeonCollisionAABB(-5.0,16.0,13.0,18.0,17.0,9.0,12.0,4.0),0)
  NcpCheck(NeonCollisionAABB(-2.0,-5.0,12.0,12.0,2.0,-4.0,3.0,5.0),1)
  NcpCheck(NeonCollisionAABB(16.0,-5.0,7.0,8.0,-14.0,13.0,5.0,1.0),0)
  NcpCheck(NeonCollisionAABB(-6.0,-13.0,10.0,9.0,-17.0,-13.0,20.0,6.0),1)
  NcpCheck(NeonCollisionAABB(18.0,5.0,8.0,19.0,-18.0,-12.0,2.0,15.0),0)
  NcpCheck(NeonCollisionAABB(13.0,-7.0,18.0,17.0,-6.0,0.0,12.0,6.0),0)
  NcpCheck(NeonCollisionAABB(16.0,-18.0,7.0,15.0,-13.0,-14.0,8.0,8.0),0)
  NcpCheck(NeonCollisionAABB(13.0,-4.0,16.0,15.0,5.0,9.0,18.0,8.0),1)
  NcpCheck(NeonCollisionAABB(-10.0,-14.0,2.0,10.0,1.0,15.0,8.0,17.0),0)
  NcpCheck(NeonCollisionAABB(6.0,9.0,7.0,17.0,18.0,9.0,3.0,10.0),0)
  NcpCheck(NeonCollisionAABB(10.0,-5.0,15.0,6.0,-8.0,-12.0,18.0,16.0),0)
  NcpCheck(NeonCollisionAABB(-3.0,14.0,17.0,0.0,5.0,7.0,6.0,13.0),0)
  NcpCheck(NeonCollisionAABB(14.0,-20.0,6.0,14.0,-4.0,-4.0,19.0,14.0),0)
  NcpCheck(NeonCollisionAABB(3.0,13.0,7.0,12.0,15.0,-2.0,4.0,13.0),0)
  NcpCheck(NeonCollisionAABB(18.0,7.0,14.0,8.0,20.0,7.0,2.0,5.0),1)
  NcpCheck(NeonCollisionAABB(11.0,-5.0,10.0,13.0,1.0,-15.0,9.0,20.0),0)
  NcpCheck(NeonCollisionAABB(-13.0,8.0,17.0,1.0,-20.0,12.0,16.0,3.0),0)
  NcpCheck(NeonCollisionAABB(-20.0,12.0,1.0,19.0,-8.0,3.0,8.0,16.0),0)
  NcpCheck(NeonCollisionAABB(8.0,-4.0,6.0,9.0,-10.0,7.0,10.0,11.0),0)
  NcpCheck(NeonCollisionAABB(4.0,-10.0,3.0,6.0,-15.0,-12.0,13.0,6.0),0)
  NcpCheck(NeonCollisionAABB(-18.0,10.0,11.0,5.0,-15.0,-10.0,5.0,6.0),0)
  NcpCheck(NeonCollisionAABB(20.0,8.0,6.0,3.0,2.0,-12.0,6.0,11.0),0)
  NcpCheck(NeonCollisionAABB(-15.0,0.0,14.0,4.0,16.0,-12.0,3.0,14.0),0)
  NcpCheck(NeonCollisionAABB(-2.0,11.0,20.0,10.0,-18.0,18.0,1.0,20.0),0)
  NcpCheck(NeonCollisionAABB(18.0,6.0,10.0,8.0,-12.0,-8.0,9.0,19.0),0)
  NcpCheck(NeonCollisionAABB(-8.0,-7.0,2.0,4.0,-5.0,13.0,2.0,9.0),0)
  NcpCheck(NeonCollisionAABB(-20.0,17.0,0.0,5.0,-14.0,15.0,17.0,9.0),0)
  NcpCheck(NeonCollisionAABB(16.0,-15.0,19.0,1.0,-13.0,5.0,12.0,18.0),0)
  NcpCheck(NeonCollisionAABB(20.0,-8.0,7.0,11.0,14.0,1.0,20.0,9.0),1)
  NcpCheck(NeonCollisionAABB(-2.0,18.0,12.0,1.0,-20.0,-15.0,14.0,12.0),0)
  NcpCheck(NeonCollisionAABB(15.0,-6.0,7.0,20.0,1.0,14.0,12.0,5.0),0)
  NcpCheck(NeonCollisionAABB(-11.0,-19.0,15.0,20.0,-19.0,7.0,1.0,10.0),0)
  NcpCheck(NeonCollisionAABB(4.0,20.0,5.0,11.0,-13.0,-1.0,16.0,19.0),0)
  NcpCheck(NeonCollisionAABB(-5.0,12.0,19.0,4.0,-9.0,20.0,12.0,6.0),0)
  NcpCheck(NeonCollisionAABB(-8.0,4.0,1.0,11.0,4.0,-10.0,19.0,20.0),0)
  NcpCheck(NeonCollisionAABB(15.0,6.0,2.0,7.0,18.0,2.0,3.0,12.0),0)
  NcpCheck(NeonCollisionAABB(-6.0,-17.0,6.0,6.0,8.0,-2.0,5.0,11.0),0)
  NcpCheck(NeonCollisionAABB(-9.0,-16.0,19.0,3.0,14.0,-4.0,7.0,15.0),0)
  NcpCheck(NeonCollisionAABB(18.0,14.0,15.0,12.0,4.0,-1.0,18.0,12.0),0)
  NcpCheck(NeonCollisionAABB(10.0,-17.0,5.0,6.0,-15.0,-1.0,13.0,13.0),0)
  NcpCheck(NeonCollisionAABB(-8.0,-11.0,10.0,1.0,13.0,-2.0,17.0,19.0),0)
  NcpCheck(NeonCollisionAABB(10.0,11.0,17.0,1.0,-9.0,-14.0,16.0,7.0),0)
  NcpCheck(NeonCollisionAABB(-5.0,-8.0,18.0,7.0,-20.0,13.0,8.0,9.0),0)
  NcpCheck(NeonCollisionAABB(-12.0,15.0,14.0,1.0,-5.0,-8.0,2.0,2.0),0)
  NcpCheck(NeonCollisionAABB(0.0,5.0,13.0,1.0,6.0,0.0,7.0,20.0),1)
  NcpCheck(NeonCollisionAABB(-1.0,-14.0,15.0,6.0,-15.0,-10.0,15.0,11.0),1)
  NcpCheck(NeonCollisionAABB(20.0,11.0,14.0,0.0,12.0,-7.0,20.0,9.0),0)
  NcpCheck(NeonCollisionAABB(-18.0,-1.0,8.0,1.0,-6.0,-15.0,14.0,5.0),0)
  NcpCheck(NeonCollisionAABB(9.0,-18.0,0.0,6.0,-2.0,7.0,20.0,14.0),0)
  NcpCheck(NeonCollisionAABB(-3.0,-17.0,14.0,11.0,19.0,10.0,12.0,19.0),0)
  NcpCheck(NeonCollisionAABB(-10.0,3.0,6.0,10.0,19.0,8.0,9.0,4.0),0)
  NcpCheck(NeonCollisionAABB(-15.0,18.0,1.0,15.0,13.0,18.0,12.0,6.0),0)
  NcpCheck(NeonCollisionAABB(-9.0,12.0,4.0,4.0,-7.0,-8.0,17.0,5.0),0)
  NcpCheck(NeonCollisionAABB(-8.0,-5.0,16.0,14.0,-2.0,8.0,20.0,15.0),1)
  NcpCheck(NeonCollisionAABB(4.0,8.0,11.0,12.0,8.0,-14.0,6.0,17.0),0)
  NcpCheck(NeonCollisionAABB(14.0,-3.0,2.0,7.0,13.0,1.0,14.0,18.0),1)
  NcpCheck(NeonCollisionAABB(15.0,16.0,17.0,16.0,-2.0,18.0,5.0,1.0),0)
  NcpCheck(NeonCollisionAABB(20.0,-1.0,13.0,11.0,-18.0,0.0,2.0,10.0),0)
  NcpCheck(NeonCollisionAABB(-2.0,0.0,19.0,4.0,-11.0,5.0,11.0,3.0),0)
  NcpCheck(NeonCollisionCircle(9.0,13.0,14.0,18.0,-14.0,14.0),0)
  NcpCheck(NeonCollisionCircle(-12.0,16.0,13.0,17.0,-3.0,1.0),0)
  NcpCheck(NeonCollisionCircle(6.0,1.0,3.0,-12.0,8.0,0.0),0)
  NcpCheck(NeonCollisionCircle(-14.0,15.0,0.0,0.0,6.0,4.0),0)
  NcpCheck(NeonCollisionCircle(8.0,-3.0,14.0,-11.0,20.0,4.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,6.0,10.0,11.0,-2.0,7.0),0)
  NcpCheck(NeonCollisionCircle(-2.0,-18.0,6.0,-18.0,-2.0,2.0),0)
  NcpCheck(NeonCollisionCircle(0.0,6.0,1.0,-5.0,12.0,10.0),1)
  NcpCheck(NeonCollisionCircle(0.0,-5.0,0.0,-3.0,0.0,0.0),0)
  NcpCheck(NeonCollisionCircle(12.0,10.0,2.0,-11.0,-12.0,1.0),0)
  NcpCheck(NeonCollisionCircle(-2.0,-10.0,14.0,-7.0,-13.0,10.0),1)
  NcpCheck(NeonCollisionCircle(15.0,-11.0,7.0,18.0,-20.0,7.0),1)
  NcpCheck(NeonCollisionCircle(8.0,1.0,13.0,-14.0,-19.0,1.0),0)
  NcpCheck(NeonCollisionCircle(19.0,17.0,6.0,12.0,-8.0,2.0),0)
  NcpCheck(NeonCollisionCircle(-18.0,-19.0,13.0,-13.0,-19.0,4.0),1)
  NcpCheck(NeonCollisionCircle(-15.0,-3.0,11.0,19.0,-19.0,9.0),0)
  NcpCheck(NeonCollisionCircle(-8.0,9.0,10.0,13.0,9.0,14.0),1)
  NcpCheck(NeonCollisionCircle(17.0,10.0,11.0,16.0,4.0,0.0),1)
  NcpCheck(NeonCollisionCircle(-14.0,-10.0,10.0,-18.0,-17.0,10.0),1)
  NcpCheck(NeonCollisionCircle(7.0,-17.0,6.0,-16.0,10.0,13.0),0)
  NcpCheck(NeonCollisionCircle(13.0,-8.0,8.0,-8.0,4.0,6.0),0)
  NcpCheck(NeonCollisionCircle(-12.0,-5.0,14.0,14.0,1.0,1.0),0)
  NcpCheck(NeonCollisionCircle(18.0,-20.0,2.0,-5.0,0.0,13.0),0)
  NcpCheck(NeonCollisionCircle(-14.0,11.0,6.0,-14.0,-5.0,4.0),0)
  NcpCheck(NeonCollisionCircle(4.0,-5.0,9.0,-5.0,14.0,1.0),0)
  NcpCheck(NeonCollisionCircle(7.0,-18.0,1.0,14.0,19.0,2.0),0)
  NcpCheck(NeonCollisionCircle(5.0,3.0,4.0,9.0,4.0,4.0),1)
  NcpCheck(NeonCollisionCircle(4.0,-6.0,0.0,13.0,13.0,9.0),0)
  NcpCheck(NeonCollisionCircle(-12.0,-1.0,0.0,-5.0,5.0,3.0),0)
  NcpCheck(NeonCollisionCircle(-2.0,-7.0,3.0,7.0,2.0,4.0),0)
  NcpCheck(NeonCollisionCircle(-16.0,1.0,9.0,10.0,7.0,0.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,3.0,13.0,4.0,-15.0,11.0),1)
  NcpCheck(NeonCollisionCircle(7.0,-10.0,8.0,3.0,4.0,4.0),0)
  NcpCheck(NeonCollisionCircle(-13.0,-1.0,5.0,-18.0,9.0,0.0),0)
  NcpCheck(NeonCollisionCircle(1.0,-5.0,11.0,-12.0,15.0,1.0),0)
  NcpCheck(NeonCollisionCircle(4.0,19.0,10.0,19.0,14.0,4.0),0)
  NcpCheck(NeonCollisionCircle(12.0,-3.0,2.0,-18.0,8.0,5.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,0.0,3.0,12.0,7.0,12.0),0)
  NcpCheck(NeonCollisionCircle(13.0,11.0,10.0,-12.0,20.0,1.0),0)
  NcpCheck(NeonCollisionCircle(11.0,17.0,8.0,-3.0,-9.0,0.0),0)
  NcpCheck(NeonCollisionCircle(-7.0,-16.0,1.0,-20.0,-11.0,13.0),1)
  NcpCheck(NeonCollisionCircle(-10.0,14.0,8.0,-15.0,-1.0,7.0),0)
  NcpCheck(NeonCollisionCircle(1.0,-20.0,9.0,-16.0,9.0,0.0),0)
  NcpCheck(NeonCollisionCircle(13.0,13.0,1.0,15.0,10.0,11.0),1)
  NcpCheck(NeonCollisionCircle(0.0,14.0,8.0,0.0,-8.0,2.0),0)
  NcpCheck(NeonCollisionCircle(-11.0,8.0,2.0,20.0,-3.0,6.0),0)
  NcpCheck(NeonCollisionCircle(9.0,-12.0,9.0,5.0,-18.0,1.0),1)
  NcpCheck(NeonCollisionCircle(-7.0,-8.0,2.0,19.0,7.0,13.0),0)
  NcpCheck(NeonCollisionCircle(2.0,-16.0,12.0,-17.0,17.0,6.0),0)
  NcpCheck(NeonCollisionCircle(-10.0,11.0,3.0,-19.0,15.0,14.0),1)
  NcpCheck(NeonCollisionCircle(18.0,14.0,14.0,4.0,-7.0,8.0),0)
  NcpCheck(NeonCollisionCircle(-1.0,-20.0,8.0,-8.0,-18.0,11.0),1)
  NcpCheck(NeonCollisionCircle(14.0,-11.0,5.0,-9.0,10.0,7.0),0)
  NcpCheck(NeonCollisionCircle(3.0,6.0,11.0,16.0,0.0,11.0),1)
  NcpCheck(NeonCollisionCircle(-2.0,-12.0,11.0,-15.0,-13.0,5.0),1)
  NcpCheck(NeonCollisionCircle(19.0,-7.0,13.0,-6.0,1.0,6.0),0)
  NcpCheck(NeonCollisionCircle(-13.0,17.0,6.0,18.0,15.0,9.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,1.0,1.0,0.0,-9.0,4.0),0)
  NcpCheck(NeonCollisionCircle(6.0,-1.0,5.0,-6.0,11.0,11.0),0)
  NcpCheck(NeonCollisionCircle(17.0,4.0,6.0,-12.0,12.0,8.0),0)
  NcpCheck(NeonCollisionCircle(2.0,10.0,3.0,4.0,20.0,11.0),1)
  NcpCheck(NeonCollisionCircle(16.0,13.0,7.0,-15.0,1.0,8.0),0)
  NcpCheck(NeonCollisionCircle(11.0,-20.0,9.0,-14.0,-11.0,1.0),0)
  NcpCheck(NeonCollisionCircle(11.0,8.0,13.0,-12.0,10.0,0.0),0)
  NcpCheck(NeonCollisionCircle(-10.0,3.0,11.0,15.0,12.0,6.0),0)
  NcpCheck(NeonCollisionCircle(-16.0,-5.0,12.0,16.0,13.0,10.0),0)
  NcpCheck(NeonCollisionCircle(-6.0,-10.0,0.0,3.0,-12.0,9.0),0)
  NcpCheck(NeonCollisionCircle(19.0,-10.0,12.0,8.0,-9.0,6.0),1)
  NcpCheck(NeonCollisionCircle(-18.0,-1.0,3.0,-13.0,-4.0,9.0),1)
  NcpCheck(NeonCollisionCircle(16.0,11.0,11.0,0.0,-12.0,11.0),0)
  NcpCheck(NeonCollisionCircle(9.0,-12.0,6.0,4.0,-12.0,7.0),1)
  NcpCheck(NeonCollisionCircle(17.0,-20.0,14.0,20.0,11.0,10.0),0)
  NcpCheck(NeonCollisionCircle(-11.0,0.0,1.0,-17.0,2.0,12.0),1)
  NcpCheck(NeonCollisionCircle(-10.0,-19.0,1.0,16.0,-4.0,6.0),0)
  NcpCheck(NeonCollisionCircle(-18.0,-14.0,6.0,-8.0,-13.0,12.0),1)
  NcpCheck(NeonCollisionCircle(-9.0,-4.0,12.0,19.0,-17.0,12.0),0)
  NcpCheck(NeonCollisionCircle(-4.0,-11.0,11.0,17.0,-13.0,10.0),0)
  NcpCheck(NeonCollisionCircle(-16.0,15.0,12.0,-2.0,-8.0,2.0),0)
  NcpCheck(NeonCollisionCircle(20.0,0.0,7.0,6.0,7.0,6.0),0)
  NcpCheck(NeonCollisionCircle(-15.0,16.0,10.0,-4.0,-1.0,5.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,20.0,6.0,-18.0,12.0,9.0),1)
  NcpCheck(NeonCollisionCircle(15.0,13.0,12.0,-19.0,19.0,0.0),0)
  NcpCheck(NeonCollisionCircle(-10.0,14.0,4.0,9.0,-3.0,13.0),0)
  NcpCheck(NeonCollisionCircle(-15.0,-10.0,4.0,-7.0,20.0,9.0),0)
  NcpCheck(NeonCollisionCircle(-19.0,-8.0,11.0,9.0,13.0,3.0),0)
  NcpCheck(NeonCollisionCircle(-14.0,3.0,10.0,13.0,10.0,6.0),0)
  NcpCheck(NeonCollisionCircle(13.0,-8.0,5.0,9.0,10.0,7.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,-20.0,3.0,7.0,2.0,14.0),0)
  NcpCheck(NeonCollisionCircle(-16.0,12.0,9.0,9.0,-20.0,7.0),0)
  NcpCheck(NeonCollisionCircle(-19.0,-14.0,12.0,11.0,-20.0,11.0),0)
  NcpCheck(NeonCollisionCircle(-2.0,-4.0,13.0,0.0,-10.0,2.0),1)
  NcpCheck(NeonCollisionCircle(-16.0,-12.0,14.0,-4.0,-1.0,2.0),0)
  NcpCheck(NeonCollisionCircle(14.0,-8.0,3.0,18.0,-18.0,9.0),1)
  NcpCheck(NeonCollisionCircle(-19.0,-13.0,11.0,6.0,10.0,13.0),0)
  NcpCheck(NeonCollisionCircle(12.0,14.0,13.0,-8.0,-5.0,14.0),0)
  NcpCheck(NeonCollisionCircle(2.0,-11.0,9.0,-9.0,-2.0,4.0),0)
  NcpCheck(NeonCollisionCircle(-8.0,-11.0,2.0,-5.0,4.0,13.0),0)
  NcpCheck(NeonCollisionCircle(-16.0,1.0,7.0,11.0,-6.0,11.0),0)
  NcpCheck(NeonCollisionCircle(-9.0,4.0,6.0,3.0,-2.0,13.0),1)
  NcpCheck(NeonCollisionCircle(-5.0,4.0,1.0,20.0,-9.0,11.0),0)
  NcpCheck(NeonCollisionLineLine(14.0,-2.0,6.0,14.0,-9.0,-2.0,-6.0,4.0,0),0)
  NcpCheck(NeonCollisionLineLine(-8.0,8.0,11.0,0.0,-2.0,-1.0,3.0,13.0,0),1)
  NcpCheck(NeonCollisionLineLine(-6.0,-13.0,12.0,-13.0,-11.0,9.0,-3.0,4.0,0),0)
  NcpCheck(NeonCollisionLineLine(-9.0,-7.0,-7.0,13.0,-13.0,0.0,-3.0,-12.0,0),1)
  NcpCheck(NeonCollisionLineLine(-11.0,-7.0,2.0,5.0,6.0,-7.0,2.0,14.0,0),0)
  NcpCheck(NeonCollisionLineLine(-8.0,13.0,-10.0,6.0,4.0,-14.0,1.0,1.0,0),0)
  NcpCheck(NeonCollisionLineLine(-9.0,-6.0,13.0,-11.0,5.0,-12.0,12.0,-7.0,0),1)
  NcpCheck(NeonCollisionLineLine(-7.0,3.0,-13.0,-7.0,-13.0,-14.0,-8.0,-10.0,0),0)
  NcpCheck(NeonCollisionLineLine(1.0,-8.0,-3.0,-8.0,3.0,9.0,13.0,-2.0,0),0)
  NcpCheck(NeonCollisionLineLine(-14.0,-4.0,5.0,13.0,-11.0,-8.0,-7.0,-12.0,0),0)
  NcpCheck(NeonCollisionLineLine(8.0,4.0,11.0,2.0,14.0,8.0,8.0,10.0,0),0)
  NcpCheck(NeonCollisionLineLine(-7.0,4.0,-6.0,14.0,0.0,-9.0,-1.0,-13.0,0),0)
  NcpCheck(NeonCollisionLineLine(-11.0,9.0,-4.0,-7.0,10.0,10.0,10.0,7.0,0),0)
  NcpCheck(NeonCollisionLineLine(-7.0,11.0,13.0,9.0,-1.0,3.0,15.0,12.0,0),1)
  NcpCheck(NeonCollisionLineLine(11.0,3.0,1.0,-7.0,-5.0,-9.0,4.0,-5.0,0),1)
  NcpCheck(NeonCollisionLineLine(-4.0,-2.0,-5.0,15.0,-5.0,-9.0,-15.0,-12.0,0),0)
  NcpCheck(NeonCollisionLineLine(10.0,-1.0,5.0,-8.0,-11.0,-1.0,-7.0,1.0,0),0)
  NcpCheck(NeonCollisionLineLine(-8.0,-5.0,4.0,-4.0,3.0,-15.0,1.0,9.0,0),1)
  NcpCheck(NeonCollisionLineLine(-10.0,-4.0,-7.0,-11.0,-6.0,9.0,-7.0,15.0,0),0)
  NcpCheck(NeonCollisionLineLine(14.0,15.0,8.0,12.0,-14.0,-4.0,-4.0,-9.0,0),0)
  NcpCheck(NeonCollisionLineLine(0.0,1.0,-1.0,-3.0,15.0,3.0,12.0,15.0,0),0)
  NcpCheck(NeonCollisionLineLine(10.0,-6.0,4.0,-8.0,-5.0,11.0,-13.0,9.0,0),0)
  NcpCheck(NeonCollisionLineLine(2.0,6.0,12.0,12.0,10.0,-10.0,6.0,14.0,0),1)
  NcpCheck(NeonCollisionLineLine(2.0,-15.0,-8.0,-1.0,4.0,0.0,-8.0,-4.0,0),1)
  NcpCheck(NeonCollisionLineLine(13.0,0.0,-7.0,-7.0,10.0,-13.0,15.0,-3.0,0),0)
  NcpCheck(NeonCollisionLineLine(12.0,-10.0,10.0,-11.0,10.0,-1.0,1.0,-14.0,0),0)
  NcpCheck(NeonCollisionLineLine(-4.0,13.0,7.0,3.0,-11.0,-7.0,13.0,-2.0,0),0)
  NcpCheck(NeonCollisionLineLine(10.0,0.0,12.0,-1.0,-3.0,14.0,9.0,-12.0,0),0)
  NcpCheck(NeonCollisionLineLine(-15.0,-6.0,6.0,-2.0,-12.0,0.0,9.0,-11.0,0),1)
  NcpCheck(NeonCollisionLineLine(-6.0,8.0,-5.0,1.0,3.0,-9.0,-7.0,-10.0,0),0)
  NcpCheck(NeonCollisionLineLine(15.0,-13.0,-9.0,13.0,6.0,6.0,5.0,-2.0,0),0)
  NcpCheck(NeonCollisionLineLine(-3.0,-14.0,-5.0,-2.0,-9.0,12.0,-6.0,-8.0,0),0)
  NcpCheck(NeonCollisionLineLine(-5.0,8.0,-12.0,11.0,-3.0,-11.0,2.0,-11.0,0),0)
  NcpCheck(NeonCollisionLineLine(14.0,-4.0,-13.0,0.0,5.0,7.0,6.0,-3.0,0),1)
  NcpCheck(NeonCollisionLineLine(8.0,-6.0,-15.0,-5.0,9.0,2.0,11.0,0.0,0),0)
  NcpCheck(NeonCollisionLineLine(10.0,-8.0,1.0,1.0,-4.0,1.0,9.0,-4.0,0),1)
  NcpCheck(NeonCollisionLineLine(9.0,0.0,5.0,-13.0,15.0,-13.0,11.0,12.0,0),0)
  NcpCheck(NeonCollisionLineLine(-10.0,13.0,-10.0,-9.0,-15.0,1.0,11.0,14.0,0),1)
  NcpCheck(NeonCollisionLineLine(9.0,-14.0,-15.0,-3.0,-3.0,4.0,-15.0,6.0,0),0)
  NcpCheck(NeonCollisionLineLine(-8.0,-11.0,-3.0,-12.0,7.0,-13.0,-3.0,14.0,0),0)
  NcpCheck(NeonCollisionLineLine(0.0,-6.0,-9.0,3.0,13.0,4.0,-9.0,8.0,0),0)
  NcpCheck(NeonCollisionLineLine(6.0,14.0,6.0,0.0,-1.0,5.0,-10.0,10.0,0),0)
  NcpCheck(NeonCollisionLineLine(8.0,-14.0,15.0,-9.0,-5.0,1.0,2.0,11.0,0),0)
  NcpCheck(NeonCollisionLineLine(1.0,15.0,-9.0,-6.0,3.0,15.0,-5.0,7.0,0),1)
  NcpCheck(NeonCollisionLineLine(-3.0,8.0,-11.0,11.0,-10.0,6.0,-2.0,12.0,0),1)
  NcpCheck(NeonCollisionLineLine(-1.0,14.0,2.0,3.0,-6.0,10.0,-11.0,11.0,0),0)
  NcpCheck(NeonCollisionLineLine(10.0,0.0,-8.0,8.0,-12.0,12.0,14.0,3.0,0),0)
  NcpCheck(NeonCollisionLineLine(8.0,-10.0,13.0,5.0,-3.0,0.0,-2.0,9.0,0),0)
  NcpCheck(NeonCollisionLineLine(-5.0,-11.0,-4.0,7.0,-12.0,1.0,1.0,15.0,0),0)
  NcpCheck(NeonCollisionLineLine(-15.0,3.0,-6.0,13.0,0.0,12.0,-8.0,10.0,0),0)
  NcpCheck(NeonCollisionLineLine(-15.0,-9.0,-14.0,-6.0,-9.0,10.0,-1.0,0.0,0),0)
  NcpCheck(NeonCollisionLineLine(-6.0,8.0,13.0,-12.0,7.0,13.0,-2.0,-10.0,0),1)
  NcpCheck(NeonCollisionLineLine(9.0,-1.0,-8.0,-6.0,-1.0,-1.0,-6.0,8.0,0),0)
  NcpCheck(NeonCollisionLineLine(-5.0,-6.0,-15.0,12.0,0.0,0.0,3.0,-10.0,0),0)
  NcpCheck(NeonCollisionLineLine(2.0,11.0,-10.0,6.0,12.0,-5.0,-10.0,-3.0,0),0)
  NcpCheck(NeonCollisionLineLine(1.0,-12.0,9.0,-5.0,14.0,0.0,-4.0,-14.0,0),0)
  NcpCheck(NeonCollisionLineLine(1.0,-1.0,3.0,-11.0,10.0,-7.0,5.0,13.0,0),0)
  NcpCheck(NeonCollisionLineLine(13.0,14.0,14.0,0.0,0.0,13.0,-4.0,-15.0,0),0)
  NcpCheck(NeonCollisionLineLine(-8.0,8.0,-11.0,-12.0,-11.0,12.0,-8.0,3.0,0),1)
  NcpCheck(NeonCollisionLineLine(1.0,3.0,6.0,-4.0,9.0,-14.0,9.0,8.0,0),0)
  NcpCheck(NeonCollisionLineCircle(-10.0,11.0,-12.0,11.0,-6.0,8.0,7.0),1)
  NcpCheck(NeonCollisionLineCircle(5.0,-15.0,13.0,-15.0,-10.0,5.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-3.0,-3.0,-2.0,15.0,-4.0,-12.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(14.0,-8.0,-1.0,14.0,-3.0,-2.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-12.0,0.0,-11.0,-2.0,7.0,-12.0,3.0),0)
  NcpCheck(NeonCollisionLineCircle(-13.0,7.0,10.0,-10.0,11.0,5.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(15.0,4.0,14.0,-7.0,4.0,-1.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(3.0,-4.0,-14.0,-12.0,4.0,-5.0,7.0),1)
  NcpCheck(NeonCollisionLineCircle(-3.0,-6.0,-6.0,-6.0,-13.0,-11.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-10.0,-12.0,-12.0,8.0,6.0,5.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-4.0,1.0,8.0,-7.0,1.0,-15.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(3.0,-12.0,14.0,-5.0,-8.0,-8.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(11.0,-2.0,-13.0,-15.0,15.0,5.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(9.0,-11.0,4.0,14.0,-14.0,13.0,6.0),0)
  NcpCheck(NeonCollisionLineCircle(-4.0,4.0,6.0,4.0,-2.0,5.0,5.0),1)
  NcpCheck(NeonCollisionLineCircle(11.0,-10.0,-9.0,-9.0,7.0,6.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-4.0,-1.0,-6.0,-12.0,-8.0,-7.0,5.0),1)
  NcpCheck(NeonCollisionLineCircle(-6.0,3.0,7.0,13.0,14.0,0.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-4.0,13.0,-15.0,-5.0,-3.0,-3.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(5.0,-5.0,9.0,14.0,-8.0,15.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(-12.0,-14.0,-13.0,-3.0,-10.0,15.0,5.0),0)
  NcpCheck(NeonCollisionLineCircle(-9.0,-12.0,-1.0,-3.0,-12.0,-12.0,4.0),1)
  NcpCheck(NeonCollisionLineCircle(-6.0,-4.0,-12.0,-8.0,6.0,-10.0,5.0),0)
  NcpCheck(NeonCollisionLineCircle(0.0,4.0,1.0,15.0,8.0,-13.0,3.0),0)
  NcpCheck(NeonCollisionLineCircle(-8.0,7.0,-8.0,-4.0,4.0,-6.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-10.0,1.0,5.0,15.0,-3.0,-14.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-8.0,13.0,10.0,-13.0,4.0,-13.0,0.0),0)
  NcpCheck(NeonCollisionLineCircle(-2.0,3.0,-12.0,-14.0,6.0,-1.0,2.0),0)
  NcpCheck(NeonCollisionLineCircle(2.0,-12.0,8.0,7.0,-3.0,0.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(-5.0,8.0,1.0,-11.0,13.0,4.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(14.0,-15.0,5.0,-15.0,6.0,13.0,3.0),0)
  NcpCheck(NeonCollisionLineCircle(-3.0,14.0,-14.0,6.0,13.0,-8.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(12.0,7.0,12.0,9.0,0.0,12.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(10.0,12.0,-15.0,7.0,3.0,-7.0,3.0),0)
  NcpCheck(NeonCollisionLineCircle(-1.0,-14.0,9.0,12.0,-13.0,6.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(-15.0,1.0,-12.0,14.0,-4.0,-15.0,0.0),0)
  NcpCheck(NeonCollisionLineCircle(-12.0,-8.0,0.0,-11.0,10.0,5.0,0.0),0)
  NcpCheck(NeonCollisionLineCircle(4.0,3.0,4.0,4.0,-14.0,5.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(-10.0,-11.0,15.0,1.0,-10.0,6.0,5.0),0)
  NcpCheck(NeonCollisionLineCircle(13.0,10.0,13.0,-3.0,12.0,15.0,3.0),0)
  NcpCheck(NeonCollisionLineCircle(13.0,-6.0,-14.0,14.0,-2.0,8.0,2.0),0)
  NcpCheck(NeonCollisionLineCircle(-14.0,-1.0,-15.0,-6.0,1.0,-14.0,6.0),0)
  NcpCheck(NeonCollisionLineCircle(1.0,-14.0,-5.0,-9.0,0.0,2.0,5.0),0)
  NcpCheck(NeonCollisionLineCircle(-3.0,3.0,-10.0,0.0,8.0,-13.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(7.0,-15.0,-11.0,-2.0,8.0,-3.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(11.0,-11.0,-3.0,7.0,-7.0,-7.0,6.0),0)
  NcpCheck(NeonCollisionLineCircle(-14.0,-10.0,13.0,13.0,-10.0,-13.0,5.0),1)
  NcpCheck(NeonCollisionLineCircle(0.0,-5.0,13.0,-11.0,7.0,14.0,7.0),0)
  NcpCheck(NeonCollisionLineCircle(-9.0,7.0,15.0,1.0,1.0,11.0,7.0),1)
  NcpCheck(NeonCollisionLineCircle(2.0,15.0,-5.0,2.0,7.0,-12.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(8.0,-5.0,12.0,1.0,15.0,12.0,5.0),0)
  NcpCheck(NeonCollisionLineCircle(-6.0,-13.0,-11.0,7.0,11.0,-10.0,5.0),0)
  NcpCheck(NeonCollisionLineCircle(-15.0,1.0,-7.0,-8.0,-2.0,0.0,3.0),0)
  NcpCheck(NeonCollisionLineCircle(-14.0,-9.0,-10.0,-12.0,-9.0,6.0,1.0),0)
  NcpCheck(NeonCollisionLineCircle(-3.0,6.0,11.0,2.0,14.0,-11.0,4.0),0)
  NcpCheck(NeonCollisionLineCircle(7.0,-12.0,-5.0,9.0,14.0,1.0,2.0),0)
  NcpCheck(NeonCollisionLineCircle(-7.0,9.0,-11.0,-15.0,-11.0,-10.0,2.0),1)
  NcpCheck(NeonCollisionLineCircle(-1.0,-11.0,1.0,5.0,-7.0,3.0,2.0),0)
  NcpCheck(NeonCollisionLineCircle(-7.0,-9.0,-4.0,-10.0,8.0,-1.0,2.0),0)
  NcpCheck(NeonCollisionLineCircle(-2.0,1.0,6.0,5.0,9.0,-5.0,5.0),0)
  NcpCheck(NeonCollisionAABB(0.0,0.0,1.0,1.0,1.0,0.0,1.0,1.0),0)
  NcpCheck(NeonCollisionAABB(0.0,0.0,0.0,1.0,-1.0,0.0,2.0,1.0),0)
  NcpCheck(NeonCollisionCircle(0.0,0.0,1.0,2.0,0.0,1.0),1)
  NcpCheck(NeonCollisionLineLine(0.0,0.0,1.0,1.0,1.0,1.0,2.0,0.0,0),0)
  NcpCheck(NeonCollisionLineLine(0.0,0.0,1.0,0.0,0.5,0.0,2.0,0.0,0),0)
  NcpCheck(NeonCollisionLineCircle(1.0,0.0,1.0,0.0,0.0,0.0,1.0),1)
  NcpCheck(NeonCollisionCircle(0.0,0.0,-1.0,0.0,0.0,1.0),-22500)
  NcpCheck(NeonCollisionAABB(MathFromBits($7FC00000),0.0,1.0,1.0,0.0,0.0,1.0,1.0),-22500)
  NcpCheck(NeonCollisionBezier(-0.1,0.0,0.0,1.0,1.0,2.0,2.0,3.0,3.0,@ncpHit),-22500)
  NcpCheck(NeonCollisionLineLine(0.0,0.0,10.0,10.0,0.0,10.0,10.0,0.0,@ncpHit),1)
  NcpCheck(MathBitsOf(ncpHit\x),1084227584)
  NcpCheck(MathBitsOf(ncpHit\y),1084227584)
  NcpCheck(NeonCollisionBezier(0.000000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[0]),0)
  NcpCheck(NeonCollisionBezier(0.050000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[1]),0)
  NcpCheck(NeonCollisionBezier(0.100000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[2]),0)
  NcpCheck(NeonCollisionBezier(0.150000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[3]),0)
  NcpCheck(NeonCollisionBezier(0.200000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[4]),0)
  NcpCheck(NeonCollisionBezier(0.250000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[5]),0)
  NcpCheck(NeonCollisionBezier(0.300000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[6]),0)
  NcpCheck(NeonCollisionBezier(0.350000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[7]),0)
  NcpCheck(NeonCollisionBezier(0.400000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[8]),0)
  NcpCheck(NeonCollisionBezier(0.450000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[9]),0)
  NcpCheck(NeonCollisionBezier(0.500000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[10]),0)
  NcpCheck(NeonCollisionBezier(0.550000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[11]),0)
  NcpCheck(NeonCollisionBezier(0.600000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[12]),0)
  NcpCheck(NeonCollisionBezier(0.650000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[13]),0)
  NcpCheck(NeonCollisionBezier(0.700000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[14]),0)
  NcpCheck(NeonCollisionBezier(0.750000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[15]),0)
  NcpCheck(NeonCollisionBezier(0.800000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[16]),0)
  NcpCheck(NeonCollisionBezier(0.850000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[17]),0)
  NcpCheck(NeonCollisionBezier(0.900000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[18]),0)
  NcpCheck(NeonCollisionBezier(0.950000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[19]),0)
  NcpCheck(NeonCollisionBezier(1.000000000,40.0,300.0,80.0,220.0,180.0,380.0,240.0,300.0,@ncpCurve[20]),0)
  For i=0 To 20 : PokeL(#NCP_REPORT+11008+i*8,MathBitsOf(ncpCurve[i]\x)) : PokeL(#NCP_REPORT+11012+i*8,MathBitsOf(ncpCurve[i]\y)) : Next
  For i=0 To 95 : ncpA[i]=$A5 : ncpB[i]=$A5 : Next
  NcpCheck(NeonCollisionMaskBind(@ncpMaskA,@ncpA[8],80,8,8,10),0)
  NcpCheck(NeonCollisionMaskBind(@ncpMaskB,@ncpB[8],80,8,8,10),0)
  For i=0 To 287 : ncpRGBA[i]=0 : Next
  For j=0 To 7 : For i=0 To 7 : ncpRGBA[j*36+i*4+3]=1 : Next : Next
  NcpCheck(NeonCollisionMaskFromRGBA(@ncpMaskA,@ncpRGBA[0],288,36),0)
  For j=0 To 7 : For i=0 To 7 : ncpB[8+j*10+i]=1 : Next : Next
  For i=0 To 287 : ncpRGBA[i]=0 : Next
  ncpRGBA[87]=255
  NcpCheck(NeonCollisionMaskFromRGBA(@ncpMaskA,@ncpRGBA[0],288,36),0)
  NcpCheck(ncpA[8],0) : NcpCheck(ncpA[31],1) : NcpCheck(ncpA[30],0)
  For j=0 To 7 : For i=0 To 7 : ncpRGBA[j*36+i*4+3]=1 : Next : Next
  NcpCheck(NeonCollisionMaskFromRGBA(@ncpMaskA,@ncpRGBA[0],288,36),0)
  For i=0 To 287 : ncpRGBA[i]=0 : Next
  NcpCheck(NeonCollisionMaskBind(@ncpMaskA,@ncpA[8],70,8,8,10),-22500)
  NcpCheck(ncpMaskA\bytes,80)
  NcpCheck(NeonCollisionMaskFromRGBA(@ncpMaskA,@ncpA[8],80,32),-22500)
  ncpTA\scale=1.0 : ncpTB\scale=1.0 : ncpTB\x=6.0 : ncpTB\y=6.0
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,1024),1)
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,1),-22503)
  ncpTB\x=100.0
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,1),0)
  ncpTA\x=3.125000000 : ncpTA\y=3.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=1.000000000
  ncpTB\x=4.375000000 : ncpTB\y=-7.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-0.875000000 : ncpTA\y=-0.750000000 : ncpTA\angle=0.000000000 : ncpTA\scale=1.000000000
  ncpTB\x=7.375000000 : ncpTB\y=9.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=4.125000000 : ncpTA\y=4.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=0.500000000
  ncpTB\x=8.375000000 : ncpTB\y=9.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-1.875000000 : ncpTA\y=-0.750000000 : ncpTA\angle=0.400000000 : ncpTA\scale=1.000000000
  ncpTB\x=-7.625000000 : ncpTB\y=-0.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=4.125000000 : ncpTA\y=-2.750000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=-6.625000000 : ncpTB\y=-4.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-3.875000000 : ncpTA\y=1.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=6.375000000 : ncpTB\y=-7.875000000 : ncpTB\angle=0.800000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=1.125000000 : ncpTA\y=-3.750000000 : ncpTA\angle=1.200000000 : ncpTA\scale=0.500000000
  ncpTB\x=9.375000000 : ncpTB\y=-7.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=0.125000000 : ncpTA\y=-0.750000000 : ncpTA\angle=1.200000000 : ncpTA\scale=0.500000000
  ncpTB\x=8.375000000 : ncpTB\y=-3.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=1.125000000 : ncpTA\y=4.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=1.000000000
  ncpTB\x=-2.625000000 : ncpTB\y=-6.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-1.875000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=2.000000000
  ncpTB\x=15.375000000 : ncpTB\y=12.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-3.875000000 : ncpTA\y=-0.750000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=5.375000000 : ncpTB\y=-4.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=3.125000000 : ncpTA\y=-3.750000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=1.000000000
  ncpTB\x=4.375000000 : ncpTB\y=7.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=3.125000000 : ncpTA\y=-2.750000000 : ncpTA\angle=0.400000000 : ncpTA\scale=2.000000000
  ncpTB\x=-4.625000000 : ncpTB\y=3.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=2.125000000 : ncpTA\y=-0.750000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=15.375000000 : ncpTB\y=-0.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=1.200000000 : ncpTA\scale=1.000000000
  ncpTB\x=-2.625000000 : ncpTB\y=12.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-1.875000000 : ncpTA\y=-2.750000000 : ncpTA\angle=0.400000000 : ncpTA\scale=1.000000000
  ncpTB\x=3.375000000 : ncpTB\y=13.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-3.875000000 : ncpTA\y=2.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=1.000000000
  ncpTB\x=-2.625000000 : ncpTB\y=9.125000000 : ncpTB\angle=0.800000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-3.875000000 : ncpTA\y=-1.750000000 : ncpTA\angle=1.200000000 : ncpTA\scale=0.500000000
  ncpTB\x=3.375000000 : ncpTB\y=14.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=1.125000000 : ncpTA\y=1.250000000 : ncpTA\angle=1.200000000 : ncpTA\scale=0.500000000
  ncpTB\x=-5.625000000 : ncpTB\y=-6.875000000 : ncpTB\angle=0.800000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-2.875000000 : ncpTA\y=-2.750000000 : ncpTA\angle=0.000000000 : ncpTA\scale=0.500000000
  ncpTB\x=-4.625000000 : ncpTB\y=14.125000000 : ncpTB\angle=0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-1.875000000 : ncpTA\y=-3.750000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=0.375000000 : ncpTB\y=-2.875000000 : ncpTB\angle=0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-0.875000000 : ncpTA\y=2.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=1.000000000
  ncpTB\x=7.375000000 : ncpTB\y=-5.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=4.125000000 : ncpTA\y=2.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=2.000000000
  ncpTB\x=8.375000000 : ncpTB\y=6.125000000 : ncpTB\angle=0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=2.125000000 : ncpTA\y=3.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=1.000000000
  ncpTB\x=13.375000000 : ncpTB\y=7.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=1.125000000 : ncpTA\y=-0.750000000 : ncpTA\angle=1.200000000 : ncpTA\scale=1.000000000
  ncpTB\x=15.375000000 : ncpTB\y=-1.875000000 : ncpTB\angle=0.800000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-3.875000000 : ncpTA\y=4.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=2.000000000
  ncpTB\x=-7.625000000 : ncpTB\y=-0.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-1.875000000 : ncpTA\y=-3.750000000 : ncpTA\angle=0.000000000 : ncpTA\scale=2.000000000
  ncpTB\x=13.375000000 : ncpTB\y=6.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-1.875000000 : ncpTA\y=0.250000000 : ncpTA\angle=1.200000000 : ncpTA\scale=1.000000000
  ncpTB\x=3.375000000 : ncpTB\y=-0.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=3.125000000 : ncpTA\y=2.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=2.000000000
  ncpTB\x=7.375000000 : ncpTB\y=-3.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=4.125000000 : ncpTA\y=-0.750000000 : ncpTA\angle=1.200000000 : ncpTA\scale=0.500000000
  ncpTB\x=3.375000000 : ncpTB\y=3.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-0.875000000 : ncpTA\y=-2.750000000 : ncpTA\angle=0.400000000 : ncpTA\scale=2.000000000
  ncpTB\x=3.375000000 : ncpTB\y=5.125000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=-2.875000000 : ncpTA\y=3.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=2.000000000
  ncpTB\x=3.375000000 : ncpTB\y=-3.875000000 : ncpTB\angle=0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpTA\x=2.125000000 : ncpTA\y=2.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=1.000000000
  ncpTB\x=1.375000000 : ncpTB\y=-6.875000000 : ncpTB\angle=-0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-0.875000000 : ncpTA\y=4.250000000 : ncpTA\angle=1.200000000 : ncpTA\scale=0.500000000
  ncpTB\x=-7.625000000 : ncpTB\y=16.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-2.875000000 : ncpTA\y=-1.750000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=-4.625000000 : ncpTB\y=14.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpTA\x=-2.875000000 : ncpTA\y=3.250000000 : ncpTA\angle=1.200000000 : ncpTA\scale=2.000000000
  ncpTB\x=14.375000000 : ncpTB\y=12.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=15
  ncpRows[1]=15
  ncpRows[2]=15
  ncpRows[3]=15
  ncpRows[4]=15
  ncpRows[5]=15
  ncpRows[6]=15
  ncpRows[7]=15
  ncpRows[8]=240
  ncpRows[9]=240
  ncpRows[10]=240
  ncpRows[11]=240
  ncpRows[12]=240
  ncpRows[13]=240
  ncpRows[14]=240
  ncpRows[15]=240
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.000000000 : ncpTA\y=0.000000000 : ncpTA\angle=0.000000000 : ncpTA\scale=1.000000000
  ncpTB\x=0.000000000 : ncpTB\y=0.000000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=0
  ncpRows[1]=0
  ncpRows[2]=0
  ncpRows[3]=0
  ncpRows[4]=0
  ncpRows[5]=0
  ncpRows[6]=0
  ncpRows[7]=0
  ncpRows[8]=72
  ncpRows[9]=5
  ncpRows[10]=218
  ncpRows[11]=59
  ncpRows[12]=163
  ncpRows[13]=207
  ncpRows[14]=221
  ncpRows[15]=82
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=0.500000000
  ncpTB\x=3.375000000 : ncpTB\y=11.125000000 : ncpTB\angle=0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=93
  ncpRows[1]=197
  ncpRows[2]=49
  ncpRows[3]=201
  ncpRows[4]=163
  ncpRows[5]=75
  ncpRows[6]=22
  ncpRows[7]=245
  ncpRows[8]=117
  ncpRows[9]=81
  ncpRows[10]=222
  ncpRows[11]=56
  ncpRows[12]=16
  ncpRows[13]=170
  ncpRows[14]=55
  ncpRows[15]=230
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=2.000000000
  ncpTB\x=-0.625000000 : ncpTB\y=3.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=223
  ncpRows[1]=192
  ncpRows[2]=238
  ncpRows[3]=111
  ncpRows[4]=95
  ncpRows[5]=243
  ncpRows[6]=83
  ncpRows[7]=36
  ncpRows[8]=167
  ncpRows[9]=128
  ncpRows[10]=168
  ncpRows[11]=146
  ncpRows[12]=41
  ncpRows[13]=14
  ncpRows[14]=166
  ncpRows[15]=18
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=1.000000000
  ncpTB\x=7.375000000 : ncpTB\y=1.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=43
  ncpRows[1]=100
  ncpRows[2]=89
  ncpRows[3]=69
  ncpRows[4]=119
  ncpRows[5]=170
  ncpRows[6]=100
  ncpRows[7]=85
  ncpRows[8]=245
  ncpRows[9]=3
  ncpRows[10]=123
  ncpRows[11]=38
  ncpRows[12]=22
  ncpRows[13]=136
  ncpRows[14]=177
  ncpRows[15]=191
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=-1.625000000 : ncpTB\y=12.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=134
  ncpRows[1]=173
  ncpRows[2]=30
  ncpRows[3]=118
  ncpRows[4]=58
  ncpRows[5]=13
  ncpRows[6]=111
  ncpRows[7]=88
  ncpRows[8]=174
  ncpRows[9]=24
  ncpRows[10]=194
  ncpRows[11]=174
  ncpRows[12]=245
  ncpRows[13]=87
  ncpRows[14]=88
  ncpRows[15]=52
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=11.375000000 : ncpTB\y=11.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=252
  ncpRows[1]=73
  ncpRows[2]=194
  ncpRows[3]=75
  ncpRows[4]=81
  ncpRows[5]=216
  ncpRows[6]=52
  ncpRows[7]=166
  ncpRows[8]=4
  ncpRows[9]=242
  ncpRows[10]=208
  ncpRows[11]=99
  ncpRows[12]=182
  ncpRows[13]=90
  ncpRows[14]=235
  ncpRows[15]=227
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=2.000000000
  ncpTB\x=11.375000000 : ncpTB\y=10.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=44
  ncpRows[1]=240
  ncpRows[2]=34
  ncpRows[3]=98
  ncpRows[4]=237
  ncpRows[5]=45
  ncpRows[6]=37
  ncpRows[7]=3
  ncpRows[8]=40
  ncpRows[9]=4
  ncpRows[10]=13
  ncpRows[11]=250
  ncpRows[12]=45
  ncpRows[13]=231
  ncpRows[14]=36
  ncpRows[15]=36
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=0.500000000
  ncpTB\x=9.375000000 : ncpTB\y=-2.875000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=95
  ncpRows[1]=71
  ncpRows[2]=111
  ncpRows[3]=157
  ncpRows[4]=31
  ncpRows[5]=116
  ncpRows[6]=55
  ncpRows[7]=131
  ncpRows[8]=33
  ncpRows[9]=138
  ncpRows[10]=32
  ncpRows[11]=235
  ncpRows[12]=121
  ncpRows[13]=233
  ncpRows[14]=0
  ncpRows[15]=153
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=1.000000000
  ncpTB\x=-6.625000000 : ncpTB\y=7.125000000 : ncpTB\angle=0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=22
  ncpRows[1]=255
  ncpRows[2]=195
  ncpRows[3]=186
  ncpRows[4]=58
  ncpRows[5]=24
  ncpRows[6]=13
  ncpRows[7]=85
  ncpRows[8]=175
  ncpRows[9]=236
  ncpRows[10]=78
  ncpRows[11]=135
  ncpRows[12]=26
  ncpRows[13]=77
  ncpRows[14]=45
  ncpRows[15]=149
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=3.375000000 : ncpTB\y=10.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=223
  ncpRows[1]=21
  ncpRows[2]=250
  ncpRows[3]=5
  ncpRows[4]=214
  ncpRows[5]=8
  ncpRows[6]=189
  ncpRows[7]=159
  ncpRows[8]=21
  ncpRows[9]=162
  ncpRows[10]=48
  ncpRows[11]=117
  ncpRows[12]=187
  ncpRows[13]=91
  ncpRows[14]=107
  ncpRows[15]=248
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=2.000000000
  ncpTB\x=-6.625000000 : ncpTB\y=-3.875000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=158
  ncpRows[1]=105
  ncpRows[2]=219
  ncpRows[3]=148
  ncpRows[4]=206
  ncpRows[5]=68
  ncpRows[6]=235
  ncpRows[7]=142
  ncpRows[8]=114
  ncpRows[9]=48
  ncpRows[10]=72
  ncpRows[11]=22
  ncpRows[12]=241
  ncpRows[13]=17
  ncpRows[14]=128
  ncpRows[15]=191
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=-5.625000000 : ncpTB\y=-0.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=18
  ncpRows[1]=244
  ncpRows[2]=244
  ncpRows[3]=89
  ncpRows[4]=70
  ncpRows[5]=241
  ncpRows[6]=193
  ncpRows[7]=32
  ncpRows[8]=58
  ncpRows[9]=155
  ncpRows[10]=160
  ncpRows[11]=215
  ncpRows[12]=202
  ncpRows[13]=197
  ncpRows[14]=181
  ncpRows[15]=116
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=1.000000000
  ncpTB\x=-0.625000000 : ncpTB\y=-7.875000000 : ncpTB\angle=0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=61
  ncpRows[1]=182
  ncpRows[2]=90
  ncpRows[3]=53
  ncpRows[4]=171
  ncpRows[5]=78
  ncpRows[6]=87
  ncpRows[7]=124
  ncpRows[8]=193
  ncpRows[9]=117
  ncpRows[10]=134
  ncpRows[11]=32
  ncpRows[12]=41
  ncpRows[13]=78
  ncpRows[14]=180
  ncpRows[15]=171
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=2.000000000
  ncpTB\x=-0.625000000 : ncpTB\y=10.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=78
  ncpRows[1]=117
  ncpRows[2]=244
  ncpRows[3]=241
  ncpRows[4]=130
  ncpRows[5]=41
  ncpRows[6]=244
  ncpRows[7]=54
  ncpRows[8]=107
  ncpRows[9]=163
  ncpRows[10]=130
  ncpRows[11]=188
  ncpRows[12]=218
  ncpRows[13]=169
  ncpRows[14]=86
  ncpRows[15]=233
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=2.000000000
  ncpTB\x=-3.625000000 : ncpTB\y=7.125000000 : ncpTB\angle=0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=139
  ncpRows[1]=25
  ncpRows[2]=196
  ncpRows[3]=153
  ncpRows[4]=181
  ncpRows[5]=226
  ncpRows[6]=93
  ncpRows[7]=167
  ncpRows[8]=76
  ncpRows[9]=40
  ncpRows[10]=148
  ncpRows[11]=62
  ncpRows[12]=120
  ncpRows[13]=122
  ncpRows[14]=180
  ncpRows[15]=3
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=-5.625000000 : ncpTB\y=8.125000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=216
  ncpRows[1]=153
  ncpRows[2]=58
  ncpRows[3]=132
  ncpRows[4]=11
  ncpRows[5]=170
  ncpRows[6]=82
  ncpRows[7]=244
  ncpRows[8]=141
  ncpRows[9]=121
  ncpRows[10]=87
  ncpRows[11]=63
  ncpRows[12]=98
  ncpRows[13]=28
  ncpRows[14]=232
  ncpRows[15]=197
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=0.500000000
  ncpTB\x=10.375000000 : ncpTB\y=-7.875000000 : ncpTB\angle=0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=176
  ncpRows[1]=16
  ncpRows[2]=100
  ncpRows[3]=236
  ncpRows[4]=51
  ncpRows[5]=49
  ncpRows[6]=75
  ncpRows[7]=46
  ncpRows[8]=12
  ncpRows[9]=158
  ncpRows[10]=202
  ncpRows[11]=70
  ncpRows[12]=52
  ncpRows[13]=125
  ncpRows[14]=186
  ncpRows[15]=168
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=1.000000000
  ncpTB\x=9.375000000 : ncpTB\y=-5.875000000 : ncpTB\angle=0.300000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=10
  ncpRows[1]=14
  ncpRows[2]=47
  ncpRows[3]=70
  ncpRows[4]=223
  ncpRows[5]=27
  ncpRows[6]=129
  ncpRows[7]=99
  ncpRows[8]=200
  ncpRows[9]=104
  ncpRows[10]=44
  ncpRows[11]=221
  ncpRows[12]=104
  ncpRows[13]=228
  ncpRows[14]=61
  ncpRows[15]=13
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=0.375000000 : ncpTB\y=5.125000000 : ncpTB\angle=0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=161
  ncpRows[1]=130
  ncpRows[2]=220
  ncpRows[3]=218
  ncpRows[4]=70
  ncpRows[5]=87
  ncpRows[6]=38
  ncpRows[7]=169
  ncpRows[8]=138
  ncpRows[9]=56
  ncpRows[10]=200
  ncpRows[11]=132
  ncpRows[12]=106
  ncpRows[13]=249
  ncpRows[14]=72
  ncpRows[15]=49
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=1.000000000
  ncpTB\x=12.375000000 : ncpTB\y=2.125000000 : ncpTB\angle=0.300000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=128
  ncpRows[1]=101
  ncpRows[2]=108
  ncpRows[3]=81
  ncpRows[4]=151
  ncpRows[5]=114
  ncpRows[6]=179
  ncpRows[7]=66
  ncpRows[8]=175
  ncpRows[9]=59
  ncpRows[10]=208
  ncpRows[11]=9
  ncpRows[12]=124
  ncpRows[13]=71
  ncpRows[14]=127
  ncpRows[15]=183
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=1.000000000
  ncpTB\x=1.375000000 : ncpTB\y=4.125000000 : ncpTB\angle=0.300000000 : ncpTB\scale=0.500000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),1)
  ncpRows[0]=139
  ncpRows[1]=104
  ncpRows[2]=223
  ncpRows[3]=26
  ncpRows[4]=253
  ncpRows[5]=243
  ncpRows[6]=91
  ncpRows[7]=29
  ncpRows[8]=215
  ncpRows[9]=41
  ncpRows[10]=221
  ncpRows[11]=208
  ncpRows[12]=153
  ncpRows[13]=253
  ncpRows[14]=79
  ncpRows[15]=242
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=-0.600000000 : ncpTA\scale=0.500000000
  ncpTB\x=7.375000000 : ncpTB\y=-7.875000000 : ncpTB\angle=0.000000000 : ncpTB\scale=1.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=136
  ncpRows[1]=66
  ncpRows[2]=69
  ncpRows[3]=85
  ncpRows[4]=80
  ncpRows[5]=49
  ncpRows[6]=27
  ncpRows[7]=32
  ncpRows[8]=65
  ncpRows[9]=159
  ncpRows[10]=80
  ncpRows[11]=128
  ncpRows[12]=221
  ncpRows[13]=55
  ncpRows[14]=72
  ncpRows[15]=219
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.000000000 : ncpTA\scale=0.500000000
  ncpTB\x=-1.625000000 : ncpTB\y=9.125000000 : ncpTB\angle=0.000000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=17
  ncpRows[1]=83
  ncpRows[2]=173
  ncpRows[3]=163
  ncpRows[4]=144
  ncpRows[5]=91
  ncpRows[6]=22
  ncpRows[7]=167
  ncpRows[8]=60
  ncpRows[9]=26
  ncpRows[10]=100
  ncpRows[11]=42
  ncpRows[12]=229
  ncpRows[13]=242
  ncpRows[14]=178
  ncpRows[15]=251
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\x=0.125000000 : ncpTA\y=0.250000000 : ncpTA\angle=0.400000000 : ncpTA\scale=0.500000000
  ncpTB\x=4.375000000 : ncpTB\y=-5.875000000 : ncpTB\angle=-0.800000000 : ncpTB\scale=2.000000000
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),0)
  ncpRows[0]=0
  ncpRows[1]=0
  ncpRows[2]=0
  ncpRows[3]=0
  ncpRows[4]=0
  ncpRows[5]=0
  ncpRows[6]=0
  ncpRows[7]=0
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),0)
  PokeI(#NCP_REPORT+12160+0*8,0)
  ncpRows[0]=1
  ncpRows[1]=2
  ncpRows[2]=4
  ncpRows[3]=8
  ncpRows[4]=16
  ncpRows[5]=32
  ncpRows[6]=64
  ncpRows[7]=128
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),0)
  PokeI(#NCP_REPORT+12160+1*8,0)
  ncpRows[0]=47
  ncpRows[1]=140
  ncpRows[2]=166
  ncpRows[3]=250
  ncpRows[4]=195
  ncpRows[5]=18
  ncpRows[6]=71
  ncpRows[7]=3
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),7)
  PokeI(#NCP_REPORT+12160+2*8,7)
  For i=0 To 6 : PokeL(#NCP_REPORT+12288+2*128+i*8,MathBitsOf(ncpTempHull[i]\x)) : PokeL(#NCP_REPORT+12292+2*128+i*8,MathBitsOf(ncpTempHull[i]\y)) : Next
  ncpRows[0]=208
  ncpRows[1]=18
  ncpRows[2]=29
  ncpRows[3]=214
  ncpRows[4]=226
  ncpRows[5]=195
  ncpRows[6]=226
  ncpRows[7]=201
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),6)
  PokeI(#NCP_REPORT+12160+3*8,6)
  For i=0 To 5 : PokeL(#NCP_REPORT+12288+3*128+i*8,MathBitsOf(ncpTempHull[i]\x)) : PokeL(#NCP_REPORT+12292+3*128+i*8,MathBitsOf(ncpTempHull[i]\y)) : Next
  ncpRows[0]=45
  ncpRows[1]=220
  ncpRows[2]=144
  ncpRows[3]=25
  ncpRows[4]=198
  ncpRows[5]=178
  ncpRows[6]=189
  ncpRows[7]=28
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),7)
  PokeI(#NCP_REPORT+12160+4*8,7)
  For i=0 To 6 : PokeL(#NCP_REPORT+12288+4*128+i*8,MathBitsOf(ncpTempHull[i]\x)) : PokeL(#NCP_REPORT+12292+4*128+i*8,MathBitsOf(ncpTempHull[i]\y)) : Next
  ncpRows[0]=181
  ncpRows[1]=145
  ncpRows[2]=127
  ncpRows[3]=220
  ncpRows[4]=105
  ncpRows[5]=46
  ncpRows[6]=71
  ncpRows[7]=133
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),4)
  PokeI(#NCP_REPORT+12160+5*8,4)
  For i=0 To 3 : PokeL(#NCP_REPORT+12288+5*128+i*8,MathBitsOf(ncpTempHull[i]\x)) : PokeL(#NCP_REPORT+12292+5*128+i*8,MathBitsOf(ncpTempHull[i]\y)) : Next
  ncpRows[0]=103
  ncpRows[1]=182
  ncpRows[2]=139
  ncpRows[3]=12
  ncpRows[4]=165
  ncpRows[5]=194
  ncpRows[6]=209
  ncpRows[7]=33
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),6)
  PokeI(#NCP_REPORT+12160+6*8,6)
  For i=0 To 5 : PokeL(#NCP_REPORT+12288+6*128+i*8,MathBitsOf(ncpTempHull[i]\x)) : PokeL(#NCP_REPORT+12292+6*128+i*8,MathBitsOf(ncpTempHull[i]\y)) : Next
  ncpRows[0]=79
  ncpRows[1]=182
  ncpRows[2]=14
  ncpRows[3]=224
  ncpRows[4]=125
  ncpRows[5]=41
  ncpRows[6]=149
  ncpRows[7]=125
  ncpRows[8]=0
  ncpRows[9]=0
  ncpRows[10]=0
  ncpRows[11]=0
  ncpRows[12]=0
  ncpRows[13]=0
  ncpRows[14]=0
  ncpRows[15]=0
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpTempHull[0],64,@ncpScratch[0],1024),6)
  PokeI(#NCP_REPORT+12160+7*8,6)
  For i=0 To 5 : PokeL(#NCP_REPORT+12288+7*128+i*8,MathBitsOf(ncpTempHull[i]\x)) : PokeL(#NCP_REPORT+12292+7*128+i*8,MathBitsOf(ncpTempHull[i]\y)) : Next
  ncpRows[0]=255
  ncpRows[1]=255
  ncpRows[2]=255
  ncpRows[3]=255
  ncpRows[4]=255
  ncpRows[5]=255
  ncpRows[6]=255
  ncpRows[7]=255
  ncpRows[8]=255
  ncpRows[9]=255
  ncpRows[10]=255
  ncpRows[11]=255
  ncpRows[12]=255
  ncpRows[13]=255
  ncpRows[14]=255
  ncpRows[15]=255
  For j=0 To 7 : For i=0 To 7
    ncpA[8+j*10+i]=(ncpRows[j]>>i) & 1 : ncpB[8+j*10+i]=(ncpRows[j+8]>>i) & 1
  Next : Next
  ncpTA\scale=0.0
  NcpCheck(NeonCollisionPixel(@ncpMaskA,@ncpTA,@ncpMaskB,@ncpTB,4096),-22500)
  NcpCheck(NeonCollisionHullScratchBytes(8),400)
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpHull[0],64,@ncpScratch[0],1024),4)
  NcpCheck(NeonCollisionPolygonValidate(@ncpHull[0],4),0)
  For i=0 To 3 : PokeL(#NCP_REPORT+12032+i*8,MathBitsOf(ncpHull[i]\x)) : PokeL(#NCP_REPORT+12036+i*8,MathBitsOf(ncpHull[i]\y)) : Next
  ncpPoly[0]\x=123.0 : ncpPoly[0]\y=456.0
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpPoly[0],3,@ncpScratch[0],1024),-22502)
  NcpCheck(MathBitsOf(ncpPoly[0]\x),1123418112)
  NcpCheck(MathBitsOf(ncpPoly[0]\y),1139015680)
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpPoly[0],8,@ncpScratch[0],399),-22502)
  NcpCheck(NeonCollisionHull(@ncpMaskA,@ncpScratch[0],8,@ncpScratch[0],1024),-22500)
  ncpPoly[0]\x=0.0 : ncpPoly[0]\y=0.0
  ncpPoly[1]\x=6.0 : ncpPoly[1]\y=0.0
  ncpPoly[2]\x=2.0 : ncpPoly[2]\y=5.0
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-9.0,1.0,@ncpPoly[0],3,-11.0,-7.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-7.0,-4.0,@ncpPoly[0],3,10.0,-11.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,10.0,2.0,@ncpPoly[0],3,-11.0,9.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-5.0,7.0,@ncpPoly[0],3,-12.0,-5.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-12.0,4.0,@ncpPoly[0],3,-9.0,-1.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-11.0,-11.0,@ncpPoly[0],3,4.0,-11.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,0.0,-10.0,@ncpPoly[0],3,10.0,-11.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,5.0,-8.0,@ncpPoly[0],3,-9.0,-11.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-2.0,9.0,@ncpPoly[0],3,6.0,8.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-3.0,1.0,@ncpPoly[0],3,-11.0,1.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-12.0,-5.0,@ncpPoly[0],3,3.0,5.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,3.0,-11.0,@ncpPoly[0],3,-10.0,-2.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-7.0,-6.0,@ncpPoly[0],3,9.0,2.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-1.0,0.0,@ncpPoly[0],3,9.0,0.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,12.0,11.0,@ncpPoly[0],3,12.0,8.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,10.0,-3.0,@ncpPoly[0],3,-4.0,8.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-10.0,3.0,@ncpPoly[0],3,10.0,4.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-3.0,-9.0,@ncpPoly[0],3,-9.0,9.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,10.0,-10.0,@ncpPoly[0],3,-12.0,-10.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,4.0,7.0,@ncpPoly[0],3,-12.0,-5.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,0.0,1.0,@ncpPoly[0],3,-3.0,7.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-10.0,0.0,@ncpPoly[0],3,-6.0,1.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,4.0,-4.0,@ncpPoly[0],3,11.0,0.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,2.0,-5.0,@ncpPoly[0],3,5.0,4.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,10.0,-10.0,@ncpPoly[0],3,6.0,8.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,6.0,11.0,@ncpPoly[0],3,0.0,-10.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-10.0,12.0,@ncpPoly[0],3,7.0,-1.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,11.0,2.0,@ncpPoly[0],3,12.0,6.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-4.0,-4.0,@ncpPoly[0],3,1.0,11.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-9.0,10.0,@ncpPoly[0],3,-10.0,8.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,8.0,0.0,@ncpPoly[0],3,11.0,-12.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,12.0,-8.0,@ncpPoly[0],3,6.0,-1.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-6.0,-1.0,@ncpPoly[0],3,-4.0,-5.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,2.0,6.0,@ncpPoly[0],3,-1.0,-2.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-2.0,-5.0,@ncpPoly[0],3,-1.0,-3.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-9.0,4.0,@ncpPoly[0],3,-1.0,-8.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,0.0,-5.0,@ncpPoly[0],3,10.0,4.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,4.0,-3.0,@ncpPoly[0],3,-1.0,-5.0),1)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-3.0,-11.0,@ncpPoly[0],3,-3.0,12.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,10.0,12.0,@ncpPoly[0],3,-8.0,-2.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-5.0,-11.0,@ncpPoly[0],3,-11.0,1.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,8.0,3.0,@ncpPoly[0],3,12.0,-9.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,1.0,-1.0,@ncpPoly[0],3,0.0,8.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,-8.0,1.0,@ncpPoly[0],3,0.0,-4.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,1.0,-8.0,@ncpPoly[0],3,5.0,0.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,5.0,11.0,@ncpPoly[0],3,-4.0,2.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,2.0,-3.0,@ncpPoly[0],3,-1.0,2.0),0)
  NcpCheck(NeonCollisionSAT(@ncpHull[0],4,6.0,-12.0,@ncpPoly[0],3,-10.0,-8.0),0)
  ncpPoly[0]\x=0.0 : ncpPoly[0]\y=0.0
  ncpPoly[1]\x=1.0 : ncpPoly[1]\y=0.0
  ncpPoly[2]\x=2.0 : ncpPoly[2]\y=0.0
  NcpCheck(NeonCollisionPolygonValidate(@ncpPoly[0],3),-22501)
  ncpPoly[0]\x=0.0 : ncpPoly[0]\y=0.0
  ncpPoly[1]\x=4.0 : ncpPoly[1]\y=0.0
  ncpPoly[2]\x=1.0 : ncpPoly[2]\y=1.0
  ncpPoly[3]\x=4.0 : ncpPoly[3]\y=4.0
  ncpPoly[4]\x=0.0 : ncpPoly[4]\y=4.0
  NcpCheck(NeonCollisionPolygonValidate(@ncpPoly[0],5),-22501)
  ncpPoly[0]\x=0.0 : ncpPoly[0]\y=0.0
  ncpPoly[1]\x=4.0 : ncpPoly[1]\y=0.0
  ncpPoly[2]\x=4.0 : ncpPoly[2]\y=4.0
  ncpPoly[3]\x=0.0 : ncpPoly[3]\y=0.0
  ncpPoly[4]\x=0.0 : ncpPoly[4]\y=4.0
  NcpCheck(NeonCollisionPolygonValidate(@ncpPoly[0],5),-22501)
  ncpPoly[0]\x=0.0 : ncpPoly[0]\y=0.0
  ncpPoly[1]\x=4.0 : ncpPoly[1]\y=4.0
  ncpPoly[2]\x=0.0 : ncpPoly[2]\y=4.0
  ncpPoly[3]\x=4.0 : ncpPoly[3]\y=0.0
  NcpCheck(NeonCollisionPolygonValidate(@ncpPoly[0],4),-22501)
  n=0
  For i=0 To 7 : If ncpA[i]<>$A5 Or ncpA[88+i]<>$A5 : n=n+1 : EndIf : Next
  For i=0 To 7 : If ncpA[8+i*10+8]<>$A5 Or ncpA[8+i*10+9]<>$A5 : n=n+1 : EndIf : Next
  NcpCheck(n,0)
  NcpCheck(NeonServiceBind(services,35),0)
  NcpCheck(NeonServiceOpen(),0)
  NcpCheck(NeonServiceCanvas(640,400),0)
  font=NeonServiceFontRegister(0,1,14)
  NcpCheck(Bool(font>0),1)
  NcpCheck(NeonServicePrepare(font,"Collision, convex hull and cubic curve"),0)
  NcpCheck(NeonServiceBegin(0.04,0.05,0.07,1.0),0)
  NcpCheck(NeonServiceText(font,20.0,15.0,"Collision, convex hull and cubic curve",0.9,0.9,0.9,1.0),0)
  NcpCheck(NeonServiceBox(40.0,60.0,100.0,75.0,0.2,0.4,0.6,1.0),0)
  NcpCheck(NeonServiceBox(120.0,100.0,100.0,75.0,0.2,0.7,0.4,1.0),0)
  NcpCheck(NeonServicePolygon(350.0,100.0,40.0,40.0,48,0.7,0.5,0.2,1.0,1),0)
  NcpCheck(NeonServicePolygon(430.0,100.0,40.0,40.0,48,0.5,0.3,0.8,1.0,1),0)
  For i=0 To 3
    j=(i+1) % 4
    ncpLines[i*4]=480.0+(ncpHull[i]\x+4.0)*12.0 : ncpLines[i*4+1]=210.0+(ncpHull[i]\y+4.0)*12.0
    ncpLines[i*4+2]=480.0+(ncpHull[j]\x+4.0)*12.0 : ncpLines[i*4+3]=210.0+(ncpHull[j]\y+4.0)*12.0
  Next
  NcpCheck(NeonServiceStaticLines(@ncpLines[0],64,8,1.0,0.5,0.2,1.0,0),0)
  For i=0 To 19
    ncpLines[i*4]=ncpCurve[i]\x : ncpLines[i*4+1]=ncpCurve[i]\y
    ncpLines[i*4+2]=ncpCurve[i+1]\x : ncpLines[i*4+3]=ncpCurve[i+1]\y
  Next
  NcpCheck(NeonServiceStaticLines(@ncpLines[0],320,40,0.3,0.8,1.0,1.0,0),0)
  NcpCheck(NeonServiceEnd(),0)
  PokeI(#NCP_REPORT+32,4) : PokeI(#NCP_REPORT+40,font)
  ProcedureReturn ncpFailure
EndProcedure
