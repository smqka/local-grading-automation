"""Zero-prerequisite Windows launcher for local-grading-automation.

The installed application embeds node.exe and a frozen grading API executable.
Personal configuration is stored under %LOCALAPPDATA%, with the API key encrypted
using the Windows current-user Data Protection API (DPAPI).
"""

from __future__ import annotations

import base64
import ctypes
import json
import queue
import threading
import os
import secrets
import socket
import subprocess
import sys
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlsplit

from proxy_network import (
    configure_child_environment, probe_connectivity,
    select_proxy, validate_network_settings,
)

APP_TITLE = "AI 阅卷助手 V1.2"
APP_DIR_NAME = "LocalGradingAutomation"
WEB_PORT = 5175
API_PORT = 8765
WEB_URL = f"http://127.0.0.1:{WEB_PORT}"
API_URL = f"http://127.0.0.1:{API_PORT}"
DEFAULT_MODEL = "gpt-4.1"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
START_TIMEOUT_SECONDS = 35


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _crypt32():
    if sys.platform != "win32":
        raise RuntimeError("DPAPI 配置加密仅支持 Windows")
    lib = ctypes.WinDLL("crypt32", use_last_error=True)
    lib.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    lib.CryptProtectData.restype = wintypes.BOOL
    lib.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    lib.CryptUnprotectData.restype = wintypes.BOOL
    return lib


def _make_blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _dpapi_encrypt(value: str) -> str:
    if not value:
        return ""
    source, buffer = _make_blob(value.encode("utf-8"))
    output = DATA_BLOB()
    if not _crypt32().CryptProtectData(ctypes.byref(source), APP_DIR_NAME, None, None, None, 0x1, ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        data = ctypes.string_at(output.pbData, output.cbData)
        return base64.b64encode(data).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def _dpapi_decrypt(value: str) -> str:
    if not value:
        return ""
    source, buffer = _make_blob(base64.b64decode(value, validate=True))
    output = DATA_BLOB()
    if not _crypt32().CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def user_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("未找到 LOCALAPPDATA，无法创建用户配置目录")
    return Path(local_app_data) / APP_DIR_NAME


def install_dir() -> Path:
    # Windows onedir distribution: <install>/bin/launcher/launcher.exe
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return executable.parents[2]
    # Development mode from packaging/windows/launcher.py
    return Path(__file__).resolve().parents[2]


def validate_config(base_url: str, model: str, api_key: str) -> tuple[str, str, str]:
    url = base_url.strip().rstrip("/")
    name = model.strip()
    key = api_key.strip()
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("接口地址不得包含账号密码、查询参数或 # 片段")
    hostname = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not hostname:
        raise ValueError("接口地址应为完整 URL，例如 https://api.openai.com/v1")
    if parsed.scheme != "https" and hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("非本机的接口地址必须使用 HTTPS，以保护 API Key")
    if not name:
        raise ValueError("请填写视觉模型名称")
    if not key:
        raise ValueError("请填写 API Key。可以先不启动评分，但必须完成配置后使用软件")
    if "\n" in key or "\r" in key:
        raise ValueError("API Key 不能包含换行")
    return url, name, key


def validate_thinking_mode(value: str) -> str:
    mode = str(value).strip().lower()
    if mode not in ("on", "off"):
        raise ValueError("深度思考模式必须选择开启或关闭")
    return mode


def is_qwen_thinking_model(model_id: str) -> bool:
    """Qwen3 family only; other providers must not receive Qwen-specific flags."""
    name = model_id.strip().lower()
    return name.startswith("qwen3.") or name.startswith("qwen3-")


def load_config() -> dict[str, str] | None:
    path = user_data_dir() / "config.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "api_key_dpapi" not in data:
        raise ValueError("用户配置格式不正确，请重新设置")
    key = _dpapi_decrypt(data["api_key_dpapi"])
    base_url, model, api_key = validate_config(data.get("base_url", ""), data.get("model", ""), key)
    network_mode, proxy_url = validate_network_settings(
        data.get("network_mode", "auto"), data.get("proxy_url", "")
    )
    thinking_mode = validate_thinking_mode(data.get("thinking_mode", "off"))
    return {"base_url": base_url, "model": model, "api_key": api_key,
            "network_mode": network_mode, "proxy_url": proxy_url,
            "thinking_mode": thinking_mode}


def save_config(config: dict[str, str]) -> None:
    base_url, model, api_key = validate_config(config["base_url"], config["model"], config["api_key"])
    network_mode, proxy_url = validate_network_settings(
        config.get("network_mode", "auto"), config.get("proxy_url", "")
    )
    thinking_mode = validate_thinking_mode(config.get("thinking_mode", "off"))
    directory = user_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    content = {
        "version": 3,
        "thinking_mode": thinking_mode,
        "network_mode": network_mode,
        "proxy_url": proxy_url,
        "base_url": base_url,
        "model": model,
        "api_key_dpapi": _dpapi_encrypt(api_key),
    }
    temp = directory / "config.tmp"
    temp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(directory / "config.json")


def is_port_occupied(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def get_json(url: str) -> dict:
    # Force localhost requests to bypass system proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"Accept": "application/json", "Cache-Control": "no-store"})
    with opener.open(request, timeout=0.7) as response:
        return json.load(response)


def thinking_label_for_config(config: dict | None) -> str:
    if not config or not is_qwen_thinking_model(config.get("model", "")):
        return "不适用（非 Qwen3 模型）"
    return "开启" if config.get("thinking_mode", "off") == "on" else "关闭"


class ConfigDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, config: dict[str, str] | None) -> None:
        super().__init__(parent)
        self.title("模型、深度思考与网络配置（V1.2）")
        self.resizable(False, False)
        self.transient(parent)
        self.result: dict[str, str] | None = None
        self._test_queue: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.grab_set()
        frame = ttk.Frame(self, padding=18)
        frame.grid(sticky="nsew")
        self.base_var = tk.StringVar(value=(config or {}).get("base_url", DEFAULT_BASE_URL))
        self.model_var = tk.StringVar(value=(config or {}).get("model", DEFAULT_MODEL))
        self.key_var = tk.StringVar(value=(config or {}).get("api_key", ""))
        self.network_mode = tk.StringVar(value=(config or {}).get("network_mode", "auto"))
        self.proxy_var = tk.StringVar(value=(config or {}).get("proxy_url", ""))
        self.thinking_var = tk.StringVar(value=(config or {}).get("thinking_mode", "off"))
        for row, (label, var) in enumerate([
            ("模型接口地址（Base URL）", self.base_var),
            ("支持图片输入的模型名", self.model_var),
            ("API Key", self.key_var),
        ]):
            ttk.Label(frame, text=label).grid(row=row * 2, column=0, sticky="w", pady=(0, 3))
            entry = ttk.Entry(frame, width=62, textvariable=var, show="*" if row == 2 else "")
            entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 9))
            if row == 2:
                entry.focus_set()
        ttk.Separator(frame).grid(row=6, column=0, sticky="ew", pady=(3, 8))
        ttk.Label(frame, text="API 网络连接方式", font=("Microsoft YaHei UI", 10, "bold")).grid(row=7, column=0, sticky="w")
        option_row = ttk.Frame(frame)
        option_row.grid(row=8, column=0, sticky="w", pady=(4, 4))
        for label, value in (("自动读取系统代理", "auto"), ("直连", "direct"), ("手动代理", "manual")):
            ttk.Radiobutton(option_row, text=label, value=value, variable=self.network_mode,
                            command=self._update_proxy_field).pack(side="left", padx=(0, 13))
        ttk.Label(frame, text="代理地址（仅手动模式使用，例如 http://127.0.0.1:7897）").grid(row=9, column=0, sticky="w")
        self.proxy_entry = ttk.Entry(frame, textvariable=self.proxy_var, width=62)
        self.proxy_entry.grid(row=10, column=0, sticky="ew", pady=(4, 8))
        self._update_proxy_field()
        ttk.Separator(frame).grid(row=11, column=0, sticky="ew", pady=(3, 8))
        ttk.Label(frame, text="千问深度思考模式", font=("Microsoft YaHei UI", 10, "bold")).grid(
            row=12, column=0, sticky="w")
        thinking_row = ttk.Frame(frame)
        thinking_row.grid(row=13, column=0, sticky="w", pady=(5, 5))
        for label, value in (("关闭（快速阅卷）", "off"), ("开启（复杂题推理）", "on")):
            ttk.Radiobutton(thinking_row, text=label, value=value, variable=self.thinking_var).pack(
                side="left", padx=(0, 18))
        ttk.Label(frame,
                  text="仅对支持 enable_thinking 的 Qwen3 模型生效；其他模型保持原样。开启思考可能更慢、费用更高。",
                  foreground="#666666", wraplength=500).grid(row=14, column=0, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="API Key 由 Windows 当前用户 DPAPI 加密保存；代理配置仅应用到本软件。",
                  foreground="#666666", wraplength=500).grid(row=15, column=0, sticky="w", pady=(0, 7))
        self.test_status = tk.StringVar(value="可先测试网络连通性（免费，不检查密钥和图片模型）。")
        ttk.Label(frame, textvariable=self.test_status, wraplength=500, foreground="#555555").grid(
            row=16, column=0, sticky="w", pady=(0, 7))
        controls = ttk.Frame(frame)
        controls.grid(row=17, column=0, sticky="e")
        self.test_button = ttk.Button(controls, text="测试网络连接", command=self._test_connection)
        self.test_button.pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="取消", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(controls, text="保存配置", command=self._save).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_visibility()
        self.focus_force()

    def _update_proxy_field(self) -> None:
        self.proxy_entry.configure(state="normal" if self.network_mode.get() == "manual" else "disabled")

    def _test_connection(self) -> None:
        try:
            target = self.base_var.get().strip().rstrip("/")
            parts = urlsplit(target)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise ValueError("请先填写有效的 API Base URL")
            mode, address = validate_network_settings(self.network_mode.get(), self.proxy_var.get())
        except ValueError as exc:
            messagebox.showwarning("配置错误", str(exc), parent=self)
            return
        self.test_button.configure(state="disabled")
        self.test_status.set("正在检查系统代理并测试连接…（最多约 20 秒）")

        def worker() -> None:
            try:
                selection = select_proxy(target, mode, address)
                result = probe_connectivity(target, selection)
            except Exception as exc:
                result = (False, f"无法执行测试：{type(exc).__name__}")
            self._test_queue.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self.after(160, self._poll_test)

    def _poll_test(self) -> None:
        try:
            ok, detail = self._test_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists():
                self.after(160, self._poll_test)
            return
        self.test_button.configure(state="normal")
        self.test_status.set(("连接成功：" if ok else "连接失败：") + detail)

    def _save(self) -> None:
        try:
            base, model, key = validate_config(self.base_var.get(), self.model_var.get(), self.key_var.get())
            network_mode, proxy_url = validate_network_settings(self.network_mode.get(), self.proxy_var.get())
            thinking_mode = validate_thinking_mode(self.thinking_var.get())
            self.result = {"base_url": base, "model": model, "api_key": key,
                           "network_mode": network_mode, "proxy_url": proxy_url,
                           "thinking_mode": thinking_mode}
            save_config(self.result)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc), parent=self)


class GradingLauncher:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("560x285")
        self.root.minsize(560, 285)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.processes: list[subprocess.Popen] = []
        self.start_time: float | None = None
        self.config: dict[str, str] | None = None
        self.logs: list = []
        self.status = tk.StringVar(value="尚未启动")
        self.network_summary = ""
        container = ttk.Frame(root, padding=22)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="AI 阅卷助手", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Label(container, text="本地运行 · 通过浏览器打开阅卷工作台", foreground="#666666").pack(anchor="w")
        ttk.Label(container, textvariable=self.status, wraplength=450).pack(anchor="w", pady=(14, 14))
        buttons = ttk.Frame(container)
        buttons.pack(anchor="w")
        self.start_button = ttk.Button(buttons, text="启动并打开工作台", command=self.start)
        self.start_button.pack(side="left")
        ttk.Button(buttons, text="模型与网络配置", command=self.edit_config).pack(side="left", padx=(10, 0))
        ttk.Button(buttons, text="查看日志", command=self.open_logs).pack(side="left", padx=(10, 0))
        ttk.Button(buttons, text="退出", command=self.quit).pack(side="left", padx=(10, 0))
        ttk.Label(container, text="关闭此窗口时，本次启动的网页服务和评分服务会一起退出。", foreground="#777777").pack(anchor="w", pady=(18, 0))
        self.root.after(100, self._initial_start)

    def _initial_start(self) -> None:
        try:
            self.config = load_config()
        except Exception as exc:
            messagebox.showwarning("配置需要修复", f"无法读取当前用户配置：{exc}\n请重新填写。", parent=self.root)
        if self.config is None:
            self.edit_config()
        if self.config:
            self.start()

    def edit_config(self) -> None:
        was_running = bool(self.processes)
        dialog = ConfigDialog(self.root, self.config)
        self.root.wait_window(dialog)
        if dialog.result is not None:
            self.config = dialog.result
            if was_running:
                self.stop()
                self.start()
        elif self.config is None:
            self.status.set("尚未配置 API Key，请点击「模型配置」。")

    def open_logs(self) -> None:
        directory = user_data_dir() / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        os.startfile(directory)

    def start(self) -> None:
        if self.processes:
            if all(p.poll() is None for p in self.processes):
                webbrowser.open(WEB_URL)
                return
            self.stop()
        if not self.config:
            self.edit_config()
            if not self.config:
                return
        occupied = [str(port) for port in (API_PORT, WEB_PORT) if is_port_occupied(port)]
        if occupied:
            self.status.set(f"启动失败：端口 {', '.join(occupied)} 已被其他程序占用")
            messagebox.showerror("端口被占用", "无法启动：本机端口 " + ", ".join(occupied) + " 已在使用。\n请先关闭旧版阅卷助手或其他占用端口的程序。", parent=self.root)
            return
        base = install_dir()
        node = base / "bin" / "node" / "node.exe"
        api = base / "bin" / "grading-api" / "grading-api.exe"
        script = base / "app" / "server" / "index.js"
        missing = [str(path) for path in (node, api, script) if not path.is_file()]
        if missing:
            messagebox.showerror("文件不完整", "安装目录缺少以下文件：\n" + "\n".join(missing), parent=self.root)
            return
        try:
            selection = select_proxy(self.config["base_url"],
                                     self.config.get("network_mode", "auto"),
                                     self.config.get("proxy_url", ""))
        except ValueError as exc:
            messagebox.showerror("网络配置错误", str(exc), parent=self.root)
            return
        env = configure_child_environment(os.environ, selection)
        env.update({
            "OPENAI_API_KEY": self.config["api_key"],
            "OPENAI_BASE_URL": self.config["base_url"],
            "OPENAI_MODEL": self.config["model"],
            # Applied only to Qwen3 family by grading_api/openai_client.py.
            "GRADING_QWEN_THINKING_MODE": self.config.get("thinking_mode", "off"),
            # Thinking output may take longer; non-thinking still has a 60s ceiling.
            "GRADING_REQUEST_TIMEOUT_SECONDS": (
                "120" if self.config.get("thinking_mode", "off") == "on"
                and is_qwen_thinking_model(self.config["model"]) else "60"
            ),
            "PORT": str(WEB_PORT),
            "GRADING_API_HOST": "127.0.0.1",
            "GRADING_API_PORT": str(API_PORT),
            "GRADING_API_URL": API_URL,
            "GRADING_ALLOWED_ORIGINS": ",".join((WEB_URL, f"http://localhost:{WEB_PORT}")),
            "GRADING_API_TOKEN": secrets.token_urlsafe(32),
        })
        log_dir = user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        tag = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            for command, name, cwd in (
                ([str(api)], "grading-api", base / "app"),
                ([str(node), str(script)], "web", base / "app"),
            ):
                log = (log_dir / f"{name}-{tag}.log").open("a", encoding="utf-8")
                self.logs.append(log)
                self.processes.append(subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags))
        except Exception as exc:
            self.stop()
            messagebox.showerror("启动失败", str(exc), parent=self.root)
            return
        self.network_summary = (selection.source +
                                (f"：{selection.proxy_url}" if selection.proxy_url else "：直连"))
        thinking_label = ("开启" if self.config.get("thinking_mode", "off") == "on" else "关闭")
        if not is_qwen_thinking_model(self.config["model"]):
            thinking_label = "不适用（非 Qwen3 模型）"
        self.status.set(f"网络：{self.network_summary}；深度思考：{thinking_label}；正在启动服务…")
        self.start_button.configure(state="disabled")
        self.start_time = time.monotonic()
        self.root.after(450, self._check_ready)

    def _check_ready(self) -> None:
        if not self.processes:
            return
        if any(p.poll() is not None for p in self.processes):
            self._startup_failed("某个后台服务已意外退出")
            return
        try:
            backend = get_json(API_URL + "/health")
            frontend = get_json(WEB_URL + "/api/health")
            if (backend.get("status") == "ok"
                    and frontend.get("service") == "exam-grading-assistant"
                    and frontend.get("gradingApiBaseUrl") == API_URL
                    and frontend.get("gradingApi", {}).get("ok")):
                self.status.set("服务已启动。网络：" + self.network_summary
                                + "。深度思考：" + thinking_label_for_config(self.config)
                                + "。工作台：" + WEB_URL)
                self.start_button.configure(state="normal", text="打开工作台")
                webbrowser.open(WEB_URL)
                return
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            pass
        if self.start_time and time.monotonic() - self.start_time >= START_TIMEOUT_SECONDS:
            self._startup_failed("服务在规定时间内未能就绪")
        else:
            self.root.after(650, self._check_ready)

    def _startup_failed(self, reason: str) -> None:
        self.stop()
        self.status.set("启动失败：" + reason)
        self.start_button.configure(state="normal", text="重试启动")
        messagebox.showerror("启动失败", reason + "。\n可点击「查看日志」排查，或修改模型配置后重试。", parent=self.root)

    def stop(self) -> None:
        for process in reversed(self.processes):
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
        self.processes.clear()
        for log in self.logs:
            try:
                log.close()
            except OSError:
                pass
        self.logs.clear()
        self.start_button.configure(state="normal", text="启动并打开工作台")

    def quit(self) -> None:
        self.stop()
        self.root.destroy()


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("此启动器只支持 Windows 10/11")
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    GradingLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
