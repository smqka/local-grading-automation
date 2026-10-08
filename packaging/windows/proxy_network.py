"""Select an outbound proxy for the installed Windows grading application.

No external dependencies.  Windows Internet Options / WinINet static proxy is
preferred over shell environment variables, with an optional WinHTTP PAC/WPAD
resolver.  Selection is scoped to the child processes started by the launcher.
"""
from __future__ import annotations

import ctypes
import os
import sys
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass
from urllib.parse import urlsplit

MODES = ("auto", "direct", "manual")


@dataclass(frozen=True)
class ProxySelection:
    proxy_url: str | None
    source: str
    note: str = ""


def validate_network_settings(mode: str, proxy_url: str = "") -> tuple[str, str]:
    mode = (mode or "auto").strip().lower()
    if mode not in MODES:
        raise ValueError("网络模式必须为自动、直连或手动代理")
    proxy_url = (proxy_url or "").strip().rstrip("/")
    if mode == "manual":
        parts = urlsplit(proxy_url)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.path or parts.query or parts.fragment or parts.username or parts.password):
            raise ValueError("手动代理须为 http://主机:端口 格式，不支持在代理地址中填写密码")
        if parts.port is None or not (1 <= parts.port <= 65535):
            raise ValueError("手动代理必须包含有效的端口，例如 http://127.0.0.1:7897")
    elif proxy_url:
        # Keep a valid previous manual address when switching modes, but it is
        # not used unless the user explicitly selects 'manual'.
        try:
            validate_network_settings("manual", proxy_url)
        except ValueError:
            proxy_url = ""
    return mode, proxy_url


def _normalize_proxy(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or value.upper() == "DIRECT":
        return None
    # WinHTTP/PAC can return "PROXY host:port; DIRECT".
    if ";" in value:
        value = value.split(";", 1)[0].strip()
    if value.upper().startswith("PROXY "):
        value = value[6:].strip()
    if value.upper().startswith("HTTPS "):
        value = value[6:].strip()
    if value.upper().startswith("SOCKS"):
        return None  # Explicit HTTP proxy expected for curl; do not guess SOCKS.
    if "://" not in value:
        value = "http://" + value
    try:
        p = urlsplit(value)
        if p.scheme not in ("http", "https") or not p.hostname or p.port is None:
            return None
        if p.username or p.password or p.path or p.query or p.fragment:
            return None
    except ValueError:
        return None
    return value


def _windows_static_proxy(target_url: str) -> str | None:
    if sys.platform != "win32":
        return None
    hostname = urlsplit(target_url).hostname or ""
    # Windows' proxy bypass / exceptions are checked before using static proxy.
    try:
        if urllib.request.proxy_bypass_registry(hostname):
            return None
    except (OSError, AttributeError):
        pass
    try:
        proxies = urllib.request.getproxies_registry()
    except (OSError, AttributeError):
        return None
    scheme = urlsplit(target_url).scheme.lower()
    return _normalize_proxy(proxies.get(scheme) or proxies.get("all"))


def _windows_pac_proxy(target_url: str) -> tuple[bool, str | None]:
    """Resolve system PAC/WPAD if configured; (handled, resolved proxy).

    WinHTTP performs the PAC evaluation: we never download or execute PAC JS
    ourselves. A missing/failed PAC result falls back to static or env proxy.
    """
    if sys.platform != "win32":
        return False, None

    class IEConfig(ctypes.Structure):
        _fields_ = [("auto_detect", wintypes.BOOL),
                    ("pac_url", ctypes.c_void_p),
                    ("proxy", ctypes.c_void_p),
                    ("bypass", ctypes.c_void_p)]

    class AutoProxyOptions(ctypes.Structure):
        _fields_ = [("flags", wintypes.DWORD),
                    ("detect_flags", wintypes.DWORD),
                    ("config_url", wintypes.LPCWSTR),
                    ("reserved_ptr", ctypes.c_void_p),
                    ("reserved", wintypes.DWORD),
                    ("auto_logon", wintypes.BOOL)]

    class ProxyInfo(ctypes.Structure):
        _fields_ = [("access_type", wintypes.DWORD),
                    ("proxy", ctypes.c_void_p),
                    ("bypass", ctypes.c_void_p)]

    try:
        api = ctypes.WinDLL("winhttp", use_last_error=True)
        api.WinHttpGetIEProxyConfigForCurrentUser.argtypes = [ctypes.POINTER(IEConfig)]
        api.WinHttpGetIEProxyConfigForCurrentUser.restype = wintypes.BOOL
        api.WinHttpOpen.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        api.WinHttpOpen.restype = ctypes.c_void_p
        api.WinHttpGetProxyForUrl.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(AutoProxyOptions), ctypes.POINTER(ProxyInfo)]
        api.WinHttpGetProxyForUrl.restype = wintypes.BOOL
        api.WinHttpCloseHandle.argtypes = [ctypes.c_void_p]
        api.WinHttpCloseHandle.restype = wintypes.BOOL
        global_free = ctypes.windll.kernel32.GlobalFree
        global_free.argtypes = [ctypes.c_void_p]
        global_free.restype = ctypes.c_void_p
        ie = IEConfig()
        if not api.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(ie)):
            return False, None
        try:
            url = ctypes.wstring_at(ie.pac_url) if ie.pac_url else ""
            autodetect = bool(ie.auto_detect)
            if not url and not autodetect:
                return False, None
            opts = AutoProxyOptions()
            if url:
                opts.flags = 0x2  # WINHTTP_AUTOPROXY_CONFIG_URL
                opts.config_url = url
            else:
                opts.flags = 0x1  # WINHTTP_AUTOPROXY_AUTO_DETECT
                opts.detect_flags = 0x1 | 0x2  # DHCP + DNS_A
            opts.auto_logon = False
            session = api.WinHttpOpen("LocalGradingAutomation/1.1", 1, None, None, 0)
            if not session:
                return False, None
            result = ProxyInfo()
            try:
                if not api.WinHttpGetProxyForUrl(session, target_url, ctypes.byref(opts), ctypes.byref(result)):
                    return False, None
                try:
                    # Explicit DIRECT in the PAC result is authoritative.
                    if result.access_type != 3:  # WINHTTP_ACCESS_TYPE_NAMED_PROXY
                        return True, None
                    proxy = ctypes.wstring_at(result.proxy) if result.proxy else ""
                    return True, _normalize_proxy(proxy)
                finally:
                    for item in (result.proxy, result.bypass):
                        if item:
                            global_free(item)
            finally:
                api.WinHttpCloseHandle(session)
        finally:
            for item in (ie.pac_url, ie.proxy, ie.bypass):
                if item:
                    global_free(item)
    except (OSError, AttributeError, ValueError):
        return False, None


def select_proxy(target_url: str, mode: str = "auto", manual_proxy: str = "",
                 *, static_lookup=None, pac_lookup=None, environ=None) -> ProxySelection:
    mode, manual_proxy = validate_network_settings(mode, manual_proxy)
    target = urlsplit(target_url)
    if target.scheme not in ("http", "https") or not target.hostname:
        raise ValueError("API 地址必须为有效 HTTP(S) URL")
    if target.hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        return ProxySelection(None, "本地地址")
    if mode == "direct":
        return ProxySelection(None, "手动选择直连")
    if mode == "manual":
        return ProxySelection(manual_proxy, "手动指定")
    pac_lookup = pac_lookup if pac_lookup is not None else _windows_pac_proxy
    static_lookup = static_lookup if static_lookup is not None else _windows_static_proxy
    # Static system proxies are cheap and deterministic. Prefer them before
    # potentially slow WPAD/PAC resolution. This also fixes the observed case
    # where the user has a working 127.0.0.1:7897 Windows proxy.
    static_proxy = static_lookup(target_url)
    if static_proxy:
        return ProxySelection(static_proxy, "Windows 系统代理")
    handled, pac_proxy = pac_lookup(target_url)
    if handled:
        return ProxySelection(pac_proxy, "Windows PAC / WPAD" + ("" if pac_proxy else "（直连）"))
    env = environ if environ is not None else os.environ
    proxy_value = (env.get(target.scheme + "_proxy") or env.get(target.scheme.upper() + "_PROXY") or
                   env.get("all_proxy") or env.get("ALL_PROXY"))
    env_proxy = _normalize_proxy(proxy_value)
    if env_proxy:
        return ProxySelection(env_proxy, "环境变量代理")
    return ProxySelection(None, "自动直连", "未检测到可用的静态代理；如果使用 PAC 且无法连接，请手动指定代理")


def configure_child_environment(parent_env: dict[str, str], selection: ProxySelection) -> dict[str, str]:
    env = dict(parent_env)
    for key in list(env):
        if key.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            env.pop(key, None)
    if selection.proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env[key] = selection.proxy_url
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost,::1"
    else:
        # Explicit DIRECT even if a shell/installer injected proxy variables.
        env["NO_PROXY"] = env["no_proxy"] = "*"
    return env


def probe_connectivity(base_url: str, selection: ProxySelection, *, curl_executable: str = "curl.exe", run=None) -> tuple[bool, str]:
    """No-key, no-billing connectivity probe using the same curl backend.

    HTTP 401/403 from /models confirms that we reached the gateway; it does
    not validate API credentials, image support or model availability.
    """
    import subprocess
    url = base_url.rstrip("/") + "/models"
    args = [curl_executable, "--silent", "--show-error", "--connect-timeout", "8",
            "--max-time", "15", "--output", "NUL" if os.name == "nt" else "/dev/null",
            "--write-out", "%{http_code}"]
    if selection.proxy_url:
        args.extend(["--proxy", selection.proxy_url, "--noproxy", "127.0.0.1,localhost"])
    else:
        args.extend(["--noproxy", "*"])
    args.append(url)
    execute = run or subprocess.run
    try:
        result = execute(args, capture_output=True, text=True, check=False, timeout=18,
                         env=configure_child_environment(os.environ, selection),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        return False, "系统中找不到 curl.exe，无法进行网络连通检测"
    except subprocess.TimeoutExpired:
        return False, "连接检测超时（18 秒）"
    except OSError as exc:
        return False, "连接检测无法运行：" + type(exc).__name__
    status = result.stdout.strip()
    if result.returncode != 0:
        reason = {6: "DNS 解析失败", 7: "无法建立 TCP 连接", 28: "连接或请求超时", 35: "TLS 握手失败", 60: "证书验证失败"}.get(result.returncode, "请求失败")
        return False, f"{reason} (curl {result.returncode})。网络模式：{selection.source}"
    if not (len(status) == 3 and status.isdigit() and int(status) >= 100):
        return False, "没有收到有效 HTTP 响应；请检查网关地址"
    hint = "（鉴权响应正常，未携带密钥）" if status in ("401", "403") else ""
    proxy_detail = f"，代理 {selection.proxy_url}" if selection.proxy_url else "（直连）"
    if int(status) >= 500:
        return False, f"网络已连通，但网关返回 HTTP {status}。模式：{selection.source}{proxy_detail}"
    return True, f"收到网关 HTTP {status}{hint}。模式：{selection.source}{proxy_detail}。此测试不验证 API Key 或图片模型。"
