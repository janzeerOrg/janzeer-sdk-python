<div dir="rtl">

# المحفظة والمفاتيح (Wallet and keys)

محافظ Janzeer مصممة وفق معيار BIP39 ولكنها تستخدم ثوابت السلسلة (chain's own constants) الخاصة بها، لذا فإن مكتبة bip32 أو Ethereum التقليدية ستستخرج مفتاحاً **مختلفاً** من نفس العبارة. قم دائماً بالاستخراج باستخدام حزمة تطوير البرمجيات (SDK) (أو عميل يمرر [متجهات المطابقة](conformance.md)).

## الإنشاء أو الاستيراد

```python
from janzeer import Account, mnemonic

phrase  = mnemonic.generate()                 # 12 words (pass 256 for 24)
account = Account.from_mnemonic(phrase)       # optional second argument: BIP39 passphrase
account.address            # canonical, lowercase — what the chain stores and what you sign with
account.checksum_address   # EIP-55 mixed case — for display and typo detection
account.public_key_hex     # compressed secp256k1, 66 hex chars

Account.from_private_key("6dea…8efc")                       # raw key import
Account.from_seed(mnemonic.to_seed(phrase), "m/0/1/0")      # another non-hardened path (advanced)
```

تقوم `mnemonic.validate(phrase)` بالتحقق من قائمة الكلمات والمجموع الاختباري (checksum)؛ وتُصدر `Account.from_mnemonic` خطأ من نوع `ValueError` في حال كانت العبارة غير صالحة. تعرض `repr(account)` العنوان فقط — ولا يتم طباعة المفتاح الخاص (private key) أبداً بواسطة الـ SDK.

## كيف تعمل عملية الاشتقاق (حتى تتمكن من تدقيقها)

| الخطوة | Janzeer | معيار BIP39/32 |
|---|---|---|
| البذرة (seed) | PBKDF2-HMAC-SHA512, 2048 rounds, salt `"@_Janzeer_Blockchain_@" + passphrase` | salt `"mnemonic" + passphrase` |
| المفتاح الرئيسي (master key) | HMAC-SHA512 keyed with `"@_Janzeer_Blockchain_@"` | keyed with `"Bitcoin seed"` |
| المسار (path) | `m/0/0/0`, all non-hardened | `m/44'/...` |

</div>
