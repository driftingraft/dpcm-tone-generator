# NES dPCM Generator

A Python tool for generating dPCM samples for the Nintendo Entertainment System (NES/Famicom).

Generate dPCM samples (.dmc) at specified pitches from arbitrary waveforms. Optimized for creating looping bass/lead sounds.

## Features

- **Multiple input formats**: Basic waveforms (saw/triangle/sine/square/pulse), FDS waveforms, HEX strings, WAV files
- **Fit mode**: Automatically finds parameters that exactly match valid dPCM sample lengths (8+128n), eliminating padding noise
- **Quality mode**: Prioritizes higher sample rates over smaller file size
- **Volume control**: Adjustable waveform amplitude
- **Loop optimization**: Auto-start value, endpoint adjustment for seamless loops
- **Batch generation**: Generate all notes in a configurable range (default: C2-F4) at once with ppmck definition files
- **Browser GUI**: All features accessible from a browser, with waveform display, audio preview, and ZIP download

## Requirements

- Python 3.8+
- Standard library only (no additional packages required)

## Installation

```bash
git clone https://github.com/yourusername/nes-dpcm-generator.git
cd nes-dpcm-generator
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

### Batch Generation (All Notes)

```bash
# Generate 30 notes at once
python dpcm_batch.py --wave saw --fit --cycles 8 --auto-start --warmup --output-dir ./dpcm_samples

# ppmck definition file is also generated
# → ./dpcm_samples/saw_defines.txt
```

## Options

### dpcm_generator.py

| Option | Short | Description |
|--------|-------|-------------|
| `--wave` | `-w` | Waveform type: saw, triangle, sine, square, pulse25, pulse12 |
| `--note` | `-n` | Note name (e.g., C3, A4, F#2) |
| `--freq` | `-f` | Frequency in Hz |
| `--rate` | `-r` | Sample rate index (0-15) |
| `--output` | `-o` | Output filename |
| `--fds` | | FDS waveform (space-separated decimals) |
| `--fds-file` | | FDS waveform file |
| `--hex` | `-x` | HEX waveform (hexadecimal string) |
| `--hex-file` | | HEX waveform file |
| `--wav` | | WAV file |
| `--cycles` | `-c` | Number of cycles (default: 1) |
| `--volume` | `-v` | Volume multiplier (default: 1.0) |
| `--fit` | | Auto-fit to valid sample length |
| `--quality` | `-q` | Prefer higher sample rate |
| `--auto-start` | `-a` | Match start value to waveform |
| `--loop-match` | `-l` | Match end value to start value |
| `--show-wave` | | Display ASCII waveform |
| `--info` | `-i` | Show sample rate information |

### dpcm_batch.py

In addition to the above:

| Option | Description |
|--------|-------------|
| `--output-dir` | Output directory |
| `--name` | Filename prefix for custom waveforms |

## Recommended Settings

### Highest Quality (larger size)

```bash
python dpcm_generator.py --wave saw --note C3 --fit --quality --cycles 16 --auto-start --warmup --output output.dmc
```

### Balanced (recommended)

```bash
python dpcm_generator.py --wave saw --note C3 --fit --cycles 8 --auto-start --warmup --output output.dmc
```

### Smallest Size

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
2. Tests 1-64 cycles for each rate
3. Finds combinations where total samples equals (8+128n)
4. Selects optimal result within 15 cents error tolerance

### The --auto-start Effect

dPCM normally starts at value 64 (center). If your waveform starts at 0, there's a "descent" period while catching up to the target, causing noise. `--auto-start` begins at the waveform's first value, avoiding this issue.

### --warmup vs --loop-match

Both options smooth the loop boundary.

- `--warmup`: repeatedly simulates one waveform period as a run-up until the encoder state reaches steady state, then uses the converged value as the start value (the run-up itself is not written to the output). **In fit mode this alone guarantees the file's end value equals its start value**, producing a perfect loop
- `--loop-match`: appends correction bits at the end of the file to bring the end value back to the start value. Useful outside fit mode (e.g., with `--rate-index`), where padding to a valid length leaves a residual mismatch at the boundary

**Recommendation**: use `--warmup` with fit mode, and `--loop-match` when not using fit mode. The GUI enables warmup by default.

## Usage with ppmck

Generated ppmck definition file example:

```
; dPCM Sample Definitions (saw)
; Generated: 2025-01-16

@DPCM0 = { "saw_C2.dmc", 1 }    ; C2
@DPCM1 = { "saw_C_s2.dmc", 3 }  ; C#2
@DPCM2 = { "saw_D2.dmc", 2 }    ; D2
...
```

In MML:

```
E @DPCM0 | c   ; Play dPCM as tone
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
