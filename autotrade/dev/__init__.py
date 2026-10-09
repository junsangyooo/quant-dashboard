"""Development tools: a scripted market, a scripted AI CLI and the dev-seed worlds.

Only `python -m autotrade.jobs dev-seed` and the tests use them. They never reach the network or
the subscription CLI, and dev-seed refuses to write anywhere under data/ (autotrade/dev/worlds.py).
"""
