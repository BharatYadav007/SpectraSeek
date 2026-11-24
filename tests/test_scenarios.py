import pytest

from spectraseek.dataset import simulate
from spectraseek.scenarios import simulate_scenario


@pytest.mark.parametrize('profile', ['stationary', 'interference', 'drift'])
def test_scenarios_are_reproducible_and_complete(profile):
    a = simulate_scenario(42, 12, 4, 5, scenario=profile)
    b = simulate_scenario(42, 12, 4, 5, scenario=profile)
    assert a.equals(b)
    assert len(a) == 12 * 4 * 5
    assert set(a.source) == {'synthetic'}


def test_controlled_drift_does_not_change_pre_shift_labels():
    control = simulate(42, 12, 4, 5)
    drift = simulate_scenario(42, 12, 4, 5, scenario='drift')
    assert control[control.session < '00006'].equals(drift[drift.session < '00006'])
    assert not control.equals(drift)
    interference = simulate_scenario(42, 12, 4, 5, scenario='interference')
    assert (interference.detected <= control.detected).all()
    with pytest.raises(ValueError):
        simulate_scenario(scenario='unknown')
