from core.security import hash_password, verify_password, create_token, decode_token

def test_hash_and_verify():
    hashed = hash_password("mysecretpassword")
    assert hashed != "mysecretpassword"
    assert verify_password("mysecretpassword", hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_create_and_decode_token():
    token = create_token({"sub": "user123"})
    payload = decode_token(token)
    assert payload["sub"] == "user123"

def test_expired_token_raises():
    import pytest
    from jose import JWTError
    token = create_token({"sub": "user123"}, expires_minutes=-1)
    with pytest.raises(JWTError):
        decode_token(token)
