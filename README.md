# AudioTool

A command-line audio toolkit for converting, trimming, looping, and inspecting audio files.

One Python script, no pip installs, runs anywhere Python and ffmpeg exist.

---

## System Requirements

You need two things installed:

| Requirement | Minimum Version | How to check |
|---|---|---|
| **Python** | 3.7 or newer | `python3 --version` |
| **ffmpeg** (includes ffprobe) | Any recent version | `ffmpeg -version` |

### Installing ffmpeg if you don't have it

**Linux (Ubuntu/Debian/Mint/MATE):**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install ffmpeg
```

**Linux (Arch):**
```bash
sudo pacman -S ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
1. Download from https://ffmpeg.org/download.html (get the "full" build)
2. Extract it somewhere (e.g. `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to your system PATH
4. Or just use WSL (Windows Subsystem for Linux) and follow the Linux instructions

---

## Quick Start

Open a terminal. Navigate to wherever you put `audiotool.py`. All commands follow this pattern:

```
python3 audiotool.py COMMAND [arguments]
```

> **Windows note:** Use `python` instead of `python3` in all the commands below. If neither works, make sure Python is added to your PATH during installation (there's a checkbox in the Python installer for this).

That's it. Every command below is a copy-paste example — just swap the filenames with yours.

---

## Commands

There are 5 commands. Here's what each one does and how to use it.

### 1. `info` — See what's in an audio file

Shows you the format, duration, codec, sample rate, channels, bitrate, and file size.

```bash
python3 audiotool.py info myfile.mp3
```

Output looks like:
```
  File:         myfile.mp3
  Format:       MP2/3 (MPEG audio layer 2/3)
  Duration:     4:42.20
  Codec:        mp3 (MP3 (MPEG audio layer 3))
  Sample rate:  44100 Hz
  Channels:     1 (mono)
  Bit rate:     128 kbps
  File size:    4.3 MB
```

If you want the raw technical data as JSON (for scripts or debugging):
```bash
python3 audiotool.py info myfile.mp3 --json
```

---

### 2. `convert` — Change audio format

Takes an input file and creates an output file in a different format. The output format is determined by the file extension you use.

**Basic conversion:**
```bash
# MP3 to WAV (lossless)
python3 audiotool.py convert song.mp3 song.wav

# WAV to MP3
python3 audiotool.py convert song.wav song.mp3

# MP3 to FLAC (lossless)
python3 audiotool.py convert song.mp3 song.flac

# Anything to OGG
python3 audiotool.py convert song.wav song.ogg
```

**Supported output formats:** `.wav`, `.mp3`, `.flac`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.aiff`

**If the output file already exists**, it will refuse and tell you. Add `-y` to overwrite:
```bash
python3 audiotool.py convert song.mp3 song.wav -y
```

#### About WAV and lossless conversion

This is important: when you convert TO WAV, the tool **always** uses uncompressed PCM encoding (specifically `pcm_s24le` — 24-bit). This means your WAV files are genuinely lossless. They're big, but they're perfect copies of the audio data.

If you want 16-bit WAV instead (smaller files, CD quality):
```bash
python3 audiotool.py convert song.mp3 song.wav --bit-depth 16
```

Bit depth options: `16`, `24` (default), or `32`.

> **Compatibility tip:** Some older or basic audio players can't handle 24-bit WAV files (they may show as empty or refuse to play). If you run into this, use `--bit-depth 16` — it's CD quality and works everywhere.

#### Controlling quality for lossy formats

For MP3, OGG, M4A, etc., you can set the bitrate:
```bash
# High quality MP3 (320 kbps)
python3 audiotool.py convert song.wav song.mp3 --bitrate 320k

# Smaller MP3 (128 kbps)
python3 audiotool.py convert song.wav song.mp3 --bitrate 128k
```

#### Changing sample rate or channels

```bash
# Convert to 48000 Hz sample rate
python3 audiotool.py convert song.mp3 song.wav --sample-rate 48000

# Convert stereo to mono
python3 audiotool.py convert song.mp3 song_mono.mp3 --channels 1

# Convert mono to stereo
python3 audiotool.py convert song.mp3 song_stereo.mp3 --channels 2
```

---

### 3. `trim` — Cut out a piece of audio

Extracts a segment from a file. You specify WHERE to start and WHERE to stop.

**Times can be written as:**
- Seconds: `30`, `90.5`
- Minutes:Seconds: `1:30`, `2:05.5`
- Hours:Minutes:Seconds: `1:30:00`

#### Using start and end times

"Give me the audio from the 30 second mark to the 1 minute mark":
```bash
python3 audiotool.py trim song.mp3 clip.mp3 -s 0:30 -e 1:00
```

"Give me from 2 minutes 15 seconds to 3 minutes":
```bash
python3 audiotool.py trim song.mp3 clip.mp3 -s 2:15 -e 3:00
```

#### Using start and duration

"Give me 30 seconds starting from the beginning":
```bash
python3 audiotool.py trim song.mp3 clip.mp3 -s 0 -d 30
```

"Give me 45 seconds starting from the 1 minute mark":
```bash
python3 audiotool.py trim song.mp3 clip.mp3 -s 1:00 -d 45
```

#### Trim and convert at the same time

The output format is determined by the file extension, so you can trim AND convert in one step:
```bash
# Trim an MP3 and save as WAV
python3 audiotool.py trim song.mp3 clip.wav -s 0 -d 30

# Trim a WAV and save as FLAC
python3 audiotool.py trim recording.wav clip.flac -s 1:00 -e 2:00
```

#### Fast trim (no re-encoding)

If you want speed and don't need format conversion, use `-c` (copy mode). This is instant but may be slightly imprecise at the start/end (by a fraction of a second):
```bash
python3 audiotool.py trim song.mp3 clip.mp3 -s 0:30 -e 1:00 -c
```

---

### 4. `loop` — Repeat audio

Creates a new file where the audio (or part of it) repeats multiple times.

#### Loop an entire file

"Repeat this whole song 3 times back to back":
```bash
python3 audiotool.py loop song.mp3 looped.mp3 -n 3
```

#### Loop just a segment

"Take the first 30 seconds and repeat it 5 times":
```bash
python3 audiotool.py loop song.mp3 looped.mp3 -s 0 -d 30 -n 5
```

"Take the part from 1:00 to 1:30 and repeat it 4 times":
```bash
python3 audiotool.py loop song.mp3 looped.mp3 -s 1:00 -e 1:30 -n 4
```

#### Add silence between loops

"Loop the first 10 seconds 3 times, with 2 seconds of silence between each repeat":
```bash
python3 audiotool.py loop song.mp3 looped.mp3 -s 0 -d 10 -n 3 --gap 2
```

The gap value is in seconds. You can use decimals like `--gap 0.5` for half a second.

#### Loop and convert

Same as trim — the output format follows the file extension:
```bash
# Loop a segment from MP3 and save as lossless WAV
python3 audiotool.py loop song.mp3 looped.wav -s 0 -d 30 -n 5
```

---

### 5. `batch` — Convert a whole folder at once

Converts every audio file in a directory to a target format.

**Convert all files in a folder to WAV:**
```bash
python3 audiotool.py batch ./my_music/ -f wav
```

This puts the converted files in the same folder. To put them somewhere else:
```bash
python3 audiotool.py batch ./my_music/ -f wav -o ./converted/
```

**Convert to MP3 at 320kbps:**
```bash
python3 audiotool.py batch ./recordings/ -f mp3 --bitrate 320k -o ./mp3s/
```

**Include subfolders (recursive):**
```bash
python3 audiotool.py batch ./my_music/ -f flac -r -o ./flac_library/
```

**Overwrite existing files:**
```bash
python3 audiotool.py batch ./my_music/ -f wav -o ./converted/ -y
```

**Dry run — see what would happen without doing anything:**
```bash
python3 audiotool.py batch ./my_music/ -f wav --dry-run
```

It skips files that are already in the target format (won't convert .wav to .wav).

---

## Common Recipes

Here are some real-world scenarios and the exact commands for them.

### "I have MP3s and I need lossless WAVs for editing"
```bash
python3 audiotool.py batch ./my_mp3s/ -f wav -o ./wavs/ -y
```

### "I need to extract a 30-second sample from the middle of a file"
```bash
python3 audiotool.py trim long_recording.mp3 sample.mp3 -s 2:30 -e 3:00
```

### "I need a 5-minute loop of a 30-second audio clip"
30 seconds x 10 = 300 seconds = 5 minutes:
```bash
python3 audiotool.py loop clip.mp3 fivemin.mp3 -n 10
```

### "I need a loop of just the intro (first 15 seconds) repeated 8 times"
```bash
python3 audiotool.py loop song.mp3 intro_loop.mp3 -s 0 -d 15 -n 8
```

### "I want to convert a folder of WAVs to MP3 for sharing, keeping them small"
```bash
python3 audiotool.py batch ./wavs/ -f mp3 --bitrate 128k -o ./small_mp3s/ -y
```

### "I need to see how long my audio file is and what format it's in"
```bash
python3 audiotool.py info mystery_file.wav
```

### "I want to make a stereo version of a mono file"
```bash
python3 audiotool.py convert mono.wav stereo.wav --channels 2
```

---

## Flags Reference

These flags work across multiple commands:

| Flag | Short | What it does | Works with |
|---|---|---|---|
| `--overwrite` | `-y` | Overwrite output files without asking | convert, trim, loop, batch |
| `--verbose` | `-v` | Show the exact ffmpeg commands being run | all (goes before the command name) |
| `--bitrate` | | Set bitrate for lossy formats (e.g. `320k`) | convert, trim, loop, batch |
| `--bit-depth` | | Set PCM bit depth for WAV: `16`, `24`, `32` | convert, trim, loop, batch |
| `--sample-rate` | | Set sample rate in Hz (e.g. `44100`, `48000`) | convert, batch |
| `--channels` | | `1` for mono, `2` for stereo | convert |
| `--json` | `-j` | Output raw JSON metadata | info |
| `--copy` | `-c` | Stream copy (fast, no re-encode) | trim |
| `--gap` | `-g` | Silence between loops in seconds | loop |
| `--recursive` | `-r` | Process subfolders | batch |
| `--dry-run` | | Preview batch operations | batch |

Note: `--verbose` goes **before** the command name:
```bash
python3 audiotool.py -v convert song.mp3 song.wav
```

---

## Troubleshooting

**"ffmpeg not found"** — Install ffmpeg. See the top of this README.

**"Output file already exists"** — Add `-y` to your command to overwrite it.

**"Unsupported output format"** — Make sure your output filename ends with a supported extension: `.wav`, `.mp3`, `.flac`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.aiff`

**Trim gives wrong duration** — Make sure you're using the right flag. `-e` is the END time in the file (absolute), `-d` is the DURATION from the start point (relative). They're different:
- `-s 1:00 -e 1:30` = from 1:00 to 1:30 = 30 seconds
- `-s 1:00 -d 30` = start at 1:00, grab 30 seconds = also 30 seconds
- `-s 1:00 -d 1:30` = start at 1:00, grab 1 minute 30 seconds = 90 seconds

**Files sound weird after conversion** — You can't recover quality that was already lost. Converting an MP3 to WAV makes it lossless *from that point on*, but it can't undo the compression artifacts from the original MP3 encoding. The WAV will be a perfect copy of the MP3 audio — not a perfect copy of whatever the MP3 was made from.

---

## Getting Help

Every command has its own help page:
```bash
python3 audiotool.py --help
python3 audiotool.py convert --help
python3 audiotool.py trim --help
python3 audiotool.py loop --help
python3 audiotool.py batch --help
python3 audiotool.py info --help
```
