; ======================================================================
;  PMFMOD v1 - THE SHARED DRIVER-MODULE CONTAINER FORMAT
; ----------------------------------------------------------------------
;  This file is constants only. It is the one numeric source the compiler
;  writer and Anvil loader consume; neither side keeps a private copy of
;  header offsets, relocation ids, limits or architecture ids.
;
;  v1 is a 160-byte little-endian header, followed by image bytes, zero
;  padding to eight bytes, 16-byte relocation records, then fixed 64-byte
;  compatible-id records. The SHA-256 covers the entire container except
;  the digest field itself (bytes 96..127). It detects damage; it is not
;  authentication and it is not a sandbox.
; ======================================================================

#PMFMOD_VERSION       = 1
#PMFMOD_HEADER_BYTES  = 160
#PMFMOD_DIGEST_BYTES  = 32
#PMFMOD_RELOC_BYTES   = 16
#PMFMOD_MATCH_BYTES   = 64
#PMFMOD_MATCH_MAX     = 8
#PMFMOD_SEAM_MAX      = 4
#PMFMOD_LOAD_ALIGN    = 4096
#PMFMOD_BSS_ALIGN     = 16

; "PMFMOD" followed by two NUL bytes.
#PMFMOD_MAGIC_0 = $50
#PMFMOD_MAGIC_1 = $4D
#PMFMOD_MAGIC_2 = $46
#PMFMOD_MAGIC_3 = $4D
#PMFMOD_MAGIC_4 = $4F
#PMFMOD_MAGIC_5 = $44
#PMFMOD_MAGIC_6 = 0
#PMFMOD_MAGIC_7 = 0

; Header offsets.
#PMFMOD_OFF_MAGIC        = 0
#PMFMOD_OFF_VERSION      = 8
#PMFMOD_OFF_HEADER_BYTES = 12
#PMFMOD_OFF_ABI_MAJOR    = 16
#PMFMOD_OFF_ABI_MINOR    = 20
#PMFMOD_OFF_SEAM_COUNT   = 24
#PMFMOD_OFF_FLAGS        = 28
#PMFMOD_OFF_IMAGE_BYTES  = 32
#PMFMOD_OFF_BSS_OFFSET   = 40
#PMFMOD_OFF_BSS_BYTES    = 48
#PMFMOD_OFF_INIT_OFFSET  = 56
#PMFMOD_OFF_RELOC_COUNT  = 64
#PMFMOD_OFF_RELOC_OFFSET = 68
#PMFMOD_OFF_ALIGN        = 72
#PMFMOD_OFF_ARCH         = 76
#PMFMOD_OFF_SEAMS        = 80
#PMFMOD_OFF_SHA256       = 96
#PMFMOD_OFF_MATCH_COUNT  = 128
#PMFMOD_OFF_MATCH_OFFSET = 132
#PMFMOD_OFF_PROBE_OFFSET = 136
#PMFMOD_OFF_QUIESCE      = 144
#PMFMOD_OFF_RESERVED1    = 152

; No v1 flag promises reload. Reload remains unsupported until stable core
; trampolines, in-flight accounting and a quiesce transaction exist.
#PMFMOD_FLAGS_V1 = 0

; Architecture ids.
#PMFMOD_ARCH_AARCH64 = 1

; Unused seam cells are canonical all-ones values.
#PMFMOD_SEAM_UNUSED = $FFFFFFFF

; Relocation entry offsets and kinds.
#PMFMOD_REL_OFF_SITE     = 0
#PMFMOD_REL_OFF_KIND     = 4
#PMFMOD_REL_OFF_RESERVED = 6
#PMFMOD_REL_OFF_ADDEND   = 8

#MREL_NONE      = 0
#MREL_ADRP_PAGE = 1
#MREL_ADD_LO12  = 2
#MREL_ABS64     = 3
#MREL_MOVW_G0   = 4
#MREL_MOVW_G1   = 5
#MREL_MOVW_G2   = 6
#MREL_MOVW_G3   = 7
#MREL_CALL26    = 8

; Engine results. Existing design codes keep their assigned values; the
; parser-only additions start at 13 and do not claim service-table slots.
#MOD_OK                  = 0
#MOD_ERR_MAGIC           = 1
#MOD_ERR_VERSION         = 2
#MOD_ERR_ABI_MAJOR       = 3
#MOD_ERR_ABI_MINOR       = 4
#MOD_ERR_HASH            = 5
#MOD_ERR_SEAM_TAKEN      = 6
#MOD_ERR_SEAM_UNDECLARED = 7
#MOD_ERR_ARENA_FULL      = 8
#MOD_ERR_RELKIND         = 9
#MOD_ERR_ALIGN           = 10
#MOD_ERR_INIT            = 11
#MOD_ERR_FILE            = 12
#MOD_ERR_HEADER          = 13
#MOD_ERR_RANGE           = 14
#MOD_ERR_MATCH           = 15
#MOD_ERR_RELOC           = 16
#MOD_ERR_ARCH            = 17
#MOD_ERR_RECORDS_FULL    = 18
#MOD_ERR_OVERLAP         = 19
#MOD_ERR_SYNC            = 20

; Record states owned by the engine. READY means verified, relocated,
; zero-initialised and cache-synchronised, not probed or activated.
#MOD_STATE_EMPTY = 0
#MOD_STATE_READY = 1
