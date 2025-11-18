import google.generativeai as genai
from app.config import settings

print("GOOGLE_API_KEY loaded from settings?")
print("  Present:", bool(settings.GOOGLE_API_KEY))
if settings.GOOGLE_API_KEY:
    print("  Prefix:", str(settings.GOOGLE_API_KEY)[:8], "Length:", len(settings.GOOGLE_API_KEY))

try:
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    print("Configured google.generativeai client.")

    models = list(genai.list_models())
    print(f"Found {len(models)} models:")
    for m in models:
        name = m.name
        methods = getattr(m, "supported_generation_methods", [])
        print(f"  {name}  ->  {methods}")

except Exception as e:
    print("ERROR while listing models:")
    print(repr(e))
