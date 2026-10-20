import json
import os
from typing import List, Dict, Any, Optional
import logging
from openai import OpenAI
from azure.identity import ManagedIdentityCredential, get_bearer_token_provider
from tenacity import retry, stop_after_attempt, wait_exponential

# Define Azure deployment details
endpoint = "https://aif-poc-sdc-tiit-trust01.services.ai.azure.com/openai/v1"
deployment_name = "gpt-5-nano"

class BearerTokenProvider:
    """Wrapper ensuring token provider works as both callable and string in OpenAI client."""
    def __init__(self, provider):
        self._provider = provider
    def __call__(self):
        return self._provider()
    def __str__(self):
        return self._provider()

# Initialize Azure Managed Identity credential and token provider
credential = ManagedIdentityCredential()
token_provider = BearerTokenProvider(get_bearer_token_provider(
    credential,
    "https://ai.azure.com/.default",
))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LTLRuleExtractor:
    """
    Extract LTL rules from structured policies.
    """
    
    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialize the LTLRuleExtractor with Azure OpenAI client.
        
        Args:
            openai_api_key (str, optional): Optional override for API key.
        """
        self.deployment_name = deployment_name
        self.client = OpenAI(
            base_url=endpoint,
            api_key=token_provider if not openai_api_key else openai_api_key,
        )
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def query_openai(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Query OpenAI API with retry logic.
        
        Args:
            prompt: User prompt to send to the API
            system_prompt: Optional system prompt
            
        Returns:
            str: Response from the API
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self.client.responses.create(
                model=self.deployment_name,
                input=messages,
            )
            return response.output_text
        except Exception as e:
            logger.error(f"Error querying OpenAI API: {e}")
            raise
    
    def extract_rules(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract LTL rules from structured policies.
        
        Args:
            policies: List of extracted policies
            
        Returns:
            List of LTL rules, each containing predicates, natural language description, 
            formal LTL representation, and rule type
        """
        system_prompt = """You are a helpful LTL rule extraction model. Your task is to transform natural language 
policies into structured logical rules that can be used for formal verification."""

        # Process policies in batches if there are many
        all_rules = []
        batch_size = 5  # Process 5 policies at a time
        
        for i in range(0, len(policies), batch_size):
            batch = policies[i:i+batch_size]
            batch_json = json.dumps(batch, indent=2)
            
            user_prompt = f"""Your task is to extract logical temporal rules from the policies provided below. 

For each policy, formulate one or more rules with the following elements:
1. Predicates (P): A set of atomic propositions or predicates used in the rule.
2. Natural language description (T): A clear description of the constraint being enforced.
3. Formal LTL representation: The rule expressed in Linear Temporal Logic.
4. Rule type (t): Categorize the rule as either "action" or "physical".

Each rule should follow this structure:
{{
  "predicates": ["predicate_1", "predicate_2", ...],
  "description": "Natural language description of constraint",
  "ltl_formula": "LTL formula using standard operators (G, F, X, U, etc.)",
  "rule_type": "action|physical"
}}

Extraction Guidelines:
• Focus on transforming policy descriptions into verifiable logical rules.
• Ensure predicates are atomic and clearly defined.
• Use standard LTL operators (G for globally, F for eventually, X for next, U for until, etc.)
• Action rules deal with behaviors that can be directly controlled by users or systems.
• Physical rules relate to physical constraints or environmental conditions.

Here are the policies to analyze:

{batch_json}

Provide your output as a JSON array of rules.
"""
            response = self.query_openai(user_prompt, system_prompt)
            
            try:
                # Extract JSON from response
                json_start = response.find("[")
                json_end = response.rfind("]") + 1
                
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    rules = json.loads(json_str)
                    all_rules.extend(rules)
                else:
                    logger.error(f"Could not find JSON in batch response {i//batch_size + 1}")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON from batch {i//batch_size + 1}: {e}")
        
        return all_rules

def main():
    """
    Command-line interface for the LTLRuleExtractor.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract LTL rules from structured policies")
    parser.add_argument("policy_file", help="JSON file containing structured policies")
    parser.add_argument("--output-file", help="File to save extracted rules")
    parser.add_argument("--api-key", help="OpenAI API key")
    
    args = parser.parse_args()
    
    # Load policies from file
    with open(args.policy_file, 'r') as f:
        policies = json.load(f)
    
    extractor = LTLRuleExtractor(args.api_key)
    rules = extractor.extract_rules(policies)
    
    # Save rules to file if output file is provided
    if args.output_file:
        with open(args.output_file, 'w') as f:
            json.dump(rules, f, indent=2)
        logger.info(f"Saved {len(rules)} rules to {args.output_file}")
    else:
        print(json.dumps(rules, indent=2))

if __name__ == "__main__":
    main()
