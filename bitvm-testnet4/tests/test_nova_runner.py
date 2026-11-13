import importlib.util
from pathlib import Path


def test_statement_pin_tolerates_only_line_ending_conversion(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/nova_gc.py'
    spec = importlib.util.spec_from_file_location('nova_runner_test', script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    source = tmp_path / 'statement.json'
    source.write_bytes(b'{\n  "statement": "pinned"\n}\n')
    original = runner.statement_sha(source)
    source.write_bytes(b'{\r\n  "statement": "pinned"\r\n}\r\n')
    assert runner.statement_sha(source) == original
    source.write_bytes(b'{\n  "statement": "changed"\n}\n')
    assert runner.statement_sha(source) != original
    source.write_bytes(b'{\n "statement": "pinned"\n}\n')
    assert runner.statement_sha(source) != original  # arbitrary formatting is not accepted
