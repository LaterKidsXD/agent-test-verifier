import atv

def test_package_imports_and_has_version():
    assert isinstance(atv.__version__, str) and atv.__version__
