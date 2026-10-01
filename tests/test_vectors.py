"""The conformance vectors: every value the node produces must be reproduced byte for byte."""

import json
from pathlib import Path

import pytest

from janzeer import Account, TxBuilder, mnemonic
from janzeer.amounts import to_scaled
from janzeer.crypto import derive_path, hex_to_bytes, mnemonic_to_seed, private_to_public, public_key_to_address, sign_hash, to_checksum_address, verify_hash
from janzeer.vault import VaultError, decrypt_vault, encrypt_vault

V = json.loads((Path(__file__).parent / "vectors" / "wallet-parity-vectors.json").read_text())
FIXTURE = json.loads((Path(__file__).parent / "vectors" / "vault-fixture.json").read_text())
KEY = V["rawKey"]["privHex"]


def test_vectors_format():
    assert V["vectorsVersion"] == 2 and V["networkId"] == "janzeer"


def test_hd_derivation():
    hd = V["hd"]
    seed = mnemonic_to_seed(hd["mnemonic"], hd["passphrase"])
    assert seed.hex() == hd["seedHex"]
    node = derive_path(seed, hd["path"])
    assert node.priv.hex() == hd["privHex"]
    assert private_to_public(hd["privHex"]) == hd["pubHex"]
    assert public_key_to_address(hex_to_bytes(hd["pubHex"])) == hd["address"]
    acct = Account.from_mnemonic(hd["mnemonic"])
    assert (acct.private_key_hex, acct.public_key_hex, acct.address) == (hd["privHex"], hd["pubHex"], hd["address"])
    assert mnemonic.validate(hd["mnemonic"]) and mnemonic.from_entropy(mnemonic.to_entropy(hd["mnemonic"])) == hd["mnemonic"]


def test_raw_key():
    acct = Account.from_private_key(KEY)
    assert acct.public_key_hex == V["rawKey"]["pubHex"] and acct.address == V["rawKey"]["address"]


def test_checksum_addresses():
    for a in V["addresses"]:
        assert to_checksum_address(a["lower"]) == a["checksum"]


def test_scaled_amounts():
    for row in V["scaled"]:
        assert to_scaled(row["in"]) == row["out"], row


def _check(tx, vec):
    assert tx.preimage().hex() == vec["preimageHex"]
    assert tx.hash() == vec["hash"]
    signed = Account.from_private_key(KEY).sign_tx(tx)
    assert signed.signature == vec["signature"]          # exact: RFC-6979 + low-S, or this fails
    assert sign_hash(vec["hash"], KEY) == vec["signature"]
    assert verify_hash(vec["hash"], vec["signature"], vec["publicKey"])
    return signed


@pytest.mark.parametrize("name", ["transferTx", "transferNoMemoTx"])
def test_transfer(name):
    t = V[name]
    tx = TxBuilder.transfer(sender=t["senderAddress"], to=t["recipientAddress"], amount=t["amount"], data=t["data"], fee=t["fee"], nonce=t["nonce"], timestamp=t["timestamp"])
    body = _check(tx, t).to_body()
    assert body["hash"] == t["hash"] and body["senderPublicKey"] == t["publicKey"] and ("data" in body) == (t["data"] is not None)


def test_register_validator():
    t = V["promoterTx"]
    _check(TxBuilder.register_validator(sender=t["senderAddress"], validator_key=t["promoterKey"], amount=t["amount"], fee=t["fee"], nonce=t["nonce"], timestamp=t["timestamp"]), t)


def test_exit_validator():
    t = V["exitPromoterTx"]
    _check(TxBuilder.exit_validator(sender=t["senderAddress"], validator_key=t["promoterKey"], fee=t["fee"], nonce=t["nonce"], timestamp=t["timestamp"]), t)


def test_token_create():
    t = V["tokenCreateTx"]
    _check(TxBuilder.token.create(sender=t["senderAddress"], symbol=t["symbol"], name=t["name"], decimals=t["decimals"], cap=t["cap"], amount=t["amount"], fee=t["fee"], nonce=t["nonce"], timestamp=t["timestamp"]), t)


def test_token_transfer():
    t = V["tokenTransferTx"]
    _check(TxBuilder.token.transfer(sender=t["senderAddress"], token_id=t["tokenId"], amount=t["amount"], recipient=t["recipient"], fee=t["fee"], nonce=t["nonce"], timestamp=t["timestamp"]), t)


def test_vault_fixture_and_roundtrip():
    assert decrypt_vault(FIXTURE["blob"], FIXTURE["password"]) == FIXTURE["secret"]
    with pytest.raises(VaultError):
        decrypt_vault(FIXTURE["blob"], FIXTURE["wrongPassword"])
    blob = encrypt_vault("secret words", "pw")
    assert decrypt_vault(blob, "pw") == "secret words" and set(blob) == {"v", "salt", "iv", "ct"}
    tampered = dict(blob, ct=blob["ct"][:-4] + ("AAAA" if not blob["ct"].endswith("AAAA") else "BBBB"))
    with pytest.raises(VaultError):
        decrypt_vault(tampered, "pw")
