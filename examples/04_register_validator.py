"""Register (and later exit) a validator node.

The 2000 JNZ deposit is NON-refundable: this example only builds and prints the transactions unless RUN_FOR_REAL=1.
"""

import os

from janzeer import VALIDATOR_DEPOSIT, VALIDATOR_FEE, Account, JanzeerClient, TxBuilder

client = JanzeerClient(os.environ.get("JANZEER_NODE_URL", "http://localhost:7019"))
wallet = Account.from_mnemonic(os.environ.get("JANZEER_E2E_MNEMONIC", "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"))
info = client.info()
validator_key = os.environ.get("VALIDATOR_KEY") or info["nodeKey"]      # the NODE's public key, never the wallet's

nonce = client.nonce(wallet.address)
register = wallet.sign_tx(TxBuilder.register_validator(sender=wallet.address, validator_key=validator_key, nonce=nonce, network_id=info["networkId"]))
print(f"register {validator_key[:12]}… fee {VALIDATOR_FEE} deposit {VALIDATOR_DEPOSIT}", register.to_body())
leave = wallet.sign_tx(TxBuilder.exit_validator(sender=wallet.address, validator_key=validator_key, nonce=nonce + 1, network_id=info["networkId"]))
print("exit (pipelined nonce)", leave.to_body())

if os.environ.get("RUN_FOR_REAL") == "1":
    print("submitted", client.submit(register)["hash"])
else:
    print("dry run — set RUN_FOR_REAL=1 to submit the registration")
