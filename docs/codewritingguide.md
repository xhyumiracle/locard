## Code Writing Guidelines

- Prioritize readability, consistency, and reuse over cleverness.
- Keep abstractions shallow and purposeful:
  avoid both over-engineering (deep, fragmented helpers) and flat “waterfall” code.
- Encapsulate only when it improves structure or reuse, not just to reduce line count.
- Prefer clear data flow and explicit logic over implicit magic.

Comments

- Do not comment every function by default.
  Skip comments when the code is self-explanatory.
- Add comments only when they clarify non-obvious intent, constraints, or edge cases.
- Use concise English, no verbosity or narrative explanations.

General Style

- Optimize for future modification, not premature generality.
- Assume the reader is an experienced engineer, not a beginner.