"""
Talks to LM Studio's local OpenAI-compatible server.
No API key, no internet call -- everything stays on your machine.
"""

import json
import requests

SYSTEM_PROMPT = """You are a Kubernetes SRE assistant. You will be shown a diff \
representing configuration drift between the live cluster state and the \
Git-declared desired state (produced by `argocd app diff`).

Classify the drift and respond with STRICT JSON only, no markdown, no prose \
outside the JSON, in this exact shape:

{
  "severity": "safe" | "risky",
  "summary": "one or two plain-English sentences explaining what changed",
  "reasoning": "one sentence on why you classified it this way"
}

Guidance for classification:
- "safe": cosmetic/non-functional changes -- labels, annotations, comments,
  ordering differences that don't affect behavior.
- "risky": anything that could affect availability, security, or correctness --
  replica count changes, deleted resources, image tag changes, resource
  limits/requests changes, RBAC/secret changes, changed env vars, changed
  ports or service selectors.

When in doubt, classify as "risky" -- a human reviewing an unnecessary alert
costs far less than an agent silently applying a bad change.
"""


def classify_drift(diff_text: str, lm_studio_url: str, model: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the drift diff:\n\n{diff_text}"},
        ],
        "temperature": 0.1,  # low temperature: we want consistent classification, not creativity
    }

    response = requests.post(lm_studio_url, json=payload, timeout=60)
    response.raise_for_status()

    raw_content = response.json()["choices"][0]["message"]["content"].strip()

    # Local models sometimes wrap JSON in markdown fences despite instructions -- strip defensively
    if raw_content.startswith("```"):
        raw_content = raw_content.strip("`")
        if raw_content.startswith("json"):
            raw_content = raw_content[4:].strip()

    try:
        result = json.loads(raw_content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM did not return valid JSON. Raw output was:\n{raw_content}"
        ) from e

    # Defensive default: if the model produces something outside {safe, risky}, treat as risky
    if result.get("severity") not in ("safe", "risky"):
        result["severity"] = "risky"
        result["reasoning"] = result.get("reasoning", "") + " (defaulted to risky: unrecognized severity value)"

    return result
