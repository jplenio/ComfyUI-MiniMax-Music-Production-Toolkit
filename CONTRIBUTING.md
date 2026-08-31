# Contributing

Contributions are welcome.

## Before opening a pull request

1. Keep existing node class IDs backward compatible unless a breaking release explicitly requires otherwise.
2. Add a clear tooltip for every new required or optional input.
3. Add or update the corresponding file in `web/docs/`.
4. Do not add machine-specific paths, credentials, private prompts, personal metadata, model weights or generated audio binaries.
5. Keep audio processing conservative by default. New processing must provide a bypass path and should report its effective settings in JSON where practical.
6. Run:

```bash
python scripts/validate_release.py
python -m unittest discover -s tests -v
```

## Prompt contributions

Bundled prompt files belong under `prompts/user/<category>/` or `prompts/system/`. Use UTF-8 text and keep filenames descriptive and portable.

## Coding style

- Prefer explicit validation and user-facing error messages.
- Use `toolkit_logging.get_logger()` instead of `print()`.
- Avoid changing the user's global logging configuration.
- Keep third-party dependencies minimal and do not install/replace PyTorch from this package.
