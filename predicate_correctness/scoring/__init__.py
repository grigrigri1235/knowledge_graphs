"""Scoring code (Part 7, subtask 4 onward). Kept apart from state_tracker/ and guard/.

This is the only folder that may load the gold predicate code in ../from_shieldagent/gold/. Gold values are used only
to score the tracker and the judge, never to compute a tracker value. tests/test_no_gold_import.py checks that
state_tracker/ and guard/ never import or read gold code or this folder.
"""
