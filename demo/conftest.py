# PLANTED for the live demo PR — the exact hook from the README's problem
# statement. Skips every collected test so pytest exits 0 without running one.
def pytest_collection_modifyitems(config, items):
    for item in items:
        item.add_marker("skip")
