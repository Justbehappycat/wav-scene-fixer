#!/usr/bin/env python3
"""Tests for wav_scene_fix: scene-name rules and safe round-trip rewriting.

Run from the repo root:
    python3 -m unittest discover tests
"""

import os
import re
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wav_scene_fix as wsf
from tests.make_test_wav import make_wav

SCENE_CASES = {
    # direct letter suffixes
    "SCENE-22": "22",
    "SCENE-22A": "22A",
    "SCENE-49J": "49J",
    "SCENE-15A_ALIENHEART": "15A",
    "SCENE-28A_ALIENHEART": "28A",
    # trailing separators
    "SCENE-29_": "29",
    "SCENE-43C_": "43C",
    # separator between number and suffix letter
    "SCENE-31-H_ALIENHEART": "31H",
    "SCENE-31-J_ALIENHEART": "31J",
    "SCENE-31-K_ALIENHEART": "31K",
    "SCENE-20_C": "20C",
    # pickups: PU marker appended after the identifier
    "SCENE-30A_PU_ALIENHEART": "30APU",
    "SCENE-43_PU_ALIENHEART": "43PU",
    "SCENE-43B_PU_": "43BPU",
    "SCENE-24B_5PU_ALIENHEART": "24BPU",
    "SCENE-43_7PU_ALIENHEART": "43PU",
    # words starting with P must not look like pickups
    "SCENE-31A_PALIENHEART": "31A",
    "SCENE-31B_PALIENHEART": "31B",
    # prefix-letter scenes
    "SCENE-A-20": "A20",
    "SCENE-A-20-A": "A20A",
}


class TestCleanSceneRegex(unittest.TestCase):
    def test_scene_cases(self):
        for raw, want in SCENE_CASES.items():
            self.assertEqual(wsf.clean_scene_regex(raw), want, raw)

    def test_unparseable_returns_input(self):
        self.assertEqual(wsf.clean_scene_regex("NO-DIGITS-HERE"), "NO-DIGITS-HERE")


class TestRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "SCENE-31-H_EXAMPLE-T001.WAV")
        make_wav(self.src, "SCENE-31-H_EXAMPLE")

    def tearDown(self):
        self.tmp.cleanup()

    def read_all(self, path):
        chunks = {}
        for cid, size, off in wsf.read_chunks(path):
            with open(path, "rb") as f:
                f.seek(off)
                chunks[cid] = f.read(size)
        return chunks

    def test_scene_and_fps_rewrite_preserve_audio(self):
        dst = os.path.join(self.tmp.name, "out.WAV")
        wsf.write_copy(self.src, dst, "31H", wsf.FPS_TABLE["23.976"])

        before, after = self.read_all(self.src), self.read_all(dst)
        # audio and format untouched
        self.assertEqual(before[b"data"], after[b"data"])
        self.assertEqual(before[b"fmt "], after[b"fmt "])
        # scene rewritten in both metadata chunks
        self.assertIn(b"zSCENE=31H\n", after[b"bext"])
        self.assertIn(b"<SCENE>31H</SCENE>", after[b"iXML"])
        # fps rewritten everywhere, TimeReference untouched
        self.assertIn(b"zSPEED=23.976ND", after[b"bext"])
        self.assertEqual(after[b"iXML"].count(b"24000/1001"), 3)
        self.assertIn(b"<TIMECODE_FLAG>NDF</TIMECODE_FLAG>", after[b"iXML"])
        self.assertEqual(before[b"bext"][338:346], after[b"bext"][338:346])
        # RIFF size header is consistent with the file length
        self.assertEqual(struct.unpack("<I", open(dst, "rb").read(8)[4:])[0],
                         os.path.getsize(dst) - 8)

    def test_scene_only_leaves_fps_alone(self):
        dst = os.path.join(self.tmp.name, "out2.WAV")
        wsf.write_copy(self.src, dst, "31H", None)
        after = self.read_all(dst)
        self.assertIn(b"zSPEED=24.000ND", after[b"bext"])
        self.assertIn(b"<TIMECODE_RATE>24/1</TIMECODE_RATE>", after[b"iXML"])

    def test_get_scene_prefers_ixml(self):
        self.assertEqual(wsf.get_scene(self.src), "SCENE-31-H_EXAMPLE")


if __name__ == "__main__":
    unittest.main()
