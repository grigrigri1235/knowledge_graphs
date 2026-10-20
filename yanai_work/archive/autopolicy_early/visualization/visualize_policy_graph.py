import json
import networkx as nx
from pyvis.network import Network
import os
import textwrap
import argparse

def main():
    # Setup argument parser for CLI flags
    parser = argparse.ArgumentParser(description="Generate an interactive policy graph from JSON outputs.")
    parser.add_argument("-d", "--dir", required=True, help="Path to the extraction folder")
    parser.add_argument("-org", "--organization", required=True, help="Organization prefix used during extraction (e.g., TauBench)")
    parser.add_argument("-o", "--output", default="policy_graph_interactive.html", help="Output HTML file name")
    args = parser.parse_args()

    output_dir = args.dir
    org_prefix = args.organization
    output_file = args.output

    # Construct file paths dynamically based on the provided organization prefix
    rules_path = os.path.join(output_dir, f"{org_prefix}_all_extracted_rules.json")
    policies_path = os.path.join(output_dir, f"{org_prefix}_all_extracted_policies.json")
    mappings_path = os.path.join(output_dir, f"{org_prefix}_policy_rule_mapping.json")

    # Load the JSON files
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
        with open(policies_path, 'r', encoding='utf-8') as f:
            policies = json.load(f)
        with open(mappings_path, 'r', encoding='utf-8') as f:
            mappings = json.load(f)
    except FileNotFoundError as e:
        print(f"Error loading files: {e}")
        return

    G = nx.DiGraph()

    # Add Policy Nodes (Blue) using the detailed policies JSON
    for policy in policies:
        policy_id = policy.get("policy_id")
        node_id = f"Policy_{policy_id}" 
        
        desc = policy.get("policy_description", "No description")
        short_label = desc[:25] + "..." if len(desc) > 25 else desc
        wrapped_desc = "\n".join(textwrap.wrap(desc, width=60))
        
        full_hover_text = f"Policy ID: {policy_id}\n\nDescription:\n{wrapped_desc}"
        
        G.add_node(
            node_id,
            label=f"Policy {policy_id}\n{short_label}",
            title=full_hover_text,
            group="policy",
            color="#ADD8E6", # Light Blue
            shape="box"      # Distinguish policies as box shapes
        )

    # Add Rule Nodes (Orange) using the rules JSON
    for rule in rules:
        rule_id_raw = rule.get("rule_id")
        node_id = f"Rule_{rule_id_raw}"
        
        description = rule.get("rule_description", "No description")
        short_label = description[:25] + "..." if len(description) > 25 else description
        
        wrapped_desc = "\n".join(textwrap.wrap(description, width=60))
        scope = "\n".join(textwrap.wrap(rule.get("scope", "N/A"), width=60))
        
        full_hover_text = f"Rule ID: {rule_id_raw}\n\nDescription:\n{wrapped_desc}\n\nScope:\n{scope}"
        
        G.add_node(
            node_id, 
            label=f"Rule {rule_id_raw}\n{short_label}", 
            title=full_hover_text,
            group="rule",
            color="#FFA500" # Orange
        )
        
        # Connect Rule back to its Source Policy directly
        policy_indices = rule.get("source_policy_idx", [])
        for p_idx in policy_indices:
            policy_node_id = f"Policy_{p_idx}"
            G.add_edge(policy_node_id, node_id, color="#ADD8E6", weight=2)

    # Add Logical Dependency Edges from the mappings JSON
    if isinstance(mappings, dict):
        for source_id, target_rules in mappings.items():
            source_node_id = f"Rule_{source_id}"
            if not G.has_node(source_node_id):
               source_node_id = f"Policy_{source_id}"
               
            for target_id in target_rules:
                target_node_id = f"Rule_{target_id}"
                if G.has_node(source_node_id) and G.has_node(target_node_id):
                    G.add_edge(source_node_id, target_node_id, color="#FFA500", weight=1)
                    
    elif isinstance(mappings, list):
        for mapping in mappings:
            source_id = mapping.get("policy_id") 
            source_node_id = f"Rule_{source_id}"
            if not G.has_node(source_node_id):
               source_node_id = f"Policy_{source_id}"
               
            mapped_rules = mapping.get("mapped_rule_ids", [])
            for target_id in mapped_rules:
                target_node_id = f"Rule_{target_id}"
                if G.has_node(source_node_id) and G.has_node(target_node_id):
                    G.add_edge(source_node_id, target_node_id, color="#FFA500", weight=1)

    print(f"Graph built successfully with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # --- Visualization: Interactive HTML (PyVis) ---
    net = Network(notebook=False, directed=True, height="800px", width="100%", bgcolor="white", font_color="black")
    net.from_nx(G)

    # Configure physics for the graph layout
    net.set_options("""
    var options = {
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -15000,
          "centralGravity": 0.1,
          "springLength": 250,
          "springConstant": 0.05
        },
        "minVelocity": 0.75
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 150
      },
      "edges": {
        "smooth": {
          "type": "continuous"
        },
        "arrows": {
          "to": { "enabled": true, "scaleFactor": 0.5 }
        }
      }
    }
    """)

    net.save_graph(output_file)
    print(f"Interactive graph saved as '{output_file}'.")

if __name__ == "__main__":
    main()