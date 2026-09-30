# AGENTS.md

Las instrucciones para asistentes de código (Codex, Cursor, Claude Code y otros) están en **[CLAUDE.md](CLAUDE.md)**:
cómo se instala, cómo se prueba sin navegador, cómo está hecho y qué reglas no se rompen.

Lo mínimo:

```bash
python -m venv .venv && . .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                            # y la persona pone su OPENROUTER_API_KEY
python app.py                                   # http://127.0.0.1:8765
```

⛔ La clave de OpenRouter nunca va en el código, en un commit ni en un log.
