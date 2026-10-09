import os
import sys
import json
import re
import argparse
from typing import List, Dict, Any, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.extractor import (
    get_azure_openai_client,
    load_file,
    call_model,
    save_json_output,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
)

DEFAULT_VR_TEMPLATE_PATH = "docs/file_formats/vr_prompt.md"


def construct_vr_prompt(template_text: str, rules_data: List[Dict[str, Any]]) -> str:
    """Inject LTL rules into the Verifiability Refinement prompt template."""
    rules_json = json.dumps(rules_data, indent=2)
    
    full_prompt = (
        f"{template_text.strip()}\n\n"
        f"---\n"
        f"## Current LTL Rules & Predicates for Verifiability Refinement:\n\n"
        f"```json\n"
        f"{rules_json}\n"
        f"```\n\n"
        f"Perform Verifiability Refinement (VR) across the predicates and rules above. "
        f"Refine vague or compound predicates to be atomic and directly verifiable by an agent. "
        f"Prune non-actionable descriptive facts (e.g. database timezone definitions). "
        f"Ensure consistent logical implication syntax ('IMPLIES'). "
        f"Provide your step-by-step reasoning, Decision: Yes, and the final refined rules strictly "
        f"in the specified JSON format with key 'rules'."
    )
    return full_prompt


def parse_vr_json_response(raw_text: str) -> Dict[str, Any]:
    """Parse JSON containing {'rules': [...]} from model response."""
    text = raw_text.strip()
    
    # 1. Look for ```json { ... } ``` block
    json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_block:
        text = json_block.group(1).strip()
    else:
        # 2. Look for outer { and }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1].strip()
        else:
            # 3. Fallback: check if an array was returned instead
            first_bracket = text.find("[")
            last_bracket = text.rfind("]")
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                array_text = text[first_bracket : last_bracket + 1].strip()
                arr = json.loads(array_text)
                return {"rules": arr}
    
    data = json.loads(text)
    if isinstance(data, list):
        data = {"rules": data}
    elif not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"Expected JSON object with 'rules' key, got keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
    
    return data


def run_vr_refinement(
    input_path: str,
    output_path: str,
    prompt_template_path: str = DEFAULT_VR_TEMPLATE_PATH,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """End-to-end Verifiability Refinement pipeline."""
    print(f"Loading raw LTL rules from: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        rules_data = json.load(f)
    
    # If wrapped in dict, extract list
    if isinstance(rules_data, dict) and "rules" in rules_data:
        rules_data = rules_data["rules"]
        
    print(f"Loading VR prompt template: {prompt_template_path}")
    template_text = load_file(prompt_template_path)
    
    prompt = construct_vr_prompt(template_text, rules_data)
    
    if dry_run:
        print(f"Dry-run mode: Skipping API call. Saving assembled prompt to {output_path}")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        return None
        
    print(f"Initializing Azure OpenAI client for model: {model}")
    client = get_azure_openai_client(endpoint=endpoint)
    
    print("Calling LLM for Verifiability Refinement (VR)...")
    raw_response = call_model(client, prompt, model=model)
    
    print("Parsing model output into JSON...")
    parsed_json = parse_vr_json_response(raw_response)
    
    print(f"Saving refined rules to: {output_path}")
    save_json_output(parsed_json, output_path)
    num_rules = len(parsed_json.get("rules", []))
    print(f"Successfully refined into {num_rules} verifiable rules.")
    return parsed_json


def main():
    parser = argparse.ArgumentParser(description="ShieldAgent Verifiability Refiner (VR)")
    parser.add_argument("--input-path", required=True, help="Path to input raw LTL rules JSON")
    parser.add_argument("--output-path", required=True, help="Path to save refined rules JSON")
    parser.add_argument("--template-path", default=DEFAULT_VR_TEMPLATE_PATH, help="Path to VR prompt template")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model deployment name")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Azure OpenAI endpoint")
    parser.add_argument("--dry-run", action="store_true", help="Assemble prompt and save without API call")
    
    args = parser.parse_args()
    
    run_vr_refinement(
        input_path=args.input_path,
        output_path=args.output_path,
        prompt_template_path=args.template_path,
        model=args.model,
        endpoint=args.endpoint,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
