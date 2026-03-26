# ImpedanceAnalyzer by Till Hänisch
# Plattformunabhängiges Userinterface für Impedanzmessungen mit dem Elektor Impedanze-Analyzer 
# 25.3.2026, Version 1.0

# Dieses Skript verbindet sich mit dem Impedanz-Analyzer über USB, führt einen Frequenz-Sweep durch,
# speichert die Messergebnisse in einer CSV-Datei und erstellt Gnuplot-Skripte sowie Matplotlib-Visualisierungen für Betrag und Phase der Impedanz.


from html import parser
import serial.tools.list_ports
import time
import math
import csv
import matplotlib.pyplot as plt
from rich.progress import track
import argparse


# -*- encoding: utf-8 -*-

# Konstanten laut Protokoll
BAUD_RATE = 19200 # Baudrate für die serielle Kommunikation mit dem Analyzer 
FREQ_FACTOR = 0.04190951586 # Umrechnung von Frequenz in die 32-bit Frequenznummer (Hz * Faktor)   

IDENTITY_CMD = b"-IDENTITY-" 
EXPECTED_ID = b"IMPAN00003" 
VERSION = "1.0"
PLOT_DELTA = 1
PLOT_PHASE = 2


# Da wir nicht wissen, an welchem COM-Port der Analyzer hängt, durchsuchen wir alle verfügbaren Ports nach einem passenden Gerät.
# TODO: Remember last used port in a config file for faster connection in the future.

def find_com_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        print("available port: " + str(port)) if (verbose) else None
        if ("USB" in port.hwid):
       	    try:
                # print("testing port " + port.device)
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
    # Frequenznummer laut Protokollbeschreibung berechnen und in 32-bit MSB umwandeln
    freq_num = int(frequency_hz / FREQ_FACTOR) 
    return freq_num.to_bytes(4, byteorder='big') 

def get_measurement(ser, freq_hz, reset_dds=False):
    # 10-Byte Befehl laut Protokollbeschreibungzusammensetzen 
    cmd = bytearray(10)
    cmd[0:4] = calculate_freq_bytes(freq_hz) # Byte 1-4: Frequenz 
    cmd[4] = 82                              # Byte 5: Immer 82 
    cmd[5] = 1                               # Byte 6: Amplitude (0 = 30mV, 1 = 120mV, 2=340mV, 7=1V) 
    cmd[6] = 82 if reset_dds else 0          # Byte 7: DDS Reset [cite: 27], vor längerer Messung einmalig setzen, damit der DDS-Chip neu synchronisiert wird (siehe Protokollbeschreibung)
    # Bytes 8-10 sind 0 
    
    ser.write(cmd)
    time.sleep(0.1)
    # Antwort lesen (47 Bytes) 
    data = ser.read(47)
    if len(data) < 47:
        return None
    
    # Antwort enthält 46 Bytes Messdaten (Real- und Imaginärteil) + 1 Byte Status (siehe Protokollbeschreibung), wir ignorieren den Status-Byte hier
    # Real- und Imaginärteil extrahieren (je 23 Bytes Text) 
    real_str = data[0:23].split(b'\x00')[0].decode('ascii')
    imag_str = data[23:46].split(b'\x00')[0].decode('ascii')
    
    
    try:
        real = float(real_str)
        imag = float(imag_str)
        magnitude = math.sqrt(real**2 + imag**2)
        return real, imag, magnitude
    except ValueError:
        return None
    
def generate_frequencies(freq_start_exp, freq_stop_exp, points_per_dec):
    frequencies = []
    for d in range(freq_start_exp, freq_stop_exp):
        start = 10**d
        step_freqs = [start * (10**(i/points_per_dec)) for i in range(points_per_dec)]
        frequencies.extend(step_freqs)
    frequencies.append(10**freq_stop_exp)
    return frequencies  

def measure_sweep(ser, frequencies):
    # measures at all given frequencies and return list of tuples: (frequency, real, imag, magnitude)
    results = []
    first = True    
    for f in track(frequencies, description="measuring..."):
        if f < 100 or f > 40000000:
            continue
        result = get_measurement(ser, f) # result is real, imag, mag 
        first=False
        if result is not None:
            results.append((f, *result))
            # print(f"{f:.2f} Hz: Real={result[0]:.4f}, Imag={result[1]:.4f}, Mag={result[2]:.4f}")    
        time.sleep(0.05) 
    print("Measurement completed.")
    return results

def do_measure_with_delta(ser, freq_start_exp, freq_stop_exp, points_per_dec, 
               filename="messung.csv", show_plot=True):
    # Measure a sweep and calculate loss factor (tan delta) for each frequency, save to CSV and create Gnuplot script and Matplotlib plot for magnitude and loss factor.
    frequencies = generate_frequencies(freq_start_exp, freq_stop_exp, points_per_dec)   

    plot_freqs, plot_mags, plot_phases, plot_loss = [], [], [], []

    try:
        with open(filename, mode='w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=';')
            csv_writer.writerow(["Frequenz_Hz", "Realteil", "Imaginaerteil", "Betrag", "Phase_Grad", "Verlustfaktor_D"])

            results = measure_sweep(ser, frequencies)
            for result in results:
                f, real, imag, mag = result

               # Berechnung Verlustfaktor D (tan delta)
                # Vorsicht: Division durch 0 verhindern
                loss_factor = abs(real / imag) if imag != 0 else float('nan')
                
                phase_deg = math.degrees(math.atan2(imag, real))
                
                
                csv_writer.writerow([f"{f:.2f}", f"{real:.4f}", f"{imag:.4f}", f"{mag:.4f}", f"{phase_deg:.2f}", f"{loss_factor:.6f}"])
                
                plot_freqs.append(f)
                plot_mags.append(mag)
                plot_phases.append(phase_deg)
                plot_loss.append(loss_factor)
                
                time.sleep(0.05)

        # Matplotlib Plot
        if show_plot and plot_freqs:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10), sharex=True)
            
            # Oben: Impedanzbetrag
            ax1.loglog(plot_freqs, plot_mags, 'b-o')
            ax1.set_ylabel('Betrag |Z| [Ohm]')
            ax1.grid(True, which="both", alpha=0.3)
            ax1.set_title("Impedanz und Verlustfaktor/Phase über Frequenz")

            if (second_plot == PLOT_DELTA):
                # Unten: Verlustfaktor D
                ax2.loglog(plot_freqs, plot_loss, 'g-s', label='tan(delta)')
                ax2.set_ylabel('Verlustfaktor D')
                ax2.set_xlabel('Frequenz [Hz]')
                ax2.grid(True, which="both", alpha=0.3)
            else:
                # Unten: Phase
                ax2.plot(plot_freqs, plot_phases, 'r--s', label='Phase')
                ax2.set_ylabel('Phase [°]')
                ax2.set_xlabel('Frequenz [Hz]')
                ax2.set_ylim(-180, 180)
                ax2.grid(True, which="both", alpha=0.3)
            plt.title ("Frequenzgang (Bode-Diagramm)")
            plt.tight_layout()
            plt.show()

    except Exception as e:
        print(f"Fehler: {e}")


def main():

    global verbose, second_plot

    parser = argparse.ArgumentParser(description="Impedanz-Analyzer Messprogramm")
    parser.add_argument("-v", "--Verbose", help="Show info helpful for debugging", action="store_true")
    parser.add_argument("-D", "--Delta", help="Show Loss factor D in second plot instead of Phase", action="store_true")
    parser.add_argument("-P", "--Phase", help="Show Phase in second plot instead of Loss factor D (default)", action="store_true")
    parser.add_argument("-s", "--StartExp", help="Start exponent for frequency sweep (10^x Hz)", type=int, default=2)
    parser.add_argument("-e", "--StopExp", help="Stop exponent for frequency sweep (10^x Hz)", type=int, default=8)
    parser.add_argument("-p", "--PointsPerDecade", help="Number of measurement points per decade (10x frequency)", type=int, default=20)
    args = parser.parse_args()

    if (args.Verbose):
            verbose = True  
    else:
            verbose = False

    if (args.Delta):
            second_plot = PLOT_DELTA
    else:  
            second_plot = PLOT_PHASE
    
    if (args.StartExp >= 0 and args.StopExp > args.StartExp):
            freq_start_exp = args.StartExp
            freq_stop_exp = args.StopExp    
    
    if (args.PointsPerDecade > 0):
            points_per_dec = args.PointsPerDecade  

    print("Impedanz-Analyzer Messprogramm, Version " + VERSION)
    port_name = find_com_port()
    if not port_name:
        print("Impedanz-Analyzer nicht gefunden.")
        return

    print(f"Verbunden mit: {port_name}\n")

    try:
        with serial.Serial(port_name, BAUD_RATE, timeout=2) as ser:
            # Beispiel: 100Hz (10^2) bis 10kHz (10^4) mit 5 Punkten/Dekade
            do_measure_with_delta(ser, freq_start_exp, freq_stop_exp, points_per_dec, filename="impedanz_messung.csv")
    except serial.SerialException as e:
        print(f"Verbindungsfehler: {e}")



if __name__ == "__main__":
    main()
