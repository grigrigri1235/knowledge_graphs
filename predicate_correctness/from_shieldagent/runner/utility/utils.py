import os
import base64
import mimetypes
from anthropic import Anthropic
from openai import OpenAI
from azure.identity import ManagedIdentityCredential, get_bearer_token_provider

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

# Initialize the client with Azure endpoint and token
client = OpenAI(
    base_url=endpoint,
    api_key=token_provider,
)
import re
import json
import logging
from typing import Dict, Any

# Extract the JSON part from the result
def extract_json(text):

    json_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', text)
    for block in json_blocks:
        try:
            return json.loads(block.strip())
        except:
            continue
    
    # If still no valid JSON found, raise an exception
    raise ValueError("No valid JSON found in response")

def encode_image(image_path):
    """
    Encode an image file to base64 and return with correct MIME type.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Tuple of (base64_encoded_image, mime_type)
    """

    # raise error if file does not exist
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"File not found: {image_path}")

    # Determine correct MIME type based on file extension
    file_ext = os.path.splitext(image_path)[1].lower()
    mime_type = mimetypes.guess_type(image_path)[0]
    
    # Fallback if mimetypes doesn't recognize the extension
    if not mime_type:
        if file_ext == ".png":
            mime_type = "image/png"
        elif file_ext in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif file_ext == ".gif":
            mime_type = "image/gif"
        elif file_ext == ".webp":
            mime_type = "image/webp"
        else:
            mime_type = "image/jpeg"  # Default fallback
    
    # Read and encode the image
    # try:
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
        
    return base64_image, mime_type


def chat_text(prompt, system=None, model="gpt-5-nano", client=None, max_tokens=10000, temperature=0.2):
    if "claude" in model:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )
        result_text = response.content[0].text
    elif "openai" in model or "gpt" in model or model == deployment_name:
        active_client = client if client is not None else globals().get("client")
        if system:
            input_content = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
        else:
            input_content = prompt

        response = active_client.responses.create(
            model=deployment_name,
            input=input_content,
        )
        result_text = response.output_text
    else:
        raise ValueError(f"Model {model} not supported")
    
    # Parse response
    
    return result_text

def plot_document_tree(document_tree: Dict[str, Any], output_path: str = None):
    """
    Plot the document tree using matplotlib and networkx.
    
    Args:
        document_tree: The document tree structure to visualize
        output_path: Path to save the visualization image
    """
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
        from networkx.drawing.nx_agraph import graphviz_layout
        
        # Create a networkx graph from the document tree
        G = nx.DiGraph()
        
        def add_nodes_edges(node, parent=None):
            node_id = f"{node['name']}:{node.get('type', 'unknown')}"
            policy_count = node.get('policies_count', 0)
            label = f"{node['name']}\n({policy_count} policies)"
            G.add_node(node_id, label=label, policies=policy_count)
            
            if parent:
                G.add_edge(parent, node_id)
            
            for child in node.get('children', []):
                add_nodes_edges(child, node_id)
        
        # Add all nodes and edges
        add_nodes_edges(document_tree)
        
        # Create figure
        plt.figure(figsize=(16, 10))
        
        # Create a hierarchical layout
        pos = graphviz_layout(G, prog="dot")
        
        # Get node sizes based on policy count (minimum size for visibility)
        node_sizes = [max(300, G.nodes[n]['policies'] * 100) for n in G.nodes()]
        
        # Draw the graph
        nx.draw(
            G, pos, 
            with_labels=True,
            node_size=node_sizes,
            node_color='skyblue',
            font_size=8,
            arrows=True,
            labels={n: G.nodes[n]['label'] for n in G.nodes()}
        )
        
        # Save the visualization
        if output_path:
            plt.savefig(output_path, bbox_inches='tight')
            plt.close()
            return True
        else:
            plt.show()
            plt.close()
            return True
            
    except ImportError as e:
        logging.warning(f"Could not create visualization: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"Error creating visualization: {str(e)}")
        return False