import pathlib
path = pathlib.Path('representants.json')
lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
start = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped == '[' or stripped.startswith('{'):
        start = i
        break
path.write_text(''.join(lines[start:]), encoding='utf-8')
