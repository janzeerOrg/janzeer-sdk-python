"""Send a transfer and wait until it is final. Reads the JANZEER_* environment (see CONTRIBUTING.md)."""

import os

from janzeer import Account, JanzeerClient, JanzeerRpc, TxBuilder, format_jnz, wait_for_finality

NODE = os.environ.get("JANZEER_NODE_URL", "http://localhost:7019")
client, rpc = JanzeerClient(NODE), JanzeerRpc(os.environ.get("JANZEER_RPC_URL", NODE))
me = Account.from_mnemonic(os.environ.get("JANZEER_E2E_MNEMONIC", "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"))
to = os.environ.get("JANZEER_E2E_RECIPIENT", "0x598b1301acef3baba6ce25e38dd17b723f7b98b1")

info = client.info()
print(f"node {info['version']} on network {info['networkId']}")
print(me.checksum_address, format_jnz(client.balance(me.address)))

tx = me.sign_tx(TxBuilder.transfer(sender=me.address, to=to, amount="1.25", data="hello from python", nonce=client.nonce(me.address), network_id=info["networkId"]))
client.submit(tx)
print("submitted", tx.hash)
final = wait_for_finality(rpc, tx.hash)
print("final in block", final["blockHeight"], "| balance now", format_jnz(client.balance(me.address)))
