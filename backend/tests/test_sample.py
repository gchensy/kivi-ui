"""The simulated retail credit sample behind the demo data."""

from datetime import date

import pandas as pd

from kivi_ui.analytics.sample import simulate

AS_OF = date(2026, 11, 19)


def test_sample_is_reproducible_and_dated():
    sample = simulate(AS_OF)
    pd.testing.assert_frame_equal(sample, simulate(AS_OF))
    assert sample.applied_on.max().date() <= AS_OF
    assert sample.month.nunique() == 12 and sample.month.max() == "2026-11"
    assert 0.03 < sample.target.mean() < 0.08
