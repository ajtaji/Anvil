; Stable shared service result codes; no device or ownership state.
#SVC_ENOSYS    = -100    ; this slot is not implemented in this Anvil
#SVC_ENOCAP    = -101    ; the board does not offer this capability group
#SVC_EARG      = -102    ; a bad argument
#SVC_EBUSY     = -103    ; the resource is in use
#SVC_ETIMEOUT  = -104    ; the operation did not complete in its bound
#SVC_EIO       = -105    ; the hardware answered, and answered badly
#SVC_EPERM     = -106    ; refused on purpose - see the note it comes with
#SVC_EFLAG     = -107    ; the container did not declare the flag this needs
#SVC_ESTATE    = -108    ; called in the wrong order
#SVC_EABI      = -109    ; this table is OLDER than the payload was built
                         ; against - see the version gate below
#SVC_EAGAIN    = -110    ; NEW AT 1.5. Not finished yet, and not failed:
                         ; the operation was started and a later call with
                         ; the same arguments carries on with it. Only the
                         ; net group answers it (a name being resolved, a
                         ; link still being given an address), because only
                         ; the net group starts work that outlives one call.

; The bounds the gate checks. Stated as constants so the gate reads them
; rather than transcribing them, and so a reader sees the reservation.
#SVC_ERR_LO    = -199    ; the #SVC_* range is -100 .. -199 inclusive
#SVC_ERR_HI    = -100
