# WAV Scene Fixer

Batch-clean scene names and fix the timecode rate in production audio WAVs
(BWF), **without ever touching the originals** — cleaned copies go to a side
folder, and the audio data is copied bit-for-bit (only the `bext` and `iXML`
metadata chunks are rewritten).

Made for the classic dailies problem: the recorder was set up with messy or
wrong scene names (or the wrong frame rate) and now every file needs fixing
before it hits post.

## What it does

Scene names are normalized to just the scene identifier, applied to both the
iXML `<SCENE>` tag and the bext `zSCENE=` line:

| Raw scene in metadata        | Cleaned |
|------------------------------|---------|
| `SCENE-15A_ALIENHEART`       | `15A`   |
| `SCENE-31-H_ALIENHEART`      | `31H`   |
| `SCENE-20_C`                 | `20C`   |
| `SCENE-43_PU_ALIENHEART`     | `43PU`  |
| `SCENE-24B_5PU_ALIENHEART`   | `24BPU` |
| `SCENE-A-20-A`               | `A20A`  |

Rules: letter suffixes may follow the number directly or after a separator;
pickup markers (`_PU_`, `_5PU_`, …) append `PU` to the identifier; prefix-letter
scenes (`A-20`) keep the letter in front. If a name doesn't parse, it's left
unchanged (and the file is still copied).

Optionally rewrites the timecode rate in the same pass — all iXML speed tags
(`TIMECODE_RATE`, `MASTER_SPEED`, `CURRENT_SPEED`, `TIMECODE_FLAG`) plus the
`zSPEED=` bext line. The bext `TimeReference` (samples since midnight) is
preserved, so the start timecode stays sample-accurate and is simply
reinterpreted at the new rate. Supported rates: 23.976, 24, 25, 29.97,
29.97df, 30, 47.952, 48, 50, 59.94, 59.94df, 60.

## Usage

### CLI

```bash
# preview — prints every old -> new mapping, writes nothing
python3 wav_scene_fix.py /path/to/dailies --dry-run

# clean scene names (copies go to /path/to/dailies/cleaned)
python3 wav_scene_fix.py /path/to/dailies

# also fix the timecode rate, custom output folder
python3 wav_scene_fix.py /path/to/dailies --fps 23.976 -o /path/to/fixed
```

No dependencies — Python 3.8+ standard library only.

### macOS app

A standalone app (no Python required) is attached to each
[release](../../releases): unzip, right-click → Open the first time
(it's unsigned), pick a folder, hit **Preview**, then **Process files**.
Apple Silicon only. To build it yourself: `./build.sh`.

## Safety model

- Originals are never modified — output always goes to a separate folder.
- Audio (`data`) and format (`fmt `) chunks are copied verbatim; unknown
  chunks are passed through untouched.
- **Preview (dry run)** shows every mapping before anything is written.
- The round-trip is covered by tests (`python3 -m unittest discover tests`),
  including audio-bytes-identical and RIFF-size checks.

## Scope and conventions

Developed against Zoom F8n Pro recordings; anything that writes standard
bext + iXML should work. The scene-naming rules (in `clean_scene_regex()` in
[wav_scene_fix.py](wav_scene_fix.py), with the expected mappings in
[tests/test_wav_scene_fix.py](tests/test_wav_scene_fix.py)) encode one
production's conventions — if yours differ (e.g. pickups named differently),
that one function is the place to change, and the tests will tell you what
you affected.

Test WAVs are generated synthetically (`tests/make_test_wav.py`) — no real
production audio in this repo.

## License

MIT
