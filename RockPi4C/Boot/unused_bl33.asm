; The Rockchip miniloader may require a normal-world image before entering BL31.
; Anvil is resident EL3 and never transfers here. Refuse any accidental entry.
_start:
  msr daifset, #15
park:
  wfe
  b park
