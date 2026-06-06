#!/usr/bin/env python3
"""
Análise Estatística e Geração de Gráficos Corrigidos (Escala Log)
Redes de Computadores II - UFPI 2026-1
Aluno: Antonio Lucas Figueredo Silva | Matrícula: 20239042538
"""

import json
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Salva os arquivos na mesma pasta onde o script for executado
OUTPUT_DIR = "."

# Configurações Visuais
COLORS = {"tcp": "#2196F3", "rudp": "#FF5722"}
SCENARIOS = ["scenario_A", "scenario_B", "scenario_C"]
SC_LABELS = {
    "scenario_A": "Cenário A\n0% perda / 10ms",
    "scenario_B": "Cenário B\n5% perda / 50ms",
    "scenario_C": "Cenário C\n10% perda / 100ms",
}

def load_results() -> dict:
    path = "all_results.json"
    if not os.path.exists(path):
        raise FileNotFoundError(f"O arquivo {path} nao foi encontrado nesta pasta!")
    with open(path, "r") as f:
        return json.load(f)

def compute_stats(values: list) -> dict:
    arr = np.array(values)
    return {
        "min":  float(arr.min()),
        "max":  float(arr.max()),
        "mean": float(arr.mean()),
        "std":  float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "n":    len(arr),
    }

# ── 1. Gráfico de Barras Comparativas ─────────────────────────────────────────
def plot_bar_comparison(results: dict):
    print("-> Gerando Gráfico 1: Barras Comparativas (Com Escala Log)...")
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(SCENARIOS))
    width = 0.35

    tcp_means  = [compute_stats(results[k]["tcp"])["mean"]  for k in SCENARIOS]
    tcp_stds   = [compute_stats(results[k]["tcp"])["std"]   for k in SCENARIOS]
    rudp_means = [compute_stats(results[k]["rudp"])["mean"] for k in SCENARIOS]
    rudp_stds  = [compute_stats(results[k]["rudp"])["std"]  for k in SCENARIOS]

    bars_tcp  = ax.bar(x - width/2, tcp_means,  width, yerr=tcp_stds, label="TCP", color=COLORS["tcp"], alpha=0.85, capsize=6)
    bars_rudp = ax.bar(x + width/2, rudp_means, width, yerr=rudp_stds, label="R-UDP (S&W)", color=COLORS["rudp"], alpha=0.85, capsize=6)

    for bar in list(bars_tcp) + list(bars_rudp):
        h = bar.get_height()
        # Ajuste dinâmico de posição do texto por causa do comportamento da escala log
        offset = h * 1.1 if h < 1 else h + (h * 0.1)
        ax.text(bar.get_x() + bar.get_width() / 2, offset, f"{h:.4f}", ha="center", va="bottom", fontsize=8, fontweight="bold")

    ax.set_ylabel("Throughput (Mbps) - Escala Log", fontsize=11)
    ax.set_title("Comparação de Throughput Médio: TCP vs R-UDP\n(barras de erro = desvio padrão)", fontsize=12, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([SC_LABELS[s] for s in SCENARIOS], fontsize=9)
    ax.set_yscale('log') 
    ax.legend()
    ax.grid(True, which="both", ls="--", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "01_bar_comparison.png"), dpi=200)
    plt.close()

# ── 2. Boxplot ────────────────────────────────────────────────────────────────
def plot_boxplot(results: dict):
    print("-> Gerando Gráfico 2: Boxplot...")
    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    fig.suptitle("Distribuição do Throughput por Cenário: TCP vs R-UDP", fontsize=13, fontweight="bold")
    
    for i, sc in enumerate(SCENARIOS):
        ax = axes[i]
        bp = ax.boxplot([results[sc]["tcp"], results[sc]["rudp"]], labels=["TCP", "R-UDP"], patch_artist=True, medianprops={"color": "black", "linewidth": 2})
        bp["boxes"][0].set_facecolor(COLORS["tcp"])
        bp["boxes"][1].set_facecolor(COLORS["rudp"])
        ax.set_yscale('log') 
        ax.set_title(SC_LABELS[sc], fontsize=10, fontweight="bold")
        ax.set_ylabel("Throughput (Mbps) - Escala Log" if i == 0 else "")
        ax.grid(True, which="both", ls="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "02_boxplot.png"), dpi=200)
    plt.close()

# ── 3. Linha de Throughput por Rodada ──────────────────────────────────────────
def plot_runs_line(results: dict):
    print("-> Gerando Gráfico 3: Linha por Rodada...")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Throughput por Rodada: TCP vs R-UDP", fontsize=13, fontweight="bold")
    
    for i, sc in enumerate(SCENARIOS):
        ax = axes[i]
        tcp_data = results[sc]["tcp"]
        rudp_data = results[sc]["rudp"]
        ax.plot(range(1, len(tcp_data) + 1), tcp_data, color=COLORS["tcp"], marker="o", linewidth=1.5, label="TCP")
        ax.plot(range(1, len(rudp_data) + 1), rudp_data, color=COLORS["rudp"], marker="s", linewidth=1.5, label="R-UDP")
        ax.set_yscale('log') 
        ax.set_title(SC_LABELS[sc], fontsize=10, fontweight="bold")
        ax.set_xlabel("Rodada")
        ax.set_ylabel("Throughput (Mbps) - Escala Log" if i == 0 else "")
        ax.legend(fontsize=9)
        ax.grid(True, which="both", ls="--", alpha=0.3)
        ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "03_runs_line.png"), dpi=200)
    plt.close()

# ── 4. Tabela Estatística Visual e CSV ─────────────────────────────────────────
def plot_stats_table(results: dict):
    print("-> Gerando Gráfico 4: Tabela Estatística Visual e CSV...")
    rows = []
    for sc in SCENARIOS:
        for proto in ["tcp", "rudp"]:
            s = compute_stats(results[sc][proto])
            rows.append({
                "Cenário": SC_LABELS[sc].replace("\n", " "),
                "Protocolo": "TCP" if proto == "tcp" else "R-UDP",
                "N": s["n"],
                "Mín (Mbps)": f"{s['min']:.4f}",
                "Méd (Mbps)": f"{s['mean']:.4f}",
                "Máx (Mbps)": f"{s['max']:.4f}",
                "DP (Mbps)": f"{s['std']:.4f}",
            })
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUTPUT_DIR, "stats_table.csv"), index=False)

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.axis("off")
    tbl = ax.table(cellText=df.values, colLabels=df.columns, cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 1.4)
    for j in range(len(df.columns)):
        tbl[0, j].set_facecolor("#37474F")
        tbl[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(1, len(df) + 1):
        color = "#E3F2FD" if df.iloc[i-1]["Protocolo"] == "TCP" else "#FBE9E7"
        for j in range(len(df.columns)):
            tbl[i, j].set_facecolor(color)
    ax.set_title("Estatísticas de Throughput – TCP vs R-UDP", fontsize=12, fontweight="bold", pad=15)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "04_stats_table.png"), dpi=200, bbox_inches="tight")
    plt.close()

# ── 5. Curva de Degradação Relativa ───────────────────────────────────────────
def plot_degradation(results: dict):
    print("-> Gerando Gráfico 5: Curva de Degradação Relativa...")
    fig, ax = plt.subplots(figsize=(9, 5))
    for proto, label in [("tcp", "TCP"), ("rudp", "R-UDP")]:
        means = [compute_stats(results[s][proto])["mean"] for s in SCENARIOS]
        ax.plot(["A", "B", "C"], means, marker="o", linewidth=2.5, markersize=8, color=COLORS[proto], label=label)
        for i, sc in enumerate(["A", "B", "C"]):
            offset_y = means[i] * 1.1 if proto == "tcp" else means[i] * 1.2
            ax.annotate(f"{means[i]:.4f}", (sc, means[i]), textcoords="offset points", xytext=(5, 5), fontsize=9, color=COLORS[proto], fontweight='bold')
    ax.set_yscale('log') 
    ax.set_xlabel("Cenário", fontsize=11)
    ax.set_ylabel("Throughput Médio (Mbps) - Escala Log", fontsize=11)
    ax.set_title("Degradação do Throughput por Cenário de Rede", fontsize=12, fontweight="bold", pad=15)
    ax.set_xticks(["A", "B", "C"])
    ax.set_xticklabels(["Cenário A", "Cenário B", "Cenário C"])
    ax.legend()
    ax.grid(True, which="both", ls="--", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "05_degradation.png"), dpi=200)
    plt.close()

# ── Execução Principal ────────────────────────────────────────────────────────
def main():
    try:
        results = load_results()
        print("Resultados carregados com sucesso! Iniciando plotagem...")
        
        plot_bar_comparison(results)
        plot_boxplot(results)
        plot_runs_line(results)
        plot_stats_table(results)
        plot_degradation(results)
        
        print("\n>>> SUCESSO ABSOLUTO! Todos os 5 gráficos foram salvos na pasta atual! <<<")
    except Exception as e:
        print(f"\n[ERRO AO EXECUTAR]: {e}")

if __name__ == "__main__":
    main()