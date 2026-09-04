# agentic_rpa — Design Notes

LLM-driven desktop automation: an agent that observes a screen and drives GUI actions (clicks, keystrokes) to complete a task, run headlessly and at scale.

## Stack

- **Xvfb** — virtual framebuffer so the GUI automation has a display to render to on a headless Linux host.
- **PyAutoGUI + Tesseract (pytesseract)** — PyAutoGUI performs the mouse/keyboard actions; Tesseract OCR reads on-screen text so the agent can locate things PyAutoGUI's image-matching alone can't find.
- **Celery** — async task queue for running RPA jobs off the request path and scaling workers horizontally.
- **FastAPI + LangChain** — API layer and the LLM agent loop that decides what actions to take.

## Gaps / Open Questions

1. **Celery broker/backend unspecified** — needs a broker (Redis or RabbitMQ) and a result backend chosen.
2. **No action-grounding schema** — how do LangChain's decisions become concrete PyAutoGUI calls? Needs a defined tool-calling schema and action space (e.g. `click(x, y)`, `type(text)`, `read_screen()`).
3. **OCR grounding is fragile** — Tesseract text-matching breaks on font, theme, resolution, or DPI changes. Consider vision-model-based screenshot grounding (feeding screenshots directly to a multimodal LLM) as a more robust alternative, at higher per-step cost.
4. **No worker isolation story** — each Celery worker driving its own PyAutoGUI/Xvfb session needs an isolated `DISPLAY` (e.g. `:1`, `:2`, ...) so concurrent workers don't collide on the same virtual screen.
5. **No state/retry strategy** — undefined how a job tracks step-by-step progress, detects a stuck/failed step, and retries or escalates.
6. **No LLM provider chosen** — LangChain is an orchestration framework, not a model; needs a stated model (and whether it needs vision support, given point 3).
