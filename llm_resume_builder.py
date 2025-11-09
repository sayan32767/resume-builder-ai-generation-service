import requests
import json
import default_schema
import re
import os
from dotenv import load_dotenv

load_dotenv()

HF_API_KEY = os.getenv("HF_API_KEY")

MODEL_URL = os.getenv("MODEL_URL")

HEADERS = {
    "Authorization": f"Bearer {HF_API_KEY}",
    "Content-Type": "application/json",
}


def call_hf_api(prompt: str) -> str:
    payload = {
        "model": "Qwen/Qwen3-1.7B:featherless-ai",

        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a JSON generator. "
                    "Do NOT output <think> or reasoning steps. "
                    "Output ONLY valid JSON. Never include explanations."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    response = requests.post(MODEL_URL, headers=HEADERS, json=payload)
    result = response.json()

    # print("\n--- HF RAW RESPONSE ---\n", result, "\n------------------------\n")

    # OpenAI-style / HF-chat style
    if isinstance(result, dict):
        if "choices" in result:
            raw_content = result["choices"][0]["message"]["content"]

            # SAVE EXACT RAW OUTPUT FOR DEBUG
            # with open("last_hf_output.txt", "w", encoding="utf-8") as f:
            #     f.write(raw_content)

            return raw_content
        if "generated_text" in result:
            return result["generated_text"]

    # Some models return list of generations
    if isinstance(result, list):
        first = result[0]
        if isinstance(first, dict) and "generated_text" in first:
            return first["generated_text"]

    raise ValueError("Unexpected HF response format from HuggingFace.")


# def safe_json_extract(text: str):
#     start = text.find("{")
#     end = text.rfind("}")

#     if start == -1 or end == -1:
#         raise ValueError("No JSON object found in output.")

#     json_str = text[start:end + 1]

#     json_str = json_str.replace(",}", "}").replace(", ]", "]")

#     return json.loads(json_str)


def safe_json_extract(text: str):
    raw = text.rstrip()

    # STEP 1 — Fix unterminated string
    unescaped_quotes = len(re.findall(r'(?<!\\)"', raw))
    if unescaped_quotes % 2 == 1:
        raw += '"'

    # STEP 2 — Now close object + array + root
    # This exact ordering matches your working manual fix
    fix = ""

    opens_curly = raw.count("{")
    closes_curly = raw.count("}")

    opens_square = raw.count("[")
    closes_square = raw.count("]")

    # Close one object if needed
    if closes_curly < opens_curly:
        fix += "}"

    # Close one array if needed
    if closes_square < opens_square:
        fix += "]"

    # Close final root object if still unbalanced
    opens_curly = raw.count("{")
    closes_curly = raw.count("}") + fix.count("}")

    if closes_curly < opens_curly:
        fix += "}"

    raw += fix

    # STEP 3 — Parse
    try:
        return json.loads(raw)
    except Exception as e:
        print("FAILED AGAIN:", e)
        print("RAW END:\n", raw[-500:])
        return {}


def sanitize_value(key, value):
    """Field-specific cleanup logic."""

    # --- Fix percentile like "96%" → "96"
    if key == "score" and isinstance(value, str):
        return value.replace("%", "").strip()

    # --- Fix ISO date "2022-08" → "2022-08-01"
    if key in ("startDate", "endDate", "issueDate") and isinstance(value, str):
        if len(value) == 7:  # "YYYY-MM"
            return value + "-01"
        return value

    # --- Fix wrong list types
    if key in ("socials", "links") and not isinstance(value, list):
        return []

    # --- skillName must be string
    if key == "skillName":
        return value if isinstance(value, str) else ""

    return value


def enforce_schema_format(data, schema, current_key=None):
    """
    Recursively enforces `data` to match EXACT shape of `schema`.
    Applies sanitization with the CORRECT field key.
    """

    # ---------------------------
    # Case: DICTIONARY
    # ---------------------------

    if isinstance(schema, dict):

        if not isinstance(data, dict):
            data = {}

        result = {}

        for key, schema_value in schema.items():

            if key not in data:
                result[key] = schema_value
                continue

            raw_value = data[key]

            # Primitive type → sanitize
            if not isinstance(schema_value, (dict, list)):
                cleaned = sanitize_value(key, raw_value)

                # Wrong primitive type → fallback to default
                if schema_value is not None and type(cleaned) != type(schema_value):
                    cleaned = schema_value

                result[key] = cleaned
                continue

            # RECURSE for nested object/list
            result[key] = enforce_schema_format(raw_value, schema_value, current_key=key)

        return result


    # ---------------------------
    # Case: LIST
    # ---------------------------
    elif isinstance(schema, list):

        if not isinstance(data, list):
            return []

        if len(schema) == 0:
            return [item for item in data if isinstance(item, (dict, str))]

        item_schema = schema[0]

        cleaned_items = []
        for item in data:
            if isinstance(item, dict):
                cleaned_items.append(enforce_schema_format(item, item_schema))

        return cleaned_items


    # ---------------------------
    # Case: PRIMITIVE
    # ---------------------------
    else:
        # NOW we pass the correct key!
        cleaned = sanitize_value(current_key, data)

        # Type mismatch → use default
        if schema is not None and type(cleaned) != type(schema):
            return schema

        return cleaned


def deep_clean(obj):
    """
    Recursively remove:
    - empty strings ""
    - empty lists []
    - empty dicts {}
    - None values
    """

    # --- Case 1: Dict ---
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            cleaned_value = deep_clean(v)

            # Skip empty, null, blank
            if cleaned_value in ("", None, [], {}):
                continue

            cleaned[k] = cleaned_value

        return cleaned

    # --- Case 2: List ---
    if isinstance(obj, list):
        cleaned_list = [deep_clean(i) for i in obj]
        cleaned_list = [i for i in cleaned_list if i not in ("", None, [], {})]

        return cleaned_list

    # --- Case 3: String ---
    if isinstance(obj, str):
        return obj.strip()  # trim spaces

    # --- Primitive (int, bool, float, etc.) ---
    return obj


def generate_resume_schema(pdf_text):
    prompt = f"""
You MUST output ONLY valid JSON.  
NO text. NO explanation. NO markdown. NO tags.  

Your output MUST EXACTLY match this structure and include EVERY field:

{{
  "resumeTitle": "",
  "resumeType": "Classic",
  "personalDetails": {{
    "fullName": "",
    "email": "",
    "phone": "",
    "address": "",
    "about": "",
    "socials": []
  }},
  "educationDetails": [
    {{
      "name": "",
      "degree": "",
      "dates": {{
        "startDate": null,
        "endDate": null
      }},
      "location": "",
      "grades": {{
        "type": null,
        "score": "",
        "message": ""
      }}
    }}
  ],
  "skills": [
    {{
      "skillName": ""
    }}
  ],
  "professionalExperience": [
    {{
      "companyName": "",
      "companyAddress": "",
      "position": "",
      "dates": {{
        "startDate": null,
        "endDate": null
      }},
      "workDescription": ""
    }}
  ],
  "projects": [
    {{
      "title": "",
      "description": "",
      "extraDetails": "",
      "links": [
        {{
          "link": ""
        }}
      ]
    }}
  ],
  "otherExperience": [
    {{
      "companyName": "",
      "companyAddress": "",
      "position": "",
      "dates": {{
        "startDate": null,
        "endDate": null
      }},
      "workDescription": ""
    }}
  ],
  "certifications": [
    {{
      "issuingAuthority": "",
      "title": "",
      "issueDate": null,
      "link": ""
    }}
  ]
}}

STRICT RULES:
- NEVER omit any field.
- If information is missing, leave empty string "" or null.
- NEVER merge multiple items (e.g., NO "Programming Languages").
- skills MUST be single items only: {{ "skillName": "Python" }}.
- socials MUST follow: {{ "name": "LINKEDIN" | "INSTAGRAM" | "GITHUB", "link": "" }}.
- dates MUST be ISO date ("2022-08-01") or null.
- certifications MUST include all 4 fields, even if blank.
- DO NOT add fields. DO NOT remove fields. DO NOT rename fields.

PDF DATA:
{pdf_text}

Return ONLY the JSON object. NOTHING else.
"""

    output = call_hf_api(prompt)
    # print("=======output======\n\n")
    # print(output)
    

    raw = safe_json_extract(output)

    # print("=======raw======\n\n")
    # print(raw)
    
    # Enforce schema & fix any missing/wrong fields
    normalized = enforce_schema_format(raw, default_schema.DEFAULT_SCHEMA)

    cleaned = deep_clean(normalized)

    return cleaned
    
    # with open("last_hf_output.txt", "r", encoding="utf-8") as f:
    #     output = f.read()

    # raw = safe_json_extract(output)

    # print('==================================')
    # print(raw)

    # normalized = enforce_schema_format(raw, default_schema.DEFAULT_SCHEMA)

    # return normalized
