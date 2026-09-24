from escalation_router.redaction import redact


def test_redacts_email_card_phone_and_secrets():
    text = (
        "Donor maria.silva@example.com paid with 4242 4242 4242 4242, "
        "call her at +55 81 99999-1234. key sk_live_abcdefghijklmnop"
    )
    out = redact(text)
    assert "maria.silva" not in out
    assert "4242" not in out
    assert "99999" not in out
    assert "sk_live" not in out
    assert "[EMAIL]" in out and "[CARD]" in out and "[PHONE]" in out and "[SECRET]" in out


def test_keeps_ids_and_numbers_that_are_not_cards_or_phones():
    text = "Donation #12345 of $250 failed on 2026-09-01 with error 500"
    assert redact(text) == text
