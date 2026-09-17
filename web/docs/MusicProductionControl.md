# Production choices · YuE2 / MiniMax

Start here: choose **YuE2** (default), **YuE2 Cover** or **MiniMax Music 3**, then decide which
production stages to run.

YuE2 Cover uses the source audio group and the same stage defaults as YuE2.
The Cover switch below controls artwork; selecting YuE2 Cover controls audio covers.

| Choice | Default | Effect |
| --- | --- | --- |
| Cover | On | Creates artwork and checks/downloads FLUX.2 models. |
| Refinement | Model default | Off for YuE2; on for MiniMax. Select On or Off to override. |
| Mastering | On | Runs Auto-EQ, manual EQ, sample-rate preparation and mastering compression. |
| Artifact reduction | On (Balanced) | Experimental time/frequency outlier reduction after Refinement, before Mastering; independent of both. |

Refinement includes declipping, filtering, FlashSR and high-frequency repair.
Turning it off skips the entire section and its FlashSR model download. Mastering
then receives generated audio, optionally processed by Artifact reduction.
Turning Mastering off passes through that same incoming audio. The original
generation is always saved. See `docs/ARTIFACT_REDUCTION.md` for audition instructions;
detected candidates are not confirmed AI errors.

Use the bundled `Music_Production_Toolkit.json` for these connections. A switch
only controls stages wired to its outputs. The profile outputs remain compatible
with the earlier Song model node. Effective choices are saved in the production JSON.

## What you set here

- **model** - YuE2, YuE2 Cover or MiniMax Music 3.
- **cover_artwork_enabled** - whether FLUX.2 cover artwork is generated. This is *not* the
  'YuE2 Cover' song mode; it only decides whether artwork is produced.
- **refinement** - `Model default` (on for MiniMax, off for YuE2) or an explicit `On` / `Off`.
- **mastering_enabled** - run the mastering area, including the final sample-rate conversion.
- **artifact_reduction_enabled** - run the experimental artifact reduction.

The node returns the model profile, an information line and four switches that the stages
behind it honour. With a switch off, the stage and its report producers are skipped rather
than computed and discarded.
