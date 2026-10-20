import os
path = r'C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\apps\planning\views_simple.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix validate function
old_validate = """        validateur_id = getattr(request.user.employe, 'id', None) if hasattr(request.user, 'employe') else None
        
        cursor.execute(\"\"\"
        UPDATE plannings 
        SET estvalide = true,
            date_validation = NOW(),
            validateur_uuid_id = %s,
            updatedat = NOW()
        WHERE id = %s
        \"\"\", [validateur_id, planning_id])"""

new_validate = """        cursor.execute(\"\"\"
        UPDATE plannings 
        SET estvalide = true,
            updated_at = NOW()
        WHERE id = %s
        \"\"\", [planning_id])"""

# Fix unvalidate function
old_unvalidate = """        cursor.execute(\"\"\"
            UPDATE plannings
            SET estvalide = FALSE, date_validation = NULL, validateur_uuid_id = NULL, updatedat = NOW()
            WHERE id = %s
        \"\"\", [id])"""

new_unvalidate = """        cursor.execute(\"\"\"
            UPDATE plannings
            SET estvalide = FALSE, updated_at = NOW()
            WHERE id = %s
        \"\"\", [id])"""

if old_validate in content:
    print("Found validate block...")
    content = content.replace(old_validate, new_validate)

if old_unvalidate in content:
    print("Found unvalidate block...")
    content = content.replace(old_unvalidate, new_unvalidate)

with open(path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
print("Done!")
