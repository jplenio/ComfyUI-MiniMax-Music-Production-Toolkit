# Cover song · SheetSage2 transcription

Expands native LoadAudio, AudioEncoderLoader and SheetSage2AudioToABC only when
**YuE2 Cover** is selected. The model-check report input ensures configured
downloads finish before the encoder is loaded. Other models return an empty
string without loading source audio or SheetSage2.

Connect `cover_abc` to Structured Song Prompt and Generate song. The LLM uses
the score to plan an arrangement; the native generator receives the original
ABC unchanged. No new ABC is generated in this mode. SheetSage2 extracts music,
not the original sung words. Supply desired lyrics in the brief or parser's
manual inputs. An empty transcription stops the cover run with an error.
