# main.py - Firmware del ESP32 (MicroPython) - Monitor de Vitrina
#
# LEGADO: esta es la versión para ESP32. La versión activa del proyecto usa
# Arduino UNO R3 (firmware/arduino_uno/arduino_uno.ino) y el puente USB-serie
# (puente_serial.py). Se conserva como referencia para una futura versión WiFi.
#
# Hardware (una sola protoboard):
#   DS18B20 : VCC -> 3.3 V, GND -> GND, DATA -> GPIO 18
#             Resistencia de 4.7 kOhm entre DATA y 3.3 V (pull-up obligatorio).
#             Se recomienda pasar el cable por la bornera de 3 pines:
#             pin 1 = 3V3, pin 2 = DATA, pin 3 = GND.
#   LED rojo: GPIO 21 -> resistencia 330 Ohm -> ánodo LED -> cátodo -> GND.
#   Ventilador 12 V:
#             - Con MOSFET canal N (recomendado): GPIO 19 -> 220 Ohm -> gate;
#               10 kOhm entre gate y GND; source -> GND; drain -> negro del ventilador;
#               rojo del ventilador -> +12 V. Diodo 1N4007 en paralelo con el ventilador
#               (cátodo a +12 V, ánodo al drain).
#             - Con módulo relé: IN -> GPIO 19, VCC -> 5 V, GND -> GND; el relé conmuta
#               el +12 V del ventilador. Muchos módulos son activos en bajo.
#             - Sin MOSFET ni relé: el ventilador queda directo a 12 V (siempre encendido)
#               y el LED solo indica la orden del backend. Es modo de demostración.
#   IMPORTANTE: un GPIO del ESP32 no puede alimentar el ventilador de 12 V.
#               Une el GND de la fuente de 12 V con el GND del ESP32 (GND común).
#               Alimenta el ESP32 por USB, no con los 12 V.
#
# Ajusta WIFI_SSID, WIFI_CLAVE y URL_BACKEND (IP del computador con Flask).

import time
import network
import machine
import onewire
import ds18x20

try:
    import urequests as requests   # MicroPython clásico
except ImportError:
    import requests                # versiones recientes de MicroPython

# ---------------- Configuración ----------------
WIFI_SSID = "TU_RED_WIFI"
WIFI_CLAVE = "TU_CLAVE"
URL_BACKEND = "http://192.168.1.50:5000/lecturas"   # IP del computador donde corre Flask
ID_VITRINA = 1

PIN_SENSOR = 18
PIN_VENTILADOR = 19
PIN_LED = 21

# "mosfet"   -> GPIO 19 activo en alto (recomendado)
# "rele"     -> GPIO 19 activo en bajo (módulo relé)
# "solo_led" -> sin MOSFET/relé: ventilador directo a 12 V, el LED solo señala
MODO_SALIDA = "mosfet"

INTERVALO_S = 1             # segundos entre lecturas (el backend puede cambiarlo)
INTERVALO_MIN_S = 1
INTERVALO_MAX_S = 60

# Regla local de respaldo (se usa solo si el backend no responde)
LOCAL_MAX = 6.0
LOCAL_HISTERESIS = 1.0


# ---------------- Clases ----------------
class SensorTemperatura:
    """Un objeto por cada sensor DS18B20. Varios sensores pueden compartir el mismo pin
    (bus 1-Wire): se distinguen con el parámetro 'indice'."""

    def __init__(self, id_sensor, pin_datos, ubicacion="vitrina", indice=0):
        self.id_sensor = id_sensor
        self.ubicacion = ubicacion
        self.temperatura_actual = None
        self._ds = ds18x20.DS18X20(onewire.OneWire(machine.Pin(pin_datos)))
        roms = self._ds.scan()
        if len(roms) <= indice:
            raise OSError("No se encontró el DS18B20: revisa 3.3 V, GND, DATA y la resistencia de 4.7 kOhm")
        self._rom = roms[indice]

    def leer_temperatura(self):
        self._ds.convert_temp()
        time.sleep_ms(750)          # tiempo de conversión del DS18B20 a 12 bits
        valor = round(self._ds.read_temp(self._rom), 2)
        if valor in (-127.0, 85.0) or not -55 <= valor <= 125:
            raise OSError("Lectura inválida del DS18B20: {}".format(valor))
        self.temperatura_actual = valor
        return valor


class SalidaVentilador:
    """Conmuta el ventilador por MOSFET (activo en alto) o por relé (activo en bajo).
    En modo 'solo_led' no hay pin de potencia: el ventilador queda directo a 12 V."""

    def __init__(self, pin, modo="mosfet"):
        self.modo = modo
        self.estado = False
        self._pin = None
        self._activo_en_bajo = False

        if modo == "solo_led":
            return
        if modo not in ("mosfet", "rele"):
            raise ValueError("MODO_SALIDA debe ser 'mosfet', 'rele' o 'solo_led'")

        self._pin = machine.Pin(pin, machine.Pin.OUT)
        self._activo_en_bajo = (modo == "rele")
        self.aplicar(False)         # arranca apagado

    def aplicar(self, encendido):
        self.estado = bool(encendido)
        if self._pin is None:
            return
        nivel = 1 if self.estado else 0
        if self._activo_en_bajo:
            nivel = 1 - nivel
        self._pin.value(nivel)


class LedEstado:
    """LED rojo que indica que la orden de enfriamiento está activa."""

    def __init__(self, pin, activo_en_alto=True):
        self._pin = machine.Pin(pin, machine.Pin.OUT)
        self._activo_en_alto = activo_en_alto
        self.aplicar(False)

    def aplicar(self, encendido):
        nivel = 1 if encendido else 0
        self._pin.value(nivel if self._activo_en_alto else 1 - nivel)


# ---------------- Funciones ----------------
def conectar_wifi(ssid, clave, intentos=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, clave)
        while not wlan.isconnected() and intentos > 0:
            time.sleep(1)
            intentos -= 1
    return wlan.isconnected()


def enviar_datos(temperatura, ventilador_encendido):
    """Envía la lectura al backend y devuelve su respuesta (dict) o None si falla.
    Si temperatura es None se avisa que el sensor falló (la interfaz muestra
    "Sensor desconectado")."""
    datos = {"id_vitrina": ID_VITRINA, "ventilador": ventilador_encendido}
    if temperatura is None:
        datos["error"] = "sensor"
    else:
        datos["temperatura"] = temperatura
    try:
        r = requests.post(URL_BACKEND, json=datos)
        respuesta = r.json()
        r.close()
        return respuesta
    except Exception as e:
        print("Error al enviar:", e)
        return None


def regla_local(temperatura, ventilador):
    """Respaldo si el backend no responde: enciende sobre LOCAL_MAX y apaga con histéresis."""
    if temperatura > LOCAL_MAX:
        ventilador.aplicar(True)
    elif temperatura <= LOCAL_MAX - LOCAL_HISTERESIS:
        ventilador.aplicar(False)


def aplicar_orden(respuesta, ventilador, led):
    """Aplica la orden del backend. Acepta 'salida.ventilador' o 'ventilador' (compatibilidad)."""
    salida = respuesta.get("salida") or {}
    orden = salida.get("ventilador", respuesta.get("ventilador", ventilador.estado))
    ventilador.aplicar(bool(orden))
    led.aplicar(ventilador.estado)


# ---------------- Programa principal ----------------
def main():
    global INTERVALO_S

    sensor = SensorTemperatura("S1", PIN_SENSOR, "Vitrina tortas")
    ventilador = SalidaVentilador(PIN_VENTILADOR, MODO_SALIDA)
    led = LedEstado(PIN_LED)

    print("Monitor de Vitrina | sensor GPIO{} | salida GPIO{} ({}) | LED GPIO{}".format(
        PIN_SENSOR, PIN_VENTILADOR, MODO_SALIDA, PIN_LED))

    if not conectar_wifi(WIFI_SSID, WIFI_CLAVE):
        print("Sin WiFi: se trabaja con la regla local")

    while True:
        try:
            temperatura = sensor.leer_temperatura()
        except Exception as e:
            print("Error de lectura:", e)
            # Avisa al backend para que genere la alerta; si responde, respeta el modo
            # manual/apagado y mantiene el LED sincronizado con la orden.
            respuesta = enviar_datos(None, ventilador.estado)
            if respuesta is not None:
                aplicar_orden(respuesta, ventilador, led)
            else:
                led.aplicar(ventilador.estado)
            time.sleep(5)
            continue

        if not network.WLAN(network.STA_IF).isconnected():
            conectar_wifi(WIFI_SSID, WIFI_CLAVE, intentos=5)

        respuesta = enviar_datos(temperatura, ventilador.estado)
        if respuesta is not None:
            # El backend decide con su regla (rango según el tipo de producto)
            aplicar_orden(respuesta, ventilador, led)
            # El intervalo de lectura se cambia desde la pantalla de Configuración
            try:
                nuevo = int(respuesta.get("intervalo", INTERVALO_S))
                INTERVALO_S = min(max(nuevo, INTERVALO_MIN_S), INTERVALO_MAX_S)
            except (TypeError, ValueError):
                pass
        else:
            regla_local(temperatura, ventilador)
            led.aplicar(ventilador.estado)

        print("T = {} C | ventilador: {} | LED: {}".format(
            temperatura, "ON" if ventilador.estado else "OFF", "ON" if ventilador.estado else "OFF"))
        time.sleep(INTERVALO_S)


main()
