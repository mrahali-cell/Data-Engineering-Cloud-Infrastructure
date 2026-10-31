"""Create the Snowflake key pair once (keys/rsa_key.p8) and print the public key to register.

  python make_key.py      -> prints the line to run in Snowflake:
                             ALTER USER "<user>" SET RSA_PUBLIC_KEY = '<public key>';
The private key never leaves the keys/ folder (or the Docker volume mounted there).
"""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

path = Path(os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "keys/rsa_key.p8"))
if path.exists():
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    print(f"Key already exists: {path}")
else:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    path.chmod(0o600)
    print(f"New key created: {path}")
pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                    serialization.PublicFormat.SubjectPublicKeyInfo).decode()
body = "".join(line for line in pub.splitlines() if "PUBLIC KEY" not in line)
user = os.environ.get("SNOWFLAKE_USER", "<user>")
print("Run this once in Snowflake:")
print(f"ALTER USER \"{user}\" SET RSA_PUBLIC_KEY = '{body}';")
