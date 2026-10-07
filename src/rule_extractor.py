import os
import sys
import json
import argparse
from typing import List, Dict, Any, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Re-use utilities from extractor
from src.extractor import (
    get_azure_openai_client,
    load_file,
    call_model,
    parse_json_response,
    save_json_output,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
)

DEFAULT_RULE_TEMPLATE_PATH = "docs/file_formats/rule_extraction_prompt.md"


def construct_rule_extraction_prompt(template_text: str, policies: List[Dict[str, Any]]) -> str:
    """Inject policies JSON into the LTL rule extraction prompt."""
    policies_json = json.dumps(policies, indent=2)
    
    full_prompt = (
        f"{template_text.strip()}\n\n"
        f"---\n"
        f"## Extracted Policies for Translation:\n\n"
        f"```json\n"
        f"{policies_json}\n"
        f"```\n\n"
        f"Extract all verifiable LTL rules from the policies above and output them strictly in the required JSON format."
    )
    return full_prompt


def run_rule_extraction(
    input_path: str,
    output_path: str,
    prompt_template_path: str = DEFAULT_RULE_TEMPLATE_PATH,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    dry_run: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """Pipeline to translate structured policies into LTL rules."""
    
    print(f"Loading policies from: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        policies = json.load(f)
        
    print(f"Loading prompt template: {prompt_template_path}")
    template_text = load_file(prompt_template_path)
    
    prompt = construct_rule_extraction_prompt(template_text, policies)
    
    if dry_run:
        print(f"Dry-run mode: Skipping API call. Saving assembled prompt to {output_path}")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        return None
        
    print(f"Initializing Azure OpenAI client for model: {model}")
    client = get_azure_openai_client(endpoint=endpoint)
    
    print("Calling LLM for LTL rule extraction...")
    raw_response = call_model(client, prompt, model=model)
    
    print("Parsing model output into JSON...")
    parsed_json = parse_json_response(raw_response)
    
    print(f"Saving extracted LTL rules to: {output_path}")
    save_json_output(parsed_json, output_path)
    print(f"Successfully extracted {len(parsed_json)} LTL rules.")
    return parsed_json


def main():
    parser = argparse.ArgumentParser(description="ShieldAgent LTL Rule Extractor")
    parser.add_argument("--input-path", required=True, help="Path to input extracted policies JSON")
    parser.add_argument("--output-path", required=True, help="Path to save output LTL rules JSON")
    parser.add_argument("--template-path", default=DEFAULT_RULE_TEMPLATE_PATH, help="Path to rule extraction prompt template")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model deployment name")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Azure OpenAI endpoint")
    parser.add_argument("--dry-run", action="store_true", help="Assemble prompt and save to output-path without calling LLM")
    
    args = parser.parse_args()
    
    run_rule_extraction(
        input_path=args.input_path,
        output_path=args.output_path,
        prompt_template_path=args.template_path,
        model=args.model,
        endpoint=args.endpoint,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
