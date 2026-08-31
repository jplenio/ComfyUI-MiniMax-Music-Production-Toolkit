# Security Policy

## Supported version

Security fixes are applied to the latest released version.

## Reporting a vulnerability

Please do not publish a suspected security issue as a public proof-of-concept before the maintainer has had a reasonable opportunity to review it. Open a GitHub issue with minimal sensitive detail and request a private contact path if necessary:

https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit/issues

## Prompt-library note

`external_directory` reads prompt files from the filesystem of the machine running ComfyUI. Only configure directories you trust. The toolkit restricts selected files to `.txt`, `.md` and `.prompt`, rejects path traversal and ignores symlinks that resolve outside the selected library root.

As with ComfyUI generally, do not expose a local ComfyUI server to untrusted networks without appropriate access controls.
