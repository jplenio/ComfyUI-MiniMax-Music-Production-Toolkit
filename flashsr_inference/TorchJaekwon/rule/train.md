# Training code rules

Reusable, tool-agnostic rules for writing and reviewing training code.

How to use: when asked to "evaluate / review the current training code", treat
each rule below as a checklist and report, item by item, what is present, what
is missing, and where. When writing new training code, satisfy every rule that
applies.

Structure: `##` is a big category, `###` is a specific rule inside it. Numbers
(e.g. "1.2") are stable handles so you can say "check rule 1.2". Add new big
categories as `## 2.`, `## 3.`, ... (suggested future ones at the bottom).

---

## 1. Resume & checkpointing

A run is *resumable* only if restarting from a checkpoint reproduces (near) the
same trajectory as if it had never stopped.

### 1.1 What must be saved AND loaded

Save **and** restore every piece of state below. A checkpoint that saves
weights only is NOT resumable. For each item, verify it is **both** written at
save time **and** read back at load time — saving without loading (or vice
versa) is a common bug.

| State to persist | Symptom if it is missing on resume |
|---|---|
| Model weights | Nothing resumes. |
| Optimizer state (Adam moments, SGD momentum) | Adaptive optimizers spike / diverge when moments reset to zero. |
| LR scheduler state (`last_epoch` / step) | Wrong learning rate after resume → instability or wasted schedule. |
| AMP / grad-scaler state | Loss scale restarts → first steps may overflow / underflow. |
| Global step + epoch + samples-consumed counter | Off-by-epoch logging, wrong LR phase, wrong stopping point. |
| RNG states (python `random`, numpy, torch CPU + CUDA) | Non-reproducible dropout / augmentation / shuffling across the restart. |
| **Dataloader / sampler state** | Data stream restarts mid-epoch → samples replayed (over-weighted) and the rest skipped. See 1.2. |
| EMA weights (if used) | Eval-quality regression after resume. |
| Best-metric / early-stopping counters | Checkpoint selection and early-stop logic silently reset. |

### 1.2 Dataloader / sampler state (the most commonly forgotten one)

Naive resume restarts the dataloader at the beginning of the current epoch. The
already-seen part of the epoch is replayed (over-weighted in training) and the
remainder is skipped. To resume the data stream correctly:

- **Persist position, not order.** Save the sampler's consumed-batch / epoch
  counters, not the full shuffled sequence. Regenerate the shuffle
  deterministically from `(seed, epoch, rank, worker_id)`.
- **Handle `num_workers > 0` with iterable datasets.** The sampler then lives
  inside worker subprocesses and is unreachable from the main process. Use a
  stateful dataloader that snapshots and restores per-worker state
  (e.g. `torchdata.StatefulDataLoader`).
- **Guard against topology changes.** The stream is a function of
  `(seed, world_size, num_workers)` plus the consumed count. If any of those
  differ on resume, "resume to the same position" is undefined. Store a
  fingerprint of these knobs and, on mismatch, fall back to a fresh reshuffle
  **with a warning** instead of restoring a meaningless position.
- **Multi-rank is fine from a single snapshot.** In lockstep data-parallel
  training every rank consumes the same number of batches, and per-worker counts
  are identical across ranks. Only counts + epoch + seed need saving, so a single
  rank-0 snapshot can restore all ranks; each rank regenerates its own shuffle
  locally from its `(rank, worker_id)` seed.

Reference implementation: `stateful_resume` in the NeMo/Lhotse pipeline of the
`ntd` project.

### 1.3 Verifying resume actually works

Don't trust that resume works because it doesn't crash. Verify it:

- Save a checkpoint **mid-epoch**, resume, and confirm: step/epoch continue from
  where they stopped, the learning rate matches the pre-stop value, and the data
  stream does **not** restart from the epoch boundary.
- Quick data check: log the first N sample IDs after resume; they should be the
  continuation of the stream, not a replay of the epoch's start.
- Acceptable tolerance: with background prefetching / `concurrent_bucketing`,
  resume is near-exact (a few boundary samples), not bit-exact. That is fine for
  training. Bit-exact replay is generally not achievable and not the goal.

---

<!--
Future big categories (add as needed, keep the numbered ##/### structure):

## 2. Reproducibility & seeding
## 3. Distributed / multi-GPU (DDP / FSDP)
## 4. Mixed precision (AMP / bf16)
## 5. Logging, metrics & validation
## 6. Performance & throughput (dataloading, profiling)
-->
