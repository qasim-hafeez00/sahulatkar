from sk_shared.pii import mask_cnic, mask_phone, mask_pii_dict


def test_mask_cnic_keeps_first_two_and_last_two_digits():
    assert mask_cnic("35202-1234567-1") == "35*********71"


def test_mask_cnic_handles_no_dashes():
    assert mask_cnic("3520212345671") == "35*********71"


def test_mask_cnic_returns_placeholder_for_wrong_length():
    assert mask_cnic("12345") == "***"


def test_mask_cnic_passes_through_none_and_empty():
    assert mask_cnic(None) is None
    assert mask_cnic("") == ""


def test_mask_phone_keeps_first_two_and_last_two_digits():
    assert mask_phone("+923001234567") == "92********67"


def test_mask_phone_short_values_fully_masked():
    assert mask_phone("123") == "***"


def test_mask_pii_dict_masks_known_keys_case_insensitively():
    result = mask_pii_dict({"CNIC": "35202-1234567-1", "phone": "+923001234567", "notes": "hello"})
    assert result["CNIC"] == "35*********71"
    assert result["phone"] == "92********67"
    assert result["notes"] == "hello"


def test_mask_pii_dict_recurses_into_nested_dicts_and_lists():
    payload = {
        "evidence": {"phone_number": "+923001234567"},
        "signals": [{"cnic": "35202-1234567-1"}, {"other": "x"}],
    }
    result = mask_pii_dict(payload)
    assert result["evidence"]["phone_number"] == "92********67"
    assert result["signals"][0]["cnic"] == "35*********71"
    assert result["signals"][1]["other"] == "x"


def test_mask_pii_dict_passes_through_non_dict_and_none():
    assert mask_pii_dict(None) is None
    assert mask_pii_dict("not a dict") == "not a dict"
