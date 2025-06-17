"""
Authors: Adam Dołowy, Cezary Charuba
"""

import os
import time
import datetime
import sys
import math

# ====== Stałe ======
# Dane Prometheus'a
PROMETHEUS_IP = "192.168.2.201"
PROMETHEUS_PORT = "9090"

# Potrzebne do wywołania zapytania
NAMESPACE = "default"
QUERY_AMF = f"query='amf_session{{service=\"open5gs-amf-metrics\",namespace=\"{NAMESPACE}\"}}'"
FULL_QUERY = f"curl -s {PROMETHEUS_IP}:{PROMETHEUS_PORT}/api/v1/query -G -d {QUERY_AMF} | jq '.data.result[0].value[" \
             f"1]' | tr -d '\"' "
GET_UPF_POD_QUERY = "kubectl get pods --no-headers -o custom-columns=\":metadata.name\" | grep upf"

# Parametry wyznaczone eksperymentalnie (opisane w sprawozdaniu) - do wyliczania skalowania
BENCHMARK_CPU_PER_UE = 30
BENCHMARK_UPF_CPU_MAX = 630


# Funkcja pobierająca aktualną nazwę poda UPF (przydatne w przypadku restartów)
def get_upf_pod():
    upf_pod_name = os.popen(GET_UPF_POD_QUERY).read().strip()
    return upf_pod_name

# Funkcja sprawdzająca aktualną ilość sesji AMF (podłączone UE)
def check_amf_sessions():
    ts = time.time()
    current_datetime = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

    print("\n============ Sprawdzanie ilości sesji AMF... ============")
    print(f"------------------ {current_datetime} ------------------")

    amf_sessions = os.popen(FULL_QUERY).read()

    print(f"----> Liczba sesji AMF = {amf_sessions}")
    return amf_sessions


# Funkcja wyliczająca przeskalowaną wartość CPU UPF na pojedynczy UE
def calc_cpu_per_ue(upf_cpu_max: int):
    cpu_per_ue = math.floor(upf_cpu_max / BENCHMARK_UPF_CPU_MAX * BENCHMARK_CPU_PER_UE)
    return cpu_per_ue


# Funkcja skalująca element UPF zgodnie z ilością sesji AMF i zadeklarowanym CPU
def scale_upf(amf_sessions: int, cpu_per_ue: int, upf_pod_name: str):
    scaled_upf_cpu = cpu_per_ue * (amf_sessions + 1)
    command = f"kubectl patch -n default pod {upf_pod_name} --subresource resize --patch '{{\"spec\":{{" \
              f"\"containers\":[{{\"name\":\"open5gs-upf\", \"resources\":{{\"limits\":{{" \
              f"\"cpu\":\"{scaled_upf_cpu}m\"}}}}}}]}}}}' "
    print(f"----> Skalowanie CPU elementu UPF na {scaled_upf_cpu}m")
    os.system(command)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) != 2:
        print("Błędna liczba argumentów, podaj dwa (MAX_UPF_CPU [m], QUERY_PERIOD [s])!")
    else:
        upf_cpu_max = sys.argv[1]
        query_period = sys.argv[2]
        if not upf_cpu_max.isdigit():
            print("Błędny 1 argument. Podaj liczbę z zakresu 210 - 2000")
            exit(-1)
        elif not (210 <= int(upf_cpu_max) <= 2000):
            print("Błędny 1 argument. Podaj liczbę z zakresu 210 - 2000")
            exit(-1)
        if not query_period.isdigit():
            print("Błędny 2 argument. Podaj liczbę >= 1")
            exit(-1)
        elif not (int(query_period) >= 1):
            print("Błędny 2 argument. Podaj liczbę >= 1")
            exit(-1)

        # Ostateczne przypisanie wartości zmiennych jako Integer
        upf_cpu_max = int(upf_cpu_max)
        query_period = int(query_period)
        # Wyliczenie przeskalowanego CPU per UE dla zadeklarowanego MAX CPU UPF
        cpu_per_ue = calc_cpu_per_ue(upf_cpu_max)
        # Pobranie nazwy poda UPF
        upf_pod_name = get_upf_pod()

        print("\n================= APLIKACJA URUCHOMIONA =================")
        print("-------------- ADAM DOŁOWY, CEZARY CHARUBA --------------")

        print(f"\n----> Current UPF pod name = {upf_pod_name}")
        print(f"\n-----------> Zapytanie wysyłane do AMF co {query_period}s <-----------")
        print(f"\n-----------> Wybrana ilość CPU dla UPF: {upf_cpu_max}m <-----------")
        print(f"\n-----------> Wyliczone max. CPU per UE: {cpu_per_ue}m <-----------\n")

        print("\n|||||||||||||| ROZPOCZYNANIE MONITOROWANIA ||||||||||||||")
        print("vvvvvvvvvvvvvv ........................... vvvvvvvvvvvvvv\n")

        new_checking = 0
        prev_amf_sessions = 0

        try:
            while True:
                current_time = time.time() * 1000
                if new_checking < current_time:
                    amf_sessions = check_amf_sessions()

                    if amf_sessions != prev_amf_sessions and amf_sessions != 0:
                        print("------------ Liczba sesji AMF uległa zmianie ------------")
                        prev_amf_sessions = amf_sessions
                        scale_upf(int(amf_sessions), cpu_per_ue, upf_pod_name)

                    new_checking = time.time() * 1000 + query_period * 1000
        except KeyboardInterrupt:
            print("Program został zatrzymany.")
