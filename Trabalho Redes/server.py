"""
Servidor de Transferência de Arquivos - TCP e R-UDP (Stop-and-Wait)
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

# ── Configurações ──────────────────────────────────────────────────────────────
X_CUSTOM_AUTH = "60a5a6453a16bd24dc7054ec50acc9c664b00e596f898c3005275a5242bfe7aa"
CHUNK_SIZE     = 1400          # bytes de dados por pacote R-UDP
TIMEOUT        = 2.0           # segundos para retransmissão
MAX_RETRIES    = 20
LOG_DIR        = "/app/logs"

# ── Formato do cabeçalho R-UDP ─────────────────────────────────────────────────
# | seq (4B) | flags (1B) | checksum (4B) | auth_len (2B) | data_len (2B) | auth | data |
# flags: 0x01=DATA  0x02=ACK  0x04=SYN  0x08=FIN
HDR_FMT  = "!IBI HH"   # seq, flags, checksum, auth_len, data_len
HDR_SIZE = struct.calcsize(HDR_FMT)   # 13 bytes fixos

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
        logging.FileHandler(os.path.join(LOG_DIR, "server.log")),
    ],
)
log = logging.getLogger("server")


# ── Utilitários R-UDP ──────────────────────────────────────────────────────────

def calc_checksum(data: bytes) -> int:
    """CRC-32 simples sobre os dados."""
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def build_packet(seq: int, flags: int, payload: bytes = b"") -> bytes:
    auth   = X_CUSTOM_AUTH.encode()
    csum   = calc_checksum(payload)
    header = struct.pack(HDR_FMT, seq, flags, csum, len(auth), len(payload))
    return header + auth + payload


def parse_packet(raw: bytes):
    """Retorna (seq, flags, auth, payload) ou None se inválido."""
    if len(raw) < HDR_SIZE:
        return None
    seq, flags, csum, auth_len, data_len = struct.unpack_from(HDR_FMT, raw)
    offset = HDR_SIZE
    auth    = raw[offset: offset + auth_len]
    offset += auth_len
    payload = raw[offset: offset + data_len]
    if calc_checksum(payload) != csum:
        log.warning(f"Checksum inválido no pacote seq={seq}")
        return None
    return seq, flags, auth.decode(errors="replace"), payload


def send_ack(sock, addr, seq: int):
    pkt = build_packet(seq, FLAG_ACK)
    sock.sendto(pkt, addr)


# ── Servidor TCP ───────────────────────────────────────────────────────────────

def run_tcp_server(host: str, port: int, save_dir: str):
    log.info(f"[TCP] Aguardando conexões em {host}:{port}")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)

    while True:
        conn, addr = srv.accept()
        log.info(f"[TCP] Conexão de {addr}")
        try:
            _tcp_receive_file(conn, addr, save_dir)
        except Exception as e:
            log.error(f"[TCP] Erro: {e}")
        finally:
            conn.close()


def _tcp_receive_file(conn, addr, save_dir):
    # 1. Recebe header JSON com metadados
    raw_len = conn.recv(4)
    meta_len = struct.unpack("!I", raw_len)[0]
    meta_raw = conn.recv(meta_len)
    meta     = json.loads(meta_raw.decode())

    auth_received = meta.get("X-Custom-Auth", "")
    filename      = os.path.basename(meta.get("filename", "received_tcp.bin"))
    filesize      = meta.get("filesize", 0)
    log.info(f"[TCP] Arquivo: {filename} | Tamanho: {filesize} B | Auth: {auth_received[:16]}...")

    # 2. Confirma metadados
    conn.sendall(b"OK")

    # 3. Recebe dados
    t_start   = time.time()
    received  = 0
    out_path  = os.path.join(save_dir, filename)
    with open(out_path, "wb") as f:
        while received < filesize:
            chunk = conn.recv(min(65536, filesize - received))
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)

    elapsed    = time.time() - t_start
    throughput = (received * 8) / elapsed / 1_000_000 if elapsed > 0 else 0

    # 4. Envia confirmação final
    result = json.dumps({
        "status":     "OK",
        "received":   received,
        "elapsed":    round(elapsed, 6),
        "throughput": round(throughput, 4),
    }).encode()
    conn.sendall(struct.pack("!I", len(result)) + result)

    log.info(f"[TCP] Concluído: {received} B em {elapsed:.3f}s | {throughput:.4f} Mbps")
    _write_log(LOG_DIR, "tcp", elapsed, throughput, received)


# ── Servidor R-UDP ─────────────────────────────────────────────────────────────

def run_rudp_server(host: str, port: int, save_dir: str):
    log.info(f"[R-UDP] Aguardando datagramas em {host}:{port}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(None)

    while True:
        try:
            _rudp_receive_file(sock, save_dir)
        except Exception as e:
            log.error(f"[R-UDP] Erro: {e}")


def _rudp_receive_file(sock, save_dir):
    # 1. Aguarda SYN com metadados
    while True:
        raw, addr = sock.recvfrom(65535)
        parsed = parse_packet(raw)
        if parsed is None:
            continue
        seq, flags, auth, payload = parsed
        if flags & FLAG_SYN:
            break

    meta     = json.loads(payload.decode())
    filename = os.path.basename(meta.get("filename", "received_rudp.bin"))
    filesize = meta.get("filesize", 0)
    log.info(f"[R-UDP] SYN de {addr} | Arquivo: {filename} | {filesize} B")

    # Confirma SYN
    send_ack(sock, addr, seq)

    # 2. Recebe blocos Stop-and-Wait
    expected_seq = 1
    t_start      = time.time()
    received     = 0
    out_path     = os.path.join(save_dir, filename)

    with open(out_path, "wb") as f:
        while True:
            sock.settimeout(10.0)
            try:
                raw, addr2 = sock.recvfrom(65535)
            except socket.timeout:
                log.warning("[R-UDP] Timeout aguardando dados")
                break

            parsed = parse_packet(raw)
            if parsed is None:
                continue
            seq, flags, auth, payload = parsed

            if flags & FLAG_FIN:
                send_ack(sock, addr2, seq)
                log.info("[R-UDP] FIN recebido")
                break

            if flags & FLAG_DATA:
                if seq == expected_seq:
                    f.write(payload)
                    received    += len(payload)
                    expected_seq += 1
                    send_ack(sock, addr2, seq)
                else:
                    # Duplicado ou fora de ordem: re-envia ACK do último recebido
                    send_ack(sock, addr2, expected_seq - 1)

    elapsed    = time.time() - t_start
    throughput = (received * 8) / elapsed / 1_000_000 if elapsed > 0 else 0
    log.info(f"[R-UDP] Concluído: {received} B em {elapsed:.3f}s | {throughput:.4f} Mbps")
    _write_log(LOG_DIR, "rudp", elapsed, throughput, received)


# ── Log de resultados ──────────────────────────────────────────────────────────

def _write_log(log_dir, proto, elapsed, throughput, received):
    path = os.path.join(log_dir, f"{proto}_results.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps({
            "timestamp":  time.time(),
            "protocol":   proto,
            "elapsed_s":  round(elapsed, 6),
            "throughput": round(throughput, 6),
            "bytes":      received,
        }) + "\n")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor Dual TCP / R-UDP")
    parser.add_argument("--host",     default="0.0.0.0")
    parser.add_argument("--tcp-port", type=int, default=5000)
    parser.add_argument("--rudp-port", type=int, default=5001, dest="rudp_port")
    parser.add_argument("--save-dir", default="/app/received")
    args = parser.parse_args()

    os.makedirs(args.save_dir, exist_ok=True)

    import threading
    
    # Cria as threads para rodar os dois servidores ao mesmo tempo
    t_tcp = threading.Thread(target=run_tcp_server, args=(args.host, args.tcp_port, args.save_dir), daemon=True)
    t_rudp = threading.Thread(target=run_rudp_server, args=(args.host, args.rudp_port, args.save_dir), daemon=True)
    
    log.info("Iniciando servidores em paralelo...")
    t_tcp.start()
    t_rudp.start()
    
    # Mantém a thread principal viva
    while True:
        time.sleep(1)