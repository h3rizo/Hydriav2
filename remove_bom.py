from pathlib import Path
path = Path('representants.json')
text = path.read_text(encoding='utf-8-sig')
path.write_text(text, encoding='utf-8')
