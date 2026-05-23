# TODO

## Dashboard controls

- Add a web UI control surface for backend lifecycle actions:
  - show Codex login status
  - start the hourly loop
  - stop the loop and dashboard
  - trigger a one-shot run for debugging
  - show the current decision source (`codex` vs fallback)
- Keep the controls simple and explicit so the page stays demo-friendly.

## Clean shutdown

- Add a dedicated shutdown action to the app so the dashboard can request a graceful stop without manual terminal steps.
- Make sure both the dashboard server and the background loop honor the same stop signal.
- Document the shutdown path in the README and keep it synced with the code.

## Nice-to-have

- Show the last successful login/check timestamp on the homepage.
- Surface the current runtime mode (`market_hours` vs `always_on`) next to the controls.
