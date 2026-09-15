# Production choices · YuE2 / MiniMax

Start here: choose **YuE2** (default) or **MiniMax Music 3**, then decide which
production stages to run.

| Choice | Default | Effect |
| --- | --- | --- |
| Cover | On | Creates artwork and checks/downloads FLUX.2 models. |
| Refinement | Model default | Off for YuE2; on for MiniMax. Select On or Off to override. |
| Mastering | On | Runs Auto-EQ, manual EQ, sample-rate preparation and mastering compression. |

Refinement includes declipping, filtering, FlashSR and high-frequency repair.
Turning it off skips the entire section and its FlashSR model download. Mastering
then receives the original generated audio. Turning mastering off passes through
the audio from generation or refinement. The original generation is always saved.

Use the bundled `Yue2_MM3_Production_Toolkit.json` for these connections. A switch
only controls stages wired to its outputs. The profile outputs remain compatible
with the earlier Song model node. Effective choices are saved in the production JSON.
