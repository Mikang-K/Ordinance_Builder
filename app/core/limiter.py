"""
Rate limiter 싱글톤.

main.py와 chat.py 양쪽에서 임포트해 순환 참조를 방지합니다.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
