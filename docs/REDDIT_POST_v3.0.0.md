# I know, another release already… but YuE2 cover songs were too exciting to sit on [ComfyUI Toolkit 3.0]

I only just added YuE2 to my Music Production Toolkit, and yes—I'm already back with 3.0. 😅

I got a little too excited about this one: **the first version of YuE2 audio covers is ready.**

You can now load an audio file, describe a new musical direction, and create a cover version inside the same ComfyUI workflow—with mastering, optional artwork and exports all connected. Regular YuE2 generation and MiniMax Music 3 are still there too.

The part I'm especially excited about is what happens to the prompt:

**Source audio → SheetSage2 → readable ABC score → LLM adapts the cover prompt → YuE2 generates the cover.**

ABC is a text format for musical notation. The LLM gets the ABC extracted from the source and uses it to plan the new arrangement. The original transcription also goes straight into YuE2. So the prompt can respond to the music's structure, rather than relying only on my description of it.

This is my first use of that open ABC description in the toolkit, and it already has me thinking about what else we could build around it. **More is in preparation.**

There are two source modes: melody + harmony, or melody with more freedom for a new accompaniment. I've also expanded the YuE2 system prompts so Style and Lyrics are asked to follow the same developed section structure—especially useful for instrumentals.

One practical detail: SheetSage2 transcribes music, not the original lyric words. Bring your own lyrics, ask for new ones, or go instrumental.

It's an initial implementation, and I'd love to hear what works—and what needs improving. What would you try first: a genre swap, an instrumental reinterpretation, or a new arrangement of one of your own tracks?

**Workflow, setup and source:** [Music Production Toolkit on GitHub](https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit)
