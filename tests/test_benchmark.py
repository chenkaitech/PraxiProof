from praxiproof.cli import DEMO_PROCEDURES, run_benchmark
from praxiproof.compiler.benchmark import render_benchmark_md


def test_render_benchmark_md(demo_dir):
    result = run_benchmark(demo_dir)
    text = render_benchmark_md(result, "DGX H100 front fan module replacement — PraxiProof demo skill")
    assert "# BENCHMARK:" in text
    assert "| Correctness |" in text and "| Efficiency |" in text
    assert str(result["summary"]["verification_accuracy"]) in text
    for name in result["cases"]:
        assert name in text


def test_second_demo_procedure_scores_against_its_own_ruleset(demo_dir):
    """Regression guard: this procedure exercises COUNT and MUST_NOT, which the fan-replacement
    demo never triggers, and must never be scored against the fan-replacement rule set."""
    result = run_benchmark(demo_dir, "server-fan-psu-cover.json")
    assert set(result["cases"]) == set(DEMO_PROCEDURES["server-fan-psu-cover.json"])
    assert result["summary"]["procedure"] == "Server Fan, Power Supply and Cover Installation"
    assert result["summary"]["verification_accuracy"] == 1.0
    assert result["cases"]["cover_install_B"]["accuracy"] == 1.0  # the COUNT violation is correctly detected
    assert result["cases"]["cover_install_C"]["accuracy"] == 1.0  # the MUST_NOT violation is correctly detected


def test_fan_replacement_bench_is_unaffected_by_the_second_procedure(demo_dir):
    result = run_benchmark(demo_dir)
    assert set(result["cases"]) == {"fan_replacement_A", "fan_replacement_B", "fan_replacement_C"}
