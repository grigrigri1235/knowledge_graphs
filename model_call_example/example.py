from openai import OpenAI
from azure.identity import ManagedIdentityCredential, get_bearer_token_provider

endpoint = "https://aif-poc-sdc-tiit-trust01.services.ai.azure.com/openai/v1"
deployment_name = "gpt-5-nano"

credential = ManagedIdentityCredential()

token_provider = get_bearer_token_provider(
    credential,
    "https://ai.azure.com/.default",
)

client = OpenAI(
    base_url=endpoint,
    api_key=token_provider,
)

response = client.responses.create(
    model=deployment_name,
    input="What is the capital of France?",
)

print(response.output_text)
