; ======================================================================
;  hal.pi4 - the capability model and the HAL seam contract.
;
;  Anvil is one core built for many boards (Anvil/ARCHITECTURE.md). The
;  core names no chip; where it needs the machine it calls a Hw* entry
;  point the BOARD supplies, and where a whole class of hardware may be
;  absent it asks the board a yes/no question FIRST. This file is the two
;  pieces of that machinery that are themselves chip-free, so they live
;  with the core rather than with any one board:
;
;    1. RequireCap()   the gate. Reads a capability the board declared and
;                      either lets a command proceed or refuses it with an
;                      honest, whole-sentence message and returns cleanly.
;                      It contains NO chip knowledge - it is handed the
;                      answer, it does not work it out.
;
;    2. #HW_* codes    the PORTABLE vocabulary the Hw* seam speaks back to
;                      the core, so a command can render a pin's mode or a
;                      pull direction without knowing that on THIS part an
;                      input is FSEL 000 and ALT5 is the code 2. The board
;                      backend translates its silicon's raw encodings into
;                      these; the core only ever sees these.
;
;  WHY THIS IS "THE SEAM" AND NOT JUST TWO HELPERS. Everything the roadmap
;  is about to add - gpio, i2c, mmc, usb, booti, dhcp/ping - is core logic
;  riding a board backend. This file names the groups, fixes the gate, and
;  writes down the contract each family builds against, so that the worker
;  who adds `ping` next month and the worker who adds `i2c` after them are
;  building against a real API and not a guess. Read this before adding a
;  family; the naming here is the API, not a suggestion.
; ======================================================================
;
; ----------------------------------------------------------------------
;  THE CAPABILITY MODEL - what "may not be feasible on every device" IS
; ----------------------------------------------------------------------
;  Stated 2026-09-01: "be aware may not be feasible on every device. anvil
;  is multi device ... anvil will target many future devices, write it so
;  that its completely modular." This is that, implemented as a MODEL
;  rather than as absence.
;
;  Each board is its own compile target - RaspberryPi4/Board/board.pi4,
;  ArduinoQ/Board/board.unoq, and "many future devices" after them. A board
;  DECLARES, as compile-time constants in its own board.pi4, which
;  capability GROUPS it offers to Anvil's command families:
;
;      #CAP_STORAGE   #CAP_NET   #CAP_GPIO   #CAP_I2C
;      #CAP_MMC       #CAP_USB   #CAP_BOOT_EL1  #CAP_PWM
;
;  ... and, since 2026-09-04 and the payload ABI (Anvil/Hal/abi.pbi),
;  seven more, added by exactly the mechanism the ADDING A NEW CAPABILITY
;  GROUP paragraph below describes:
;
;      #CAP_CONSOLE   #CAP_TOUCH   #CAP_GNSS   #CAP_UART
;      #CAP_SPI       #CAP_VEHLINK #CAP_RTC
;
;  Nothing about the model changed to admit them. The gate takes the flag
;  as a value, so the set of groups is open, and each of the seven has its
;  Hw<GROUP>* contract in the SEAM GROUPS section below like every other.
;
;  1 means "this board offers this hardware group to Anvil - a family
;  gated behind it may assume the board's Hw<group> backend is present and
;  works". 0 means "Anvil cannot reach this group here" - because the
;  board genuinely has no such hardware, or because no backend for it has
;  been written for this board yet. From the operator's seat those are the
;  same fact, and the same honest refusal, so one flag carries both.
;
;  WHY COMPILE-TIME CONSTANTS, AND NOT A RUNTIME PROBE. Three reasons, and
;  they line up with the precedent already in this tree (#ANVIL_CACHE in
;  RaspberryPi4/Board/cache.pi4, #ANVIL_V3D_CONSOLE and #DSP_DMA_LINKED in
;  board.pi4):
;
;    * IT IS BOARD KNOWLEDGE, KNOWN WHEN THE BOARD IS CHOSEN. Building a
;      board already IS choosing its hardware includes; declaring what
;      those includes provide belongs in the same file, one line each,
;      reviewable against the board.
;    * IT KEEPS THE CORE CHIP-FREE. RequireCap is handed a number. It
;      never asks "which board is this" - there is no such question in the
;      core, and adding one would be the fork this whole split exists to
;      prevent. The board declares; the core reads.
;    * NO PER-BOARD #ifdef FOREST. A command is compiled once, for every
;      board, and DEGRADES AT RUN TIME through the gate. There is no
;      CompilerIf on a chip name anywhere in the core, and there is no
;      second copy of a command for the board that lacks the hardware.
;
;  THIS IS NOT KB-GATING, AND THE DISTINCTION IS LOAD-BEARING. The U-Boot
;  inventory (Raspberry Pi 4/U-Boot command and feature inventory.md, S5
;  point 7) warns in as many words: "resist per-build feature gating even
;  when it would save a few KB ... Ours is always the same commands."
;  A capability is NEVER set to 0 to make an image smaller on a board that
;  HAS the hardware and a working backend. It is 0 only when the group is
;  genuinely out of Anvil's reach on that board. Genuinely-absent hardware
;  is legitimately absent; present hardware is never hidden to save space.
;
;  MEMORY OPS NEED NO CAPABILITY. receive, run, memory, write, fill, copy,
;  compare, crc32, base and the transfer protocol are universal - every
;  device that can run Anvil has RAM and a way in. They are gated by
;  nothing and ride no Hw* group. The capability model is for hardware a
;  device may simply not have.
;
;  THEY DO, HOWEVER, ASK THE BOARD WHETHER AN ADDRESS IS SAFE TO TOUCH.
;  That is not a capability and it is not a gate on a hardware GROUP - it
;  is a question about one range, asked and answered per command, through
;  the HwAddr* seam described below. The distinction matters: RequireCap
;  refuses a whole command on a board that cannot do it at all, while
;  HwAddrCheck refuses ONE ADDRESS on a board that can perfectly well do
;  the command everywhere else.
;
;  ADDING A NEW CAPABILITY GROUP. A future family that needs a class of
;  hardware none of these seven names covers (say a real-time clock, or a
;  CAN controller) adds one #CAP_<GROUP> per board.pi4, documents the
;  Hw<GROUP>* seam it calls in the SEAM GROUPS section below, and gates its
;  command with RequireCap. Nothing in this file has to change to add one -
;  the gate takes the flag as a value, so the set of groups is open.
;
; ----------------------------------------------------------------------
;  THE SEAM GROUPS - the Hw* entry points each family calls
; ----------------------------------------------------------------------
;  A family never touches a register. It calls a Hw<Group><Op> the board
;  supplies, and the board is the only thing that knows the part. These
;  are the group names the roadmap needs; a board provides the ones its
;  capability flags claim, and a clean "unsupported" path (via the gate)
;  for the ones they do not.
;
;    HwGpio*   (#CAP_GPIO)  general-purpose I/O. IMPLEMENTED as the
;              demonstrator of this whole model - see Anvil/Core/gpio_cmd.pbi
;              and, on the Pi 4, RaspberryPi4/Board/hw_gpio.pi4 over
;              RaspberryPi4/Lib/gpio.pi4. The read seam the `gpio` command
;              uses today:
;                 HwGpioCount()          how many GPIO lines exist
;                 HwGpioUserMax()        highest pin on the user header, -1
;                                        if the board has no such header
;                 HwGpioModeGet(pin)     #HW_GPIO_IN / _OUT / _ALT, or -1
;                 HwGpioAltGet(pin)      alt number 0..N for an ALT pin,
;                                        else -1 (the board owns the
;                                        silicon's ALT numbering)
;                 HwGpioLevelGet(pin)    0, 1, or -1 for a bad pin
;                 HwGpioPullGet(pin)     #HW_PULL_NONE / _UP / _DOWN, -1
;              and the write seam the fuller gpio family rides:
;                 HwGpioMode(pin, mode)  mode is a #HW_GPIO_* code
;                 HwGpioWrite(pin, lvl)  lvl 0 clears, non-zero sets
;                 HwGpioToggle(pin)
;                 HwGpioReservedReason(pin)  0 if the pin is free for the
;                                        operator to reconfigure, else the
;                                        ADDRESS of a lowercase fragment
;                                        naming the on-board function that
;                                        owns the pin - it reads after
;                                        "GPIO n is ", printed by the core
;                                        with UartWriteStr the same way
;                                        RequireCap prints *reason. This
;                                        gates WRITES only: reading a pin is
;                                        always allowed for diagnostics. The
;                                        BOARD owns the list, because which
;                                        pins carry the console, the card and
;                                        the radio is chip-and-wiring
;                                        knowledge and the core must stay
;                                        chip-free - it prints the sentence
;                                        the board hands back and never
;                                        learns which pins those are.
;
;    HwStorage* (#CAP_STORAGE)  a block medium plus a filesystem, for
;              load / save / mount / (future) fatls / ls. The Pi 4 backend
;              is already in RaspberryPi4/Board/storage.pi4: StorageUp()
;              brings a medium up and reports which, and the FAT layer
;              takes its block reader/writer by pointer (FatSetBlockReader
;              / FatSetBlockWriter over MscReadBlock / SdReadBlock). These
;              existing entry points ARE the storage seam; a later pass may
;              rename them Hw* for uniformity, which is cosmetic and out of
;              scope here.
;
;    HwFile*   (#CAP_STORAGE, same group)  THE FILE-LEVEL OPERATION, and
;              the reason it exists beside the block-level one above is
;              worth stating rather than discovering.
;
;              The Pi 4's storage is a BLOCK device with our own FAT
;              driver on top of it: the board hands fat.pi4 a sector
;              reader and the core walks directories itself. The Arduino
;              UNO Q has no such thing and never will from inside Anvil -
;              it runs as a UEFI application with boot services up, and
;              the firmware owns the eMMC. What the Q HAS is a FILE
;              SERVICE: EFI_SIMPLE_FILE_SYSTEM_PROTOCOL on the EFI System
;              Partition, which opens a file BY NAME and gives back its
;              bytes. There is no sector to read and no FAT to parse.
;
;              Two boards, two levels. If the core asked for the Pi 4's
;              level, the Q could not answer; if it asked for the Q's, the
;              Pi 4 would have to pretend. So the seam is defined at the
;              level THE CORE ACTUALLY NEEDS - and for `boot <file>`,
;              `settings load` and `settings save` that need is exactly
;              open-by-name, size, read-at-offset, write-whole, close.
;              Both boards can provide that honestly: the Pi 4 over
;              fat.pi4 (RaspberryPi4/Board/hw_file.pi4), the Q over UEFI
;              (ArduinoQ/Board/hw_file_q.unoq).
;
;                 HwStorageUp()          bring the medium up and report
;                                        1 ready / 0 with a reason already
;                                        printed. A COMMAND calls this
;                                        once before it reads files; the
;                                        file operations below do not, and
;                                        that is deliberate - on the Pi 4
;                                        bringing the medium up enumerates
;                                        PCIe, xHCI and USB mass storage
;                                        and prints a paragraph, which is
;                                        not something a getter may do. It
;                                        is also the contract that already
;                                        held before this seam existed:
;                                        SettingsLoad has never brought a
;                                        medium up.
;                 HwFileOpen(*name)      open one file by name for
;                                        reading, on the medium that is
;                                        already up. 1 on success, 0 on
;                                        failure with HwFileLastError()
;                                        set.
;                 HwFileSize()           the open file's length in bytes
;                 HwFileReadAt(off, dst, n)
;                                        n bytes from byte offset `off` of
;                                        the open file into memory at dst.
;                                        Returns the count actually read,
;                                        or -1 on a medium error. AN
;                                        OFFSET, not a stream position,
;                                        deliberately: the container
;                                        reader below reads a header into
;                                        the monitor's own memory and THEN
;                                        reads the image to a completely
;                                        different address, and a seam
;                                        with a hidden cursor makes that
;                                        an ordering puzzle instead of two
;                                        statements.
;                 HwFileClose()          release it. Safe to call twice.
;                 HwFileWritable()       1 if HwFileWriteAll can work at
;                                        all on this board right now. THE
;                                        WRITE GATE, the same discipline
;                                        HwMmcCanWrite() sets: a board
;                                        whose medium is readable but not
;                                        writable answers 0 and the caller
;                                        refuses loudly instead of finding
;                                        out half way through a file.
;                 HwFileWriteAll(*name, src, n)
;                                        replace the whole of that file
;                                        with n bytes from src, creating
;                                        it if it is not there and
;                                        resizing it to match. 1 or 0.
;                                        WHOLE-FILE, not a stream: every
;                                        writer the core has - the
;                                        settings store - rewrites its
;                                        file completely, and a partial
;                                        write API would be a capability
;                                        nothing uses and every board has
;                                        to implement.
;                                        THAT REASONING WAS CORRECT AND IT
;                                        IS NOW OUT OF DATE - see
;                                        HwFileAppend immediately below.
;                 HwFileAppend(*name, src, n)
;                                        APPEND n bytes to the end of that
;                                        file, creating it if it is not
;                                        there. Returns a #HW_FILE_* code.
;
;                                        WHY IT EXISTS, when the paragraph
;                                        above says a partial write API is
;                                        a capability nothing uses. RULE 11:
;                                        a recipe's step dies with its
;                                        reason, and this reason has died.
;                                        The settings store was the only
;                                        writer when that was written. An
;                                        ELD's log is APPEND-ONLY and grows
;                                        to megabytes, and rewriting it on
;                                        every duty-status change is
;                                        O(n-squared) writes on flash -
;                                        which would burn a stick out in a
;                                        truck, slowly, and look like a
;                                        hardware fault when it did.
;
;                                        THE CONTRACT THAT MAKES IT SAFE:
;                                        IT APPENDS ALL n BYTES OR NONE. A
;                                        board that cannot promise that
;                                        answers #HW_FILE_READONLY from
;                                        HwFileWritable() rather than
;                                        appending unsafely - the same
;                                        write-gate discipline
;                                        HwMmcCanWrite() sets.
;
;                                        On the Pi 4 that means fat.pi4
;                                        writes the DATA CLUSTERS FIRST AND
;                                        THE DIRECTORY ENTRY'S SIZE LAST,
;                                        so a power cut mid-append leaves a
;                                        file that is SHORT BUT NOT
;                                        CORRUPT - and fixed-size records
;                                        mean a short file loses at most
;                                        one record, which a journal scan
;                                        detects.
;
;                                        NOT IMPLEMENTED ON ANY BOARD YET
;                                        (Phase A item 3). The ABI slot
;                                        exists and answers #SVC_ENOSYS,
;                                        which is the truth; a fallback
;                                        that read the file, appended in
;                                        memory and rewrote the whole thing
;                                        would BE the O(n-squared) path
;                                        this entry point exists to avoid,
;                                        while reporting success.
;                 HwFileLastError()      a #HW_FILE_* code for the last
;                                        call that failed
;                 HwFileErrorText()      that failure as a whole English
;                                        sentence, as a POINTER (print it
;                                        with UartWriteStr, never Print -
;                                        see the note at the foot of this
;                                        file)
;
;              THE BOARD ARMS AND DISARMS ITS OWN WRITER. On the Pi 4 the
;              rule has always been that fat.pi4's block writer is
;              installed around exactly one call and taken away again on
;              every path out, so that no later bug anywhere in the
;              monitor can reach the boot medium. That rule did not
;              change; it MOVED, from each calling command into
;              HwFileWriteAll, which is now the one place that arms it.
;              One place is a stronger version of the same guarantee than
;              three places that each remember to.
;
;    HwNet*    (#CAP_NET)  an IP-capable interface, for get / put / net and
;              dhcp / ping / dns. The portable protocol
;              (Anvil/Core/net_cmd.pbi over Lib/net.pi4 and Lib/tftp.pi4 -
;              IP/UDP/ARP/TFTP) sits ABOVE this seam; the seam itself is
;              the board's frame tx/rx and link control, which is HwLink*
;              below - 2026-09-05, when the last of the command layer's
;              calls into one board's network file moved behind it. The
;              Pi 4 answers HwLinkOpen / HwLinkClose in
;              RaspberryPi4/Board/eth.pi4 over Lib/genet.pi4; the UNO Q
;              answers them in ArduinoQ/Board/hw_net_q.pi4.
;
;    HwLink*   (#CAP_NET, same group)  THE WIRE ITSELF - one frame in, one
;              frame out, and what this particular wire can carry.
;
;              WHY THIS EXISTS AND WHEN IT ARRIVED. RaspberryPi4/Lib/link.pi4
;              is the policy layer the ruling 2 of 2026-09-02 ordered -
;              "merge to one IP layer that rides whichever link is up" - and
;              it was written on the Pi 4, for the Pi 4, naming ELEVEN
;              chip-specific procedures directly: Cyw43Send, Cyw43Receive,
;              Cyw43ReceivePtr, Cyw43DataPtr, Cyw43DataMax, GenetSend,
;              GenetRecvWait, WifiConsoleOn, WifiConsoleTakeUdp,
;              WifiNoteRxProof, WifiServiceEapolFrame. Its own header said
;              what that cost: "A TARGET WITHOUT A RADIO drops cyw43.pi4 and
;              wifi.pi4 and CANNOT INCLUDE THIS FILE AS IT STANDS."
;
;              So the whole of net / ping / dns / dhcp / tcp / http - every
;              line of which is already portable and already builds for a
;              second board - was locked to one board by the file underneath
;              it. Moving those eleven names behind a seam is the same move
;              HwGpio* made, for the same reason, and it is what
;              Anvil/ARCHITECTURE.md means by "the core never names a chip".
;
;              THE SEAM IS PER-KIND, NOT PER-DEVICE-NUMBER. A board declares
;              which of the #HW_LINK_* kinds below it can offer; link.pi4
;              picks one and then addresses every call to that kind. A board
;              with one link answers for one kind and refuses the rest; the
;              Pi 4 answers for two.
;
;                 HwLinkHas(kind)        1 if this board has hardware of
;                                        this kind AT ALL. Compile-time
;                                        truth about the board, not a
;                                        run-time state - it is what lets
;                                        the policy skip a kind entirely
;                                        rather than probe it.
;                 HwLinkTxMax(kind)      the largest 802.3 frame THIS link
;                                        will carry, asked at run time
;                                        because on a radio it is a
;                                        property of a transmit buffer and
;                                        would go stale written down.
;                 HwLinkSend(kind, buf, n, ms)
;                                        1 sent, 0 not. A driver that
;                                        transmits out of its own buffer
;                                        copies from buf itself; the caller
;                                        never learns which kind it has.
;                 HwLinkRecv(kind, buf, max, ms)
;                                        bytes received, 0 or less for
;                                        nothing within ms.
;                                        ms = 0 MEANS "LOOK ONCE AND DO
;                                        NOT WAIT". IT DOES NOT MEAN "DO
;                                        NOT LOOK", and a backend that
;                                        refuses a zero budget without
;                                        polling its ring is WRONG.
;                                        MEASURED ON THE Pi 4,
;                                        2026-09-07: the network console
;                                        pump passes 0 at an idle prompt
;                                        because there is nothing there
;                                        to wait for; the wired driver
;                                        answered an argument error
;                                        before looking at a single
;                                        descriptor, and the wired
;                                        console was DEAF while
;                                        announcing itself as listening.
;                                        The radio's poll had always
;                                        honoured 0, so one seam produced
;                                        two behaviours from three lines
;                                        of shared code. See
;                                        RaspberryPi4/Board/hw_link.pi4.
;                 HwLinkRxPtr(kind)      WHERE THE FRAME JUST RECEIVED
;                                        ACTUALLY IS. A driver that filled
;                                        buf returns buf; a driver with its
;                                        own single receive buffer returns
;                                        that, and nothing is copied. Valid
;                                        only immediately after a
;                                        HwLinkRecv that returned > 0.
;                                        THIS IS THE ONE ASYMMETRY IN THE
;                                        SEAM AND IT IS DELIBERATE: forcing
;                                        every driver to fill the caller's
;                                        buffer would put a 1514-byte copy
;                                        on the radio path of a board whose
;                                        caches are off, to hide a fact the
;                                        caller can simply be told.
;                 HwLinkMacPtr(kind)     the six bytes frames leave with, or
;                                        0 if this link has no hardware
;                                        address (a point-to-point serial
;                                        line does not).
;                 HwLinkName(kind)       the ADDRESS of a lowercase noun
;                                        phrase - "the wired Ethernet",
;                                        "the Wi-Fi radio", "the SLIP
;                                        serial link". Printed with
;                                        UartWriteStr, like every other
;                                        board-supplied fragment here.
;                 HwLinkReady(kind)      CAN THIS LINK CARRY A FRAME RIGHT
;                                        NOW - added 2026-09-07 for the
;                                        network console. HwLinkHas is a
;                                        compile-time fact about the board;
;                                        this is a run-time fact about the
;                                        wire. On the Pi 4 the wired side
;                                        answers "the driver started and the
;                                        PHY still sees a link" and the
;                                        radio answers "the association is
;                                        keyed".
;                                        THE CONSOLE NEEDS IT AND NOTHING
;                                        ELSE DOES YET. Arming a console on
;                                        an interface that cannot transmit
;                                        produces a board that says it is
;                                        listening and answers nobody, which
;                                        is the exact failure the console
;                                        work of 2026-09-06 and 2026-09-07
;                                        exists to end. It is a QUESTION,
;                                        never a bring-up: a board answers
;                                        it with register reads and must not
;                                        start anything to do so.
;
;              AND THREE HOOKS FOR WHAT ONLY SOME LINKS NEED. These are not
;              decoration: they are the two behaviours that used to make
;              link.pi4 name Wi-Fi, expressed so that a board which needs
;              neither answers 0 and costs nothing.
;
;                 HwLinkOfferRaw(kind, p, n)
;                                        the board gets FIRST REFUSAL on a
;                                        received frame, before the IP
;                                        layer sees it. 1 = "I consumed
;                                        it". On the Pi 4's radio this is
;                                        the EAPOL rekey (ethertype $888E),
;                                        which is not IP and must never
;                                        reach NetInput - a board that
;                                        ignored it would keep transmitting
;                                        under a key nobody will decrypt.
;                 HwLinkOfferUdp(kind, p)
;                                        the same question for a datagram
;                                        the IP layer has already
;                                        classified as UDP. On the Pi 4
;                                        this is the NETWORK CONSOLE taking
;                                        its own keystrokes back out of the
;                                        stream - and until 2026-09-07 it
;                                        asked that only of the radio,
;                                        which is why a board on a cable
;                                        alone had no console at all. It
;                                        now asks the console, which knows
;                                        which interface it armed on.
;
;                                        THREE ANSWERS SINCE 2026-09-07:
;                                        0 nobody here wanted it, 1 it was
;                                        taken, 2 IT WAS TAKEN AND A REPLY
;                                        IS STAGED - the caller must put
;                                        that frame on the wire. The third
;                                        arrived with the board's own DHCP
;                                        server: two pumps race for every
;                                        frame at an idle prompt, and a
;                                        reply staged by the one that lost
;                                        and never sent is a client whose
;                                        lease request times out against a
;                                        board that was serving addresses.
;                                        A board with no such service never
;                                        answers 2 and needs no code for
;                                        it.
;                 HwLinkNoteRx(kind, r)  the board is told what the IP layer
;                                        made of the frame (a #NET_IN_*
;                                        code). The Pi 4's radio uses it to
;                                        wind the "we have had a reply, so
;                                        this association is alive in both
;                                        directions" clock. Everything else
;                                        does nothing.
;
;              AND SIX MORE, ADDED 2026-09-05, BECAUSE THE COMMANDS WERE
;              STILL NAMING ONE BOARD. The ten above moved the WIRE behind
;              the seam and RaspberryPi4/Lib/link.pi4 stopped naming a chip
;              that day. The COMMAND layer did not: Anvil/Core/net_cmd.pbi
;              still called EthUp, EthUpIp, EthLinkUp, EthDown, EthResolve,
;              EthRun and EthSendStaged in RaspberryPi4/Board/eth.pi4, and
;              GenetSpeed and GenetFullDuplex in RaspberryPi4/Lib/genet.pi4,
;              so the shared core could not be compiled for a second board
;              even though every layer under it already could. These six are
;              the smallest set that removes all of them. THREE ARE GETTERS
;              a command wants in order to PRINT, and three are the bring-up
;              and teardown a command DRIVES.
;
;                 HwLinkSpeed(kind)      how fast this link is running, in
;                                        megabits per second, or
;                                        #HW_LINK_SPEED_UNKNOWN when the
;                                        board has no such number. A LINK
;                                        THAT CANNOT MEASURE ITS OWN RATE
;                                        ANSWERS UNKNOWN AND NEVER A NOMINAL
;                                        ONE: a serial line's baud rate is a
;                                        constant somebody typed, and
;                                        printing it as a negotiated speed
;                                        tells an operator the far end
;                                        agreed to something it never saw.
;                 HwLinkDuplex(kind)     #HW_LINK_DUPLEX_FULL, _HALF or
;                                        _UNKNOWN. The same rule.
;                 HwLinkWhyText(kind)    the ADDRESS of a lowercase phrase
;                                        saying what the DRIVER under this
;                                        link last had to say - it reads
;                                        after "The link driver said: ". A
;                                        board with nothing to say answers
;                                        an empty string and the caller
;                                        prints no line at all. This is the
;                                        seam's answer to EthWhyGenet(),
;                                        which had the shared core printing
;                                        one MAC driver's error text.
;                 HwLinkOpen(needIp)     CHOOSE AN INTERFACE, CONFIGURE THE
;                                        ONE IP LAYER FOR IT, AND SAY IN A
;                                        FULL SENTENCE WHY NOT IF IT COULD
;                                        NOT. 1 if something is now carrying
;                                        traffic, 0 if nothing is.
;                                        needIp = 1 the caller must be able
;                                        to send from an address; needIp = 0
;                                        the caller is about to ask for one
;                                        (dhcp), so a link with a carrier
;                                        and no address is a good answer.
;                                        THE FACTS ARE THE BOARD'S AND THE
;                                        POLICY IS NOT. A board gathers its
;                                        own carrier and address facts and
;                                        hands them to LinkSelect (two
;                                        interfaces) or LinkUseKind (one);
;                                        the preference order lives once, in
;                                        RaspberryPi4/Lib/link.pi4, and a
;                                        board that reimplemented it would
;                                        be a second copy of a decision that
;                                        must not be made twice.
;                                        IT IS SILENT ON SUCCESS, because
;                                        which link won and why is worded
;                                        the same on every board and the
;                                        command layer prints it.
;                 HwLinkClose()          stop whatever this board started -
;                                        the receive DMA above all, so that
;                                        no bus master is writing into
;                                        memory while a payload runs. 1 if
;                                        something was actually stopped, 0
;                                        if there was nothing to stop, so
;                                        the caller can tell the operator
;                                        which of the two happened without
;                                        reading a board's own global.
;                 HwLinkSayDetail()      print whatever else THIS BOARD has
;                                        to say about the link now in use,
;                                        and nothing at all when it has
;                                        nothing. The Pi 4 uses it for the
;                                        wired receive region's address and
;                                        for the warning that the hardware
;                                        address is a made-up one; both are
;                                        true of this board only and neither
;                                        belongs in a shared command. A
;                                        board with nothing to add defines
;                                        an empty procedure - it does NOT
;                                        omit it.
;
;              AND ONE MORE, ADDED 2026-09-06, BECAUSE AN ADDRESS IS NOT
;              ALWAYS JUST THREE NUMBERS IN THE IP LAYER. The `dhcp`
;              command is portable in every line: it runs its own
;              DISCOVER/REQUEST over whichever link the policy selected
;              and hands the lease to NetSetIPv4. On a board whose
;              selected link is a RADIO that is only half of what has
;              happened - the radio's own driver keeps its own answer to
;              "does this board have an address", and the things only a
;              radio has hang off that answer.  The command cannot say so
;              without naming a radio, so it tells the BOARD instead.
;
;                 HwLinkAddressBound(kind, ip, mask, gw)
;                                        THE LINK OF THIS KIND HAS JUST
;                                        BEEN GIVEN AN ADDRESS by
;                                        something other than the board's
;                                        own bring-up - today that is the
;                                        `dhcp` command, which has already
;                                        applied it to the one IP layer.
;                                        The board does whatever else that
;                                        transition means to it, and
;                                        answers nothing. A board with
;                                        nothing to do defines an empty
;                                        procedure - it does NOT omit it.
;                                        IT MUST BE IDEMPOTENT: it is
;                                        called on every completed lease,
;                                        a renewal of an address the board
;                                        already has included.
;                                        THE DEFECT IT EXISTS FOR, in one
;                                        sentence: a Pi 4 that took its
;                                        lease through this command
;                                        ANSWERED PING AND ITS WIRELESS
;                                        CONSOLE WAS DEAF, because the
;                                        radio never learned it had an
;                                        address and so never armed the
;                                        console - and with no serial
;                                        cable there was then no way in at
;                                        all.
;
;              AND ONE MORE, ADDED 2026-09-07, BECAUSE AN ADDRESS THAT IS
;              NOT A LEASE HAS TO REACH THE WIRE SOMEHOW. HwLinkOpen's
;              automatic choice deliberately will not pay a wired
;              bring-up while a radio is working, which is right for
;              `ping` and wrong for an operator typing this board's own
;              address into it. The gap is measurable: on 2026-09-07 a
;              board with `net address` set and a cable running straight
;              to the machine trying to reach it answered that machine's
;              pings and had NO CONSOLE ON THE CABLE AT ALL, because the
;              console arms from the interface holding the address and
;              nothing had put the stored address on an interface.
;
;                 HwLinkStaticUp()       PUT THE ADDRESS THIS BOARD HAS
;                                        STORED ON THE WIRE, NOW, and
;                                        answer the #HW_LINK_* kind that
;                                        ended up carrying it, or
;                                        #HW_LINK_NONE. This is the
;                                        EXPLICIT act - the three address
;                                        setters, and the boot's fallback
;                                        when no DHCP server answers - so
;                                        it IS allowed to pay a link wait
;                                        that the automatic path would
;                                        not.
;                                        IT ANSWERS THE KIND AND NOT 1,
;                                        because the preference order
;                                        still applies once the link is
;                                        up: a caller that assumed "wired"
;                                        would print a sentence about a
;                                        cable while a pinned radio
;                                        carried the traffic.
;                                        IT MUST BE BOUNDED IN EVERY ARM,
;                                        and it must ask whether there is
;                                        anything to bring up BEFORE it
;                                        pays for one, because the boot
;                                        path calls it. A board with no
;                                        stored address, or no way to use
;                                        one, answers #HW_LINK_NONE in
;                                        constant time - it does NOT omit
;                                        the procedure.
;                                        IT APPLIES NOTHING ELSE. The
;                                        caller runs the same tail a lease
;                                        runs (NetAddressBound), so a
;                                        stored address and a leased one
;                                        reach one state by one path.
;
;              AND ONE MORE, ADDED 2026-09-09, BECAUSE A LINK THAT
;              MISBEHAVES LEAVES ITS EVIDENCE IN THE CONTROLLER AND
;              NOWHERE ELSE. On 2026-09-08 this board was on a cable
;              straight into a laptop and the laptop's Ethernet card was
;              reset twelve times and then stopped by Windows. The
;              question that decided the diagnosis - had this board been
;              sending 802.3x PAUSE frames - had an exact answer in a
;              UniMAC counter, and there was no command that would print
;              it. A hypothesis stood in for a number for a day.
;
;                 HwLinkSayCounters()    PRINT WHAT THIS BOARD'S OWN
;                                        NETWORK HARDWARE HAS COUNTED,
;                                        in sentences, for the interface
;                                        now in use. Not the IP layer's
;                                        tallies - `net` already prints
;                                        those and they are the same on
;                                        every board - but the
;                                        controller's own: pause frames
;                                        sent and received, framing
;                                        errors, overruns, and whatever
;                                        else THIS part counts.
;                                        A BOARD WITH NO SUCH COUNTERS
;                                        SAYS SO IN A SENTENCE rather
;                                        than staying silent, because
;                                        silence at a prompt reads as a
;                                        broken command. It does NOT
;                                        omit the procedure.
;                                        IT READS AND PRINTS AND
;                                        NOTHING ELSE. It must be safe
;                                        to type at any moment - on a
;                                        link that is up, down, or was
;                                        never started - and it must not
;                                        clear what it reads, because
;                                        the next person to type it is
;                                        usually the same person ten
;                                        seconds later comparing two
;                                        readings.
;
;              A BOARD MUST DEFINE ALL NINETEEN, even the ones it has nothing
;              to say to. That is the same rule the rest of this seam follows
;              and it is not bureaucracy: a missing procedure is a link
;              error naming a symbol, while a seam that is optional in
;              places produces a board that builds and then behaves
;              differently for a reason nobody can see.
;              Pi 4: RaspberryPi4/Board/hw_link.pi4 for the thirteen that are
;              one call into a driver, and RaspberryPi4/Board/eth.pi4 for
;              HwLinkOpen, HwLinkClose, HwLinkSayDetail, HwLinkSayCounters,
;              HwLinkAddressBound and HwLinkStaticUp. THE SPLIT IS AN
;              INCLUDE-ORDER FACT AND NOT A DESIGN: those six read the
;              settings store and this board's own network globals, which
;              arrive in the build long after hw_link.pi4 has to.
;              UNO Q: ArduinoQ/Board/hw_link_q.pi4 for the ten, and
;              ArduinoQ/Board/hw_net_q.pi4 for the eight.
;
;    HwBootEl1 (#CAP_BOOT_EL1)  arm64 Image / EL1 handoff, for the coming
;              booti. The one entry point the family will call:
;                 HwBootToEl1(entry, dtb)   install an EL1, place the DTB
;                                           pointer in x0, drop to EL1 and
;                                           branch to `entry`. Does not
;                                           return.
;              NOT implemented on any board yet; named here so booti's
;              author builds against a fixed seam. A board with no way to
;              reach EL1 declares #CAP_BOOT_EL1 = 0 and the command refuses.
;
;    HwAddr*   (NO CAPABILITY - see below)  IS THIS ADDRESS SAFE TO TOUCH.
;              The board answers for a range the OPERATOR typed, before
;              the core reads or writes one byte of it:
;                 HwAddrCheck(lo, hi, forWrite)
;                                        #HW_ADDR_SAFE / _UNCLOCKED /
;                                        _UNKNOWN for the whole inclusive
;                                        range lo..hi. forWrite is 1 when
;                                        the command is about to WRITE,
;                                        0 when it will only read, so a
;                                        board that can allow a read of
;                                        something it will not allow a
;                                        write to has somewhere to say so.
;                 HwAddrReason()         the ADDRESS of a lowercase
;                                        fragment naming the block and
;                                        why - it reads after "is inside
;                                        ", printed with UartWriteStr
;                                        exactly as RequireCap prints
;                                        *reason and as the core prints
;                                        HwGpioReservedReason(). Valid
;                                        only immediately after a
;                                        HwAddrCheck() that did not answer
;                                        SAFE.
;                 HwAddrBlockLo() / HwAddrBlockHi()
;                                        the extent of the block that
;                                        matched, so the refusal can print
;                                        it. Same validity rule, and the
;                                        same pattern as memrange.pi4's
;                                        gMonHitLo / gMonHitHi.
;
;              IT HAS NO #CAP_ FLAG, DELIBERATELY. A capability answers
;              "does this board have this class of hardware"; every board
;              has addresses, so there is nothing to be absent. What
;              differs is what the board KNOWS about them, and that is an
;              answer, not a capability. A board with nothing to declare
;              answers SAFE for what it maps and UNKNOWN elsewhere, and
;              says so in HwAddrReason().
;
;              WHY THE BOARD AND NOT THE CORE. On one part in this tree an
;              MMIO read of a block whose clock is gated does not fault
;              and does not return $FFFFFFFF - it STALLS THE BUS, and the
;              board has to be power-cycled by hand. Which blocks those
;              are is chip-and-firmware knowledge of exactly the kind the
;              core may not learn, and a guard inside a DRIVER cannot help
;              because `memory` never calls a driver. The precedent is
;              HwMonLo()/HwMonHi(): the core asks where the monitor is
;              rather than assuming, because the answer is the board's.
;
;    HwId*     (NO CAPABILITY - see below)  WHAT THIS COMPUTER IS. The
;              banner (Anvil/Core/help.pbi) and `version`
;              (Anvil/Core/flow_cmd.pbi) print no board's facts as prose;
;              they ask this seam. IMPLEMENTED as
;              RaspberryPi4/Board/hw_id.pi4 and ArduinoQ/Board/hw_id_q.unoq.
;
;                 HwIdBoard()            the PRODUCT name of the computer,
;                                        as a person would say it -
;                                        "Raspberry Pi 4". The address of a
;                                        short fragment, the same way
;                                        HwAddrReason() returns one
;                 HwIdCpu()              the core, "Cortex-A72"
;                 HwIdTarget()           the word that follows `-t` on the
;                                        compiler's command line. This one
;                                        is a CHECKABLE CLAIM
;                                        about how the image was produced,
;                                        and the worst line in `version` to
;                                        get wrong
;                 HwPmfTargetId()        the numeric PMFBOOT target identity
;                                        for this board. Unlike HwIdTarget,
;                                        this is an admission ABI: the common
;                                        payload reader compares it exactly
;                                        against v2 compiler provenance
;                 HwIdEl()               the exception level, 0..3, READ
;                                        from the running processor. Never
;                                        a constant: it was one, and it was
;                                        right on one board by luck and
;                                        wrong on the other in fact
;                 HwIdSayConsole()       PRINTS the console paragraph. A
;                                        returned fragment would not do -
;                                        it is several sentences and one of
;                                        them carries an address. Same
;                                        shape as HwAddrReport()
;                 HwIdSayImage()         PRINTS what kind of image this is
;                                        (a kernel8.img, a UEFI
;                                        application, ...), inside version
;                 HwIdImageBase()        where the running image starts
;                 HwIdImageLen()         how long it is in bytes, or 0 when
;                                        the board cannot say. The two
;                                        together are what let `version`
;                                        run a crc32 over the monitor
;                                        itself - forum 586, the content
;                                        stamp, as opposed to the build
;                                        number, which is only a label
;                 HwIdSayImageWhere()    PRINTS the PROVENANCE of that
;                                        length, or the reason there is
;                                        not one. One procedure, two jobs,
;                                        and the core calls it either way.
;                                        CALL IT AFTER HwIdImageLen(), the
;                                        same ordering rule
;                                        HwI2cSourceWhere() carries
;
;              IT HAS NO #CAP_ FLAG, DELIBERATELY, and for a blunter
;              reason than HwAddr*'s: a board with no GPIO is a real
;              board, and a board with no IDENTITY is not a thing. Every
;              board supplies this seam whole. A board that genuinely
;              cannot answer one of the numeric rows says so with a 0 and
;              a whole sentence, which is a different thing from a group
;              of hardware being absent.
;
;              WHY IT EXISTS AT ALL - forum 575. The core used to print
;              one board's name, one board's console and one board's
;              exception level as literals, so the SECOND board's very
;              first line of output described a different computer, and it
;              worked around that by carrying its own banner and its own
;              `version`. That is the fork this whole split exists to
;              prevent, and it would have been copied again by the third
;              board. If a future board needs to say something the core
;              does not print, the answer is another row here - not
;              another banner.
;
;    HwI2c*    (#CAP_I2C)   the I2C bus, for the `i2c` family
;              (Anvil/Core/i2c_cmd.pbi). IMPLEMENTED on the Pi 4 as
;              RaspberryPi4/Board/hw_i2c.pi4 over RaspberryPi4/Lib/i2c.pi4,
;              and on the Arduino UNO Q as ArduinoQ/Board/hw_i2c_q.unoq.
;              The transaction seam:
;                 HwI2cDefaultBus()      the bus `i2c` uses when none is named
;                 HwI2cBusValid(bus)     1 if this board drives that bus
;                 HwI2cUp(bus)           bring it up - MUX THE PINS, set the
;                                        clock, enable the controller. 1/0.
;                                        Idempotent; the core calls it once
;                                        per command, before any transaction.
;                 HwI2cProbe(bus,addr)   a #HW_I2C_* code
;                 HwI2cRead(bus,addr,*b,n) / HwI2cWrite(bus,addr,*b,n)
;                 HwI2cSetSpeed(bus,hz) / HwI2cGetSpeed(bus)
;
;              AND THE CLOCK SEAM, which is what makes a RATE believable.
;              An I2C rate is a divider away from some other clock, and
;              until 2026-09-03 the core printed a figure computed from a
;              DATASHEET CONSTANT for that clock while the same board was
;              measuring the clock at over three times the constant (forum
;              622). So a board that derives its rate from a clock now has
;              to say which clock, how it knows, and what the divider can
;              and cannot reach:
;                 HwI2cSourceHz(bus)     the clock feeding the divider, in
;                                        Hz, ASKED FOR NOW rather than
;                                        cached - a governor moves it. 0 if
;                                        this board's rate does not come
;                                        from a divider it can name.
;                 HwI2cSourceWhere(bus)  the ADDRESS of a short fragment
;                                        saying where that number came from
;                                        ("measured by the firmware just
;                                        now"), printed with UartWriteStr
;                                        exactly as HwI2cPinFunc() is. 0 if
;                                        the board has nothing to say.
;                 HwI2cRateMin(bus) / HwI2cRateMax(bus)
;                                        the slowest and fastest SCL this
;                                        bus can actually produce right
;                                        now, in Hz, so a rate outside them
;                                        is REFUSED with the nearest
;                                        reachable one named, instead of
;                                        being silently clamped. 0 from
;                                        either means the board will not
;                                        say, and the core then prints no
;                                        range rather than inventing one.
;
;              AND THE PIN SEAM, which is what makes a bus verdict
;              believable. An I2C master is useless until the two pads are
;              switched from plain I/O to the controller's alternate
;              function, and a controller driving pins it is not connected
;              to fails in a way that looks EXACTLY like bad wiring. So the
;              board also answers what the pins are and what they are doing:
;                 HwI2cPin(bus, which)   the pin carrying the bus, which =
;                                        #HW_I2C_SDA (data) or #HW_I2C_SCL
;                                        (clock); -1 if the board cannot say
;                 HwI2cPinFunc(bus)      the ADDRESS of a short lowercase
;                                        fragment naming the function those
;                                        pins must be on for the controller
;                                        to reach them ("alt0" on the Pi 4),
;                                        printed with UartWriteStr exactly as
;                                        HwAddrReason() is. 0 if the board
;                                        has nothing to say.
;                 HwI2cPinReady(bus,which)  1 if that pin is on that function
;                                        RIGHT NOW, 0 if it is not, -1 if the
;                                        board cannot tell
;                 HwI2cPadLevel(bus,which)  the level AT THE PAD - 1 high, 0
;                                        low, -1 if the board cannot read it.
;                                        This is the measurement that makes a
;                                        wedged-bus verdict honest: see
;                                        I2cTimeoutVerdict() in
;                                        Anvil/Core/i2c_cmd.pbi.
;
;              A board that cannot answer the pin seam returns -1 (and 0 for
;              the name), and the core says the pads could not be read rather
;              than guessing - which is the entire reason for asking.
;    ------------------------------------------------------------------
;     THE SEVEN GROUPS THE PAYLOAD ABI ADDED, 2026-09-04.
;
;     Anvil/Hal/abi.pbi hands a payload a service table, and a payload is
;     an APPLICATION rather than a diagnostic - so it needs classes of
;     hardware the monitor's own command families never wanted. Each of
;     these is a group in exactly the sense above: one #CAP_ per board,
;     one Hw<GROUP>* contract here, one honest refusal where it is 0.
;
;     THE ONE THAT IS NOT HERE, AND WHY. There was a #CAP_CAN and an
;     HwCan* seam in the brief this work was built from. The ruling of
;     2026-09-04 is that the product itself does not hook to the engine
;     port at all: a separate device plugs into that port and reaches
;     this board over Wi-Fi or LoRa - so the CAN controller belongs to a
;     SECOND UNIT and not to the board Anvil runs on. The seam it left
;     behind is HwVeh*, below, and it is a different shape because it is
;     a different problem: not a bus, but a radio link to a box that has
;     the bus.
;    ------------------------------------------------------------------
;
;    HwCon*    (#CAP_CONSOLE)  A PIXEL SURFACE ANVIL CAN HAND TO A
;              PAYLOAD. Not the monitor's own console - that is a terminal
;              grid and belongs to Anvil. This is the raw surface an
;              application draws its own interface on, and the split is
;              the whole point: THE PAYLOAD OWNS THE PIXELS AND ANVIL OWNS
;              THE DEVICE. Pi 4 backend: RaspberryPi4/Board/hw_con.pi4
;              over Lib/display.pi4 and Board/display.pi4's rasteriser.
;                 HwConWidth() / HwConHeight()   pixels
;                 HwConTier()            #HW_TIER_V3D / _DMA / _CPU.
;                                        INFORMATIONAL - the payload draws
;                                        the same either way, and this is
;                                        here so a measured frame time can
;                                        be read against the path that
;                                        produced it.
;                 HwConTextHeight()      the ONE line height this board
;                                        rasterises at. This part has
;                                        three fonts and a single size,
;                                        and says so rather than letting a
;                                        caller lay out against a size it
;                                        asked for and did not get.
;                 HwConFrameBegin()      claim the surface. 1, or 0 when
;                                        there is no framebuffer - a real
;                                        state here, because the mailbox
;                                        can decline.
;                 HwConFrameEnd()        present it. On a direct path
;                                        there is nothing to flip and THE
;                                        CACHE CLEAN IS STILL NOT
;                                        OPTIONAL: the payload may be
;                                        running cached and the display
;                                        controller reads DRAM.
;                 HwConRect(x,y,w,h,argb)
;                                        a filled, ALPHA-BLENDED
;                                        rectangle. THE ONE PRIMITIVE THE
;                                        WHOLE UI IS BUILT FROM. Alpha is
;                                        the top byte; 255 takes a path
;                                        with no read at all.
;                 HwConText(x,y,*s,argb,bg)
;                                        one run, BASELINE AT y - because
;                                        that is what a rasteriser takes,
;                                        and because two runs of different
;                                        glyphs align on their baselines.
;                                        bg is a COLOUR and not an alpha:
;                                        glyph coverage is blended between
;                                        fg and bg without reading the
;                                        surface, which is what makes it
;                                        fast and what makes it wrong over
;                                        a picture.
;                 HwConTextWidth(*s)     measure without drawing
;                 HwConCapture()         KEEP THE FRAME THE SCREEN IS
;                                        SHOWING, where something that is
;                                        not the screen can read it back.
;                                        1 kept, 0 refused. Added
;                                        2026-09-11 under the ruling that
;                                        every board run comes back with a
;                                        picture: a payload's last frame
;                                        is destroyed by the monitor's own
;                                        first printed line on the way
;                                        back, so a picture that is not
;                                        taken while it exists cannot be
;                                        taken at all. THE BOARD DECIDES
;                                        WHAT "THE FRAME THE SCREEN IS
;                                        SHOWING" MEANS - on a board whose
;                                        console is drawn turned, the
;                                        buffer being scanned is not the
;                                        buffer being drawn into, and
;                                        capturing the second one would
;                                        keep a picture nobody saw.
;                 HwConBacklight(pct)    0..100, or -1 if this board
;                                        drives no backlight it can set.
;                                        -1 AND NOT A SILENT SUCCESS: a
;                                        payload dimming for night driving
;                                        that got 0 back would show the
;                                        driver a screen that never dims
;                                        and no reason why.
;              CLIPPING IS NOT IN THIS SEAM. Intersecting two rectangles
;              is arithmetic and not silicon, so Anvil/Hal/abi.pbi does it
;              in the core - the same arithmetic on every board, provable
;              with no board at all.
;
;    HwTouch*  (#CAP_TOUCH)  A FINGER ON THE GLASS, and it is its own
;              group rather than an extension of hid.pi4's mouse path
;              because a touch surface is not a mouse. THERE IS NO HOVER,
;              THERE IS NO BUTTON, THERE IS NO CURSOR, and there are up to
;              ten simultaneous contacts. A UI written against a mouse and
;              handed touch events has a hover state that never clears and
;              a right-click that never comes.
;                 HwTouchUp()            bring the controller up. 1 ready,
;                                        0 with a reason already available
;                                        from HwTouchErrText(). Idempotent.
;                 HwTouchPoll(*ev)       dequeue ONE event into *ev. 1 got
;                                        one, 0 empty, negative on error.
;                                        A QUEUE AND NOT A STATE,
;                                        deliberately: a tap that begins
;                                        and ends between two UI frames
;                                        must still be seen, and a
;                                        state-polling seam loses it.
;                 HwTouchQueued()        how many are waiting
;                 HwTouchFlush()         discard them. CALLED ON EVERY
;                                        SCREEN CHANGE - a stale tap that
;                                        lands on the new screen is the
;                                        bug that makes a driver change
;                                        duty status by accident.
;                 HwTouchMaxPoints()     1, 5 or 10
;                 HwTouchErrText()       a whole sentence, as a POINTER
;
;              THE RASPBERRY PI 4 IMPLEMENTS THIS SEAM - 2026-09-08,
;              RaspberryPi4/Board/hw_touch.pi4 over Lib/touch_goodix.pi4.
;              This block used to say no board did, and that the
;              capability and the slots therefore answered differently on
;              the one board with the hardware. They do not any more:
;              SvcCapGet(#SVCCAP_TOUCH) answers 1 and the slots answer
;              over the seam.
;
;              A BOARD WITH NEITHER still answers 0 to the capability and
;              #SVC_ENOCAP from the slots, and the pair is still the
;              point: "this board has no touch surface" sends an operator
;              to check wiring, and "this monitor cannot offer you the
;              one it has" sends them to a release note.
;
;              THE `touch` COMMAND STAYS A BOARD FILE and that is not an
;              inconsistency. The seam is the DRIVER surface and it is
;              portable; the command prints sentences about a Waveshare
;              ribbon, a GPIO expander at $45 and which pair of pins the
;              panel is on, none of which is Core's business. When a
;              second board grows a panel, the two commands are what get
;              compared and a Core one designed from both.
;
;              THE BACKEND MAY OFFER MORE THAN THE SIX, and the Pi 4's
;              does - HwTouchContacts() for how many are down NOW, and
;              HwTouchPointX/Y/Id for the frame just read. They are board
;              additions, named in the same family, and they are NOT part
;              of this contract: the first is what stops a pointer
;              sticking down when a queue overflows or is flushed, and
;              the rest let a report print a whole frame without
;              consuming the events something else is reading. They are
;              the first candidates to come into the contract when there
;              are two boards to shape it from.
;
;              WHERE THE COORDINATES COME FROM, and it is the part a
;              second board must copy rather than reinvent: the +0 and +4
;              fields are SCREEN pixels because the BOARD maps them,
;              through the same rotation and the same scale the console's
;              own pixels go through, in the display layer and nowhere
;              else. On the Pi 4 that is ScrTouchX / ScrTouchY in
;              RaspberryPi4/Board/screen_geom.pi4, beside the forward map
;              they are the inverse of. A driver that carried its own
;              rotation would be a second opinion about which way up the
;              panel is, and the two would disagree the first time
;              somebody turned the screen.
;              The event record is 32 bytes and ITS LAYOUT IS PART OF THE
;              PORTABLE VOCABULARY, so the core never learns a
;              controller's report format:
;                 +0  i32 x        pixels, ALREADY ROTATED AND SCALED TO
;                                  THE SCREEN, not the panel - the board
;                                  does the transform, because
;                                  panel-to-screen orientation is wiring
;                                  knowledge
;                 +4  i32 y
;                 +8  i32 id       contact id, stable for one touch
;                 +12 i32 state    #HW_TOUCH_DOWN / _MOVE / _UP / _CANCEL
;                 +16 i64 ticks    when the CONTROLLER reported it, not
;                                  when it was dequeued. A UI that
;                                  debounces or measures a long press
;                                  needs the former.
;                 +24 i32 pressure 0..255, or -1 if it cannot say
;                 +28 i32 reserved 0
;
;    HwGnss*   (#CAP_GNSS)  WHERE THE TRUCK IS, AND HOW MUCH TO TRUST IT.
;                 HwGnssUp()             bring the receiver up, configure
;                                        the message set, set the rate
;                 HwGnssPoll()           service the UART and decode. 1 if
;                                        a new fix landed since the last
;                                        call, 0 if not, negative on error
;                 HwGnssFix(*fix)        copy the most recent fix and
;                                        return its quality code. ALWAYS
;                                        FILLS, even when the fix is
;                                        invalid, so the age and the
;                                        accuracy are readable in exactly
;                                        the case they are needed.
;                 HwGnssAgeMs()          since the last VALID fix, or -1
;                 HwGnssPpsTicks()       at the last PPS rising edge, or
;                                        -1. The board wires PPS to a
;                                        GPIO; this is how the clock is
;                                        disciplined between fixes.
;                 HwGnssSatsUsed()       satellites in the solution
;                 HwGnssErrText()        a whole sentence, as a POINTER
;              Two fields in the 64-byte fix record carry REQUIREMENTS
;              rather than data, and they are why this seam is specified
;              rather than improvised:
;                 hacc_mm      the receiver's OWN horizontal accuracy
;                              estimate. THE FIELD THAT MAKES 4.3.1.6(c)
;                              CHECKABLE RATHER THAN ASSUMED: a fix whose
;                              reported accuracy is worse than half a mile
;                              is not a valid measurement for the
;                              regulation's purposes.
;                 speed_mmps   RECORDED, NEVER USED FOR THE DRIVING
;                              DECISION. 4.3.1.2(b) requires speed from
;                              the ECM, and GNSS speed at a standstill is
;                              noise - which is precisely how phantom
;                              driving events are manufactured.
;
;    HwUart*   (#CAP_UART)  A SECOND SERIAL PORT. The console UART is
;              Anvil's and is not this; this is the other one, for a GNSS
;              receiver.
;                 HwUartCount()          how many BEYOND the console. 0 is
;                                        a legitimate answer.
;                 HwUartOpen(n, baud)    8N1. Anything else is not in this
;                                        seam because nothing in this tree
;                                        needs it.
;                 HwUartRead(n,*b,len)   bytes actually read, 0 if none,
;                                        negative on error. NON-BLOCKING,
;                                        ALWAYS - a blocking read in a
;                                        cooperative single-stack
;                                        scheduler is a hang.
;                 HwUartWrite(n,*b,len)  also non-blocking; the caller
;                                        spins and pumps, the way every
;                                        emit path in this tree does
;                 HwUartRxOverrun(n)     bytes the HARDWARE dropped since
;                                        the last call. THE NUMBER THAT
;                                        PROVES a 1 Hz receiver is not
;                                        overrunning a FIFO, rather than
;                                        assuming it.
;                 HwUartClose(n)
;
;    HwSpi*    (#CAP_SPI)  THE TRANSPORT NOTHING IN THIS TREE HAS. There
;              is no SPI library at all. It stays on the critical path
;              after the 2026-09-04 ruling because LoRa is a module on SPI
;              and LoRa is the vehicle link's second transport.
;                 HwSpiBusValid(bus)     1 if this board drives it
;                 HwSpiUp(bus, hz, mode) mux the pins, set the clock and
;                                        the CPOL/CPHA mode (0..3), enable
;                                        the controller. Idempotent.
;                 HwSpiSetSpeed(bus,hz) / HwSpiGetSpeed(bus)
;                 HwSpiXfer(bus,cs,*tx,*rx,n)
;                                        ONE full-duplex transfer of n
;                                        bytes with chip select asserted
;                                        FOR THE WHOLE OF IT. Either
;                                        buffer may be 0. FULL DUPLEX AND
;                                        ONE CALL, deliberately: a
;                                        register read that is
;                                        command-then-data in a single CS
;                                        assertion reads garbage on some
;                                        parts and works on others if the
;                                        seam drops CS between them.
;                 HwSpiPin(bus, which)   #HW_SPI_MOSI / _MISO / _SCLK /
;                                        _CS0 / _CS1, or -1. Same
;                                        reasoning as the I2C pin seam: a
;                                        controller driving pins it is not
;                                        connected to fails in a way that
;                                        looks EXACTLY like bad wiring,
;                                        and forum 584 is what that costs.
;                 HwSpiPinFunc(bus)      the ADDRESS of a lowercase
;                                        fragment naming the function
;                                        those pins must be on ("alt0" on
;                                        the Pi 4)
;
;    HwVeh*    (#CAP_VEHLINK)  THE LINK TO THE ENGINE-PORT UNIT.
;
;              THE DECISION, 2026-09-04: "hardy itself will not hook to
;              the engine port, there will be a device that hooks to that
;              port which communicates with hardy over wifi or lora". So
;              the board Anvil runs on has NO CAN transceiver and NO J1939
;              stack; what it has is a radio link to a second unit that
;              has both.
;
;              THE SEAM IS NOT A TRANSPORT. It is the engine-data stream
;              PLUS the health of the path it arrives over, because for
;              compliance those two are inseparable: an odometer reading
;              is only as good as the knowledge of how old it is and which
;              of the two hops was broken when it stopped arriving.
;                 HwVehUp()              1 ready, 0 with a reason from
;                                        HwVehErrText(). Idempotent.
;                 HwVehDown()
;                 HwVehState()           #HW_VEH_DOWN / _SEARCHING /
;                                        _LINKED / _STALE
;                 HwVehTransport()       #HW_VEH_XPORT_NONE / _WIFI /
;                                        _LORA. Informational only - the
;                                        payload decodes the same record
;                                        either way, which is the whole
;                                        reason this is a seam and not two
;                                        drivers.
;                 HwVehPoll()            1 if a NEW engine record landed
;                                        since the last call, 0 if not,
;                                        negative on error. A POLL AND NOT
;                                        A CALLBACK - no procedure in this
;                                        language is re-entrant, so the
;                                        ABI is call-and-return only.
;                 HwVehData(*rec)        copy the 96-byte record and
;                                        return its freshness code. ALWAYS
;                                        FILLS, even when stale or never
;                                        populated, so the age and the
;                                        sequence number are readable in
;                                        exactly the case they are needed.
;                 HwVehLastHeardMs()     since ANY frame of any kind from
;                                        the unit, or -1 if never heard.
;                                        NOT the record's age: a unit that
;                                        is talking but has lost the
;                                        engine is heard and has nothing
;                                        new to say.
;                 HwVehLossState()       #HW_VEH_LOSS_NONE / _ENGINE /
;                                        _UNIT - see the vocabulary below,
;                                        which is where the reasoning is
;                 HwVehEngineLostMs()    how long the UNIT has been
;                                        reporting it cannot hear the
;                                        engine; -1 if it can, and -2 IF
;                                        WE CANNOT SAY BECAUSE WE CANNOT
;                                        HEAR THE UNIT. That third answer
;                                        is the point: "I do not know" is
;                                        not "it is fine", and a payload
;                                        that treated -2 as a duration
;                                        would aggregate a made-up figure
;                                        into a malfunction the regulation
;                                        defines by duration.
;                 HwVehDiag(which)       one counter by #HW_VEHDIAG_* id,
;                                        or -1 for an id this board does
;                                        not keep. COUNTERS AND NOT A
;                                        HEALTH VERDICT, for the same
;                                        reason #HW_I2C_TIMEOUT stopped
;                                        carrying a diagnosis: a number an
;                                        operator can read survives being
;                                        wrong about its cause, and a
;                                        verdict does not.
;                 HwVehUnitId()          the ADDRESS of the HEARD unit's
;                                        identity, or 0. Read against the
;                                        paired identity in the settings
;                                        store: a Hardy talking to the
;                                        wrong truck's unit is a
;                                        compliance failure that looks
;                                        exactly like a working system.
;                 HwVehErrText()         a whole sentence, as a POINTER
;
;              WHAT THIS SEAM DELIBERATELY DOES NOT KNOW: a PGN, an SPN, a
;              resolution, a transport protocol, a radio frame format or a
;              pairing policy. J1939 lives in the vehicle unit; the wire
;              format between the two boxes is the board backend's; the
;              pairing is a setting and a home-server record. The seam
;              speaks only the engine record and the health of the path -
;              which is what makes it the same seam whether the radio is
;              Wi-Fi, LoRa, or whatever a later truck needs.
;
;    HwClock*  (#CAP_RTC)  THE TIME, AND WHERE IT CAME FROM.
;                 HwClockUtc(*out)       fill a seven-field time record.
;                                        Returns the PROVENANCE code,
;                                        because "what time is it" and
;                                        "how much do you trust it" are
;                                        one answer and splitting them is
;                                        how a restored floor gets logged
;                                        as a measurement.
;                 HwClockProvenance()    the same code, filling nothing
;                 HwClockUncertaintyMs() worst-case error RIGHT NOW
;                 HwClockLastSyncTicks() at the last authoritative sync
;                 HwClockNotifyGnss(*fix)
;                                        THE ONLY WAY A TIME ENTERS THE
;                                        SYSTEM FROM OUTSIDE. Called by
;                                        the GNSS backend, never by a
;                                        payload.
;              THERE IS NO HwClockSet() AND ITS ABSENCE IS A REQUIREMENT.
;              49 CFR 395 Appendix A 4.3.1.5(a) requires an ELD to obtain
;              date and time "automatically without allowing any external
;              input or interference from a motor carrier, driver, or any
;              other person". A SETTER WOULD BE A WAY TO MAKE THE DEVICE
;              LIE, so there is none to refuse.
;
;              DRIFT IS NOT THE RISK; A WRONG START IS. CNTFRQ_EL0 reads
;              54 MHz on this board and a DS3231 is 2 ppm; even a plain
;              50 ppm oscillator takes about 138 days to drift the ten
;              minutes 4.3.1.5(b) allows. So HwClockUncertaintyMs() is
;              elapsed-since-sync times a worst_ppm that is a NAMED
;              CONSTANT CARRYING ITS SOURCE, with a floor for the sync's
;              own error - not a guess.
;
;              THE PI 4 HAS NO RTC AND THE PREMISE IS RE-CHECKED RATHER
;              THAN REMEMBERED: the gate greps the four device trees for
;              an rtc@ node on every run - five hits, all of them uartclk
;              (Raspberry Pi 4/A wall clock and a task list 2026-08-28).
;              #CAP_RTC = 1 here would mean a DS3231 is wired to I2C, and
;              a board built without one declares 0 and starts
;              #HW_CLK_UNSET every cold boot.
;
;    HwBoard*  (NO CAPABILITY)  THREE FACTS THE PAYLOAD ABI NEEDS AND NO
;              COMMAND FAMILY DOES. They have no #CAP_ for the same reason
;              HwAddr* has none: every board has an identity, a way to
;              reset and a cache state, so there is nothing to be absent.
;                 HwBoardName()          the ADDRESS of a printable name.
;                                        Never Print() it - see the note
;                                        at the foot of this file.
;                 HwReboot()             reset the board. Does not return.
;                 HwMmuState()           bit 0 MMU on, bit 1 D-cache on,
;                                        bit 2 I-cache on. THE PAYLOAD
;                                        ASKS RATHER THAN ASSUMING,
;                                        because Anvil's own state is not
;                                        fixed: `cache on` and `cache off`
;                                        are operator commands and RunAt's
;                                        handover behaviour is behaviour,
;                                        not contract.
;              The board also declares #SVC_BOARD_ID, one of
;              Anvil/Hal/abi.pbi's #SVC_BOARD_* codes. INFORMATIONAL ONLY:
;              a payload that branches on it has re-forked the thing the
;              capability model exists to prevent, and the ABI gate looks
;              for exactly that.
;    HwPwm*    (#CAP_PWM)  a modulated output and the part's own
;              temperature, for the `fan` family (Anvil/Core/fan_cmd.pbi).
;              IMPLEMENTED on the Pi 4 as RaspberryPi4/Board/hw_pwm.pi4
;              over RaspberryPi4/Lib/pwm.pi4 and Lib/thermal.pi4.
;
;              WHY ONE GROUP AND NOT TWO. A thermometer with no fan is a
;              reading nobody acts on and a fan with no thermometer is a
;              switch; the `fan` command needs both or neither, so one
;              flag gates both and a board that has only one of them
;              declares 0 and says which in its comment. If a family ever
;              wants the temperature ALONE, that is the day this splits
;              into #CAP_PWM and #CAP_TEMP - and not before, because two
;              flags nothing distinguishes is two ways to be wrong.
;
;              THE OUTPUT SEAM:
;                 HwPwmPinCount()        how many pins this board will
;                                        offer for a fan, 0 if none
;                 HwPwmPinAt(i)          the i'th of them, -1 out of range
;                 HwPwmPinIsHard(pin)    1 if a real PWM channel reaches
;                                        that pin, 0 if only the software
;                                        toggle can, -1 if not a pin here
;                 HwPwmDefaultPin()      the pin a board KNOWS its fan is
;                                        on, or -1 - and -1 is the honest
;                                        answer on a board where the fan
;                                        is whatever somebody wired
;                 HwPwmHzDefault()       the frequency this board's usual
;                                        fan wants
;                 HwPwmHzMin(pin) / HwPwmHzMax(pin)
;                                        the envelope for that pin, so a
;                                        refusal can name the reachable
;                                        range instead of saying no
;                 HwPwmBegin(pin, hz)    claim the pin. A #HW_PWM_* code
;                 HwPwmDuty(permille)    0..1000. A #HW_PWM_* code
;                 HwPwmEnd()             release it, leaving the pad in
;                                        the state the board considers
;                                        safe for a fan
;                 HwPwmService()         called from the periodic tick.
;                                        A no-op for a hardware channel
;                                        and the whole mechanism for a
;                                        software one
;                 HwPwmKind()            #HW_PWM_KIND_* - what is running
;                 HwPwmPin() / HwPwmHz() / HwPwmDutyNow()
;                                        what is running, read back rather
;                                        than remembered by the core
;                 HwPwmDetail(which)     one board-specific number for the
;                                        diagnostic report - see the
;                                        #HW_PWM_DETAIL_* selectors below.
;                                        -1 for a number this board has no
;                                        equivalent of, which is how a
;                                        second board with a different
;                                        divider arrangement stays honest
;                 HwPwmReservedReason(pin)  0, or the ADDRESS of a
;                                        lowercase fragment saying what
;                                        the board is already using that
;                                        pin for - the same shape and the
;                                        same contract as
;                                        HwGpioReservedReason
;
;              AND THE TEMPERATURE SEAM, in the same group:
;                 HwTempMilliC()         the part's temperature in
;                                        millidegrees CELSIUS, or
;                                        #HW_TEMP_NONE
;                 HwTempMaxMilliC()      where the part starts throttling
;                                        itself, or #HW_TEMP_NONE
;                 HwTempSource()         a #HW_TEMP_SRC_* code saying
;                                        WHICH mechanism answered, because
;                                        a board that has silently fallen
;                                        back to a slow path should say so
;
;              A BOARD ANSWERS IN CELSIUS AND NOBODY PRINTS IT. The
;              conversion to Fahrenheit is HwTempMilliF()/HwTempWholeF()
;              in this file, once, for the whole tree - see THE
;              TEMPERATURE section below for why it is here and not in
;              the sensor library.
;
;    HwMmc*    (#CAP_MMC)   the raw `mmc` family, distinct from the
;              mounted-filesystem path #CAP_STORAGE rides. IMPLEMENTED on
;              the Pi 4 as RaspberryPi4/Board/hw_mmc.pi4 over
;              RaspberryPi4/Lib/emmc.pi4, driven by Anvil/Core/mmc_cmd.pbi.
;              The seam the `mmc` command uses:
;                 HwMmcInfo()            bring the card up; 1 ready, 0 not
;                 HwMmcBlockCount()      capacity in blocks, 0 = unknown
;                 HwMmcBlockSize()       the transfer unit, 512 here
;                 HwMmcType()            a #HW_MMC_* card class code
;                 HwMmcReadBlock(lba,*b) one block card->RAM, 1/0
;                 HwMmcCanWrite()        1 if writing is available at all
;                 HwMmcWriteBlock(lba,*b) one block RAM->card, 1/0
;                 HwMmcErrorText()       a whole-sentence reason, as a ptr
;              HwMmcCanWrite() IS THE WRITE GATE: a board whose driver
;              cannot write returns 0 and `mmc write` refuses loudly rather
;              than pretending, without the core learning why.
;    HwUsb*    (#CAP_USB)  the USB host, for the `usb` DIAGNOSTICS family
;              (Anvil/Core/usb_cmd.pbi). The Pi 4 backend is
;              RaspberryPi4/Board/hw_usb.pi4, thin over Lib/pcie + Lib/xhci
;              + Lib/usbmsc + the enumeration walk in Board/cursor_input.pi4
;              - it EXPOSES what that stack already knows, it does not
;              re-drive it. The three anchor names named at scoping time
;              are implemented:
;                 HwUsbEnumerate()       bring the controller up and run the
;                                        one-time attach walk; 1 if the host
;                                        is up (with or without devices), 0
;                                        if PCIe or xHCI would not start
;                 HwUsbTree()            ensure enumerated, build the device
;                                        inventory, return the device count,
;                                        or -1 if the host is not up
;                 HwUsbReadBlock(lba,*b) one 512-byte block off the mounted
;                                        mass-storage LUN into *b; 1 or 0
;              and the read seam the `usb` command renders through, all
;              speaking the portable #HW_USB_* vocabulary below the core:
;                 HwUsbHostPresent()     is the xHCI host up
;                 HwUsbHostVid()/Pid()   the host controller's own PCI ids
;                 HwUsbHostVersion()     the xHCI version (BCD)
;                 HwUsbPortCount()       root ports on the controller
;                 HwUsbPortConnected(p)  1/0
;                 HwUsbPortSpeed(p)      a #HW_USB_SPEED_* code
;                 HwUsbHubPresent()      is there an internal/root hub
;                 HwUsbHubRootPort()     which root port it sits on
;                 HwUsbHubPorts()        its downstream port count
;                 HwUsbHubPortConnected(p) / HwUsbHubPortSpeed(p)
;                 HwUsbDevCount()        addressed devices in the inventory
;                 HwUsbDevSlot(i) / DevKind(i) / DevSpeed(i) / DevRoute(i)
;                 HwUsbDevAddress(i) / DevVid(i) / DevPid(i) / DevClass(i)
;                                        (Vid/Pid/Class are -1 when the
;                                        device descriptor could not be re-read)
;                 HwUsbStorageReady()    is a mass-storage LUN up
;                 HwUsbStorageVendor()/Product()   INQUIRY strings (pointers)
;                 HwUsbStorageBlockSize()/BlockCount()
;                 HwUsbStorageError()    the device's own last error sentence
;                 HwUsbReadAvailable()   1 if a raw block read is exposed
; ======================================================================

; ----------------------------------------------------------------------
;  THE PORTABLE HAL VOCABULARY.
;
;  What a Hw* seam speaks back to the core. The board backend maps its
;  silicon's raw encodings onto these; the core never sees a raw FSEL code
;  or a chip's pull-field value. -1 is the universal "bad argument" answer
;  a getter returns, matching Lib/gpio.pi4's DigitalRead (-1 for a bad
;  pin) so a bad pin can never read as a real low.
; ----------------------------------------------------------------------
#HW_GPIO_IN   = 0             ; the pin is a plain input
#HW_GPIO_OUT  = 1             ; the pin is a plain output
#HW_GPIO_ALT  = 2             ; the pin is on an alternate function - which
                             ; one is HwGpioAltGet()'s answer, because the
                             ; ALT numbering is the board's to know

#HW_PULL_NONE = 0            ; no resistor selected
#HW_PULL_UP   = 1            ; pull-up selected
#HW_PULL_DOWN = 2            ; pull-down selected

; The card class HwMmcType() reports. The distinction that matters to a
; reader of raw blocks is byte- versus block-addressing, so that is what
; the vocabulary carries; the backend maps its silicon's CCS/OCR onto it.
#HW_MMC_UNKNOWN = 0          ; not identified yet, or no card
#HW_MMC_SDSC    = 1          ; standard capacity, byte addressed
#HW_MMC_SDHC    = 2          ; high/extended capacity (SDHC/SDXC), block addressed

; ----------------------------------------------------------------------
;  THE PWM AND TEMPERATURE VOCABULARY - the `fan` family's seam.
;
;  RESULT CODES. Zero is success and every failure is negative and
;  SEPARATELY NAMED, because the whole value of this seam to the command
;  above it is being able to say which of five different things went
;  wrong in a sentence an operator can act on. "The fan could not be
;  set up" is not one of those.
; ----------------------------------------------------------------------
#HW_PWM_OK      = 0
#HW_PWM_PIN     = -1   ; this board will not modulate that pin
#HW_PWM_HZ      = -2   ; a frequency this board's clocking cannot make
#HW_PWM_DUTY    = -3   ; a duty outside 0..1000 permille
#HW_PWM_BUSY    = -4   ; the clocking would not settle
#HW_PWM_STATE   = -5   ; nothing has been begun, so there is nothing to
                       ; set or end
#HW_PWM_INUSE   = -6   ; the board's one modulator is already elsewhere

; The duty scale, fixed HERE so the core and every backend agree without
; either of them naming a range register. Permille, not percent: a fan
; curve that can only step in percent hunts at the bottom of its range.
#HW_PWM_DUTY_MAX = 1000

; WHICH MECHANISM IS DRIVING THE PIN. The core reports this because the
; two are not the same promise: a hardware channel keeps its waveform
; while a command runs for a minute, and a software one does not.
#HW_PWM_KIND_NONE = 0
#HW_PWM_KIND_HARD = 1  ; a real modulator in the part
#HW_PWM_KIND_SOFT = 2  ; a level toggled from the periodic tick, coarse

; HwPwmDetail() selectors. ONE ACCESSOR WITH A SELECTOR rather than six
; named ones, because these are the numbers a DIAGNOSTIC wants and every
; board's set is different - a board whose modulator has no divider
; answers -1 to that selector and the report simply omits the line. Six
; named accessors would make five of them meaningless on the next board
; and would still not cover its sixth.
#HW_PWM_DETAIL_RANGE   = 0   ; the period, in whatever counts the part uses
#HW_PWM_DETAIL_DIVISOR = 1   ; the divisor between the source and those counts
#HW_PWM_DETAIL_SRCHZ   = 2   ; the clock feeding the divisor, in Hz
#HW_PWM_DETAIL_STALLS  = 3   ; software kind only: times the tick was too
                             ; late and the pin was parked
#HW_PWM_DETAIL_EDGES   = 4   ; software kind only: edges driven so far

; ----------------------------------------------------------------------
;  TEMPERATURE.
;
;  THE SEAM ANSWERS IN MILLIDEGREES CELSIUS. EVERY PERSON READS
;  FAHRENHEIT. Those are two different statements and both are true, and
;  the line between them is this file.
;
;  BELOW THE SEAM it is Celsius because that is what the silicon says.
;  The BCM2711's AVS monitor converts its ring-oscillator code with two
;  coefficients out of a device tree, in millidegrees Celsius; the
;  VideoCore firmware answers GET_TEMPERATURE in millidegrees Celsius.
;  A driver rewritten into Fahrenheit stops being checkable line by line
;  against the document it was written from, which is the one property
;  that makes a sensor library trustworthy.
;
;  ABOVE THE SEAM it is Fahrenheit because that is the house unit for
;  anything a person reads. The conversion is HERE, it is ONE function,
;  and it is the only one in the tree - project ruling, 2026-09-07. A
;  second copy in a command or in a board file is how two lines of the
;  same report come to disagree by a degree, and how a caller ends up
;  holding a Celsius number it believes is Fahrenheit.
;
;  WHY THE CONVERSION LIVES IN THE SEAM AND NOT IN THE SENSOR LIBRARY.
;  It is pure arithmetic and not a fact about any chip, and the callers
;  are spread across both sides of the tree: a board's own information
;  command, the fan policy in Anvil/Core, the fan command's report. The
;  Pi 4 has RaspberryPi4/Lib/thermal.pi4 and the UNO Q has no such file
;  at all - putting the arithmetic there would mean a second copy on
;  every board that has none, which is exactly what "one conversion"
;  forbids. This file is compiled into every board and is included ahead
;  of every one of those callers, so there is one copy and every caller
;  reaches it.
;
;  #HW_TEMP_NONE IS NOT ZERO AND NOT -1, and both of those matter: 0 C
;  and -1 C are real temperatures, and a sentinel that collides with a
;  reading is how a fan ends up stopped in a hot room. -273151
;  millidegrees is below absolute zero, so it can never be a
;  measurement. IT IS THE SENTINEL IN BOTH UNITS: -273.151 F is also
;  below absolute zero (which is -459.67 F), so one number serves both
;  sides of the conversion and there is no second sentinel to keep in
;  step with the first.
; ----------------------------------------------------------------------
#HW_TEMP_NONE = -273151

#HW_TEMP_SRC_NONE     = 0   ; nothing answered
#HW_TEMP_SRC_REGISTER = 1   ; a sensor the core read directly
#HW_TEMP_SRC_FIRMWARE = 2   ; a platform firmware answered a request

; The freezing point of water in MILLI-FAHRENHEIT, named rather than
; typed as 32000 at the one site that uses it, so a reader can see the
; 32 of "F = C * 9 / 5 + 32" and the thousand of "milli" separately.
#HW_TEMP_F_OFFSET_MILLI = 32000

; ----------------------------------------------------------------------
;  HwTempMilliF(milliC) - THE ONE CONVERSION. Millidegrees Celsius in,
;  milli-Fahrenheit out.
;
;      F = C * 9 / 5 + 32     ->     mF = mC * 9 / 5 + 32000
;
;  INTEGER THROUGHOUT. There is no floating point in the monitor's
;  temperature path on either target and there is no reason to introduce
;  one for a multiply and a divide: milliC is at most a few hundred
;  thousand, times nine is under ten million, and the whole 64-bit width
;  of both targets is available.
;
;  MULTIPLY FIRST, DIVIDE ONCE, AT THE END. Dividing by five before
;  multiplying by nine would throw away up to four millidegrees and then
;  scale the loss.
;
;  IT ROUNDS TO NEAREST AND IT IS CORRECT ON BOTH SIDES OF ZERO. Integer
;  division truncates toward zero in this language, so adding half the
;  divisor is right for a positive value and wrong for a negative one -
;  the same trap ThermalWholeC() documents, and the same fix. A Pi 4
;  below freezing is an unheated workshop in winter and is not
;  hypothetical; a rounding rule that is only right in the common half
;  is never noticed and never right.
;
;  #HW_TEMP_NONE PASSES THROUGH UNCHANGED, so a caller can make the same
;  sentinel test either side of the conversion. Without this, the
;  sentinel would convert to a perfectly ordinary-looking -459 F and a
;  "no thermometer" would print as a temperature.
; ----------------------------------------------------------------------
Procedure.i HwTempMilliF(milliC.i)
  Define n.i
  If milliC = #HW_TEMP_NONE
    ProcedureReturn #HW_TEMP_NONE
  EndIf
  n = milliC * 9
  If n >= 0
    ProcedureReturn (n + 2) / 5 + #HW_TEMP_F_OFFSET_MILLI
  EndIf
  ProcedureReturn -((-n + 2) / 5) + #HW_TEMP_F_OFFSET_MILLI
EndProcedure

; ----------------------------------------------------------------------
;  HwTempMilliCOf(milliF) - the conversion BACKWARDS, for the one job
;  that needs it: reading a fan curve off a card that was written before
;  this ruling. Nothing a person reads goes through here.
;
;      C = (F - 32) * 5 / 9   ->   mC = (mF - 32000) * 5 / 9
;
;  Same rounding rule, same reason.
; ----------------------------------------------------------------------
Procedure.i HwTempMilliCOf(milliF.i)
  Define n.i
  If milliF = #HW_TEMP_NONE
    ProcedureReturn #HW_TEMP_NONE
  EndIf
  n = (milliF - #HW_TEMP_F_OFFSET_MILLI) * 5
  If n >= 0
    ProcedureReturn (n + 4) / 9
  EndIf
  ProcedureReturn -((-n + 4) / 9)
EndProcedure

; ----------------------------------------------------------------------
;  HwTempWhole(milli) - thousandths to whole degrees, rounded to NEAREST
;  and correct on both sides of zero.
;
;  UNIT-BLIND ON PURPOSE. It is the same arithmetic for milli-Fahrenheit
;  and for millidegrees Celsius, and giving it a unit in its name would
;  invite a second copy for the other one.
;
;  #HW_TEMP_NONE passes through, for the reason above.
; ----------------------------------------------------------------------
Procedure.i HwTempWhole(milli.i)
  If milli = #HW_TEMP_NONE
    ProcedureReturn #HW_TEMP_NONE
  EndIf
  If milli >= 0
    ProcedureReturn (milli + 500) / 1000
  EndIf
  ProcedureReturn -((-milli + 500) / 1000)
EndProcedure

; HwTempWholeF(milliC) - the whole number a person reads, from the unit
; the seam answers in. Every "NNN F" in this monitor comes from here, so
; there is one place where a rounding rule could ever change.
Procedure.i HwTempWholeF(milliC.i)
  ProcedureReturn HwTempWhole(HwTempMilliF(milliC))
EndProcedure

; ----------------------------------------------------------------------
;  THE LAST SAMPLE - the temperature as a VALUE, for a reader that must
;  not take the reading itself.
;
;  HwTempMilliC() is a seam. On a board whose thermal implementation is
;  loadable, the call goes through a pointer held in the service table,
;  and a pointer is a call to every procedure whose address that table
;  can hold - so a reader reachable from the boot walk or from the screen
;  service cannot ask the seam at all without closing a call loop that
;  does not exist at run time. That is a true statement about the shape
;  of the program, not a limitation to be argued with: the reading is a
;  side effect of touching hardware, and a repaint is not the place for
;  one.
;
;  SO THE READING AND THE READER ARE SEPARATED. One periodic owner takes
;  the sample - once a second, on the path that already touches hardware
;  for a living - and publishes it here in the seam's own unit,
;  millidegrees Celsius, unconverted, because that is what the board said.
;  Anything that only wants to SHOW a temperature reads this and does no
;  hardware at all.
;
;  IT STARTS AT #HW_TEMP_NONE and it means it: before the first sample
;  there is no reading, and a caller must make the same sentinel test it
;  would make on the seam's own answer. A zero here would be 32 F on the
;  panel of a board that has never been asked.
;
;  THE VOCABULARY IS THE HAL'S because the unit and the sentinel are. A
;  second board defines the sample the same way whether or not it has a
;  fan, and a board with no thermometer at all simply never publishes
;  one and reads the sentinel forever.
; ----------------------------------------------------------------------
Global gHwTempSampledMilliC.i = #HW_TEMP_NONE

; The last published sample, in millidegrees Celsius, or #HW_TEMP_NONE.
Procedure.i HwTempSampled()
  ProcedureReturn gHwTempSampledMilliC
EndProcedure

; ----------------------------------------------------------------------
;  THE ADDRESS-SAFETY VOCABULARY - what HwAddrCheck() answers.
;
;  THREE ANSWERS AND NOT TWO, and the third one is the whole reason this
;  seam is worth having. A yes/no predicate forces a board to lie in one
;  direction or the other about every address nobody has measured: say
;  "safe" and the first person to type one wedges the board, say "unsafe"
;  and the monitor refuses most of the machine it is supposed to be a
;  debugger for. UNKNOWN is the honest third answer - "nobody has proven
;  this one either way" - and the core treats it differently from both:
;  it refuses, says exactly that, and tells the operator how to override
;  it deliberately.
;
;  SAFE means the board has a positive reason to believe the access
;  completes: DRAM it has mapped, or a block it has actually read on
;  silicon. It does NOT mean "probably fine".
;
;  UNCLOCKED means the board KNOWS this block is gated, powered down, or
;  otherwise unable to answer a bus transaction right now. On some parts
;  that is a fault; on at least one part in this tree it is a hang with
;  no message and no recovery but the power switch.
;
;  UNKNOWN means the board has no entry for this address. It is not a
;  failure of the seam - it is the seam refusing to guess.
;
;  THE VALUES ARE POSITIVE AND SAFE IS ZERO so that `If HwAddrCheck(...)
;  <> 0` reads as "there is something to say about this address", which
;  is the shape every other refusal in the core already has, and so that
;  a board which has not implemented the seam cannot accidentally answer
;  SAFE by returning nothing - a procedure that falls off its end returns
;  an unspecified value, and the value that would be waved through is the
;  one this ordering makes least likely.
; ----------------------------------------------------------------------
#HW_ADDR_SAFE      = 0   ; the board has a reason to believe this works
#HW_ADDR_UNCLOCKED = 1   ; the board knows this block cannot answer now
#HW_ADDR_UNKNOWN   = 2   ; the board has no entry for this address

; ----------------------------------------------------------------------
;  THE LINK KINDS - what sort of wire a frame goes out of.
;
;  These are the values the HwLink* seam is addressed by and the values
;  RaspberryPi4/Lib/link.pi4's policy layer stores as "the link in use".
;  They live HERE, once, rather than in link.pi4, because both the board
;  backends and the portable policy have to agree on them and a constant
;  defined twice is a constant that eventually differs.
;
;  A KIND IS NOT A DRIVER AND IT IS NOT A DEVICE NUMBER. It is the answer
;  to "what sort of thing is carrying this frame", which is the only thing
;  the portable layers ever need to know - the radio needs a rekey served
;  and has a smaller transmit ceiling; a point-to-point serial line has no
;  hardware address and no ARP to do; a firmware-carried link has no
;  driver at all. Everything below that is the board's.
;
;  THE LIST IS OPEN. A future board with a link none of these describes
;  adds one name here, one Case in its own HwLinkName, and nothing else -
;  the policy layer switches on presence and carrier, not on the kind.
; ----------------------------------------------------------------------
#HW_LINK_NONE     = 0   ; nothing is carrying anything
#HW_LINK_WIRED    = 1   ; a wired Ethernet MAC the board drives itself
#HW_LINK_WIFI     = 2   ; a radio, joined to a network
#HW_LINK_SERIAL   = 3   ; a point-to-point serial line carrying framed
                        ; packets (SLIP, RFC 1055). No MAC, no ARP, no
                        ; broadcast domain - the peer is the only peer.
#HW_LINK_FIRMWARE = 4   ; the platform firmware moves the frames and the
                        ; board writes no driver at all. On the UNO Q this
                        ; is EFI_SIMPLE_NETWORK_PROTOCOL, IF the firmware
                        ; publishes one.
#HW_LINK_FILE     = 5   ; A CONFORMANCE CHANNEL, NEVER A PRODUCT LINK.
                        ; Frames are read from a file and replies written
                        ; to another, so the whole IP stack can be
                        ; exercised on real silicon before any wire
                        ; exists. It must never be selected by the
                        ; ordinary policy and must never be described to
                        ; an operator as a network - see LinkUseKind.

; ----------------------------------------------------------------------
;  WHAT A LINK CAN SAY ABOUT ITSELF - the answers HwLinkSpeed and
;  HwLinkDuplex are allowed to give.
;
;  UNKNOWN IS A REAL ANSWER AND IT IS NEGATIVE ON PURPOSE. Every other
;  value either of these can return is a count - megabits per second, or
;  one of two duplex states - and a count is never negative, so a caller
;  that forgets to check cannot mistake "this board does not know" for a
;  measurement. That is the same discipline the -1 getters elsewhere in
;  this file use, and it exists because the alternative that reads
;  naturally - answer zero - is indistinguishable from a link running at
;  no speed at all.
;
;  A BOARD ANSWERS UNKNOWN WHENEVER THE NUMBER WOULD BE A GUESS. A serial
;  line's configured baud rate is not a negotiated speed and a link with
;  no far end to negotiate with has no duplex state; printing either as
;  though it were measured is the quiet wrong answer this project refuses.
; ----------------------------------------------------------------------
#HW_LINK_SPEED_UNKNOWN  = -1  ; no measurable rate for this kind
#HW_LINK_DUPLEX_UNKNOWN = -1  ; the question does not apply, or nothing
                              ; has negotiated yet
#HW_LINK_DUPLEX_HALF    = 0
#HW_LINK_DUPLEX_FULL    = 1

; ----------------------------------------------------------------------
;  THE NETWORK CONSOLE'S UDP PORT - ONE HOME, 2026-09-07.
;
;  It was #WIFI_CON_PORT in RaspberryPi4/Lib/wifi.pi4, which was right
;  while the console could only ride a radio and wrong the moment it could
;  ride a cable as well. THE NUMBER ITSELF HAS NOT CHANGED AND MUST NOT:
;  every host tool in tools/ speaks to 5555, and a monitor that quietly
;  moved its own console port would strand every note anybody has written
;  down.
;
;  It lives here rather than in Anvil/Core/netconsole.pbi because
;  RaspberryPi4/Lib/wifi.pi4 prints it in its status line and is included
;  BEFORE the console, and two literal 5555s would eventually be two
;  different numbers.
; ----------------------------------------------------------------------
#NETCON_PORT = 5555

; Maximum frames drained from one interface before cooperative polling
; gives the rest of the monitor a turn. Linux bcmgenet uses a budgeted
; NAPI drain; 64 is large enough for bursts without creating an
; unbounded prompt stall.
#LINK_RX_BUDGET = 64

; ----------------------------------------------------------------------
;  THE I2C RESULT VOCABULARY - what the HwI2c* seam speaks back to the
;  core. A bus transaction is not a yes/no: it can succeed, find nothing at
;  an address, be refused by a slave that stretches the clock too long, or
;  hang on a bus with no pull-ups. The core renders an honest sentence per
;  case (Anvil/Core/i2c_cmd.pbi) without knowing that on THIS part the ACK
;  failure is status bit 8 and the stretch timeout is bit 9 - the board
;  backend (RaspberryPi4/Board/hw_i2c.pi4 over Lib/i2c.pi4) maps its
;  silicon's status bits onto these. 0 is success; the failures are
;  negative so a getter that returns a byte value (0..255) can never be
;  confused with an error, the same discipline the -1 getters use above.
; ----------------------------------------------------------------------
#HW_I2C_OK      = 0          ; the transaction completed
#HW_I2C_NACK    = -2         ; no device answered / a byte was not ACKed
#HW_I2C_CLKT    = -3         ; slave held the clock down past the timeout
#HW_I2C_TIMEOUT = -4         ; the controller never finished. WHAT THAT MEANS
                             ; IS NOT DECIDED HERE - see the note below
#HW_I2C_ARG     = -5         ; a bad argument (count, address range)
#HW_I2C_NOBUS   = -6         ; this board has no such I2C bus
#HW_I2C_RANGE   = -7         ; a well-formed rate the divider cannot reach
                             ; from the clock it is fed by. SEPARATE FROM
                             ; #HW_I2C_ARG on purpose: the argument was
                             ; fine, the answer depends on a clock that
                             ; moves under the board, and the caller is
                             ; owed the reachable range rather than "out
                             ; of range". HwI2cRateMin/Max supply it.

; ----------------------------------------------------------------------
;  #HW_I2C_TIMEOUT USED TO CARRY A DIAGNOSIS. IT NO LONGER DOES.
;
;  The comment on that line said "(bus wedged)" and the core printed it
;  that way: SDA or SCL stuck low, check the wiring and the pull-ups. That
;  is ONE cause of a controller that never finishes, and on a Pi 4 with
;  nothing attached it was the wrong one every single time - the pads were
;  measured idle-high, with pull-ups, at the moment the sentence blamed
;  them (forum 584). A code that names a cause the code cannot know is the
;  same defect shape as the RP2350's IC_RAW_INTR_STAT read, which could not
;  tell "no device" from "not connected" and said the confident thing.
;
;  So #HW_I2C_TIMEOUT now means exactly and only "the controller did not
;  complete the transfer", and the CAUSE is decided afterwards by MEASURING
;  the two pads through HwI2cPadLevel(). I2cTimeoutVerdict() in
;  Anvil/Core/i2c_cmd.pbi turns those two levels into one verdict, and both
;  the probe path and the read/write path render that same verdict - one
;  condition, one answer, whichever command asked.
; ----------------------------------------------------------------------

; Which of a bus's two pins is being asked about. These are I2C concepts,
; not chip concepts - every I2C bus has a data line and a clock line - so
; the core may name them, and the board maps them onto its own pins.
#HW_I2C_SDA = 0              ; the data line
#HW_I2C_SCL = 1              ; the clock line

; ----------------------------------------------------------------------
;  USB - the portable vocabulary the HwUsb* seam speaks back to the core,
;  so the `usb` command can render a device's speed and kind without
;  knowing that on THIS controller a SuperSpeed port reports 4 and a
;  mass-storage class is 8. The board backend (RaspberryPi4/Board/hw_usb.pi4
;  on the Pi 4) maps the controller's raw speed IDs and USB class bytes
;  onto these; the core (Anvil/Core/usb_cmd.pbi) only ever sees these.
;
;  These are USB concepts, not chip concepts - every USB host has a
;  notion of low/full/high/super speed and of a device class - so they
;  belong in the portable vocabulary exactly as the GPIO codes above do.
; ----------------------------------------------------------------------
#HW_USB_SPEED_UNKNOWN = 0   ; the port has not been reset, or is empty
#HW_USB_SPEED_LOW     = 1   ; 1.5 Mb/s
#HW_USB_SPEED_FULL    = 2   ; 12 Mb/s
#HW_USB_SPEED_HIGH    = 3   ; 480 Mb/s
#HW_USB_SPEED_SUPER   = 4   ; 5 Gb/s

; What a device attached to the bus IS, as far as enumeration could tell.
; HwUsbDevKind() speaks these. OTHER covers a device that was addressed
; but is neither a boot-protocol HID device, a hub, nor mass storage this
; monitor could bring up - it is on the bus and named honestly, not hidden.
#HW_USB_KIND_OTHER    = 0
#HW_USB_KIND_KEYBOARD = 1
#HW_USB_KIND_MOUSE    = 2
#HW_USB_KIND_STORAGE  = 3
#HW_USB_KIND_HUB      = 4

; ----------------------------------------------------------------------
;  THE FILE RESULT VOCABULARY - what the HwFile* seam speaks back to the
;  core when it refuses. The core renders an honest sentence per case
;  without knowing that on the Pi 4 "not there" is fat.pi4's
;  #FAT_ERR_NOTFOUND and on the Arduino UNO Q it is UEFI's
;  EFI_NOT_FOUND ($800000000000000E) coming back from
;  EFI_FILE_PROTOCOL.Open. The board backend maps its medium's codes onto
;  these; the core only ever sees these.
;
;  NOT-THERE HAS ITS OWN CODE AND THAT IS THE WHOLE POINT OF THE LIST. On
;  a first boot there is no SETTINGS.TXT and there should not be one, and
;  a monitor that answered "the medium refused" at that moment would send
;  a new owner looking for a fault in a stick that is perfectly fine.
;  settings.pi4 has made that distinction since it was written; this
;  vocabulary is that distinction moved to where both boards can speak it.
;
;  0 is success and the failures are positive, unlike the I2C codes above
;  which are negative because those getters also return byte VALUES. No
;  HwFile* entry point returns a byte value, so there is nothing to
;  collide with and a plain enumeration reads better.
; ----------------------------------------------------------------------
#HW_FILE_OK        = 0   ; the operation completed
#HW_FILE_NOTFOUND  = 1   ; no file of that name. NORMAL, not a fault
#HW_FILE_NOMEDIUM  = 2   ; no medium came up at all, so there is nowhere
                         ; for a file of any name to be
#HW_FILE_IO        = 3   ; the medium was there and the transfer failed
#HW_FILE_BADNAME   = 4   ; the name is not one this board's medium can
                         ; express (on the Pi 4, anything that is not a
                         ; root-directory 8.3 short name)
#HW_FILE_READONLY  = 5   ; readable here, not writable here
#HW_FILE_TOOBIG    = 6   ; the length asked for is beyond what this
                         ; backend will transfer in one call
#HW_FILE_NOTOPEN   = 7   ; a read or a size was asked for with no file
                         ; open - a caller bug, said out loud rather
                         ; than answered with a plausible zero

; ----------------------------------------------------------------------
;  THE SHAPE OF A DIRECTORY NAME, as HwDirName() hands one back.
;
;  ELEVEN RAW BYTES: eight of base and three of extension, space-padded,
;  with no dot stored between them. That is the 8.3 short name every FAT
;  volume keeps in its directory entries, and it is in the portable
;  vocabulary for the same reason #HW_USB_SPEED_HIGH is - the core has to
;  format one, and formatting it needs to know where the extension starts.
;
;  IT IS A COPY OF fat.pi4's #FAT_NAME_LEN AND THAT IS DELIBERATE. The
;  core cannot name #FAT_NAME_LEN: Anvil/Core/fs_cmd.pbi compiles for the
;  Arduino UNO Q, which has no fat.pi4 in its build at all, and it used to
;  size its row buffer with that constant - which is exactly the sort of
;  quiet coupling this seam exists to remove. A board whose names are not
;  8.3 hands back whatever it has, padded into eleven bytes, or answers 0
;  from HwFileCanList() and is never asked.
; ----------------------------------------------------------------------
#HW_DIR_NAME_LEN  = 11       ; the raw bytes HwDirName() writes
#HW_DIR_BASE_MAX  = 8        ; ... of which this many are the base
#HW_DIR_EXT_MAX   = 3        ; ... and this many the extension

; ----------------------------------------------------------------------
;  THE VOCABULARIES THE PAYLOAD ABI ADDED, 2026-09-04.
;
;  Same discipline as everything above: these are CONCEPTS, not chip
;  encodings. Every board's backend maps its silicon onto them and the
;  core - and now the payload, through Anvil/Hal/abi.pbi - only ever sees
;  these.
;
;  THE ONE HARD RULE ABOUT THEIR NUMBERS. The service table's own error
;  set (#SVC_*) occupies -100 .. -199, and NO #HW_* CODE ANYWHERE IN THIS
;  FILE MAY EVER BE MORE NEGATIVE THAN -99. The two ranges have to be
;  disjoint because several ABI slots are straight re-exports of a Hw*
;  seam and must be able to answer either vocabulary from one register:
;  slot 116 returns #HW_I2C_* on a board with a bus and #SVC_ENOCAP on a
;  board without one. When #SVC_ENOCAP was -2 that was the same number as
;  #HW_I2C_NACK, and a payload on a board with no I2C at all would have
;  rendered "no device answered at that address" - a sentence sending the
;  operator to check wiring that is not there.
;
;  That is the defect shape this tree has paid for twice already: the
;  RP2350's IC_RAW_INTR_STAT read, and #HW_I2C_TIMEOUT's old "(bus
;  wedged)". tools/a64/a64_abi_check.py parses both files and goes red if
;  either bound is broken.
; ----------------------------------------------------------------------

; Which drawing path a console surface is actually using. INFORMATIONAL:
; the payload draws the same either way, and this exists so a measured
; frame time can be read against the path that produced it.
#HW_TIER_CPU  = 0            ; a processor loop over the framebuffer
#HW_TIER_DMA  = 1            ; the DMA engine
#HW_TIER_V3D  = 2            ; the 3D core

; What a touch contact is doing. FOUR STATES AND NOT THREE, and the
; fourth is the one that matters: _CANCEL means the CONTROLLER LOST THE
; CONTACT - a palm, a reset, a wet screen - and it is NOT the same as
; _UP. A UI that treats it as _UP will fire a button the driver did not
; press, which on this product is a duty-status change nobody made.
#HW_TOUCH_DOWN   = 0
#HW_TOUCH_MOVE   = 1
#HW_TOUCH_UP     = 2
#HW_TOUCH_CANCEL = 3

; The quality of a satellite fix, as HwGnssFix() returns it.
#HW_GNSS_NOFIX = 0
#HW_GNSS_2D    = 1
#HW_GNSS_3D    = 2
#HW_GNSS_DGPS  = 3

; Which of an SPI bus's pins is being asked about. SPI concepts, not chip
; concepts, exactly as #HW_I2C_SDA and #HW_I2C_SCL are.
#HW_SPI_MOSI = 0
#HW_SPI_MISO = 1
#HW_SPI_SCLK = 2
#HW_SPI_CS0  = 3
#HW_SPI_CS1  = 4

#HW_SPI_OK    =  0
#HW_SPI_ARG   = -8           ; a bad argument (count, mode, chip select)
#HW_SPI_NOBUS = -9           ; this board has no such SPI bus
#HW_SPI_IO    = -10          ; the controller did not complete the transfer

; ----------------------------------------------------------------------
;  THE VEHICLE-LINK VOCABULARY.
;
;  Ruling of 2026-09-04: the engine port belongs to a SECOND UNIT that
;  talks to this board over Wi-Fi or LoRa. So there are two hops between
;  the engine and the log, and they fail independently.
; ----------------------------------------------------------------------
#HW_VEH_DOWN      = 0        ; the link has not been brought up
#HW_VEH_SEARCHING = 1        ; up, and no unit has answered yet
#HW_VEH_LINKED    = 2        ; a unit is answering
#HW_VEH_STALE     = 3        ; it answered, and has not lately

#HW_VEH_XPORT_NONE = 0
#HW_VEH_XPORT_WIFI = 1
#HW_VEH_XPORT_LORA = 2

; THE TWO LOSS STATES, AND WHY THEY ARE TWO. 49 CFR 395 Appendix A 4.3.1.1
; makes more than thirty minutes of lost ECM connectivity, aggregated over
; twenty-four hours, a malfunction. With one box that was one measurement;
; with two boxes it is two, and BOTH COUNT AND ARE RECORDED SEPARATELY,
; because they have different causes and different fixes - the first is a
; diagnostic-connector or J1939 fault in the truck, the second is a radio,
; power or pairing fault.
;
; COLLAPSING THEM WOULD PRODUCE A LOG THAT CANNOT TELL A MECHANIC WHICH
; BOX TO LOOK AT, and would let a device that has merely lost its radio
; report confidently about an engine it cannot reach.
#HW_VEH_LOSS_NONE   = 0      ; the unit is heard AND the unit hears the engine
#HW_VEH_LOSS_ENGINE = 1      ; THE UNIT LOST THE ENGINE. The radio is fine and
                             ; the unit is telling us its own ECM connection
                             ; is down. Known POSITIVELY, from the unit.
#HW_VEH_LOSS_UNIT   = 2      ; WE LOST THE UNIT. The radio is down, so we do
                             ; not know whether the engine is connected. This
                             ; is not "engine present" and it is not "engine
                             ; absent" - it is no measurement at all.

; How fresh the engine record HwVehData() filled actually is.
#HW_VEH_NEVER = 0            ; nothing has ever arrived
#HW_VEH_STALE_REC = 1        ; something did, and not lately
#HW_VEH_FRESH = 2            ; the current record is current

; The link's own diagnostics, by id. COUNTERS AND NOT A HEALTH VERDICT,
; for the same reason #HW_I2C_TIMEOUT stopped carrying a diagnosis: a
; number an operator can read survives being wrong about its cause, and a
; verdict does not.
#HW_VEHDIAG_RX        = 0    ; frames accepted from the unit
#HW_VEHDIAG_DROPPED   = 1    ; frames the queue had no room for
#HW_VEHDIAG_MALFORMED = 2    ; frames that failed their own checks
#HW_VEHDIAG_RESYNCS   = 3    ; times the link was re-established
#HW_VEHDIAG_SIGNAL    = 4    ; the transport's signal figure, dBm on both
                             ; Wi-Fi and LoRa - so this one is portable
#HW_VEHDIAG_LATENCYMS = 5    ; the last measured one-way latency, or -1

; ----------------------------------------------------------------------
;  WHERE A TIME CAME FROM. HwClockUtc() and HwClockProvenance() answer one
;  of these, and the ORDER IS THE TRUST ORDER.
;
;  #HW_CLK_RESTORED IS A FLOOR, NOT A TIME, and RtcTrusted() has always
;  answered 0 for it. A clock read back off the boot medium says only
;  "it is at least this late"; treating that as a measurement is how a
;  log gets timestamps that are confidently wrong.
; ----------------------------------------------------------------------
#HW_CLK_UNSET    = 0         ; nobody has told this board what time it is.
                             ; Every getter answers -1 and an ELD refuses
                             ; to record.
#HW_CLK_RESTORED = 1         ; read back from the boot medium. A FLOOR.
#HW_CLK_RTC      = 2         ; a battery-backed clock said so
#HW_CLK_GNSS     = 3         ; a satellite said so. The only authoritative
                             ; source, and the only one 4.3.1.5(a) admits
                             ; without a person in the loop.

; ----------------------------------------------------------------------
;  RequireCap(cap, *name, *reason) - the gate.
;
;  cap      the capability flag the board declared, passed BY VALUE by the
;           command handler, e.g. RequireCap(#CAP_GPIO, ...). RequireCap
;           does not know which constant it is; it only knows 0 or not-0.
;  *name    the command word, for the message - "gpio", "i2c", "booti".
;  *reason  the operator-facing reason the group is absent, as a lowercase
;           fragment that reads after "because" - e.g. "this board exposes
;           no general-purpose I/O pins to Anvil". It is generic to the
;           hardware CLASS, not to any chip, so the core stays chip-free:
;           whether a board lacks GPIO because it has no pins or because no
;           driver was written, the operator's fact is the same sentence.
;
;  RETURNS 1 when the capability is present, so the caller proceeds. When
;  it is absent it prints the honest, whole-sentence refusal in the tone
;  of Anvil/Core/memcmd.pbi - names the command, gives the reason, says
;  plainly that nothing was done and that this is one core across many
;  boards, not a fault - and RETURNS 0 so the command returns cleanly. NO
;  silent failure: a gated command that is absent still prints, on the one
;  path this project cares about most.
;
;  BOTH string arguments are pointers (*name/*reason). A string literal at
;  a call site materialises to the address of that literal in the image,
;  which is exactly what UartWriteStr() takes - the same mechanism every
;  UartWriteStr("...") in this tree uses. They are printed with
;  UartWriteStr and NOT Print: Print() picks its formatter from the
;  argument TYPE and an untyped pointer is not a .s, so Print(*name) would
;  print the ADDRESS in decimal. That trap is documented at PutClockRow,
;  at UsbDiskUp and in settings_cmd.pi4; this is it avoided once more.
; ----------------------------------------------------------------------
Procedure.i RequireCap(cap.i, *name, *reason)
  If cap <> 0
    ProcedureReturn 1
  EndIf
  Print("!! the ")
  UartWriteStr(*name)
  PrintN(" command is not available on this board, because")
  Print("   ")
  UartWriteStr(*reason)
  PrintN(".")
  PrintN("   Nothing was done. Anvil is one core built for many boards, so a")
  PrintN("   command that needs hardware this board does not have refuses in a")
  PrintN("   whole sentence rather than pretending or failing quietly. This is")
  PrintN("   not a fault. Type info to see what this board is, and help for the")
  PrintN("   commands that do work here.")
  ProcedureReturn 0
EndProcedure
