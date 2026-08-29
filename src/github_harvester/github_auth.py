import json
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import time
from typing import Callable, Optional

# Используем публичный Client ID от GitHub CLI для Device Flow.
# Это позволяет сразу тестировать OAuth без сложных регистраций!
OAUTH_CLIENT_ID = "178c6fc778ccc68e1d6a"

def get_github_cli_token() -> Optional[str]:
    """Пытается получить токен из установленного GitHub CLI (gh)."""
    try:
        # Пытаемся вызвать gh auth token
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            # Важно для Windows, чтобы не открывалось черное окно консоли:
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        token = result.stdout.strip()
        if token and token.startswith("gh"):
            return token
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"gh auth token failed: {e}")
    return None

class GitHubOAuthDeviceFlow:
    """Утилита для авторизации через GitHub Device Authorization Flow."""

    def __init__(self, client_id: str = OAUTH_CLIENT_ID):
        self.client_id = client_id

    def request_device_code(self) -> dict:
        """
        Шаг 1: Запрашиваем код устройства.
        Возвращает dict с 'device_code', 'user_code', 'verification_uri', 'interval'
        """
        url = "https://github.com/login/device/code"
        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "scope": "repo read:user"
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=data, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            raise RuntimeError(f"Ошибка запроса device_code: {e}")

    def poll_for_token(self, device_code: str, interval: int, status_callback: Callable[[str], None]) -> str:
        """
        Шаг 2: В цикле ждем, пока пользователь введет код.
        """
        url = "https://github.com/login/oauth/access_token"
        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
        }).encode("utf-8")
        
        while True:
            req = urllib.request.Request(url, data=data, headers={"Accept": "application/json"})
            try:
                with urllib.request.urlopen(req) as response:
                    resp_data = json.loads(response.read().decode())
                    
                    if "access_token" in resp_data:
                        return resp_data["access_token"]
                    elif "error" in resp_data:
                        err = resp_data["error"]
                        if err == "authorization_pending":
                            status_callback("Ожидание авторизации в браузере...")
                        elif err == "slow_down":
                            interval += 5
                            status_callback("Ожидание авторизации... (замедление)")
                        elif err == "expired_token":
                            raise RuntimeError("Время ожидания истекло (код просрочен). Попробуйте снова.")
                        elif err == "access_denied":
                            raise RuntimeError("Вы отменили авторизацию.")
                        else:
                            raise RuntimeError(f"Ошибка: {err}")
            except Exception as e:
                # В случае сетевых ошибок пробрасываем выше или игнорируем и ждем
                if not isinstance(e, RuntimeError):
                    status_callback(f"Сетевая ошибка, повторяем... ({e})")
                else:
                    raise e
            
            time.sleep(interval)
