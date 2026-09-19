#!/usr/bin/env python3
"""Guard the touch status command against unsupported hardware diagnoses."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RaspberryPi4/Board/touch_cmd.pi4"


def section(text, start, end):
    lo = text.index(start)
    hi = text.index(end, lo)
    return text[lo:hi]


def main():
    text = SOURCE.read_text(encoding="utf-8")
    mcu = section(text, "Procedure.i TouchSayMcu()", "EndProcedure")
    status = section(text, "Procedure TouchStatus()", "EndProcedure")
    observed = mcu + status

    required = (
        "An ACK followed by failed reads does not identify the",
        "software shadow does not prove the pin levels",
        "Neither supported address completed the six-byte read from $8140",
        "does not distinguish controller state, reset, wiring, fitted",
        "no reset diagnosis follows from them",
        "address alone does not identify the Waveshare panel",
    )
    forbidden = (
        "held in reset or is not fitted",
        "Treat the MCU as",
        "suspect the ribbon",
        "THE RIBBON CARRIES I2C AND IS SEATED",
        "nothing on this bus is alive",
        "$14 is the first-generation Waveshare panel",
        "$5D is the DSI-TOUCH generation",
        "The Goodix could not have answered before this line",
        "A RANGE OF ZERO IS AN UNPROGRAMMED CONFIG BLOCK",
        "still read, which is how to tell a dead controller from this",
        "What the values MEAN is not published anywhere",
    )
    for phrase in required:
        if phrase not in observed:
            raise AssertionError("missing evidence-limited status text: " + phrase)
    for phrase in forbidden:
        if phrase in observed:
            raise AssertionError("unsupported touch diagnosis returned: " + phrase)

    if "HwTouchRestart()" not in status:
        raise AssertionError("status behavior changed while editing diagnostics")
    if status.index("HwTouchRestart()") > status.index("a = Gt9Addr()"):
        raise AssertionError("status probe ordering changed")
    if "TouchTraceShow()" in status or "DsiV2TouchReset()" in status:
        raise AssertionError("status text edit added trace/reset actions")

    command = section(text, "Procedure TouchPanel()", "EndProcedure")
    for phrase in (
            "The accepted write and software shadow do not prove pin levels",
            "The shadow does not prove the electrical reset level",
            "does not by itself"):
        if phrase not in command:
            raise AssertionError("missing evidence-limited panel text: " + phrase)
    for phrase in ("Nothing is powered", "THE PANEL IS POWERED",
                   "that is a wiring or a generation answer"):
        if phrase in command:
            raise AssertionError("unsupported panel diagnosis returned: " + phrase)

    print("touch_status_text_check: PASS 26 evidence and behavior guards")


if __name__ == "__main__":
    main()
