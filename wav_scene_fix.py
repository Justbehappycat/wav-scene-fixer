#!/usr/bin/env python3
"""Batch-clean scene names (and optionally frame rate) in BWF/iXML WAV metadata.

Reads production WAVs, rewrites the SCENE value in both the bext description
(zSCENE=) and the iXML chunk, and can rewrite the timecode rate. Originals are
never touched: cleaned copies are written to a side folder (default: ./cleaned
next to the input folder).

Scene-name cleanup is rule-based: SCENE-31-H_ALIENHEART -> 31H,
SCENE-43_PU_X -> 43PU (pickups get a PU suffix), SCENE-A-20-A -> A20A.

Examples:
    python3 wav_scene_fix.py ~/Downloads/dailies --dry-run
    python3 wav_scene_fix.py ~/Downloads/dailies --fps 23.976
"""

import argparse
import os
import re
import struct
import sys

CHUNK_COPY_BLOCK = 8 * 1024 * 1024

FPS_TABLE = {
    "23.976": ("24000/1001", "NDF", "23.976ND"),
    "23.98":  ("24000/1001", "NDF", "23.976ND"),
    "24":     ("24/1",       "NDF", "24.000ND"),
    "25":     ("25/1",       "NDF", "25.000ND"),
    "29.97":  ("30000/1001", "NDF", "29.970ND"),
    "29.97df": ("30000/1001", "DF", "29.970DF"),
    "30":     ("30/1",       "NDF", "30.000ND"),
    "47.952": ("48000/1001", "NDF", "47.952ND"),
    "48":     ("48/1",       "NDF", "48.000ND"),
    "50":     ("50/1",       "NDF", "50.000ND"),
    "59.94":  ("60000/1001", "NDF", "59.940ND"),
    "59.94df": ("60000/1001", "DF", "59.940DF"),
    "60":     ("60/1",       "NDF", "60.000ND"),
}


def read_chunks(path):
    """Yield (chunk_id, size, absolute_data_offset) for every RIFF chunk."""
    with open(path, "rb") as f:
        hdr = f.read(12)
        if len(hdr) < 12 or hdr[:4] != b"RIFF" or hdr[8:12] != b"WAVE":
            raise ValueError("not a RIFF/WAVE file")
        while True:
            h = f.read(8)
            if len(h) < 8:
                return
            cid, size = h[:4], struct.unpack("<I", h[4:])[0]
            yield cid, size, f.tell()
            f.seek(size + (size % 2), 1)


def get_scene(path):
    """Return the scene string from iXML (preferred) or bext zSCENE."""
    bext_scene = None
    for cid, size, off in read_chunks(path):
        with open(path, "rb") as f:
            if cid == b"iXML":
                f.seek(off)
                xml = f.read(size).decode("utf-8", errors="replace")
                m = re.search(r"<SCENE>(.*?)</SCENE>", xml, re.S)
                if m and m.group(1).strip():
                    return m.group(1).strip()
            elif cid == b"bext":
                f.seek(off)
                desc = f.read(256).decode("ascii", errors="replace")
                m = re.search(r"zSCENE=([^\r\n\x00]*)", desc)
                if m and m.group(1).strip():
                    bext_scene = m.group(1).strip()
    return bext_scene


def clean_scene_regex(raw):
    """Extract a scene identifier like 15A / 31H / A20 / 43PU from the raw string.

    Handles: direct suffixes (SCENE-22A), separator suffixes (SCENE-31-H,
    SCENE-20_C), prefix-letter scenes (SCENE-A-20-A -> A20A), and pickup
    markers (_PU_, _5PU_ -> PU appended after the identifier).
    """
    s = raw.upper()
    pickup = bool(re.search(r"[-_ ][0-9]*PU(?=[-_ .]|$)", s))
    m = re.search(
        r"(?:SCENE|SC)[-_ ]*"
        r"(?:([A-Z]{1,2})[-_ ])?"      # optional prefix letters: A-20 -> A
        r"([0-9]{1,4})"                # scene number
        r"(?:[-_ ]?([A-Z]{1,2}))?"     # optional suffix letters: 22A, 31-H, 20_C
        r"(?=[-_ .]|$)", s)
    if not m:
        m = re.search(r"(?:^|[-_ ])([A-Z]{1,2}[-_ ])?([0-9]{1,4})([A-Z]{1,2})?(?=[-_ .]|$)", s)
    if not m:
        return raw
    prefix, number, suffix = (m.group(1) or "").rstrip("-_ "), m.group(2), m.group(3) or ""
    if suffix == "PU":  # separator+PU was captured as a suffix; it's the pickup marker
        pickup, suffix = True, ""
    return prefix + number + suffix + ("PU" if pickup else "")


def rewrite_bext(data, new_scene, fps_entry):
    """Return bext chunk data with zSCENE (and zSPEED if fps given) replaced."""
    desc = data[:256].decode("ascii", errors="replace")
    desc = re.sub(r"(zSCENE=)[^\r\n\x00]*", lambda m: m.group(1) + new_scene, desc)
    if fps_entry:
        desc = re.sub(r"(zSPEED=)[^\r\n\x00]*", lambda m: m.group(1) + fps_entry[2], desc)
    raw = desc.encode("ascii", errors="replace")[:256].ljust(256, b"\x00")
    return raw + data[256:]


def rewrite_ixml(data, new_scene, fps_entry):
    """Return iXML chunk data with SCENE (and timecode-rate tags if fps given) replaced."""
    xml = data.decode("utf-8", errors="replace")
    xml = re.sub(r"<SCENE>.*?</SCENE>", f"<SCENE>{new_scene}</SCENE>", xml, flags=re.S)
    if fps_entry:
        rate, flag, _ = fps_entry
        for tag in ("TIMECODE_RATE", "MASTER_SPEED", "CURRENT_SPEED"):
            xml = re.sub(rf"<{tag}>.*?</{tag}>", f"<{tag}>{rate}</{tag}>", xml, flags=re.S)
        xml = re.sub(r"<TIMECODE_FLAG>.*?</TIMECODE_FLAG>",
                     f"<TIMECODE_FLAG>{flag}</TIMECODE_FLAG>", xml, flags=re.S)
    return xml.encode("utf-8")


def write_copy(src, dst, new_scene, fps_entry):
    """Stream-copy src to dst, rewriting bext and iXML chunks."""
    chunks = list(read_chunks(src))
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(b"RIFF\x00\x00\x00\x00WAVE")
        for cid, size, off in chunks:
            fin.seek(off)
            if cid in (b"bext", b"iXML"):
                data = fin.read(size)
                data = (rewrite_bext if cid == b"bext" else rewrite_ixml)(
                    data, new_scene, fps_entry)
                fout.write(cid + struct.pack("<I", len(data)) + data)
                if len(data) % 2:
                    fout.write(b"\x00")
            else:
                fout.write(cid + struct.pack("<I", size))
                remaining = size + (size % 2)
                while remaining:
                    block = fin.read(min(CHUNK_COPY_BLOCK, remaining))
                    if not block:
                        raise IOError(f"truncated chunk {cid!r} in {src}")
                    fout.write(block)
                    remaining -= len(block)
        total = fout.tell()
        fout.seek(4)
        fout.write(struct.pack("<I", total - 8))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input_dir", help="folder containing WAV files")
    ap.add_argument("-o", "--output-dir",
                    help="side folder for cleaned copies (default: <input_dir>/cleaned)")
    ap.add_argument("--fps", help="rewrite timecode rate, e.g. 24, 23.976, 29.97df "
                                  f"(choices: {', '.join(FPS_TABLE)})")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change without writing files")
    args = ap.parse_args()

    fps_entry = None
    if args.fps:
        key = args.fps.lower().rstrip("ndf") if args.fps.lower().endswith("ndf") else args.fps.lower()
        fps_entry = FPS_TABLE.get(args.fps.lower()) or FPS_TABLE.get(key)
        if not fps_entry:
            sys.exit(f"unsupported fps {args.fps!r}; choices: {', '.join(FPS_TABLE)}")

    in_dir = os.path.abspath(args.input_dir)
    out_dir = os.path.abspath(args.output_dir or os.path.join(in_dir, "cleaned"))
    if os.path.commonpath([in_dir]) == os.path.commonpath([in_dir, out_dir]) and in_dir == out_dir:
        sys.exit("output dir must differ from input dir")

    wavs = sorted(
        os.path.join(in_dir, n) for n in os.listdir(in_dir)
        if n.lower().endswith(".wav") and os.path.isfile(os.path.join(in_dir, n))
    )
    if not wavs:
        sys.exit(f"no .wav files found in {in_dir}")

    scenes = {}
    for w in wavs:
        try:
            scenes[w] = get_scene(w)
        except ValueError as e:
            print(f"SKIP {os.path.basename(w)}: {e}")
    mapping = {s: clean_scene_regex(s) for s in scenes.values() if s}

    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)

    changed = 0
    for w in wavs:
        if w not in scenes:
            continue
        raw = scenes[w]
        name = os.path.basename(w)
        if raw is None:
            print(f"SKIP {name}: no scene metadata found")
            continue
        new = mapping.get(raw, raw)
        fps_note = f", fps -> {fps_entry[0]} {fps_entry[1]}" if fps_entry else ""
        print(f"{name}: scene {raw!r} -> {new!r}{fps_note}")
        if not args.dry_run:
            write_copy(w, os.path.join(out_dir, name), new, fps_entry)
            changed += 1

    if args.dry_run:
        print(f"\ndry run: {len(wavs)} file(s) scanned, nothing written")
    else:
        print(f"\n{changed} file(s) written to {out_dir}")


if __name__ == "__main__":
    main()
