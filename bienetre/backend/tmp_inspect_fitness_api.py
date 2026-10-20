import json
from pathlib import Path

from django.contrib.auth.models import User
from rest_framework.test import APIClient


user = User.objects.filter(username="admin_bienetre").first()
if user is None:
    raise SystemExit("admin_bienetre introuvable")

client = APIClient()
client.force_authenticate(user)

paths = {
    "cycle": "/api/v1/fitness/workout-plans/cycle/",
    "today": "/api/v1/fitness/workout-plans/today/",
    "today_session": "/api/v1/fitness/workout-plans/today-session/",
    "history": "/api/v1/fitness/workout-sessions/",
}

dump_dir = Path("/tmp/bienetre_fitness_responses")
dump_dir.mkdir(parents=True, exist_ok=True)

for name, path in paths.items():
    response = client.get(path, HTTP_HOST="bienetre.hydria.mg")
    data = response.data
    (dump_dir / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    if name == "cycle":
        sample = {
            "plan": data.get("plan"),
            "first_week": data.get("weeks", [None])[0] if data.get("weeks") else None,
        }
        if sample["first_week"] and sample["first_week"].get("items"):
            sample["first_week"]["items"] = sample["first_week"]["items"][:1]
    elif name == "today":
        sample = dict(data)
        sample["items"] = sample.get("items", [])[:1]
    elif name == "history":
        sample = data[:1] if isinstance(data, list) else data
    else:
        sample = data
    print(f"### {name} status={response.status_code} root={type(data).__name__}")
    print(json.dumps(sample, ensure_ascii=False, default=str, indent=2))
