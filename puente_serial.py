# puente_serial.py - Puente entre el Arduino UNO (USB serie) y el backend Flask.
#
# El Arduino UNO R3 no tiene WiFi. Este programa lee las líneas que envía por
# USB, las publica en POST /lecturas y le devuelve la orden del ventilador y el
# intervalo de lectura.
#
# Uso:
#   python puente_serial.py COM3          (Windows)
#   python puente_serial.py /dev/ttyUSB0  (Linux)
#
# Protocolo:
#   Arduino -> PC : L,<temperatura>,<ventilador>,<sensor_ok>
#                   E,<ventilador>                 (sensor desconectado)
#   PC -> Arduino : V,<0|1>                        (orden del ventilador)
#                   I,<segundos>                   (intervalo de lectura)
#
# Requiere: pip install pyserial requests
# El backend debe estar corriendo: python backend/app.py

import sys
import time

import requests

try:
    import serial
except ImportError:
    raise SystemExit("Falta pyserial. Instala con: pip install pyserial")

URL_BACKEND = "http://127.0.0.1:5000/lecturas"
ID_VITRINA = 1
BAUDIOS = 115200
REINTENTO_S = 5
TIMEOUT_HTTP_S = 5
INTERVALO_MIN_S = 10
INTERVALO_MAX_S = 60


def interpretar(linea):
    """Convierte una línea del Arduino en el JSON de /lecturas.

    Devuelve (datos, None) si es una lectura válida, (None, aviso) si la línea
    parece una lectura pero está mal formada, o (None, None) si no es una línea
    del protocolo (por ejemplo, READY u otro mensaje de depuración).
    """
    linea = linea.strip()

    if linea.startswith("L,"):
        partes = linea.split(",")
        if len(partes) != 4:
            return None, "Línea L inválida: " + linea
        try:
            temperatura = float(partes[1])
            ventilador = bool(int(partes[2]))
            sensor_ok = bool(int(partes[3]))
        except ValueError:
            return None, "Valores inválidos: " + linea
        datos = {"id_vitrina": ID_VITRINA, "ventilador": ventilador}
        if sensor_ok:
            datos["temperatura"] = temperatura
        else:
            datos["error"] = "sensor"
        return datos, None

    if linea.startswith("E,"):
        partes = linea.split(",")
        if len(partes) != 2:
            return None, "Línea E inválida: " + linea
        try:
            ventilador = bool(int(partes[1]))
        except ValueError:
            return None, "Valor inválido: " + linea
        return {"id_vitrina": ID_VITRINA, "error": "sensor", "ventilador": ventilador}, None

    return None, None


def abrir_puerto(nombre):
    while True:
        try:
            puerto = serial.Serial(nombre, BAUDIOS, timeout=1)
            puerto.reset_input_buffer()   # descarta datos viejos
            time.sleep(2)                 # el Arduino se reinicia al abrir el puerto
            print("Conectado a", nombre)
            return puerto
        except serial.SerialException as e:
            print("No se pudo abrir", nombre, ":", e)
            print("Reintentando en", REINTENTO_S, "s...")
            time.sleep(REINTENTO_S)


def enviar_al_arduino(puerto, linea):
    try:
        puerto.write((linea + "\n").encode("ascii"))
    except serial.SerialException as e:
        print("Error escribiendo al Arduino:", e)


def main():
    if len(sys.argv) < 2:
        print("Uso: python puente_serial.py COM3")
        print("     python puente_serial.py /dev/ttyUSB0")
        return

    nombre = sys.argv[1]
    puerto = abrir_puerto(nombre)
    print("Puente listo. Ctrl+C para salir.")

    while True:
        try:
            linea = puerto.readline().decode("ascii", errors="ignore").strip()
        except serial.SerialException as e:
            print("Se perdió el puerto:", e)
            try:
                puerto.close()
            except serial.SerialException:
                pass
            puerto = abrir_puerto(nombre)
            continue

        if not linea:
            continue

        datos, aviso = interpretar(linea)
        if datos is None:
            if aviso:
                print("Aviso:", aviso)
            else:
                print("Arduino:", linea)
            continue

        try:
            r = requests.post(URL_BACKEND, json=datos, timeout=TIMEOUT_HTTP_S)
            if not r.ok:
                print("Backend respondió", r.status_code, r.text[:200])
                continue
            respuesta = r.json()
        except (requests.RequestException, ValueError) as e:
            print("Backend no disponible:", e)
            continue

        salida = respuesta.get("salida") or {}
        ventilador = bool(salida.get("ventilador", respuesta.get("ventilador", False)))
        try:
            intervalo = int(respuesta.get("intervalo", 30))
        except (TypeError, ValueError):
            intervalo = 30
        intervalo = max(INTERVALO_MIN_S, min(INTERVALO_MAX_S, intervalo))

        if "temperatura" in datos:
            print("T={:.2f} C | estado={} | ventilador={}".format(
                datos["temperatura"], respuesta.get("estado"), "ON" if ventilador else "OFF"))
        else:
            print("Sensor desconectado | estado={} | ventilador={}".format(
                respuesta.get("estado"), "ON" if ventilador else "OFF"))

        enviar_al_arduino(puerto, "V,{}".format(1 if ventilador else 0))
        enviar_al_arduino(puerto, "I,{}".format(intervalo))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPuente detenido.")
