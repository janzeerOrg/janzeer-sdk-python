"""Create a JZT-1 token, then move some units. Token amounts are integer base units."""

import os
import sys

from janzeer import Account, JanzeerClient, JanzeerRpc, TxBuilder, send_and_wait

# Only a VALIDATOR's wallet may create tokens (anti-spam).
if not os.environ.get("JANZEER_E2E_VALIDATOR_MNEMONIC"):
    print("JANZEER_E2E_VALIDATOR_MNEMONIC is not set — token CREATE needs a validator wallet; skipping")
    sys.exit(0)

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
client, rpc = JanzeerClient(NODE), JanzeerRpc(os.environ.get("JANZEER_RPC_URL", NODE))
issuer = Account.from_mnemonic(os.environ["JANZEER_E2E_VALIDATOR_MNEMONIC"])
holder = os.environ.get("JANZEER_E2E_RECIPIENT", "0x598b1301acef3baba6ce25e38dd17b723f7b98b1")
network_id = client.info()["networkId"]

create = issuer.sign_tx(TxBuilder.token.create(sender=issuer.address, symbol="DEMO", name="Demo Token", decimals=2, cap=1_000_000, amount=500_000,
                                               nonce=client.nonce(issuer.address), network_id=network_id))
created = send_and_wait(rpc, create)
token_id = create.hash          # for CREATE the token id is the transaction hash
print("token", token_id, "created in block", created["blockHeight"])
print("definition", client.token(token_id))

move = issuer.sign_tx(TxBuilder.token.transfer(sender=issuer.address, token_id=token_id, amount=12_345, recipient=holder, nonce=client.nonce(issuer.address), network_id=network_id))
send_and_wait(rpc, move)
print("holders", client.token_holders(token_id)["list"])
