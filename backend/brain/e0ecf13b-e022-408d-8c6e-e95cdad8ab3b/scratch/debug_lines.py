import os
path = r'C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\planning\views_simple.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

target_lines = lines[1423:1428] # 1424 to 1428 (0-indexed)
for i, line in enumerate(target_lines):
    print(f"Line {1424+i}: {repr(line)}")
