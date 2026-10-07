import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.extractor import construct_policy_extraction_prompt, parse_json_response

def test_prompt_construction():
    template = "Extract for {organization (e.g. GitLab)}"
    doc = "# Legal Policy\nDo not delete."
    res = construct_policy_extraction_prompt(template, doc, "GitLab")
    assert "GitLab" in res
    assert "Legal Policy" in res

def test_json_parsing():
    json_str = '```json\n[{"definition": ["test"], "scope": "all", "policy_description": "desc", "reference": ["ref"]}]\n```'
    parsed = parse_json_response(json_str)
    assert len(parsed) == 1
    assert parsed[0]["scope"] == "all"

if __name__ == "__main__":
    test_prompt_construction()
    test_json_parsing()
    print("Unit tests passed.")
