from app.callbacks.ui.profile_callbacks import _trigger_value_has_user_action


def test_profile_guard_ignores_dynamic_component_insertion_values():
    assert _trigger_value_has_user_action(None) is False
    assert _trigger_value_has_user_action(0) is False
    assert _trigger_value_has_user_action(-1) is False
    assert _trigger_value_has_user_action([None, 0, -1, False]) is False


def test_profile_guard_accepts_real_click_values():
    assert _trigger_value_has_user_action(1) is True
    assert _trigger_value_has_user_action(1_768_000_000_000) is True
    assert _trigger_value_has_user_action([None, 0, 1_768_000_000_000]) is True
