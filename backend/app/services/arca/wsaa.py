from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from .config import ArcaConfig
from .models import ArcaAuthTicket


class WsaaError(RuntimeError):
    pass


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(root: ET.Element, name: str) -> str:
    for element in root.iter():
        if local_name(element.tag) == name:
            return element.text or ""
    return ""


def build_tra(service: str) -> str:
    now = datetime.now(timezone.utc)
    unique_id = str(int(time.time()))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{unique_id}</uniqueId>
    <generationTime>{utc_iso(now - timedelta(minutes=10))}</generationTime>
    <expirationTime>{utc_iso(now + timedelta(hours=12))}</expirationTime>
  </header>
  <service>{escape(service)}</service>
</loginTicketRequest>"""


def is_ticket_valid(ticket: ArcaAuthTicket) -> bool:
    try:
        expiration = datetime.fromisoformat(ticket.expiration_time.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expiration > datetime.now(timezone.utc) + timedelta(minutes=5)


def load_cached_ticket(config: ArcaConfig) -> ArcaAuthTicket | None:
    path = Path(config.token_cache_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ticket = ArcaAuthTicket(token=str(data["token"]), sign=str(data["sign"]), expiration_time=str(data["expiration_time"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return ticket if is_ticket_valid(ticket) else None


def save_cached_ticket(config: ArcaConfig, ticket: ArcaAuthTicket) -> None:
    path = Path(config.token_cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": ticket.token, "sign": ticket.sign, "expiration_time": ticket.expiration_time}), encoding="utf-8")
    path.chmod(0o600)


def sign_tra(config: ArcaConfig, tra: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        tra_path = Path(tmpdir) / "tra.xml"
        cms_path = Path(tmpdir) / "tra.cms"
        tra_path.write_text(tra, encoding="utf-8")
        command = [
            "openssl",
            "smime",
            "-sign",
            "-in",
            str(tra_path),
            "-out",
            str(cms_path),
            "-signer",
            config.cert_path,
            "-inkey",
            config.key_path,
            "-outform",
            "DER",
            "-nodetach",
        ]
        if config.key_password:
            command.extend(["-passin", f"pass:{config.key_password}"])
        result = subprocess.run(command, capture_output=True, text=True, timeout=config.timeout_seconds)
        if result.returncode != 0:
            raise WsaaError((result.stderr or "Error firmando TRA WSAA").strip())
        return base64.b64encode(cms_path.read_bytes()).decode("ascii")


def login_cms(config: ArcaConfig, cms: str) -> ArcaAuthTicket:
    envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <soapenv:Header/>
  <soapenv:Body>
    <wsaa:loginCms>
      <wsaa:in0>{escape(cms)}</wsaa:in0>
    </wsaa:loginCms>
  </soapenv:Body>
</soapenv:Envelope>"""
    request = urllib.request.Request(
        config.wsaa_url,
        data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            root = ET.fromstring(body)
            fault = child_text(root, "faultstring") or child_text(root, "exception")
        except ET.ParseError:
            fault = body.strip()
        message = fault or str(error)
        raise WsaaError(f"Error WSAA {error.code}: {message}") from error
    except urllib.error.URLError as error:
        raise WsaaError(f"Error WSAA: {error}") from error

    root = ET.fromstring(body)
    login_return = child_text(root, "loginCmsReturn")
    if not login_return:
        fault = child_text(root, "faultstring") or "WSAA no devolvio token"
        raise WsaaError(fault)
    ticket_root = ET.fromstring(login_return)
    token = child_text(ticket_root, "token")
    sign = child_text(ticket_root, "sign")
    expiration_time = child_text(ticket_root, "expirationTime")
    if not token or not sign or not expiration_time:
        raise WsaaError("Respuesta WSAA incompleta")
    return ArcaAuthTicket(token=token, sign=sign, expiration_time=expiration_time)


def get_auth_ticket(config: ArcaConfig) -> ArcaAuthTicket:
    cached = load_cached_ticket(config)
    if cached:
        return cached
    ticket = login_cms(config, sign_tra(config, build_tra(config.service)))
    save_cached_ticket(config, ticket)
    return ticket
