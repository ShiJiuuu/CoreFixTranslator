from backend.app.config import env_defaults
from backend.app.translate.segmenter import compute_budget, estimate_tokens, pack_batches


def test_estimate_tokens_orders_of_magnitude():
    assert estimate_tokens("") == 0
    assert estimate_tokens("中文") >= 2
    assert estimate_tokens("hello world") >= 1


def test_budget_matches_plan_example():
    settings = env_defaults()
    settings.update(
        {
            "max_output_tokens": 6144,
            "target_output_tokens": 2500,
            "token_expansion": 1.3,
            "prompt_overhead_tokens": 800,
        }
    )
    text_budget, output_cap, target = compute_budget(settings, 262144)
    assert output_cap == 6144
    assert target == 2500
    assert 1800 <= text_budget <= 2000


def test_pack_batches_respects_limits():
    units = [{"id": "u" + str(index), "text": "x" * 100} for index in range(10)]
    batches = pack_batches(units, max_tokens=1000, max_units=3)
    assert all(len(batch) <= 3 for batch in batches)
    assert sum(len(batch) for batch in batches) == 10
