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
generation is always saved. See `ARTIFACT_REDUCTION.md` for audition instructions;
detected candidates are not confirmed AI errors.

Use the bundled `Yue2_MM3_Production_Toolkit.json` for these connections. A switch
only controls stages wired to its outputs. The profile outputs remain compatible
with the earlier Song model node. Effective choices are saved in the production JSON.
