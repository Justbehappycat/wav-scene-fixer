#!/usr/bin/env python3
"""Generate small synthetic BWF WAV files for testing.

Creates files with bext + iXML chunks shaped like Zoom F8n Pro output
(zSCENE=/zTAKE= lines in the bext description, SCENE/TAKE/TIMECODE_RATE
tags in iXML) and a short block of silence — no real production audio.

Usage:
    python3 tests/make_test_wav.py OUTPUT_DIR [SCENE ...]
"""

import os
import struct
import sys

IXML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<BWFXML>
	<IXML_VERSION>1.5</IXML_VERSION>
	<PROJECT></PROJECT>
	<SCENE>{scene}</SCENE>
	<TAKE>{take}</TAKE>
	<TAPE></TAPE>
	<CIRCLED>FALSE</CIRCLED>
	<SPEED>
		<NOTE></NOTE>
		<MASTER_SPEED>24/1</MASTER_SPEED>
		<CURRENT_SPEED>24/1</CURRENT_SPEED>
		<TIMECODE_RATE>24/1</TIMECODE_RATE>
		<TIMECODE_FLAG>NDF</TIMECODE_FLAG>
		<FILE_SAMPLE_RATE>48000</FILE_SAMPLE_RATE>
		<AUDIO_BIT_DEPTH>16</AUDIO_BIT_DEPTH>
	</SPEED>
</BWFXML>
"""


def chunk(cid, data):
    if len(data) % 2:
        data += b"\x00"
    return cid + struct.pack("<I", len(data)) + data


def make_bext(scene, take):
    desc = (f"zSPEED=24.000ND\nzTAKE={take}\nzUBITS=00000000\n"
            f"zSCENE={scene[:32]}\nzTAPE=\nzCIRCLED=FALSE\n").encode("ascii")
    data = bytearray(602)  # minimal bext v1 size
    data[0:len(desc[:256])] = desc[:256]
    data[256:256 + 10] = b"TestWriter"        # originator
    data[320:330] = b"2026-01-01"             # origination date
    data[330:338] = b"10:00:00"               # origination time
    data[338:346] = struct.pack("<Q", 48000 * 3600)  # TimeReference: 01:00:00:00
    struct.pack_into("<H", data, 346, 1)      # version
    return bytes(data)


def make_wav(path, scene, take="001", seconds=0.1):
    sr, ch, bits = 48000, 1, 16
    audio = b"\x00" * int(sr * seconds) * ch * (bits // 8)
    fmt = struct.pack("<HHIIHH", 1, ch, sr, sr * ch * bits // 8, ch * bits // 8, bits)
    body = (chunk(b"bext", make_bext(scene, take))
            + chunk(b"iXML", IXML_TEMPLATE.format(scene=scene, take=take).encode())
            + chunk(b"fmt ", fmt)
            + chunk(b"data", audio))
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    scenes = sys.argv[2:] or ["SCENE-15A_EXAMPLE", "SCENE-31-H_EXAMPLE",
                              "SCENE-43_PU_EXAMPLE", "SCENE-A-20-A"]
    os.makedirs(out, exist_ok=True)
    for scene in scenes:
        name = f"{scene}-T001.WAV"
        make_wav(os.path.join(out, name), scene)
        print("wrote", os.path.join(out, name))


if __name__ == "__main__":
    main()
