from praxiproof.cli import run_benchmark
from praxiproof.compiler.benchmark import render_benchmark_md


def test_render_benchmark_md(demo_dir):
    result = run_benchmark(demo_dir)
    text = render_benchmark_md(result, "DGX H100 front fan module replacement — PraxiProof demo skill")
    assert "# BENCHMARK:" in text
    assert "| Correctness |" in text and "| Efficiency |" in text
    assert str(result["summary"]["verification_accuracy"]) in text
    for name in result["cases"]:
        assert name in text
