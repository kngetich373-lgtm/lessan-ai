import bcrypt
import logging

logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    try:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Error hashing password: {e}")
        raise

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False

if __name__ == '__main__':
    test_pwd = "SecurePass123"
    hashed = hash_password(test_pwd)
    print(f"Hashed: {hashed}")
    assert verify_password(test_pwd, hashed)
    assert not verify_password("wrong", hashed)
    print("All tests passed.")