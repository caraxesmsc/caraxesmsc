# Installing the profile

1. Rename the folder `_move-to-.github` to `.github`, then copy everything in this folder (README.md, assets/, scripts/, .github/) into the root of the public repo `caraxesmsc/caraxesmsc`, replacing the old README. Skip preview.html and the PNG; they are only for local viewing.
2. Push to `main`. The **Refresh contribution pulse** workflow runs once on push, then every day at 06:17 Cairo time, and commits a fresh `assets/pulse.svg`.
3. Check: repo → Settings → Actions → General → Workflow permissions must be **Read and write**.
4. Optional, but makes the number match your profile exactly: create a classic token with only the `read:user` scope and save it as the repo secret `PULSE_TOKEN`. Without it, the workflow reads your public contribution page, which shows the same total as long as "Private contributions" is on in your profile settings.

The bot commits use the github-actions identity, so they don't add to your own contribution count.

Test locally: `python3 scripts/build_pulse.py --out assets/pulse.svg` (standard library only).

All three SVGs respect "reduce motion": they show a still, final frame.
