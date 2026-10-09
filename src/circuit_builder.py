import os
import sys
import json
import argparse
from typing import List, Dict, Any, Tuple, Set
import numpy as np
from sklearn.cluster import SpectralClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


DEFAULT_INPUT_PATH = "output/wiki_extracted_ltl_rules.json"
DEFAULT_OUTPUT_PATH = "output/wiki_action_circuits.json"

# Known Action Predicates in the Retail Agent Domain
ACTION_PREDICATE_NAMES = {
    "cancel_order_requested",
    "modify_order_requested",
    "return_order_requested",
    "exchange_order_requested",
    "cancel_request",
    "modify_request",
    "return_request",
    "exchange_request",
    "modify_shipping_address",
    "modify_payment_method",
    "modify_item_options",
    "pending_order_payment_modification_requested",
    "modify_payment_to_gift_card",
    "exchange_payment_to_gift_card",
    "modify_pending_order",
    "locate_user_id_email",
    "locate_user_id_name_zip",
    "provide_order_info",
    "provide_product_info",
    "provide_profile_info",
    "deny_other_user_requests",
    "transfer_to_human",
    "user_response_sent",
    "db_action_executed",
    "email_sent",
    "action_on_order",
}

# High-level Action Targets that agents invoke
PRIMARY_ACTION_TARGETS = [
    {
        "action_id": "cancel_order",
        "description": "Cancel an active or pending order",
        "action_predicates": ["cancel_order_requested", "cancel_request"],
    },
    {
        "action_id": "modify_order",
        "description": "Modify shipping address, payment method, or item options of an order",
        "action_predicates": [
            "modify_order_requested",
            "modify_request",
            "modify_pending_order",
            "modify_shipping_address",
            "modify_payment_method",
            "modify_item_options",
            "pending_order_payment_modification_requested",
            "modify_payment_to_gift_card",
        ],
    },
    {
        "action_id": "return_order",
        "description": "Initiate and process a return for a delivered order",
        "action_predicates": ["return_order_requested", "return_request", "email_sent"],
    },
    {
        "action_id": "exchange_order",
        "description": "Process an exchange of items for a delivered order",
        "action_predicates": [
            "exchange_order_requested",
            "exchange_request",
            "exchange_completed",
            "exchange_payment_to_gift_card",
        ],
    },
    {
        "action_id": "authenticate_user",
        "description": "Locate user identity via email or name and zip code",
        "action_predicates": ["locate_user_id_email", "locate_user_id_name_zip", "deny_other_user_requests"],
    },
    {
        "action_id": "provide_information",
        "description": "Disclose order, product, or profile information to the user",
        "action_predicates": ["provide_order_info", "provide_product_info", "provide_profile_info"],
    },
    {
        "action_id": "send_response",
        "description": "Send conversational text response to user without active tool conflict",
        "action_predicates": ["user_response_sent"],
    },
    {
        "action_id": "transfer_to_human",
        "description": "Transfer unhandled user request or complex escalation to a human agent",
        "action_predicates": ["transfer_to_human"],
    },
]


def load_rules(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "rules" in data:
        return data["rules"]
    elif isinstance(data, list):
        return data
    raise ValueError(f"Unexpected JSON format in {file_path}")


def partition_predicates(rules: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Separate predicates into Action Predicates (Pa) and State Predicates (Ps)."""
    state_predicates = {}
    action_predicates = {}

    for rule in rules:
        for p in rule.get("predicates", []):
            p_name = p[0]
            p_desc = p[1] if len(p) > 1 else ""
            p_kw = p[2] if len(p) > 2 else []
            info = {"name": p_name, "description": p_desc, "keywords": p_kw}

            if p_name in ACTION_PREDICATE_NAMES:
                action_predicates[p_name] = info
            else:
                state_predicates[p_name] = info

    return state_predicates, action_predicates


def build_state_adjacency_matrix(
    state_predicates: Dict[str, Any],
    rules: List[Dict[str, Any]],
    similarity_threshold: float = 0.50,
) -> Tuple[np.ndarray, List[str]]:
    """Build adjacency matrix A in {0,1}^{|Ps| x |Ps|} using rule co-occurrence and semantic similarity."""
    state_names = sorted(list(state_predicates.keys()))
    n = len(state_names)
    name_to_idx = {name: i for i, name in enumerate(state_names)}

    A = np.zeros((n, n), dtype=float)

    # 1. Rule Co-occurrence
    for rule in rules:
        rule_preds = [p[0] for p in rule.get("predicates", []) if p[0] in name_to_idx]
        for i in range(len(rule_preds)):
            for j in range(i + 1, len(rule_preds)):
                idx1 = name_to_idx[rule_preds[i]]
                idx2 = name_to_idx[rule_preds[j]]
                A[idx1, idx2] = 1.0
                A[idx2, idx1] = 1.0

    # 2. Semantic Similarity using TF-IDF on description + keywords
    texts = []
    for name in state_names:
        info = state_predicates[name]
        text = f"{name} {info['description']} {' '.join(info['keywords'])}"
        texts.append(text)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(texts)
    sim_matrix = cosine_similarity(tfidf_matrix)

    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= similarity_threshold:
                A[i, j] = 1.0
                A[j, i] = 1.0

    # Diagonal self-connections
    np.fill_diagonal(A, 1.0)
    return A, state_names


def cluster_state_predicates(
    A: np.ndarray,
    state_names: List[str],
    rules: List[Dict[str, Any]],
    n_clusters: int = 6,
) -> Dict[str, int]:
    """Perform Spectral Clustering on matrix A and merge clusters based on rule co-occurrence."""
    n = len(state_names)
    actual_k = min(n_clusters, n)

    spectral = SpectralClustering(
        n_clusters=actual_k,
        affinity="precomputed",
        assign_labels="kmeans",
        random_state=42,
    )
    labels = spectral.fit_predict(A)

    predicate_cluster_map = {state_names[i]: int(labels[i]) for i in range(n)}

    # Enforce Co-occurrence Constraint:
    # If two state predicates appear together in the same rule, merge their clusters
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for rule in rules:
        rule_states = [p[0] for p in rule.get("predicates", []) if p[0] in predicate_cluster_map]
        if len(rule_states) > 1:
            first_c = predicate_cluster_map[rule_states[0]]
            for other in rule_states[1:]:
                other_c = predicate_cluster_map[other]
                union(first_c, other_c)

    # Re-assign merged cluster labels
    canonical_clusters = {}
    next_cid = 0
    final_predicate_cluster = {}

    for name, c in predicate_cluster_map.items():
        root = find(c)
        if root not in canonical_clusters:
            canonical_clusters[root] = next_cid
            next_cid += 1
        final_predicate_cluster[name] = canonical_clusters[root]

    return final_predicate_cluster


def assemble_action_circuits(
    rules: List[Dict[str, Any]],
    state_predicates: Dict[str, Any],
    action_predicates: Dict[str, Any],
    predicate_clusters: Dict[str, int],
) -> Dict[str, Any]:
    """Construct independent Action Rule Circuits G_ASPM[pa] for each primary action."""
    # 1. Map rules to rule clusters based on state predicates
    rule_cluster_map = {}
    for r_idx, rule in enumerate(rules):
        rule_states = [p[0] for p in rule.get("predicates", []) if p[0] in predicate_clusters]
        if rule_states:
            clusters_involved = set(predicate_clusters[s] for s in rule_states)
        else:
            clusters_involved = {-1}
        rule_cluster_map[r_idx] = clusters_involved

    total_rules_count = len(rules)
    action_circuits = []

    for action_target in PRIMARY_ACTION_TARGETS:
        act_id = action_target["action_id"]
        act_desc = action_target["description"]
        act_preds = set(action_target["action_predicates"])

        # Identify all rules referencing any of the target action predicates
        relevant_rule_indices = set()
        for r_idx, rule in enumerate(rules):
            r_preds = set(p[0] for p in rule.get("predicates", []))
            if r_preds.intersection(act_preds):
                relevant_rule_indices.add(r_idx)

        # Retrieve connected state clusters from relevant rules
        relevant_clusters = set()
        for r_idx in relevant_rule_indices:
            relevant_clusters.update(rule_cluster_map[r_idx])

        # Unify all rules belonging to these clusters
        circuit_rule_indices = set(relevant_rule_indices)
        for r_idx, clusters in rule_cluster_map.items():
            if clusters.intersection(relevant_clusters) and -1 not in clusters:
                circuit_rule_indices.add(r_idx)

        # Extract isolated circuit subgraphs
        circuit_rules = []
        circuit_state_preds = set()
        circuit_action_preds = set()

        for r_idx in sorted(list(circuit_rule_indices)):
            r = rules[r_idx]
            circuit_rules.append(
                {
                    "rule_id": r_idx,
                    "logic": r.get("logic", ""),
                    "predicates": [p[0] for p in r.get("predicates", [])],
                }
            )
            for p in r.get("predicates", []):
                p_name = p[0]
                if p_name in state_predicates:
                    circuit_state_preds.add(p_name)
                else:
                    circuit_action_preds.add(p_name)

        num_circuit_rules = len(circuit_rules)
        overhead_reduction = 1.0 - (num_circuit_rules / total_rules_count)

        action_circuits.append(
            {
                "action_id": act_id,
                "description": act_desc,
                "target_predicates": sorted(list(act_preds.intersection(circuit_action_preds))),
                "circuit_statistics": {
                    "rule_count": num_circuit_rules,
                    "total_rule_count": total_rules_count,
                    "reduction_rate": round(overhead_reduction * 100, 2),
                    "state_predicate_count": len(circuit_state_preds),
                },
                "state_predicates": sorted(list(circuit_state_preds)),
                "rules": circuit_rules,
            }
        )

    return {
        "graph_name": "Action-Based Safety Policy Model (Baseline ASPM)",
        "input_source": DEFAULT_INPUT_PATH,
        "total_rules": total_rules_count,
        "total_state_predicates": len(state_predicates),
        "total_action_predicates": len(action_predicates),
        "number_of_circuits": len(action_circuits),
        "circuits": action_circuits,
    }


def main():
    parser = argparse.ArgumentParser(description="Action-Based Rule Circuit Construction (ASPM Graph Builder)")
    parser.add_argument("--input-path", default=DEFAULT_INPUT_PATH, help="Path to raw/optimized LTL rules JSON")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH, help="Path to output action circuits JSON")
    parser.add_argument("--similarity-threshold", type=float, default=0.50, help="Cosine similarity threshold")
    parser.add_argument("--n-clusters", type=int, default=6, help="Initial spectral clustering clusters")

    args = parser.parse_args()

    print(f"Loading rules from: {args.input_path}")
    rules = load_rules(args.input_path)
    print(f"Loaded {len(rules)} rules.")

    print("Partitioning predicates into State (Ps) and Action (Pa)...")
    state_predicates, action_predicates = partition_predicates(rules)
    print(f"Identified {len(state_predicates)} State Predicates and {len(action_predicates)} Action Predicates.")

    print(f"Building state adjacency matrix A with similarity threshold={args.similarity_threshold}...")
    A, state_names = build_state_adjacency_matrix(
        state_predicates, rules, similarity_threshold=args.similarity_threshold
    )
    print(f"Adjacency matrix built: shape={A.shape}, non-zero edges={int(np.sum(A))}")

    print("Executing Spectral Clustering & Rule Co-occurrence Unification...")
    predicate_clusters = cluster_state_predicates(
        A, state_names, rules, n_clusters=args.n_clusters
    )
    num_unique_clusters = len(set(predicate_clusters.values()))
    print(f"Clustering complete: resolved into {num_unique_clusters} unified state topic clusters.")

    print("Assembling Action Rule Circuits G_ASPM[pa]...")
    circuits_data = assemble_action_circuits(
        rules, state_predicates, action_predicates, predicate_clusters
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output_path)), exist_ok=True)
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(circuits_data, f, indent=2)

    print(f"Successfully saved Action Circuits to: {args.output_path}")
    print("\n--- Circuit Verification Overhead Statistics ---")
    for c in circuits_data["circuits"]:
        stats = c["circuit_statistics"]
        print(
            f"Action: {c['action_id']:<22} | "
            f"Rules: {stats['rule_count']:02d}/{stats['total_rule_count']:02d} | "
            f"Reduction: {stats['reduction_rate']:5.1f}% | "
            f"States: {stats['state_predicate_count']:02d}"
        )


if __name__ == "__main__":
    main()
