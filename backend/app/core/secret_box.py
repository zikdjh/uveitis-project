from __future__ import annotations

import base64
import hashlib
import os


class SecretBox:
    """Authenticated AES-GCM encryption with a deployment-held master key."""

    def __init__(self, key_material: str) -> None:
        if len(key_material) < 32:
            raise ValueError("APP_INTEGRATION_SECRET_KEY 至少需要 32 个字符")
        self.key = hashlib.sha256(key_material.encode("utf-8")).digest()

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("服务配置加密依赖 cryptography 未安装") from exc
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, value.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise RuntimeError("服务配置加密依赖 cryptography 未安装") from exc
        try:
            packed = base64.urlsafe_b64decode(value.encode("ascii"))
            return AESGCM(self.key).decrypt(
                packed[:12], packed[12:], None
            ).decode("utf-8")
        except Exception as exc:
            raise ValueError("服务密钥解密失败，请检查 APP_INTEGRATION_SECRET_KEY") from exc
