"""
Cliente de Transferência de Arquivos - TCP e R-UDP (Stop-and-Wait)
Redes de Computadores II - UFPI 2026-1
Aluno: Antonio Lucas Figueredo Silva
Matrícula: 20239042538
X-Custom-Auth: 60a5a6453a16bd24dc7054ec50acc9c664b00e596f898c3005275a5242bfe7aa
"""

import socket
import struct
import hashlib
import os
import time
import logging
import argparse
import json
import zlib

# ── Configurações ──────────────────────────────────────────────────────────────
X_CUSTOM_AUTH = "60a5a6453a16bd24dc7054ec50acc9c664b00e596f898c3005275a5242bfe7aa"
CHUNK_SIZE    = 1400
TIMEOUT       = 2.0
MAX_RETRIES   = 20
LOG_DIR       = "/app/logs"

HDR_FMT  = "!IBI HH"                                                                                                                       
HDR_SIZE = struct.calcsize(HDR_FMT)

FLAG_DATA = 0x01
FLAG_ACK  = 0x02
FLAG_SYN  = 0x04
FLAG_FIN  = 0x08

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "client.log")),
    ],
)
log = logging.getLogger("client")


# ── Utilitários R-UDP ──────────────────────────────────────────────────────────

def calc_checksum(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def build_packet(seq: int, flags: int, payload: bytes = b"") -> bytes:
    auth   = X_CUSTOM_AUTH.encode()
    csum   = calc_checksum(payload)
    header = struct.pack(HDR_FMT, seq, flags, csum, len(auth), len(payload))
    return header + auth + payload


def parse_packet(raw: bytes):
    if len(raw) < HDR_SIZE:
        return None
    seq, flags, csum, auth_len, data_len = struct.unpack_from(HDR_FMT, raw)
    offset  = HDR_SIZE
    auth    = raw[offset: offset + auth_len]
    offset += auth_len
    payload = raw[offset: offset + data_len]
    if calc_checksum(payload) != csum:
        return None
    return seq, flags, auth.decode(errors="replace"), payload


# ── Cliente TCP ────────────────────────────────────────────────────────────────

def send_tcp(host: str, port: int, filepath: str) -> dict:
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    log.info(f"[TCP] Enviando '{filename}' ({filesize} B) para {host}:{port}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))

    # 1. Envia metadados
    meta = json.dumps({
        "X-Custom-Auth": X_CUSTOM_AUTH,
        "filename":      filename,
        "filesize":      filesize,
    }).encode()
    sock.sendall(struct.pack("!I", len(meta)) + meta)

    # 2. Aguarda confirmação
    ack = sock.recv(2)
    if ack != b"OK":
        raise RuntimeError("Servidor não confirmou metadados")

    # 3. Envia arquivo
    t_start = time.time()
    sent    = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sock.sendall(chunk)
            sent += len(chunk)

    # 4. Recebe resultado do servidor
    raw_len = sock.recv(4)
    res_len = struct.unpack("!I", raw_len)[0]
    result  = json.loads(sock.recv(res_len).decode())
    sock.close()

    elapsed    = result["elapsed"]
    throughput = result["throughput"]
    log.info(f"[TCP] OK: {sent} B em {elapsed:.3f}s | {throughput:.4f} Mbps")
    _write_log(LOG_DIR, "tcp", elapsed, throughput, sent)
    return result


# ── Cliente R-UDP (Stop-and-Wait) ──────────────────────────────────────────────

def send_rudp(host: str, port: int, filepath: str) -> dict:
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    log.info(f"[R-UDP] Enviando '{filename}' ({filesize} B) para {host}:{port}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    addr = (host, port)

    # 1. SYN com metadados
    meta    = json.dumps({
        "X-Custom-Auth": X_CUSTOM_AUTH,
        "filename":      filename,
        "filesize":      filesize,
    }).encode()
    syn_pkt = build_packet(0, FLAG_SYN, meta)

    for attempt in range(MAX_RETRIES):
        sock.sendto(syn_pkt, addr)
        try:
            raw, _ = sock.recvfrom(65535)
            parsed = parse_packet(raw)
            if parsed and (parsed[1] & FLAG_ACK) and parsed[0] == 0:
                log.info("[R-UDP] SYN-ACK recebido")
                break
        except socket.timeout:
            log.warning(f"[R-UDP] SYN timeout (tentativa {attempt+1})")
    else:
        raise RuntimeError("Sem resposta ao SYN após máximo de tentativas")

    # 2. Envia dados Stop-and-Wait
    seq     = 1
    t_start = time.time()
    sent    = 0
    retransmissions = 0

    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            pkt = build_packet(seq, FLAG_DATA, chunk)

            for attempt in range(MAX_RETRIES):
                sock.sendto(pkt, addr)
                try:
                    raw, _ = sock.recvfrom(65535)
                    parsed = parse_packet(raw)
                    if parsed and (parsed[1] & FLAG_ACK) and parsed[0] == seq:
                        break
                except socket.timeout:
                    log.warning(f"[R-UDP] Timeout seq={seq} (tentativa {attempt+1})")
                    retransmissions += 1
            else:
                raise RuntimeError(f"Falha ao confirmar seq={seq}")

            sent += len(chunk)
            seq  += 1

    # 3. FIN
    fin_pkt = build_packet(seq, FLAG_FIN)
    for _ in range(MAX_RETRIES):
        sock.sendto(fin_pkt, addr)
        try:
            raw, _ = sock.recvfrom(65535)
            parsed = parse_packet(raw)
            if parsed and (parsed[1] & FLAG_ACK):
                break
        except socket.timeout:
            pass

    elapsed    = time.time() - t_start
    throughput = (sent * 8) / elapsed / 1_000_000 if elapsed > 0 else 0
    log.info(
        f"[R-UDP] OK: {sent} B em {elapsed:.3f}s | {throughput:.4f} Mbps | "
        f"Retransmissões: {retransmissions}"
    )

    result = {
        "status":           "OK",
        "bytes":            sent,
        "elapsed":          round(elapsed, 6),
        "throughput":       round(throughput, 6),
        "retransmissions":  retransmissions,
    }
    _write_log(LOG_DIR, "rudp", elapsed, throughput, sent)
    sock.close()
    return result


# ── Log ────────────────────────────────────────────────────────────────────────

def _write_log(log_dir, proto, elapsed, throughput, sent):
    path = os.path.join(log_dir, f"{proto}_results.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({
            "":  time.time(),
            "prottimestampocol":   proto,
            "elapsed_s":  round(elapsed, 6),
            "throughput": round(throughput, 6),
            "bytes":      sent,
        }) + "\n")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente TCP / R-UDP")
    parser.add_argument("--mode",  choices=["tcp", "rudp"], required=True)
    parser.add_argument("--host",  default="server")
    parser.add_argument("--port",  type=int, default=5000)
    parser.add_argument("--file",  required=True, help="Arquivo a enviar")
    args = parser.parse_args()

    if args.mode == "tcp":
        send_tcp(args.host, args.port, args.file)
    else:
        send_rudp(args.host, args.port, args.file)
