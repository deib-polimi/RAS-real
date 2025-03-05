import os
import re
import argparse
import scipy.io
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Parametri per le dimensioni dei font
FONT_SIZE_AXIS_LABELS = 30
FONT_SIZE_TICKS = 30
FONT_SIZE_LEGEND = 22
FONT_WEIGHT = 'bold'

# Parametri per il grafico
FIGURE_SIZE = (10, 6)
LINE_WIDTH = 2
LINE_ALPHA = 1.0
GRID_ALPHA = 0.5
VERTICAL_LINE_ALPHA = 0.5

# Parametri per il processamento dei dati
MOVING_AVERAGE_WINDOW = 30
POINTS_TO_REMOVE = 20

def extract_keys(folder_name):
    """
    Estrae workload, controller e application dal nome della cartella.
    Il pattern atteso è: exp-<workload>_<controller>-aws-<application>-<timestamp>
    """
    pattern = r"exp-([^_]+)_([^-]+)-aws-([^\\-]+)-.*"
    m = re.match(pattern, folder_name)
    if m:
        workload = m.group(1)
        controller = m.group(2)
        application = m.group(3)
        return workload, controller, application
    return None, None, None

def load_data(mat_file):
    """Carica i dati da data.mat e restituisce time, cores, rts, users."""
    data = scipy.io.loadmat(mat_file)
    cores = np.array(data.get('cores')).flatten()
    rts = np.array(data.get('rts')).flatten()
    users = np.array(data.get('users')).flatten()
    time = np.array(data.get('time')).flatten() if 'time' in data else np.arange(len(cores))
    
    # Ordina i dati in base al tempo
    sort_idx = np.argsort(time)
    time = time[sort_idx]
    cores = cores[sort_idx]
    rts = rts[sort_idx]
    users = users[sort_idx]
    
    # Applica media mobile
    cores = np.convolve(cores, np.ones(MOVING_AVERAGE_WINDOW)/MOVING_AVERAGE_WINDOW, mode='same')
    rts = np.convolve(rts, np.ones(MOVING_AVERAGE_WINDOW)/MOVING_AVERAGE_WINDOW, mode='same')
    users = np.convolve(users, np.ones(MOVING_AVERAGE_WINDOW)/MOVING_AVERAGE_WINDOW, mode='same')
    
    # Rimuovi gli ultimi punti spuri
    time = time[:-POINTS_TO_REMOVE]
    cores = cores[:-POINTS_TO_REMOVE]
    rts = rts[:-POINTS_TO_REMOVE]
    users = users[:-POINTS_TO_REMOVE]
    
    return time, cores, rts, users

def main(input_dir):
    # Imposta lo stile Seaborn
    sns.set_style("whitegrid")
    sns.set_context("notebook", font_scale=1.2)
    
    # Crea la directory plots se non esiste
    plots_dir = os.path.join(input_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    
    # Configurazione dei colori e stili
    colors = ['#1f77b4', '#d62728', '#2ca02c']  # Blu, Rosso, Verde
    line_styles = ['-', '--', '-.']
    controller_map = {"ct": "ScaleX", "qn": "QNCTRL", "robust": "ROBUST"}
    
    # Ordine desiderato dei controller
    controller_order = ["ScaleX", "QNCTRL", "ROBUST"]
    
    groups = {}
    event_time = 300  # evento rumoroso a time = 300
    
    # Raggruppa le sottocartelle che rispettano il pattern e salva anche il controller
    for entry in os.listdir(input_dir):
        folder_path = os.path.join(input_dir, entry)
        if os.path.isdir(folder_path) and entry.startswith("exp-"):
            workload, controller, application = extract_keys(entry)
            if workload and controller and application:
                key = (workload, application)
                groups.setdefault(key, []).append((folder_path, controller))
    
    if not groups:
        print("Nessuna cartella con il pattern atteso trovato.")
        return
    
    # Per ogni gruppo genera 3 grafici separati
    for (workload, application), entries in groups.items():
        print(f"\nProcessing {workload} - {application}")
        # Dizionari per raccogliere i dati per ciascun controller
        data_cores = {}
        data_rts = {}
        data_users = {}
        time_data = {}
        
        for folder, controller in entries:
            mat_file = os.path.join(folder, 'data.mat')
            if not os.path.exists(mat_file):
                print(f"File {mat_file} non trovato. Salto questo esperimento.")
                continue
            time, cores, rts, users = load_data(mat_file)
            time_data[controller] = time
            data_cores[controller] = cores
            data_rts[controller] = rts
            data_users[controller] = users
        
        if not time_data:
            continue

        # Ordina i controller secondo l'ordine desiderato
        sorted_controllers = sorted(time_data.keys(), 
                                 key=lambda x: controller_order.index(controller_map.get(x.lower(), x)))

        # Grafico per Core Utilization
        plt.figure(figsize=FIGURE_SIZE)
        for idx, controller in enumerate(sorted_controllers):
            label = controller_map.get(controller.lower(), controller)
            plt.plot(time_data[controller], data_cores[controller], 
                    label=label, color=colors[idx], linestyle=line_styles[idx],
                    linewidth=LINE_WIDTH, alpha=LINE_ALPHA)
        plt.axvline(event_time, color='gray', linestyle='--', alpha=VERTICAL_LINE_ALPHA)
        plt.xlabel("Time (s)", fontsize=FONT_SIZE_AXIS_LABELS, fontweight=FONT_WEIGHT)
        plt.ylabel("Number of Cores", fontsize=FONT_SIZE_AXIS_LABELS, fontweight=FONT_WEIGHT)
        plt.xticks(fontsize=FONT_SIZE_TICKS)
        plt.yticks(fontsize=FONT_SIZE_TICKS)
        plt.legend(loc='upper left', frameon=True, fancybox=True, shadow=True, fontsize=FONT_SIZE_LEGEND)
        plt.grid(True, alpha=GRID_ALPHA)
        plt.savefig(os.path.join(plots_dir, f"Core_Utilization_{workload}_{application}.pdf"), bbox_inches='tight')
        plt.close()

        # Grafico per Response Times
        plt.figure(figsize=FIGURE_SIZE)
        for idx, controller in enumerate(sorted_controllers):
            label = controller_map.get(controller.lower(), controller)
            plt.plot(time_data[controller], data_rts[controller], 
                    label=label, color=colors[idx], linestyle=line_styles[idx],
                    linewidth=LINE_WIDTH, alpha=LINE_ALPHA)
        plt.axvline(event_time, color='gray', linestyle='--', alpha=VERTICAL_LINE_ALPHA)
        plt.axhline(0.25, color='red', linestyle='--', alpha=VERTICAL_LINE_ALPHA)
        plt.xlabel("Time (s)", fontsize=FONT_SIZE_AXIS_LABELS, fontweight=FONT_WEIGHT)
        plt.ylabel("Response Time (s)", fontsize=FONT_SIZE_AXIS_LABELS, fontweight=FONT_WEIGHT)
        plt.xticks(fontsize=FONT_SIZE_TICKS)
        plt.yticks(fontsize=FONT_SIZE_TICKS)
        plt.legend(loc='upper left', frameon=True, fancybox=True, shadow=True, fontsize=FONT_SIZE_LEGEND)
        plt.grid(True, alpha=GRID_ALPHA)
        plt.savefig(os.path.join(plots_dir, f"Response_Times_{workload}_{application}.pdf"), bbox_inches='tight')
        plt.close()

        # Grafico per User Requests
        plt.figure(figsize=FIGURE_SIZE)
        first_controller = sorted_controllers[0]  # Usa il primo controller ordinato
        plt.plot(time_data[first_controller], data_users[first_controller], 
                color=colors[0], linewidth=LINE_WIDTH, alpha=LINE_ALPHA)
        plt.xlabel("Time (s)", fontsize=FONT_SIZE_AXIS_LABELS, fontweight=FONT_WEIGHT)
        plt.ylabel("Number of Requests", fontsize=FONT_SIZE_AXIS_LABELS, fontweight=FONT_WEIGHT)
        plt.xticks(fontsize=FONT_SIZE_TICKS)
        plt.yticks(fontsize=FONT_SIZE_TICKS)
        plt.grid(True, alpha=GRID_ALPHA)
        plt.savefig(os.path.join(plots_dir, f"User_Requests_{workload}_{application}.pdf"), bbox_inches='tight')
        plt.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Script per generare grafici da file .mat raggruppati per workload e application usando matplotlib")
    parser.add_argument("input_dir", help="Cartella contenente le cartelle degli esperimenti")
    args = parser.parse_args()
    main(args.input_dir)