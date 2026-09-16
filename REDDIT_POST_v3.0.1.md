# Reddit announcement draft — v3.0.1

Post after the GitHub release is published.

## Title

YuE2 sounding a little harsh? I added EQ presets + experimental artifact cleanup to my ComfyUI music toolkit

## Post

Another small update to my Music Production Toolkit: **3.0.1 is out!**

After adding YuE2 cover versions, I wanted more ways to shape the finished
sound—especially those moments when the upper mids or highs get a little sharp.

What's new:

- **24 manual EQ presets**, including two clearly labeled **YuE2 - Smooth highs**
  options. Manual EQ still starts Flat, and you can tweak every setting.
- **10 Auto-EQ presets + Custom**, in one selector with explanations. The
  workflow starts with a gentle warm tilt, so you don't need a reference track.
- **Experimental artifact reduction**, with its own on/off switch in CHOOSE.
  It looks for brief spectral outliers and gently attenuates them. You can run
  analysis only or listen to the removed audio to check what it's doing.
- A fix for Reference Auto-EQ stopping production when no reference was connected.

The cleanup is an experiment, not a magic “remove all AI artifacts” button.
It can catch wanted sounds too, so listening to the difference matters. It
starts on with Balanced sensitivity; you can turn it off independently of mastering.

And yes, **YuE2 Cover** is still there: upload a track, let SheetSage2 extract its
ABC score, and use that musical description to inform the cover prompt. Regular
YuE2 generation and **MiniMax Music 3** are available in the same workflow.

**Code + release:**
https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit/releases/tag/v3.0.1

If you try the cleanup or the YuE2 EQ presets, I'd love to hear where they help
and where they get in the way. That's the useful feedback for the next version.
