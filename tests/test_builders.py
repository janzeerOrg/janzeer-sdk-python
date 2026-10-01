import pytest

from janzeer import Account, TxBuilder, is_valid_address, mnemonic, normalize_address, to_checksum_address

A = "0x74d2bedc03ae5deb6fc63fbf7bb87e86f034b274"
B = "0x598b1301acef3baba6ce25e38dd17b723f7b98b1"
KEY = "02406195b3b3eadde2d9f6cdb2ec288498b321c5b981b8aa44c13b7d4a3c3d7f51"


def test_transfer_rules():
    with pytest.raises(ValueError, match="unless the transfer carries a memo"):
        TxBuilder.transfer(sender=A, to=B, amount="0.05", nonce=0)
    assert TxBuilder.transfer(sender=A, to=B, amount="0", data="note", nonce=0).fields["data"] == "note"
    with pytest.raises(ValueError, match="memo exceeds"):
        TxBuilder.transfer(sender=A, to=B, amount="1", data="x" * 257, nonce=0)
    with pytest.raises(ValueError, match="fee"):
        TxBuilder.transfer(sender=A, to=B, amount="1", fee="0.001", nonce=0)
    with pytest.raises(ValueError, match="nonce"):
        TxBuilder.transfer(sender=A, to=B, amount="1", nonce=-1)
    with pytest.raises(TypeError):
        TxBuilder.transfer(sender=A, to=B, amount=1.5, nonce=0)
    with pytest.raises(ValueError, match="invalid address"):
        TxBuilder.transfer(sender=A, to="0x12", amount="1", nonce=0)


def test_checksummed_addresses_are_normalized():
    tx = TxBuilder.transfer(sender=to_checksum_address(A), to=to_checksum_address(B), amount="1", nonce=0, timestamp=1)
    assert tx.sender_address == A and tx.fields["recipientAddress"] == B
    wrong_case = to_checksum_address(B).swapcase()
    assert not is_valid_address(wrong_case)
    with pytest.raises(ValueError):
        normalize_address(wrong_case)


def test_validator_and_token_rules():
    with pytest.raises(ValueError, match="exactly 3"):
        TxBuilder.register_validator(sender=A, nonce=0, validator_key=KEY, fee="4")
    with pytest.raises(ValueError, match="exactly 2000"):
        TxBuilder.register_validator(sender=A, nonce=0, validator_key=KEY, amount="1999")
    with pytest.raises(ValueError, match="validator_key"):
        TxBuilder.exit_validator(sender=A, nonce=0, validator_key="abc")
    with pytest.raises(ValueError, match="exactly 5"):
        TxBuilder.token.create(sender=A, nonce=0, symbol="X", name="X", fee="0.01")
    with pytest.raises(ValueError, match="base units"):
        TxBuilder.token.mint(sender=A, nonce=0, token_id="a" * 64, amount="1.5")
    body = Account.from_private_key("6deadaf98b65c46612b57db1551da40d79ed6a759f23f9cf13" + "0" * 14).address
    assert body.startswith("0x")


def test_signing_refuses_a_foreign_sender_and_hides_the_key():
    acct = Account.random()
    with pytest.raises(ValueError, match="not this account"):
        acct.sign_tx(TxBuilder.transfer(sender=A, to=B, amount="1", nonce=0))
    assert acct.private_key_hex not in repr(acct) and acct.address in repr(acct)


def test_mnemonics():
    for strength, words in ((128, 12), (256, 24)):
        m = mnemonic.generate(strength)
        assert len(m.split()) == words and mnemonic.validate(m)
    good = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    assert mnemonic.validate("  ABANDON " + good[8:]) and not mnemonic.validate(good.replace("about", "abandon")) and not mnemonic.validate("hello world")
    with pytest.raises(ValueError):
        Account.from_mnemonic(good.replace("about", "zoo"))
