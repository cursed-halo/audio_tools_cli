#!/usr/bin/env python3
"""audiotool - CLI audio toolkit wrapping ffmpeg.

Convert, trim, loop, and inspect audio files from the command line.
Requires ffmpeg and ffprobe to be installed.
"""

import argparse
import json
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import sys
import time

__version__ = "1.0.0"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac",
    ".wma", ".opus", ".webm", ".aiff", ".aif",
}

WAV_CODECS = {
    16: "pcm_s16le",
    24: "pcm_s24le",
    32: "pcm_s32le",
}

FORMAT_CODEC_MAP = {
    ".wav":  lambda bd=24, br=None: ["-c:a", WAV_CODECS[bd]],
    ".flac": lambda bd=24, br=None: ["-c:a", "flac"],
    ".mp3":  lambda bd=24, br=None: ["-c:a", "libmp3lame"] + (["-b:a", br] if br else ["-q:a", "2"]),
    ".ogg":  lambda bd=24, br=None: ["-c:a", "libvorbis"] + (["-b:a", br] if br else ["-q:a", "5"]),
    ".opus": lambda bd=24, br=None: ["-c:a", "libopus"] + (["-b:a", br] if br else ["-b:a", "128k"]),
    ".m4a":  lambda bd=24, br=None: ["-c:a", "aac"] + (["-b:a", br] if br else ["-b:a", "192k"]),
    ".aac":  lambda bd=24, br=None: ["-c:a", "aac"] + (["-b:a", br] if br else ["-b:a", "192k"]),
    ".aiff": lambda bd=24, br=None: ["-c:a", WAV_CODECS.get(bd, "pcm_s24le").replace("le", "be")],
    ".aif":  lambda bd=24, br=None: ["-c:a", WAV_CODECS.get(bd, "pcm_s24le").replace("le", "be")],
}

CHANNEL_NAMES = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def check_dependencies():
    """Ensure ffmpeg and ffprobe are available."""
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"[ERROR] '{tool}' not found in PATH. Install ffmpeg first.", file=sys.stderr)
            sys.exit(1)


def run_ffprobe(input_path):
    """Run ffprobe and return parsed JSON data."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] ffprobe failed on '{input_path}'", file=sys.stderr)
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[ERROR] ffprobe returned invalid data for '{input_path}'", file=sys.stderr)
        sys.exit(1)


def format_cmd(cmd):
    """Format a command list for display, quoting args with spaces."""
    if platform.system() == "Windows":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def run_ffmpeg(cmd, verbose=False):
    """Run an ffmpeg command, handling errors."""
    # Prevent ffmpeg from reading stdin (avoids hangs in scripts/pipelines)
    if "-nostdin" not in cmd:
        cmd = [cmd[0], "-nostdin"] + cmd[1:]
    if verbose:
        print(f"[CMD] {format_cmd(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr_lines = [l for l in result.stderr.strip().split("\n") if l.strip()]
        err_msg = stderr_lines[-1] if stderr_lines else "Unknown error"
        print(f"[ERROR] ffmpeg failed: {err_msg}", file=sys.stderr)
        return False
    return True


def get_audio_stream(probe_data):
    """Extract the first audio stream from probe data."""
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    return None


def validate_input_file(path_str):
    """Validate that the input file exists and is readable."""
    p = pathlib.Path(path_str)
    if not p.exists():
        print(f"[ERROR] File not found: {path_str}", file=sys.stderr)
        sys.exit(1)
    if not p.is_file():
        print(f"[ERROR] Not a file: {path_str}", file=sys.stderr)
        sys.exit(1)
    return p


def validate_output_path(path_str, overwrite=False):
    """Validate output path. Prompt/error if file exists."""
    p = pathlib.Path(path_str)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not overwrite:
        print(f"[ERROR] Output file already exists: {path_str}", file=sys.stderr)
        print("       Use -y / --overwrite to overwrite.", file=sys.stderr)
        sys.exit(1)
    return p


def codec_flags(ext, bit_depth=24, bitrate=None):
    """Return ffmpeg codec flags for a given output extension."""
    ext = ext.lower()
    if ext not in FORMAT_CODEC_MAP:
        supported = ", ".join(sorted(FORMAT_CODEC_MAP.keys()))
        print(f"[ERROR] Unsupported output format '{ext}'. Supported: {supported}", file=sys.stderr)
        sys.exit(1)
    return FORMAT_CODEC_MAP[ext](bd=bit_depth, br=bitrate)


def parse_time(value):
    """Validate and return a time string for ffmpeg. Used as argparse type."""
    value = value.strip()
    # Accept raw seconds (possibly with decimal)
    try:
        secs = float(value)
        if secs < 0:
            raise argparse.ArgumentTypeError(f"Time cannot be negative: {value}")
        return value
    except ValueError:
        pass
    # Accept MM:SS or HH:MM:SS (with optional decimal)
    parts = value.split(":")
    if len(parts) in (2, 3):
        try:
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    float(part)  # last part can have decimals
                else:
                    int(part)
            return value
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(f"Invalid time format: '{value}' (use SS, MM:SS, or HH:MM:SS)")


def time_to_seconds(value):
    """Convert a time string to seconds (float)."""
    parts = value.split(":")
    if len(parts) == 1:
        return float(parts[0])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(value)


def format_duration(seconds):
    """Format seconds to human-readable duration."""
    if seconds is None:
        return "N/A"
    seconds = float(seconds)
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:05.2f}"
    return f"{mins}:{secs:05.2f}"


def format_file_size(size_bytes):
    """Format bytes to human-readable size."""
    size_bytes = int(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_file_duration(input_path):
    """Get duration in seconds from a file via ffprobe."""
    data = run_ffprobe(input_path)
    fmt = data.get("format", {})
    dur = fmt.get("duration")
    if dur:
        return float(dur)
    stream = get_audio_stream(data)
    if stream and stream.get("duration"):
        return float(stream["duration"])
    return None


# ---------------------------------------------------------------------------
# Subcommand: info
# ---------------------------------------------------------------------------

def cmd_info(args):
    """Show audio file information."""
    input_path = validate_input_file(args.input)
    data = run_ffprobe(input_path)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    fmt = data.get("format", {})
    stream = get_audio_stream(data)

    if not stream:
        print(f"[ERROR] No audio stream found in '{input_path}'", file=sys.stderr)
        sys.exit(1)

    duration = fmt.get("duration") or stream.get("duration")
    bit_rate = fmt.get("bit_rate") or stream.get("bit_rate")
    channels = int(stream.get("channels", 0))
    sample_rate = stream.get("sample_rate", "N/A")
    codec_name = stream.get("codec_name", "N/A")
    codec_long = stream.get("codec_long_name", "")
    file_size = fmt.get("size") or os.path.getsize(input_path)
    format_name = fmt.get("format_long_name", fmt.get("format_name", "N/A"))
    bits_per_sample = stream.get("bits_per_raw_sample") or stream.get("bits_per_sample")

    ch_label = CHANNEL_NAMES.get(channels, f"{channels}ch")
    br_str = f"{int(bit_rate) // 1000} kbps" if bit_rate else "N/A"

    print(f"  File:         {input_path.name}")
    print(f"  Path:         {input_path}")
    print(f"  Format:       {format_name}")
    print(f"  Duration:     {format_duration(duration)}")
    print(f"  Codec:        {codec_name}" + (f" ({codec_long})" if codec_long else ""))
    if bits_per_sample and str(bits_per_sample) != "0":
        print(f"  Bit depth:    {bits_per_sample}-bit")
    print(f"  Sample rate:  {sample_rate} Hz")
    print(f"  Channels:     {channels} ({ch_label})")
    print(f"  Bit rate:     {br_str}")
    print(f"  File size:    {format_file_size(file_size)}")


# ---------------------------------------------------------------------------
# Subcommand: convert
# ---------------------------------------------------------------------------

def cmd_convert(args):
    """Convert audio between formats."""
    input_path = validate_input_file(args.input)
    output_path = validate_output_path(args.output, overwrite=args.overwrite)
    out_ext = output_path.suffix.lower()

    bit_depth = args.bit_depth or 24
    flags = codec_flags(out_ext, bit_depth=bit_depth, bitrate=args.bitrate)

    cmd = ["ffmpeg", "-i", str(input_path)]
    cmd += flags
    if args.sample_rate:
        cmd += ["-ar", str(args.sample_rate)]
    if args.channels:
        cmd += ["-ac", str(args.channels)]
    if args.overwrite:
        cmd += ["-y"]
    cmd += [str(output_path)]

    t0 = time.time()
    ok = run_ffmpeg(cmd, verbose=args.verbose)
    elapsed = time.time() - t0

    if ok:
        print(f"[OK] Converted {input_path.name} -> {output_path.name} ({elapsed:.1f}s)")
        # Verify WAV losslessness
        if out_ext == ".wav" and args.verbose:
            out_data = run_ffprobe(str(output_path))
            out_stream = get_audio_stream(out_data)
            if out_stream:
                print(f"     Verified: output codec is {out_stream.get('codec_name', '?')} (lossless PCM)")
    else:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: trim
# ---------------------------------------------------------------------------

def cmd_trim(args):
    """Trim/cut a segment from an audio file."""
    input_path = validate_input_file(args.input)
    output_path = validate_output_path(args.output, overwrite=args.overwrite)
    out_ext = output_path.suffix.lower()

    if not args.end and not args.duration:
        print("[ERROR] Specify either --end or --duration for trimming.", file=sys.stderr)
        sys.exit(1)

    # Warn if start is past the file duration
    file_dur = get_file_duration(str(input_path))
    start_sec = time_to_seconds(args.start)
    if file_dur and start_sec >= file_dur:
        print(f"[WARN] Start time ({args.start}) is past the file duration ({format_duration(file_dur)})", file=sys.stderr)

    cmd = ["ffmpeg", "-ss", args.start, "-i", str(input_path)]
    if args.end:
        # With -ss before -i (input seeking), -to is relative to the seeked
        # position, so convert absolute end time to a duration instead.
        end_sec = time_to_seconds(args.end)
        dur_sec = end_sec - start_sec
        if dur_sec <= 0:
            print(f"[ERROR] End time ({args.end}) must be after start time ({args.start}).", file=sys.stderr)
            sys.exit(1)
        cmd += ["-t", str(dur_sec)]
    elif args.duration:
        cmd += ["-t", args.duration]

    if args.copy:
        cmd += ["-c", "copy"]
    else:
        bit_depth = args.bit_depth or 24
        cmd += codec_flags(out_ext, bit_depth=bit_depth, bitrate=args.bitrate)

    if args.overwrite:
        cmd += ["-y"]
    cmd += [str(output_path)]

    t0 = time.time()
    ok = run_ffmpeg(cmd, verbose=args.verbose)
    elapsed = time.time() - t0

    if ok:
        out_dur = get_file_duration(str(output_path))
        print(f"[OK] Trimmed {input_path.name} -> {output_path.name} "
              f"(duration: {format_duration(out_dur)}, {elapsed:.1f}s)")
    else:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: loop
# ---------------------------------------------------------------------------

def cmd_loop(args):
    """Loop an audio file or a segment of it."""
    input_path = validate_input_file(args.input)
    output_path = validate_output_path(args.output, overwrite=args.overwrite)
    out_ext = output_path.suffix.lower()
    count = args.count

    if count < 1:
        print("[ERROR] Loop count must be at least 1.", file=sys.stderr)
        sys.exit(1)
    if count > 1000:
        print("[ERROR] Loop count too high (max 1000).", file=sys.stderr)
        sys.exit(1)

    bit_depth = args.bit_depth or 24
    out_codec = codec_flags(out_ext, bit_depth=bit_depth, bitrate=args.bitrate)
    has_segment = args.start is not None or args.end is not None or args.duration is not None

    if has_segment:
        # Build a filter graph: trim segment, split, optionally pad with gap, concat
        start_sec = time_to_seconds(args.start) if args.start else 0
        end_sec = None
        if args.end:
            end_sec = time_to_seconds(args.end)
        elif args.duration:
            end_sec = start_sec + time_to_seconds(args.duration)

        trim_parts = f"start={start_sec}"
        if end_sec is not None:
            trim_parts += f":end={end_sec}"

        # Build filter: trim -> split -> (optional gap pad) -> concat
        filters = []
        filters.append(f"[0:a]atrim={trim_parts},asetpts=PTS-STARTPTS,asplit={count}" +
                        "".join(f"[s{i}]" for i in range(count)))

        if args.gap and args.gap > 0:
            # Add silence pad to all segments except the last
            for i in range(count - 1):
                filters.append(f"[s{i}]apad=pad_dur={args.gap}[p{i}]")
            concat_inputs = "".join(f"[p{i}]" for i in range(count - 1)) + f"[s{count - 1}]"
        else:
            concat_inputs = "".join(f"[s{i}]" for i in range(count))

        filters.append(f"{concat_inputs}concat=n={count}:v=0:a=1[out]")
        filter_str = ";".join(filters)

        cmd = ["ffmpeg", "-i", str(input_path), "-filter_complex", filter_str, "-map", "[out]"]
    else:
        # Whole-file loop: use concat with multiple inputs
        if count <= 50:
            # Multi-input approach (clean for moderate counts)
            cmd = ["ffmpeg"]
            for _ in range(count):
                cmd += ["-i", str(input_path)]

            if args.gap and args.gap > 0:
                # Generate silence and interleave
                filters = []
                sr_data = run_ffprobe(str(input_path))
                sr_stream = get_audio_stream(sr_data)
                sr = sr_stream.get("sample_rate", "44100") if sr_stream else "44100"
                ch = sr_stream.get("channels", "1") if sr_stream else "1"

                # Create silence audio
                filters.append(
                    f"anullsrc=r={sr}:cl={'stereo' if int(ch) == 2 else 'mono'},"
                    f"atrim=duration={args.gap}[silence]"
                )
                # Split silence for count-1 gaps
                if count > 2:
                    filters.append(f"[silence]asplit={count - 1}" +
                                   "".join(f"[g{i}]" for i in range(count - 1)))
                else:
                    filters.append("[silence]acopy[g0]")

                # Build concat: input0 gap0 input1 gap1 ... inputN
                concat_parts = []
                for i in range(count):
                    concat_parts.append(f"[{i}:a]")
                    if i < count - 1:
                        concat_parts.append(f"[g{i}]")
                n_total = count + (count - 1)  # inputs + gaps
                filters.append(f"{''.join(concat_parts)}concat=n={n_total}:v=0:a=1[out]")

                filter_str = ";".join(filters)
                cmd += ["-filter_complex", filter_str, "-map", "[out]"]
            else:
                filter_parts = "".join(f"[{i}:a]" for i in range(count))
                cmd += ["-filter_complex",
                        f"{filter_parts}concat=n={count}:v=0:a=1[out]",
                        "-map", "[out]"]
        else:
            # For high counts, use concat demuxer via pipe
            # Use forward slashes for ffmpeg compatibility on all platforms
            resolved = str(input_path.resolve()).replace("\\", "/")
            concat_list = "\n".join(f"file '{resolved}'" for _ in range(count))
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0",
                "-protocol_whitelist", "file,pipe",
                "-i", "pipe:0",
            ]
            # We'll handle this specially below
            cmd += out_codec
            if args.overwrite:
                cmd += ["-y"]
            cmd += [str(output_path)]

            if args.verbose:
                print(f"[CMD] {' '.join(cmd)}")
                print(f"[CMD] (stdin: concat list with {count} entries)")

            t0 = time.time()
            result = subprocess.run(cmd, input=concat_list, capture_output=True, text=True)
            elapsed = time.time() - t0
            if result.returncode != 0:
                stderr_lines = [l for l in result.stderr.strip().split("\n") if l.strip()]
                err_msg = stderr_lines[-1] if stderr_lines else "Unknown error"
                print(f"[ERROR] ffmpeg failed: {err_msg}", file=sys.stderr)
                sys.exit(1)

            out_dur = get_file_duration(str(output_path))
            print(f"[OK] Looped {input_path.name} x{count} -> {output_path.name} "
                  f"(duration: {format_duration(out_dur)}, {elapsed:.1f}s)")
            return

    cmd += out_codec
    if args.overwrite:
        cmd += ["-y"]
    cmd += [str(output_path)]

    t0 = time.time()
    ok = run_ffmpeg(cmd, verbose=args.verbose)
    elapsed = time.time() - t0

    if ok:
        out_dur = get_file_duration(str(output_path))
        seg_info = ""
        if has_segment:
            s = args.start or "0"
            e = args.end or (args.duration and f"+{args.duration}") or "end"
            seg_info = f" (segment {s}-{e})"
        print(f"[OK] Looped {input_path.name}{seg_info} x{count} -> {output_path.name} "
              f"(duration: {format_duration(out_dur)}, {elapsed:.1f}s)")
    else:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand: batch
# ---------------------------------------------------------------------------

def cmd_batch(args):
    """Batch convert audio files in a directory."""
    input_dir = pathlib.Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"[ERROR] Not a directory: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    target_ext = args.format if args.format.startswith(".") else f".{args.format}"
    target_ext = target_ext.lower()

    if target_ext not in FORMAT_CODEC_MAP:
        supported = ", ".join(sorted(FORMAT_CODEC_MAP.keys()))
        print(f"[ERROR] Unsupported format '{target_ext}'. Supported: {supported}", file=sys.stderr)
        sys.exit(1)

    output_dir = pathlib.Path(args.output_dir) if args.output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect audio files
    if args.recursive:
        files = sorted(f for f in input_dir.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)
    else:
        files = sorted(f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS)

    if not files:
        print(f"[INFO] No audio files found in '{input_dir}'")
        return

    converted = 0
    skipped = 0
    failed = 0
    total = len(files)

    bit_depth = args.bit_depth or 24
    flags = codec_flags(target_ext, bit_depth=bit_depth, bitrate=args.bitrate)

    for i, f in enumerate(files, 1):
        # Compute output path, preserving subdirectory structure
        rel = f.relative_to(input_dir)
        out_file = output_dir / rel.with_suffix(target_ext)

        if f.suffix.lower() == target_ext:
            print(f"[{i}/{total}] Skipping {f.name} (already {target_ext})")
            skipped += 1
            continue

        if out_file.exists() and not args.overwrite:
            print(f"[{i}/{total}] Skipping {f.name} (output exists, use -y to overwrite)")
            skipped += 1
            continue

        out_file.parent.mkdir(parents=True, exist_ok=True)

        if args.dry_run:
            print(f"[{i}/{total}] Would convert {f.name} -> {out_file.name}")
            converted += 1
            continue

        cmd = ["ffmpeg", "-i", str(f)] + flags
        if args.sample_rate:
            cmd += ["-ar", str(args.sample_rate)]
        if args.overwrite:
            cmd += ["-y"]
        cmd += [str(out_file)]

        t0 = time.time()
        ok = run_ffmpeg(cmd, verbose=args.verbose)
        elapsed = time.time() - t0

        if ok:
            print(f"[{i}/{total}] Converted {f.name} -> {out_file.name} ({elapsed:.1f}s)")
            converted += 1
        else:
            print(f"[{i}/{total}] FAILED {f.name}")
            failed += 1

    print(f"\nBatch complete: {converted} converted, {failed} failed, {skipped} skipped.")


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="audiotool",
        description="CLI audio toolkit — convert, trim, loop, and inspect audio files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  audiotool info song.mp3
  audiotool convert song.mp3 song.wav
  audiotool convert song.mp3 song.wav --bit-depth 16
  audiotool trim song.mp3 clip.mp3 -s 0:30 -e 1:00
  audiotool trim song.mp3 clip.mp3 -s 0 -d 30
  audiotool loop song.mp3 looped.mp3 -n 3
  audiotool loop song.mp3 looped.wav -s 0 -d 30 -n 5
  audiotool loop song.mp3 looped.wav -s 0 -d 30 -n 5 --gap 1.5
  audiotool batch ./music/ -f flac
  audiotool batch ./music/ -f wav -o ./converted/ -y
""")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="print ffmpeg commands")

    sub = parser.add_subparsers(dest="command", help="available commands")

    # --- info ---
    p_info = sub.add_parser("info", help="show audio file information",
                            description="Display metadata and technical details of an audio file.")
    p_info.add_argument("input", help="input audio file")
    p_info.add_argument("-j", "--json", action="store_true", help="output raw JSON from ffprobe")
    p_info.set_defaults(func=cmd_info)

    # --- convert ---
    p_conv = sub.add_parser("convert", help="convert audio between formats",
                            description="Convert an audio file to a different format. "
                                        "WAV output always uses lossless PCM encoding.")
    p_conv.add_argument("input", help="input audio file")
    p_conv.add_argument("output", help="output file (format from extension)")
    p_conv.add_argument("--bitrate", help="bitrate for lossy formats (e.g. 320k, 192k)")
    p_conv.add_argument("--sample-rate", type=int, help="output sample rate (e.g. 44100, 48000)")
    p_conv.add_argument("--channels", type=int, choices=[1, 2], help="1=mono, 2=stereo")
    p_conv.add_argument("--bit-depth", type=int, choices=[16, 24, 32],
                        help="PCM bit depth for WAV/AIFF output (default: 24)")
    p_conv.add_argument("-y", "--overwrite", action="store_true", help="overwrite output if it exists")
    p_conv.set_defaults(func=cmd_convert)

    # --- trim ---
    p_trim = sub.add_parser("trim", help="cut/extract a segment from audio",
                            description="Extract a segment from an audio file by specifying "
                                        "start and end times or duration.")
    p_trim.add_argument("input", help="input audio file")
    p_trim.add_argument("output", help="output file")
    p_trim.add_argument("-s", "--start", type=parse_time, required=True,
                        help="start time (SS, MM:SS, or HH:MM:SS)")
    end_group = p_trim.add_mutually_exclusive_group()
    end_group.add_argument("-e", "--end", type=parse_time,
                           help="end time (mutually exclusive with --duration)")
    end_group.add_argument("-d", "--duration", type=parse_time,
                           help="duration from start (mutually exclusive with --end)")
    p_trim.add_argument("-c", "--copy", action="store_true",
                        help="stream copy (no re-encode, faster but less precise)")
    p_trim.add_argument("--bitrate", help="bitrate for lossy output formats")
    p_trim.add_argument("--bit-depth", type=int, choices=[16, 24, 32],
                        help="PCM bit depth for WAV/AIFF output (default: 24)")
    p_trim.add_argument("-y", "--overwrite", action="store_true", help="overwrite output if it exists")
    p_trim.set_defaults(func=cmd_trim)

    # --- loop ---
    p_loop = sub.add_parser("loop", help="loop audio or a segment of it",
                            description="Create a looped version of an audio file or a specific segment.\n"
                                        "Example: loop the first 30 seconds 5 times.")
    p_loop.add_argument("input", help="input audio file")
    p_loop.add_argument("output", help="output file")
    p_loop.add_argument("-n", "--count", type=int, required=True, help="number of times to loop")
    p_loop.add_argument("-s", "--start", type=parse_time,
                        help="start of segment to loop (default: beginning)")
    loop_end = p_loop.add_mutually_exclusive_group()
    loop_end.add_argument("-e", "--end", type=parse_time, help="end of segment to loop")
    loop_end.add_argument("-d", "--duration", type=parse_time, help="duration of segment to loop")
    p_loop.add_argument("-g", "--gap", type=float, default=0,
                        help="seconds of silence between loops (default: 0)")
    p_loop.add_argument("--bitrate", help="bitrate for lossy output formats")
    p_loop.add_argument("--bit-depth", type=int, choices=[16, 24, 32],
                        help="PCM bit depth for WAV/AIFF output (default: 24)")
    p_loop.add_argument("-y", "--overwrite", action="store_true", help="overwrite output if it exists")
    p_loop.set_defaults(func=cmd_loop)

    # --- batch ---
    p_batch = sub.add_parser("batch", help="batch convert files in a directory",
                             description="Convert all audio files in a directory to a target format.")
    p_batch.add_argument("input_dir", help="directory containing audio files")
    p_batch.add_argument("-f", "--format", required=True,
                         help="target format extension (wav, mp3, flac, ogg, m4a, opus)")
    p_batch.add_argument("-o", "--output-dir", help="output directory (default: same as input)")
    p_batch.add_argument("--bitrate", help="bitrate for lossy formats")
    p_batch.add_argument("--sample-rate", type=int, help="output sample rate")
    p_batch.add_argument("--bit-depth", type=int, choices=[16, 24, 32],
                         help="PCM bit depth for WAV/AIFF output (default: 24)")
    p_batch.add_argument("-r", "--recursive", action="store_true", help="include subdirectories")
    p_batch.add_argument("-y", "--overwrite", action="store_true", help="overwrite existing outputs")
    p_batch.add_argument("--dry-run", action="store_true", help="show what would be done")
    p_batch.set_defaults(func=cmd_batch)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    check_dependencies()
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func") or args.func is None:
        parser.print_help()
        sys.exit(0)

    args.verbose = getattr(args, "verbose", False)
    args.func(args)


if __name__ == "__main__":
    main()
