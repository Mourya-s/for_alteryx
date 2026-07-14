import json
import os
from google import genai

print("USING NEW FILE")
print("FILE =", os.path.abspath(__file__))

# Gemini API Key

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


# Read workflow JSON
with open("generated/workflow.json", "r", encoding="utf-8") as f:
    workflow = json.load(f)

# Prompt
prompt = f"""
Return ONLY a valid JSON object.

Do not explain.
Do not add markdown.
Do not add ```json.
Do not add any text before or after.

Schema:

{{
  "pyspark_code": "",
  "databricks_yml": "",
  "jobs_yml": ""
}}

Workflow:
{json.dumps(workflow, indent=2)}
"""

# Call Gemini
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
)

# Save raw response
with open("generated/llm_output.txt", "w", encoding="utf-8") as f:
    f.write(response.text)

print("LLM output saved.")

print("GEMINI RESPONSE:")
print(response.text)

# Parse returned JSON
json_text = response.text.strip()

if json_text.startswith("```json"):
    json_text = json_text.replace("```json", "", 1)

if json_text.endswith("```"):
    json_text = json_text[:-3]

json_text = json_text.strip()

print("PARSED RESPONSE:")
print(json_text)

result = json.loads(json_text)

# Generate files
os.makedirs("generated/src", exist_ok=True)
os.makedirs("generated/resources", exist_ok=True)

with open("generated/src/workflow.py", "w", encoding="utf-8") as f:
    f.write(result["pyspark_code"])

with open("generated/databricks.yml", "w", encoding="utf-8") as f:
    f.write(result["databricks_yml"])

with open("generated/resources/jobs.yml", "w", encoding="utf-8") as f:
    f.write(result["jobs_yml"])

print("Generated:")
print("  generated/src/workflow.py")
print("  generated/databricks.yml")
print("  generated/resources/jobs.yml")
