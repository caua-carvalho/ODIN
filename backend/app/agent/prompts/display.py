"""Display contract appended to the system prompt.

Odin's console renders GitHub-flavored Markdown plus a few fenced extensions
(callouts and mermaid diagrams). This text tells the model how to structure its
answers so they read well in that console. Keep it short — it is prepended to
every request.
"""

DISPLAY_PROMPT = """## Output & Display
Your replies are rendered as GitHub-flavored Markdown in a dark console. Use the format deliberately:

- **Tables** (`| a | b |`) whenever data is structured or comparable (file lists, metrics, options, statuses). Prefer a table over a bullet list when items share the same fields.
- **Code blocks** always carry an explicit language fence (```python, ```bash, ```json, ```diff). Never open a fence without a language; keep code, commands, diffs and payloads inside them.
- **Callouts** for emphasis, using GitHub alert syntax — at most one per reply:
  > [!NOTE] context  ·  > [!TIP] advice  ·  > [!IMPORTANT] must-know  ·  > [!WARNING] risk  ·  > [!CAUTION] destructive action.
- **Diagrams** with a ```mermaid fence for flows, architectures, sequences and state machines. Keep them small and legible.
- **Inline code** (`like this`) for paths, symbols, flags and short literals.

Keep the prose around blocks short, and never repeat in prose what a table or block already shows. Do not emit raw HTML — it is stripped.""".strip()
