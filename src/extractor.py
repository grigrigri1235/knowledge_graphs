import os
import sys
import json
import re
import argparse
from typing import List, Dict, Any, Optional
from openai import OpenAI
from azure.identity import ManagedIdentityCredential, get_bearer_token_provider

DEFAULT_ENDPOINT = "https://aif-poc-sdc-tiit-trust01.services.ai.azure.com/openai/v1"
DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_SCOPE = "https://ai.azure.com/.default"
DEFAULT_TEMPLATE_PATH = "docs/file_formats/policy_extraction_prompt.md"


def get_azure_openai_client(
    endpoint: str = DEFAULT_ENDPOINT,
    scope: str = DEFAULT_SCOPE,
) -> OpenAI:
    """Initialize Azure OpenAI client using Managed Identity."""
    credential = ManagedIdentityCredential()
    token_provider = get_bearer_token_provider(credential, scope)
    client = OpenAI(
        base_url=endpoint,
        api_key=token_provider,
    )
    return client


def load_file(file_path: str) -> str:
    """Read and return text content of a file, stripping YAML frontmatter if present."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Strip YAML frontmatter (lines between --- and --- at the start of the file)
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].strip()
    return content


def construct_policy_extraction_prompt(
    template_text: str,
    doc_text: str,
    organization: str = "GitLab",
) -> str:
    """Inject organization and document content into the extraction prompt template."""
    prompt = template_text.replace("{organization (e.g. GitLab)}", organization)
    prompt = prompt.replace("{organization}", organization)
    
    full_prompt = (
        f"{prompt.strip()}\n\n"
        f"---\n"
        f"## Organization Handbook Document Content:\n\n"
        f"```markdown\n"
        f"{doc_text.strip()}\n"
        f"```\n\n"
        f"Extract all actionable policies following the guidelines and JSON format specified above."
    )
    return full_prompt


def call_model(
    client: OpenAI,
    prompt: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Execute model call using OpenAI responses API."""
    response = client.responses.create(
        model=model,
        input=prompt,
    )
    return response.output_text


def parse_json_response(raw_text: str) -> List[Dict[str, Any]]:
    """Extract and parse JSON array from raw model response text."""
    text = raw_text.strip()
    
    # Check for markdown code fences (```json ... ``` or ``` ... ```)
    json_block_match = re.search(r"```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```", text, re.DOTALL)
    if json_block_match:
        text = json_block_match.group(1).strip()
    else:
        # Alternatively find first [ and last ]
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            text = text[first_bracket : last_bracket + 1].strip()
    
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of policies, got {type(data).__name__}")
    return data


def save_json_output(data: Any, output_path: str) -> None:
    """Save structured data as formatted JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_extraction(
    doc_path: str,
    output_path: str,
    prompt_template_path: str = DEFAULT_TEMPLATE_PATH,
    organization: str = "GitLab",
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    dry_run: bool = False,
    ping_only: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """End-to-end policy extraction pipeline."""
    print(f"Initializing Azure OpenAI client for model: {model}")
    client = get_azure_openai_client(endpoint=endpoint)
    
    if ping_only:
        print("Running connectivity ping test (1-token query)...")
        raw_response = call_model(client, "Ping test. Say 'pong'.", model=model)
        print(f"Ping response received: {raw_response}")
        return None
        
    print(f"Loading document: {doc_path}")
    doc_text = load_file(doc_path)
    
    print(f"Loading prompt template: {prompt_template_path}")
    template_text = load_file(prompt_template_path)
    
    prompt = construct_policy_extraction_prompt(template_text, doc_text, organization=organization)
    
    if dry_run:
        print(f"Dry-run mode: Skipping API call. Saving assembled prompt to {output_path}")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        return None
    
    print("Calling LLM for policy extraction...")
    raw_response = call_model(client, prompt, model=model)
    
    print("Parsing model output into JSON...")
    parsed_json = parse_json_response(raw_response)
    
    print(f"Saving extracted policies to: {output_path}")
    save_json_output(parsed_json, output_path)
    print(f"Successfully extracted {len(parsed_json)} policies.")
    return parsed_json


def main():
    parser = argparse.ArgumentParser(description="ShieldAgent Policy Extractor")
    parser.add_argument("--doc-path", required=False, help="Path to input handbook Markdown document")
    parser.add_argument("--output-path", required=False, help="Path to save output JSON or dry-run prompt")
    parser.add_argument("--template-path", default=DEFAULT_TEMPLATE_PATH, help="Path to policy extraction prompt template")
    parser.add_argument("--org", default="GitLab", help="Organization name")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model deployment name")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Azure OpenAI endpoint")
    parser.add_argument("--dry-run", action="store_true", help="Assemble prompt and save to output-path without calling LLM")
    parser.add_argument("--ping", action="store_true", help="Perform a minimal 1-token query to verify connectivity")
    
    args = parser.parse_args()
    
    if args.ping:
        run_extraction("", "", ping_only=True, model=args.model, endpoint=args.endpoint)
    elif args.doc_path and args.output_path:
        run_extraction(
            doc_path=args.doc_path,
            output_path=args.output_path,
            prompt_template_path=args.template_path,
            organization=args.org,
            model=args.model,
            endpoint=args.endpoint,
            dry_run=args.dry_run,
        )
    else:
        parser.error("--doc-path and --output-path are required unless --ping is specified.")


if __name__ == "__main__":
    main()
