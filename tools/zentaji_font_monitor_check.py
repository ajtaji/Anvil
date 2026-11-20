"""Check proportional and monospace console glyphs on the native GPU scanout."""
from pathlib import Path
import time
from unittest.mock import patch

from pmfshot import png
import pmfshot_wifi
from zentaji_package_check import screen_check


def marker_spans(rows, columns=20):
    """Span of evenly spaced vertical strokes on each matching scan line."""
    matches = []
    for row in rows[128:]:
        xs = [x for x in range(len(row)//3) if min(row[3*x:3*x+3]) > 110]
        runs = []
        for x in xs:
            if runs and x == runs[-1][-1]+1:
                runs[-1].append(x)
            else:
                runs.append([x])
        if len(runs) != columns or not 7 <= runs[0][0] < 40:
            continue
        centers = [(run[0]+run[-1]) / 2 for run in runs]
        gaps = [b-a for a,b in zip(centers, centers[1:])]
        if min(gaps)>1 and max(gaps)-min(gaps)<=2:
            matches.append(centers[-1]-centers[0])
    return matches


def check_fonts(command, client, port, folder):
    def measure(tag,columns):
        marker = "I"*columns
        command("echo "+marker, marker)
        capture=folder/("font-"+tag+".png")
        deadline=time.monotonic()+90
        while True:
            with patch.object(pmfshot_wifi, "PORT", port):
                width,height,rows = pmfshot_wifi.grab_reliable("127.0.0.1", timeout=90)
            client.prompt()
            assert (width,height)==(1024,768)
            capture.write_bytes(png(width,height,rows))
            spans=marker_spans(rows, columns)
            if spans:
                screen_check(capture)
                return sorted(spans)[len(spans)//2]
            if time.monotonic()>=deadline:
                raise AssertionError(f"No {columns}-stroke marker on GPU frame {capture}")
            time.sleep(0.5)

    font_bytes=(Path(__file__).resolve().parents[1]/"RaspberryPi3/Data/fonts/CourierPrime-Regular.ttf").stat().st_size
    command("font info","selected font: embedded TrueType")
    command("font select bitmap","This console uses TrueType")
    command("font load 1 BAD.TTF","could not read or validate")
    command("font load 1 MONO.TTF",f"{font_bytes} bytes")
    command("font select 1","font slot 1 selected")
    command("font select 2","could not be selected")
    command("font size 16","font size changed")
    small=measure("mono16",20)
    command("font size 24","font size changed")
    large=measure("mono24",21)
    # Courier Prime has 1228 font units of advance per 2048-unit em.
    assert abs(small-19*16*1228/2048)<3 and abs(large-20*24*1228/2048)<3,(small,large)
    command("font size 512","does not fit the display")
    command("font info","text size 24 pixels")
    command("font default 1","default font set to slot 1")
    command("settings save","pmf> ")
    command("reset","default TrueType font loaded from")
    info = command("font info","slot 0: selected")
    assert "text size 24 pixels" in info and "MONO.TTF" in info
    command("font unload 0","font slot 0 unloaded")
    command("font info","selected font: embedded TrueType")
    command("font default embedded","embedded TrueType is the default")
    command("font size 16","font size changed")
    command("settings save","pmf> ")
    command("reset","Zentaji boot ROM v1")
    command("font info","default font: embedded TrueType")
    return dict(mono16_span=small,mono24_span=large,restored_default=True)
