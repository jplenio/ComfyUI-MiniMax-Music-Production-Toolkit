# EQ presets and YuE2 recommendations

The Auto-EQ node offers **10 presets**, and the manual EQ editor offers **24
presets**, each with a Custom entry. Select a preset, execute and audition.
The selections set the existing controls/JSON, so saved workflows and API
execution use the same values. No new models or dependencies are needed.

## Defaults and editing

Auto-EQ has **one preset selector with explanation**. Warm/Bright/Reference is
chosen by that preset; the former separate `target_mode` dropdown is hidden.
The numerical settings remain editable. Custom displays the retained tonal
target in its explanation; select another preset to change that target.
Existing saved settings and API inputs stay compatible.

- All bundled workflows start at **Warm - gentle (workflow default)** for
  Auto-EQ: Warm tilt, 35% strength, 2 dB maximum, four bands, 40–16000 Hz.
  No reference audio is required.
- Standalone Auto-EQ nodes retain their existing Reference/50%/3 dB/six-band
  defaults (**Reference - balanced**). Reference presets require reference audio.
  Without it, Auto-EQ warns and returns neutral settings so production can
  continue. Choose a Warm/Bright preset for correction without a reference.
- Manual EQ starts **Flat**: zero preamp and no bands. Existing saved custom
  settings are preserved on load; no preset is applied automatically for YuE2.
- Selecting a preset replaces the corresponding controls, including the manual
  preamp. Edit individual values afterward; the selector shows Custom when no
  recipe matches. Custom itself preserves values. Manual Undo restores the
  previous curve, including after preset selection. Reset returns to Flat.
- Auto-EQ presets do not toggle enabled, change reference connections or change
  the separate manual EQ. Connected EQ settings are read-only; linked Auto-EQ
  parameter inputs disable its preset selector. Edit the upstream values instead.
- Curves and preamp are saved in `eq_settings_json`, not a second preset field.
  The existing EQ report records the actual settings. Preset names are inferred
  from values on load; band IDs do not affect matching.
- Manual recipes support typical music rates of 32 kHz and above. At lower
  rates, reduce frequencies to the supported maximum (45% of the sample rate,
  capped at 20 kHz). The backend validates rather than silently clamping them.
- Boost presets include explicit negative preamp for headroom; this is not a
  limiter or a guarantee against peaks. Compare at matched listening level.

After updating the toolkit, reload the ComfyUI page to load the new frontend
files. Existing workflows gain the selectors without rewiring or reimporting.

## YuE2: start with Smooth highs

**YuE2 - Smooth highs** is the first choice for a mix with sharp upper mids or
bright, synthetic-sounding treble:

- Broad peak at **3500 Hz, −1.5 dB, Q 0.9**.
- High shelf at **7500 Hz, −2 dB, slope 0.7**.
- Preamp **0 dB**, leaving the bass practically unchanged.

**YuE2 - Smooth highs (strong)** increases the peak cut to **−2.5 dB**, moves
the shelf to **7000 Hz at −3 dB**, and adds a **14 kHz, second-order low-pass
(Q ≈ 0.707)**. Try it only if the gentle curve leaves too much edge/fizz; it
also removes some air and cymbal brightness. Filter responses overlap, and a
shelf's listed frequency is its transition midpoint, not a brick-wall boundary.

These are toolkit starting points derived from general EQ practice, **not
official YuE2 settings or a model-specific measured optimum**. No supplied
YuE2 song was available for a listening comparison. iZotope discusses broad
treble cuts, high shelves and filtering as options for
[taming harsh treble](https://www.izotope.com/community/blog/8-tips-for-taming-harsh-treble-in-the-mix).
Its [vocal EQ guide](https://www.izotope.com/community/blog/how-to-eq-vocals)
places vocal harshness around 2–5 kHz; the 3.5 kHz choice here is a conservative
starting point for auditioning the whole mix, not a claim about every source.

A static EQ reduces an entire frequency region throughout the song. It cannot
selectively remove intermittent metallic noises, chirps or generation errors.
[Dynamic EQ](https://www.izotope.com/community/blog/when-to-use-dynamic-eq-in-a-mix)
can target harsh moments more selectively, but these presets do not implement
dynamic EQ. Persistent artifacts may need a dedicated repair step or a new
generation. The [RX EQ documentation](https://downloads.izotope.com/docs/rx6/40-eq/index.html)
also describes EQ as one part of restoration, rather than complete repair.

## Auto-EQ catalog

All entries use 40–16000 Hz except Upper-mid softening (1000–10000 Hz).
Warm and Bright are creative tilt targets, not genre standards. Analysis
still adapts the proposed bands to the actual source. Reference presets compare
broad source/reference balance; they do not copy the reference arrangement.

| Preset | Target | Strength | Max gain | Bands |
| --- | --- | ---: | ---: | ---: |
| Warm - gentle (workflow default) | Warm tilt | 35% | 2 dB | 4 |
| Warm - subtle mastering | Warm tilt | 20% | 1 dB | 3 |
| Warm - rounded mix | Warm tilt | 55% | 3 dB | 5 |
| Warm - upper-mid softening | Warm tilt | 45% | 2 dB | 4 |
| Bright - subtle mastering | Bright tilt | 20% | 1 dB | 3 |
| Bright - gentle clarity | Bright tilt | 35% | 2 dB | 4 |
| Bright - open mix | Bright tilt | 50% | 3 dB | 5 |
| Reference - subtle mastering | Reference track | 25% | 1.5 dB | 4 |
| Reference - balanced | Reference track | 50% | 3 dB | 6 |
| Reference - broad match | Reference track | 70% | 4 dB | 6 |

## Manual EQ catalog

Values below are in Hz and dB. Unspecified Q is approximately 0.707;
shelf slope is stated explicitly. Negative preamp is part of the preset.

| Preset | Filters | Preamp |
| --- | --- | ---: |
| Flat | No filters (unity) | 0 dB |
| YuE2 - Smooth highs | peak 3500 Hz, -1.5 dB, Q 0.9; high shelf 7500 Hz, -2 dB, slope 0.7 | 0 dB |
| YuE2 - Smooth highs (strong) | peak 3500 Hz, -2.5 dB, Q 0.9; high shelf 7000 Hz, -3 dB, slope 0.7; lowpass 14000 Hz, Q 0.707 | 0 dB |
| Warm - gentle tilt | low shelf 180 Hz, +1 dB, slope 0.7; high shelf 6000 Hz, -1 dB, slope 0.7 | -1 dB |
| Warm - dark mix | high shelf 4500 Hz, -2.5 dB, slope 0.7 | 0 dB |
| Air - gentle lift | high shelf 10000 Hz, +1.5 dB, slope 0.7 | -1.5 dB |
| Clarity - gentle presence | peak 2200 Hz, +1.2 dB, Q 0.8 | -1.2 dB |
| Bass - gentle weight | low shelf 110 Hz, +1.5 dB, slope 0.7 | -1.5 dB |
| Bass - tighten boom | peak 140 Hz, -2 dB, Q 0.8 | 0 dB |
| Sub - reduce rumble | highpass 28 Hz, Q 0.707 | 0 dB |
| Sub - lighter low end | low shelf 65 Hz, -2 dB, slope 0.7 | 0 dB |
| Low mids - reduce mud | peak 280 Hz, -1.8 dB, Q 0.85 | 0 dB |
| Low mids - add body | peak 220 Hz, +1.2 dB, Q 0.7 | -1.2 dB |
| Mids - reduce boxiness | peak 550 Hz, -1.8 dB, Q 1 | 0 dB |
| Mids - soften nasal tone | peak 1200 Hz, -1.8 dB, Q 1.2 | 0 dB |
| Upper mids - tame bite | peak 3200 Hz, -2 dB, Q 0.9 | 0 dB |
| Treble - soften cymbals | peak 6500 Hz, -1.5 dB, Q 1; high shelf 10000 Hz, -1.5 dB, slope 0.7 | 0 dB |
| Treble - reduce sibilant tone | peak 7000 Hz, -2.5 dB, Q 1.3 | 0 dB |
| Treble - reduce hiss and fizz | high shelf 8500 Hz, -2 dB, slope 0.7; lowpass 14000 Hz, Q 0.707 | 0 dB |
| Acoustic - gentle warmth | peak 180 Hz, +1 dB, Q 0.7; peak 3500 Hz, -1 dB, Q 0.9 | -1 dB |
| Piano - softer attack | peak 2800 Hz, -1.5 dB, Q 0.8; high shelf 9000 Hz, -0.8 dB, slope 0.7 | 0 dB |
| Vocal mix - gentle focus | peak 300 Hz, -1 dB, Q 0.8; peak 1800 Hz, +1 dB, Q 0.9 | -1 dB |
| Electronic - tighten and open | low shelf 80 Hz, +1 dB, slope 0.7; peak 300 Hz, -1.5 dB, Q 0.8; high shelf 9000 Hz, +1 dB, slope 0.7 | -2 dB |
| Vintage - mellow top | high shelf 5000 Hz, -2 dB, slope 0.7; lowpass 12000 Hz, Q 0.707 | 0 dB |

See [Audio mastering](AUDIO_MASTERING.md) for routing, JSON schemas and DSP details.
The catalog shipped with the frontend is [eq_presets.json](../web/eq_presets.json).
