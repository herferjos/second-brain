# Exocort capturers

Minimal runner that boots the audio and screen capturers defined in `exocort/configs/config.toml`.

1. Install dependencies (e.g., `pip install .`).
2. Adjust `exocort/configs/config.toml` to set `capturer.path` (relative to the directory where you run the runner) and configure the `[capturer.audio]` / `[capturer.screen]` sections for the destinations and capture settings you want.
3. Run:
   ```bash
   python -m exocort.runner --config exocort/config.toml
   ```
   or use the entry point `exocort` once the package is installed.

The runner starts only the enabled services, keeps their loops modular, and relies on the TOML file for configuration.
