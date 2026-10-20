import os
path = r'C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\planning\views_simple.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = """        cursor = connection.cursor()
        cursor.execute(\"\"\"
        UPDATE plannings 
        SET estvalide = true
        WHERE id = %s
        \"\"\", [planning_id])"""

new = """        cursor = connection.cursor()
        validateur_id = getattr(request.user.employe, 'id', None) if hasattr(request.user, 'employe') else None
        
        cursor.execute(\"\"\"
        UPDATE plannings 
        SET estvalide = true,
            date_validation = NOW(),
            validateur_uuid_id = %s,
            updatedat = NOW()
        WHERE id = %s
        \"\"\", [validateur_id, planning_id])"""

if old in content:
    print("Found and replacing...")
    new_content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    print("Done!")
else:
    print("Not found!")
    # Try with \r\n just in case
    old_rn = old.replace('\n', '\r\n')
    if old_rn in content:
        print("Found with \\r\\n and replacing...")
        new_content = content.replace(old_rn, new.replace('\n', '\r\n'))
        with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
            f.write(new_content)
        print("Done!")
    else:
        print("Still not found!")
