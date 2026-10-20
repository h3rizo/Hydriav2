import sys

file_path = r'C:\Users\Dir Soakoja\Documents\Formation appli web\hydria nuxt django\backend\templates\accounting\etat_taxe_communale.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Bloc à supprimer
org_filter_block = """                <div class="form-control">
                    <label class="label"><span class="label-text">Organisation</span></label>
                    <select name="organisation_id" id="organisation-select" class="select select-bordered">
                        <option value="">Toutes les organisations</option>
                        {% for organisation in organisations %}
                        <option value="{{ organisation.id }}" {% if selected_organisation_id == organisation.id|stringformat:"s" %}selected{% endif %}>
                            {{ organisation.nom_organisation }}
                        </option>
                        {% endfor %}
                    </select>
                </div>"""

if org_filter_block in content:
    content = content.replace(org_filter_block, "")
    print("Organization filter block removed.")
else:
    # Try a slightly different version if whitespace differs
    import re
    pattern = r'<div class="form-control">\s*<label class="label"><span class="label-text">Organisation</span></label>.*?</div>'
    content = re.sub(pattern, "", content, flags=re.DOTALL)
    print("Organization filter removed via regex fallback.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully simplified interface.")
