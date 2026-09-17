# Instrumental check · keep least vocal take

Keeps the first candidate whose transcript contained no more words than the
tolerance, and asks ComfyUI for the next one only when the previous take
contained words.

Every candidate input is declared lazy, so a clean first render costs **one**
generation, not eleven. The retries only happen when they are needed.

`max_retries` accepts 0 to 10. When no take reaches the tolerance, the take with
the **fewest recognised words** is used for the rest of the chain and the other
candidate files are deleted — the word counts were already measured, so handing
back whichever take happened to be last would throw that measurement away. Equal
counts keep the earliest take. A long unattended run therefore always ends with
audio rather than an error, and the log carries a warning naming the outcome.

## Candidate files

Each take is written to its own temporary WAV while the run is in progress, so a
take can be auditioned later:

```text
<system temp>/mmt-instrumental-check/<take-N>-<random>/candidate.wav
```

The kept file stays after the run; the others are removed by this node. If a run
is cancelled before the selection node executes, leftovers are pruned the next
time the check runs (directories older than 24 hours). The audio that continues
downstream is the winner's original float data, not the 16-bit temporary copy.

The report records every attempt, the words and transcript of each, the kept
take, the kept file path and whether the budget was exhausted; it is stored in
the generation record as `instrumental_check_result`.

This node is created inside the generation expansion. Switch the feature on with
**instrumental vocal check** in Music settings; it only applies to YuE2
instrumental covers. See
[Instrumental check · words heard](MiniMaxInstrumentalVocalCheck.md).
