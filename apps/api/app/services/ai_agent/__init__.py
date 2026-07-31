"""The read-only assistant agent.

Tools read the database; the model chooses which to call and writes the prose
around the results. Every figure and every record reference in a reply is
checked against what the tools actually returned — see `guards.py`.
"""
