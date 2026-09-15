# Optional audio stage · Audio + reports

This switch bypasses a complete Refinement or Mastering section. It selects
processed audio when enabled and original audio when disabled, without changing
samples or sample rate itself.

Both audio inputs and the report inputs are lazy: a disabled stage does not run
just to provide metadata. Route all report consumers through this switch as in
the bundled dual-model workflow. An independent preview or output connected
directly inside the stage will still request that part of the graph.

Refinement report slots: FlashSR settings, PRE preset, PRE settings, POST preset,
POST settings, hybrid crossover, HF repair, declipping.
Mastering report slots: manual EQ, Auto-EQ, compressor, release preparation.
Disabled stages return explicit bypass records instead of stale settings.
