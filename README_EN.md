# dPCM Tone Generator

A tool that turns any waveform into a **dPCM file that loops seamlessly** on the NES/Famicom.
It lets the dPCM channel hold a pitched, sustained tone for as long as you want.

## Quick start

For what this tool is actually for, see **[About this tool](docs/concept.md)** (in Japanese).
For everyday use, just follow these steps:

1. Download the package for your OS (Windows / Mac) from **[Releases](https://github.com/driftingraft/dpcm-tone-generator/releases)**.
2. Extract it and **double-click** `Start.bat` (Windows) or `Start.command` (Mac).
3. Your browser opens and you can start right away (no Python install on Windows).

For a detailed walkthrough, see the **[GUI manual](docs/gui_manual.md)** (in Japanese).

---

## Features

- **Multiple input formats**: Basic waveforms (saw/triangle/sine/square/pulse), FDS waveforms, HEX strings, WAV files
- **Fit mode**: Automatically finds parameters that exactly match valid dPCM sample lengths (8+128n), eliminating padding noise
- **Three quality settings**: Size first / minimum rate index (balanced) / quality first
- **Volume control**: Adjustable waveform amplitude
- **Loop optimization**: Auto-start value, endpoint adjustment for seamless loops
- **Sub-octave mixing**: Layers a sub-harmonic one octave below to reinforce the low end (cycle count is automatically made even to keep the loop boundary aligned)
- **Batch generation**: Generate all notes in a configurable range (default: C2-F4) at once with ppmck definition files
- **Sunsoft-bass method**: Covers every note with a minimal set of samples, greatly reducing memory usage
- **Browser GUI**: All features accessible from a browser, with waveform display, audio preview, and ZIP download

## Requirements

- Python 3.8+
- Standard library only (no additional packages required)

## Installation

```bash
git clone https://github.com/driftingraft/dpcm-tone-generator.git
cd dpcm-tone-generator
```

## Usage

### GUI (Browser)

```bash
python dpcm_gui.py
```

Starts a local web server (default: http://127.0.0.1:8765/ ) and opens your browser. No additional packages required.

The interface auto-detects your browser language (English / Japanese) and has a language toggle at the top-right corner.

- **Single**: equivalent to dpcm_generator.py — waveform graph, dPCM/pre-encode audio preview, ppmck definition example
- **Batch**: equivalent to dpcm_batch.py — generate all notes in a configurable range (default: C2-F4), per-note playback, ZIP download
- **Sunsoft**: equivalent to dpcm_sunsoft.py — analysis, minimal sample set generation, scale preview playback
- **Rates**: NTSC dPCM sample rate table

```bash
python dpcm_gui.py --port 8000     # change port
python dpcm_gui.py --no-browser    # do not open the browser automatically
```

See the **[GUI manual](docs/gui_manual.md)** (in Japanese, with screenshots) for details.

### No-Python distribution (for end users)

For users without Python, you can build a ready-to-run package that needs no installation:

- **Windows**: bundles the official embeddable Python — just extract and double-click `Start.bat`.
- **Mac**: uses the system `python3` — double-click `Start.command` (it offers to install the Command Line Developer Tools if `python3` is missing).

Build both (output goes to `dist/`):

```bash
python packaging/build_package.py --zip
```

See **[packaging/README.md](packaging/README.md)** for details.

### Basic Usage

```bash
# Generate a sawtooth wave at C3
python dpcm_generator.py --wave saw --note C3 --output saw_c3.dmc

# Recommended: fit mode + auto-start + warmup
python dpcm_generator.py --wave saw --note C3 --fit --auto-start --warmup --output saw_c3.dmc
```

### From FDS Waveform

```bash
# FDS format (space-separated decimals, 0-63, 64 samples)
python dpcm_generator.py --fds "00 01 02 03 ... 63 63 00 00" --note C3 --fit --auto-start --output fds_c3.dmc

# From file
python dpcm_generator.py --fds-file waveform.txt --note C3 --fit --auto-start --output fds_c3.dmc
```

### High Quality Settings

```bash
# Quality mode + multiple cycles + volume adjustment
python dpcm_generator.py --wave saw --note C3 --fit --quality --cycles 16 --volume 0.5 --auto-start --output saw_c3.dmc
```

### Sub-Octave Mixing (low-end reinforcement)

`--sub-octave` mixes a sub-harmonic one octave below (half the frequency) into the fundamental. Useful for adding weight to bass sounds. The value is the mix amount: `0.3` layers it at 30% of the fundamental's amplitude.

```bash
# Mix the sub-octave at 30% of the fundamental
python dpcm_generator.py --wave saw --note C3 --fit --sub-octave 0.3 --auto-start --output saw_c3.dmc

# Also available in batch and Sunsoft-bass modes
python dpcm_batch.py --wave saw --fit --sub-octave 0.3 --output-dir ./dpcm_samples
python dpcm_sunsoft.py --wave saw --sub-octave 0.3 --output-dir ./sunsoft_samples
```

Because the sub-octave has twice the period of the fundamental, an odd cycle count leaves it half a period out of alignment at the loop boundary, causing clicks. To avoid this, **the cycle count is automatically adjusted to an even number** whenever `--sub-octave` is used (in fit mode, only even-cycle candidates are searched). If no even-cycle solution exists within the error tolerance, the tool falls back to the normal behavior with a warning.

### Batch Generation (All Notes)

```bash
# Generate 30 notes at once (default: C2-F4)
python dpcm_batch.py --wave saw --fit --cycles 8 --auto-start --warmup --output-dir ./dpcm_samples

# Specify the note range (e.g., C3-B5)
python dpcm_batch.py --wave saw --fit --auto-start --warmup --start C3 --end B5 --output-dir ./dpcm_samples

# ppmck definition file is also generated
# → ./dpcm_samples/saw_defines.txt
```

### Sunsoft-Bass Method

The Sunsoft-bass method covers every note with a minimal number of samples. By replaying a single sample at different rates, it dramatically reduces memory usage.

```bash
# Analyze first (check which samples are needed)
python dpcm_sunsoft.py --analyze-only --start C2 --end F4

# Generate the samples
python dpcm_sunsoft.py --wave saw --start C2 --end F4 --fit --auto-start --warmup --output-dir ./sunsoft_samples

# Tighten the error tolerance (default: 25 cents)
python dpcm_sunsoft.py --wave saw --start C2 --end F4 --max-error 15 --fit --output-dir ./sunsoft_samples
```

#### Quality-first vs. size-first

**Quality-first mode** is the default. It picks base samples from near the top of the target range (C4-E4 and so on); higher notes are played at the highest rate ($F), so each cycle holds more samples and sounds better.

**Size-first mode** (`--size-priority`) also considers notes above the target range (E6 and so on) as base-sample candidates. It minimizes the sample count, but more notes end up played at lower rates, so quality drops.

```bash
# Quality-first (default) — base samples land around C4-E4
python dpcm_sunsoft.py --analyze-only --start C2 --end E4 --max-error 50
# → Base samples: C4, C#4, D4, D#4, E4 (5 samples, mean error 13.8 cents)

# Size-first — fewer samples
python dpcm_sunsoft.py --analyze-only --start C2 --end E4 --max-error 50 --size-priority
# → Base samples: C5, C#5, D#6, E6 (4 samples, mean error 22.2 cents)
```

Example results (30 notes from C2-F4, saw wave, fit mode, 8 cycles, 25-cent tolerance):

| Method | Samples | Total size |
|---|---|---|
| Conventional (one sample per note) | 30 | 1998 bytes |
| Sunsoft-bass (quality-first) | 8 | 1128 bytes (~44% smaller) |
| Sunsoft-bass (size-first) | 4 | 260 bytes (~87% smaller) |

Fewer samples also means fewer ppmck instrument definitions used (only 0-63 are available).

## Options

### dpcm_generator.py

| Option | Short | Description |
|--------|-------|-------------|
| `--wave` | `-w` | Waveform type: saw, triangle, sine, square, pulse25, pulse12 |
| `--note` | `-n` | Note name (e.g., C3, A4, F#2) |
| `--freq` | `-f` | Frequency in Hz |
| `--rate-index` | `-r` | Sample rate index (0-15) |
| `--output` | `-o` | Output filename |
| `--fds` | | FDS waveform (space-separated decimals) |
| `--fds-file` | | FDS waveform file |
| `--hex` | `-x` | HEX waveform (hexadecimal string) |
| `--hex-file` | | HEX waveform file |
| `--wav` | | WAV file |
| `--cycles` | `-c` | Number of cycles (default: 1) |
| `--volume` | `-v` | Volume multiplier (default: 1.0) |
| `--sub-octave` | | Amount of sub-octave to mix (0.0 = none, 0.3 = 30% of the fundamental; cycle count is made even automatically) |
| `--fit` | | Auto-fit to valid sample length |
| `--quality` | `-q` | In fit mode, prefer higher sample rates |
| `--min-rate-index` | | In fit mode, set the lowest allowed sample rate index (0-15) |
| `--auto-start` | `-a` | Match start value to waveform |
| `--loop-match` | `-l` | Match end value to start value |
| `--show-wave` | | Display ASCII waveform |
| `--info` | `-i` | Show sample rate information |
| `--dpcm-index` | | ppmck definition number (default: 0) |
| `--dpcm-path` | | dmc file path used in the ppmck definition |

### dpcm_batch.py

In addition to the options above:

| Option | Short | Description |
|--------|-------|-------------|
| `--output-dir` | `-o` | Output directory |
| `--name` | `-n` | Filename prefix for custom waveforms |
| `--start` | | First note to generate (default: C2) |
| `--end` | | Last note to generate (default: F4) |
| `--dpcm-start-index` | | Starting number for the ppmck definitions (default: 0) |
| `--dpcm-path` | | dmc file path used in the ppmck definitions |

### dpcm_sunsoft.py

| Option | Short | Description |
|--------|-------|-------------|
| `--wave` | | Waveform type: saw, triangle, sine, square, pulse25, pulse12 |
| `--fds` | | FDS waveform file |
| `--hex` | | HEX waveform data |
| `--wav` | | WAV file |
| `--analyze-only` | | Analyze only (no samples generated) |
| `--start` | | First note (default: C2) |
| `--end` | | Last note (default: F4) |
| `--max-error` | | Error tolerance in cents (default: 25.0) |
| `--output-dir` | `-o` | Output directory |
| `--prefix` | | Filename prefix (default: sunsoft_) |
| `--fit` | | Fit mode (match valid dPCM sample lengths) |
| `--cycles` | | Number of cycles (default: 8) |
| `--volume` | | Volume (0.0-1.0, default: 1.0) |
| `--sub-octave` | | Amount of sub-octave to mix (0.0 = none, 0.3 = 30% of the fundamental; cycle count is made even automatically) |
| `--auto-start` | | Match start value to waveform |
| `--loop-match` | | Match end value to start value for looping |
| `--prefer-quality` | | Prefer higher rates when selecting playback rates |
| `--size-priority` | | Size-first mode (also uses samples outside the target range; quality-first is the default) |
| `--dpcm-start-index` | | Starting number for the per-note ppmck definitions (default: 0) |
| `--dpcm-path` | | dmc file path used in the ppmck definitions |

## Recommended Settings

### Highest Quality (larger size)

```bash
python dpcm_generator.py --wave saw --note C3 --fit --quality --cycles 16 --auto-start --warmup --output output.dmc
```

### Balanced (recommended)

Set a lower bound on the sample rate with `--min-rate-index` while keeping the size down:

```bash
# Pick the smallest size among rates $8 and above
python dpcm_generator.py --wave saw --note C3 --fit --min-rate-index 8 --auto-start --warmup --output output.dmc
```

### Size First

```bash
python dpcm_generator.py --wave saw --note C3 --fit --auto-start --warmup --output output.dmc
```

### Smallest Size (without fit)

```bash
python dpcm_generator.py --wave saw --note C3 --loop-match --output output.dmc
```

## Technical Details

### NES dPCM Specifications

- 1-bit delta modulation (+2 or -2 per sample)
- Sample values: 0-127 (7-bit)
- Valid sample lengths: 8 + 128n (n=0,1,2,...)
- Valid byte lengths: 1 + 16n
- 16 sample rates available (NTSC)

### How Fit Mode Works

1. Searches all 16 sample rates
2. Tests a range of cycle counts for each rate (1-64 in `dpcm_generator.py`, up to 128 for the Sunsoft-bass method)
3. Finds combinations where total samples equals (8+128n)
4. Selects the optimal result within the error tolerance (15 cents in `dpcm_generator.py`, 25 cents by default for the Sunsoft-bass method via `--max-error`)

### The --auto-start Effect

dPCM normally starts at value 64 (center). If your waveform starts at 0, there's a "descent" period while catching up to the target, causing noise. `--auto-start` begins at the waveform's first value, avoiding this issue.

### --warmup vs --loop-match

Both options smooth the loop boundary.

- `--warmup`: repeatedly simulates one waveform period as a run-up until the encoder state reaches steady state, then uses the converged value as the start value (the run-up itself is not written to the output). **In fit mode this alone guarantees the file's end value equals its start value**, producing a perfect loop
- `--loop-match`: appends correction bits at the end of the file to bring the end value back to the start value. Useful outside fit mode (e.g., with `--rate-index`), where padding to a valid length leaves a residual mismatch at the boundary

**Recommendation**: use `--warmup` with fit mode, and `--loop-match` when not using fit mode. The GUI enables warmup by default.

## Usage with ppmck

Example of a generated ppmck definition file (with the loop flag):

```
; === saw dPCM sample definitions ===
; Note: the sample rate differs for each pitch

@DPCM0 = { "saw_C2.dmc", 12, 0, 0, 1 }   ; C2
@DPCM1 = { "saw_C_s2.dmc", 1, 0, 0, 1 }  ; C#2
@DPCM2 = { "saw_D2.dmc", 6, 0, 0, 1 }    ; D2
...
```

Specifying the definition numbers and the path:

```bash
# Start numbering at 20 and set the path
python dpcm_batch.py --wave saw --fit --dpcm-start-index 20 --dpcm-path "D:\music\dpcm\" --output-dir ./out
```

Output:
```
@DPCM20 = { "D:\music\dpcm\saw_C2.dmc", 12, 0, 0, 1 }  ; C2
@DPCM21 = { "D:\music\dpcm\saw_C_s2.dmc", 1, 0, 0, 1 } ; C#2
...
```

In MML (on the E channel, specify the @DPCM number directly with the `n` command instead of note names like cdefgab):

```
E n0   ; Play @DPCM0 as a tone (looped)
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) (written primarily in Japanese).

## Development note

This project is developed with the help of generative AI ([Claude Code](https://claude.com/claude-code)).

## Author / Contact

- **漂流いかだ / driftingraft** (Circle: 時遊戯画 / Jiyugiga)
- Website: [Jiyugiga](https://jiyugiga.sakura.ne.jp/)
- GitHub: https://github.com/driftingraft
- X (Twitter): [@KOR_jiyugiga](https://x.com/KOR_jiyugiga)

Bug reports and feature requests are also welcome via GitHub Issues.

## License

MIT License

## References

- [NESDev Wiki - APU DMC](https://www.nesdev.org/wiki/APU_DMC)
- [ppmck](https://github.com/ppmck/ppmck)
