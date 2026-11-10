; Shared resident service state; include after the Neon font/sprite port types.
Global avsLogicalW.i,avsLogicalH.i
Global avsCopyDmaTicks.i,avsCopyCleanTicks.i,avsCopyPublishTicks.i
Global avsContext.i, avsEpoch.i, avsReady.i, avsFrame.i, avsFontCount.i, avsError.i
Global Dim avsFont.NeonVkPortFontRef[32]
Global Dim avsSprite.NeonVkPortSpriteRef[#NEON_SERVICE_MAX_SPRITES]
Global Dim avsSpriteHandle.i[#NEON_SERVICE_MAX_SPRITES]
Global avsSpriteClock.i,avsBatch.i
Global Dim avsOwnedFont.i[#NEON_SERVICE_MAX_FONT_ASSETS]
Global avsPreviousFont.i=-1,avsPreviousFontGeneration.i
Global avsParticleReady.i,avsParticleCount.i
Global avsParticleCameraX.f,avsParticleCameraY.f,avsParticleCameraZoom.f
Global avsEndFrames.i,avsEndFailed.i,avsEndWorstFrame.i,avsEndWorstRc.i
Global Dim avsEndTotal.i[6]
Global Dim avsEndWorst.i[6]

