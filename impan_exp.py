# ImpedanceAnalyzer by Till Hänisch
# Plattformunabhängiges Userinterface für Impedanzmessungen mit dem Elektor Impedanze-Analyzer 
# 25.3.2026, Version 1.0

# Dieses Skript verbindet sich mit dem Impedanz-Analyzer über USB, führt einen Frequenz-Sweep durch,
# speichert die Messergebnisse in einer CSV-Datei und erstellt Gnuplot-Skripte sowie Matplotlib-Visualisierungen für Betrag und Phase der Impedanz.


import serial.tools.list_ports
import time
import math
import csv
import matplotlib.pyplot as plt

# -*- encoding: utf-8 -*-

# Konstanten laut Protokoll
BAUD_RATE = 19200 # Baudrate für die serielle Kommunikation mit dem Analyzer 
FREQ_FACTOR = 0.04190951586 # Umrechnung von Frequenz in die 32-bit Frequenznummer (Hz * Faktor)   

IDENTITY_CMD = b"-IDENTITY-" 
EXPECTED_ID = b"IMPAN00003" 

# Da wir nicht wissen, an welchem COM-Port der Analyzer hängt, durchsuchen wir alle verfügbaren Ports nach einem passenden Gerät.
# TODO: Remember last used port in a config file for faster connection in the future.

def find_com_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        print("available port: " + str(port))
        if ("USB" in port.hwid):
       	    try:
                print("testing port " + port.device)
                with serial.Serial(port.device, BAUD_RATE, timeout=0.5) as ser:
                    # Teste Port mit Identitätsabfrage
                    ser.write(b"X")
                    time.sleep(0.1)
                    response = ser.read(1)
                    if (response == b"U"):
                        print("Analyzer seems to be alive")
                        time.sleep(0.1)
                        ser.write(IDENTITY_CMD) 
                        response = ser.read(10) 
                        if response == EXPECTED_ID:
                            return port.device
            except:
                print("Error testing port " + port.device)
                continue
    return None

def calculate_freq_bytes(frequency_hz):
    # Frequenznummer berechnen und in 32-bit MSB umwandeln
    freq_num = int(frequency_hz / FREQ_FACTOR) 
    return freq_num.to_bytes(4, byteorder='big') 

def get_measurement(ser, freq_hz, reset_dds=False):
    # 10-Byte Befehl zusammensetzen [cite: 20]
    cmd = bytearray(10)
    cmd[0:4] = calculate_freq_bytes(freq_hz) # Byte 1-4: Frequenz [cite: 22]
    cmd[4] = 82                              # Byte 5: Immer 82 [cite: 24]
    cmd[5] = 1                               # Byte 6: Amplitude (1 = 120mV) [cite: 25]
    cmd[6] = 82 if reset_dds else 0          # Byte 7: DDS Reset [cite: 27]
    # Bytes 8-10 sind 0 [cite: 29]
    
    ser.write(cmd)
    time.sleep(0.1)
    # Antwort lesen (47 Bytes) [cite: 32]
    data = ser.read(47)
    if len(data) < 47:
        return None
    
    # Real- und Imaginärteil extrahieren (je 23 Bytes Text) [cite: 33]
    real_str = data[0:23].split(b'\x00')[0].decode('ascii')
    imag_str = data[23:46].split(b'\x00')[0].decode('ascii')
    
    
    try:
        real = float(real_str)
        imag = float(imag_str)
        magnitude = math.sqrt(real**2 + imag**2)
        return real, imag, magnitude
    except ValueError:
        return None
import math
import csv
import time
import matplotlib.pyplot as plt

def do_measure_with_delta(ser, freq_start_exp, freq_stop_exp, points_per_dec, 
               filename="messung.csv", show_plot=True):
    # ... (Frequenzgenerierung wie gehabt) ...
    frequencies = []
    for d in range(freq_start_exp, freq_stop_exp):
        start = 10**d
        step_freqs = [start * (10**(i/points_per_dec)) for i in range(points_per_dec)]
        frequencies.extend(step_freqs)
    frequencies.append(10**freq_stop_exp)

    plot_freqs, plot_mags, plot_phases, plot_loss = [], [], [], []

    print(f"\n{'Freq (Hz)':>12} | {'Real (R)':>10} | {'Imag (X)':>10} | {'Betrag |Z|':>10} | {'tan(delta)':>10}")
    print("-" * 75)

    try:
        with open(filename, mode='w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=';')
            csv_writer.writerow(["Frequenz_Hz", "Realteil", "Imaginaerteil", "Betrag", "Phase_Grad", "Verlustfaktor_D"])

            first = True
            for f in frequencies:
                if f < 100 or f > 40000000:
                    continue

                result = get_measurement(ser, f, reset_dds=first)
                if result is None:
                    continue
                
                real, imag, mag = result
                
                # Berechnung Verlustfaktor D (tan delta)
                # Vorsicht: Division durch 0 verhindern
                loss_factor = abs(real / imag) if imag != 0 else float('nan')
                
                phase_deg = math.degrees(math.atan2(imag, real))
                
                print(f"{f:12.1f} | {real:10.2f} | {imag:10.2f} | {mag:10.2f} | {loss_factor:10.4f}")
                
                csv_writer.writerow([f"{f:.2f}", f"{real:.4f}", f"{imag:.4f}", f"{mag:.4f}", f"{phase_deg:.2f}", f"{loss_factor:.6f}"])
                
                plot_freqs.append(f)
                plot_mags.append(mag)
                plot_phases.append(phase_deg)
                plot_loss.append(loss_factor)
                
                first = False
                time.sleep(0.05)

        # Gnuplot Skript Erweiterung (.plt)
        dat_name = filename.replace('.csv', '.dat')
        plt_name = filename.replace('.csv', '.plt')
        
        with open(dat_name, 'w') as f_dat:
            f_dat.write("# Freq Mag Phase tanDelta\n")
            for i in range(len(plot_freqs)):
                f_dat.write(f"{plot_freqs[i]} {plot_mags[i]} {plot_phases[i]} {plot_loss[i]}\n")

        with open(plt_name, 'w') as f_plt:
            f_plt.write(f'set title "Kondensator-Analyse: {filename}"\n')
            f_plt.write('set xlabel "Frequenz [Hz]"\n')
            f_plt.write('set ylabel "Verlustfaktor tan(delta)"\n')
            f_plt.write('set logscale x\n')
            f_plt.write('set logscale y\n') # Oft ist auch D logarithmisch sinnvoll
            f_plt.write('set grid xtics ytics mxtics\n')
            f_plt.write(f'plot "{dat_name}" using 1:4 with linespoints title "tan(delta)"\n')
            f_plt.write('pause -1\n')

        # Matplotlib Plot
        if show_plot and plot_freqs:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10), sharex=True)
            
            # Oben: Impedanzbetrag
            ax1.loglog(plot_freqs, plot_mags, 'b-o')
            ax1.set_ylabel('Betrag |Z| [Ohm]')
            ax1.grid(True, which="both", alpha=0.3)
            ax1.set_title("Impedanz und Verlustfaktor")

            # Unten: Verlustfaktor D
            ax2.loglog(plot_freqs, plot_loss, 'g-s', label='tan(delta)')
            ax2.set_ylabel('Verlustfaktor D')
            ax2.set_xlabel('Frequenz [Hz]')
            ax2.grid(True, which="both", alpha=0.3)
            
            plt.tight_layout()
            plt.show()

    except Exception as e:
        print(f"Fehler: {e}")

def do_measure(ser, freq_start_exp, freq_stop_exp, points_per_dec, 
               filename="messung.csv", show_plot=True):
    """
    Führt einen Frequenz-Sweep durch, speichert Ergebnisse (CSV/Gnuplot) 
    und visualisiert Betrag (log/log) und Phase.
    """
    # Frequenzliste generieren
    frequencies = []
    for d in range(freq_start_exp, freq_stop_exp):
        start = 10**d
        step_freqs = [start * (10**(i/points_per_dec)) for i in range(points_per_dec)]
        frequencies.extend(step_freqs)
    frequencies.append(10**freq_stop_exp)

    plot_freqs, plot_mags, plot_phases = [], [], []

    print(f"\nStarte Sweep: 10^{freq_start_exp} Hz bis 10^{freq_stop_exp} Hz")
    print(f"{'Frequenz (Hz)':>12} | {'Real':>12} | {'Imag':>12} | {'Betrag':>12} | {'Phase(°)':>8}")
    print("-" * 90)

    try:
        # 1. CSV Datei vorbereiten
        with open(filename, mode='w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=';')
            csv_writer.writerow(["Frequenz_Hz", "Realteil", "Imaginaerteil", "Betrag", "Phase_Grad"])

            first = True
            for f in frequencies:
                # Syntax-Check: continue überspringt ungültige Frequenzen
                if f < 100 or f > 40000000:
                    continue

                # Messung triggern
                result = get_measurement(ser, f, reset_dds=first)
                
                # Falls Messung fehlschlägt (None), zum nächsten Punkt springen
                if result is None:
                    print(f"{f:12.1f} | Messfehler!")
                    continue
                
                real, imag, mag = result
                phase_deg = math.degrees(math.atan2(imag, real))
                
                print(f"{f:12.1f} | {real:12.4f} | {imag:12.4f} | {mag:12.4f} | {phase_deg:8.2f}")
                csv_writer.writerow([f"{f:.2f}", f"{real:.4f}", f"{imag:.4f}", f"{mag:.4f}", f"{phase_deg:.2f}"])
                
                plot_freqs.append(f)
                plot_mags.append(mag)
                plot_phases.append(phase_deg)
                
                first = False
                time.sleep(0.05) 

        # 2. Vollständige Gnuplot-Dateien erzeugen
        dat_name = filename.replace('.csv', '.dat')
        plt_name = filename.replace('.csv', '.plt')
        
        # Datendatei
        with open(dat_name, 'w') as f_dat:
            f_dat.write("# Frequenz(Hz) Betrag(Ohm) Phase(Grad)\n")
            for i in range(len(plot_freqs)):
                f_dat.write(f"{plot_freqs[i]} {plot_mags[i]} {plot_phases[i]}\n")

        # Skriptdatei für Gnuplot
        with open(plt_name, 'w') as f_plt:
            f_plt.write(f'set title "Impedanz-Analyse: {filename}"\n')
            f_plt.write('set xlabel "Frequenz [Hz]"\n')
            f_plt.write('set ylabel "Betrag |Z| [Ohm]"\n')
            f_plt.write('set y2label "Phase [Grad]"\n')
            f_plt.write('set logscale x\n')
            f_plt.write('set logscale y\n')
            f_plt.write('set y2tics\n')
            f_plt.write('set ytics nomirror\n')
            f_plt.write('set grid xtics ytics mxtics\n')
            f_plt.write('set y2range [-180:180]\n')
            f_plt.write(f'plot "{dat_name}" axes x1y1 with lines title "Betrag", ')
            f_plt.write(f'"{dat_name}" axes x1y2 with lines title "Phase"\n')
            f_plt.write('pause -1 "Beliebige Taste zum Schliessen"\n')

        print(f"\nDateien '{dat_name}' und '{plt_name}' erfolgreich erstellt.")

        # 3. Matplotlib Log-Log Plot
        if show_plot and plot_freqs:
            
            fig, ax1 = plt.subplots(figsize=(10, 6))
            ax1.set_xlabel('Frequenz (Hz)')
            ax1.set_ylabel('Betrag |Z| (Ohm)', color='blue')
            ax1.loglog(plot_freqs, plot_mags, 'b-o', label='Betrag')
            ax1.grid(True, which="both", alpha=0.3)

            ax2 = ax1.twinx()
            ax2.set_ylabel('Phase (°)', color='red')
            ax2.plot(plot_freqs, plot_phases, 'r--s', label='Phase', alpha=0.6)
            ax2.set_ylim(-180, 180)
            
            plt.title("Frequenzgang (Bode-Diagramm)")
            plt.tight_layout()
            plt.show()

    except Exception as e:
        print(f"Kritischer Fehler: {e}")

def main():

    port_name = find_com_port()
    if not port_name:
        print("Impedanz-Analyzer nicht gefunden.")
        return

    print(f"Verbunden mit: {port_name}\n")
    print(f"{'Frequenz (Hz)':>15} | {'Realteil':>15} | {'Imaginärteil':>15} | {'Betrag':>15}")
    print("-" * 70)

    try:
        with serial.Serial(port_name, BAUD_RATE, timeout=2) as ser:
            # Beispiel: 100Hz (10^2) bis 10kHz (10^4) mit 5 Punkten/Dekade
            do_measure_with_delta(ser, freq_start_exp=2, freq_stop_exp=7, points_per_dec=20, filename="impedanz_messung.csv")
    except serial.SerialException as e:
        print(f"Verbindungsfehler: {e}")



if __name__ == "__main__":
    main()
