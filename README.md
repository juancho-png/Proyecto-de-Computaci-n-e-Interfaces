# Monitor de Vitrina — Computación e Interfaces (UTB)

Sistema de monitoreo y control de temperatura de vitrinas:
**Arduino UNO R3 + DS18B20 → USB serie → puente Python → backend Flask/SQLite → interfaz web**.

## Estructura
```
backend/app.py          Backend (API + sirve la interfaz)
backend/static/         Interfaz web (index.html, css/, js/, vendor/chart.umd.js, fonts/)
backend/sembrar_demo.py Carga un día de lecturas de ejemplo (para probar o presentar)
firmware/arduino_uno/arduino_uno.ino  Firmware activo (Arduino UNO R3)
firmware/esp32/main.py  Versión anterior para ESP32 (referencia, no se usa)
puente_serial.py        Puente USB-serie entre el Arduino y el backend
simulador.py            "Placa falsa" para probar sin hardware
docs/hardware.md        Cableado, pines y pruebas del hardware real
docs/esquema.svg        Esquema de conexiones (una sola protoboard)
```

## Hardware (resumen)

| Componente | Pin Arduino | Nota |
|---|---|---|
| DS18B20 DATA | **D2** | Pull-up de 4.7 kΩ a **5 V** |
| DS18B20 VCC / GND | **5V / GND** | Bornera de 3 pines |
| MOSFET (gate) o relé (IN) | **D3** | 220 Ω al gate, 10 kΩ gate–GND, diodo 1N4007 |
| LED rojo | **D4** | 330 Ω a GND |
| Ventilador 12 V | +12 V y drain del MOSFET | **Nunca directo a un pin** |
| Arduino | **USB 5 V** | No conectar los 12 V al Arduino |

El Arduino UNO R3 **no tiene WiFi**. Por eso se conecta por USB al PC y
`puente_serial.py` publica las lecturas en el backend. El backend y la interfaz
web siguen funcionando igual.

Detalle completo, distribución en la protoboard y pruebas:
[`docs/hardware.md`](docs/hardware.md).
Si no hay MOSFET ni relé, el firmware puede funcionar con `TIPO_SALIDA 2`
(el ventilador queda directo a 12 V y el LED solo indica la orden).

## Cómo ejecutarlo
```bash
# 1) Dependencias (desde la raíz del proyecto)
pip install -r backend/requirements.txt

# 2) Backend
cd backend
python app.py                      # abre http://127.0.0.1:5000/

# 3) En otra terminal, desde la raíz del proyecto:
python puente_serial.py COM3       # Windows (Arduino real)
python puente_serial.py /dev/ttyUSB0   # Linux

# 4) Sin hardware (desde la raíz):
python simulador.py 1              # lecturas simuladas cada 1 s
python backend/sembrar_demo.py     # opcional: historial de ejemplo
```

Para el Arduino real:

1. Abrir `firmware/arduino_uno/arduino_uno.ino` en Arduino IDE.
2. Instalar las librerías **OneWire** y **DallasTemperature**.
3. Seleccionar **Arduino Uno** y el puerto COM.
4. Subir el sketch y **cerrar el Monitor Serie** (el puerto queda ocupado).
5. Ejecutar `python puente_serial.py COM3`.

La interfaz también se abre desde otro equipo de la red:
`http://IP_DEL_PC:5000/`. Si el backend corre en otro PC, cambiar `URL_BACKEND`
en `puente_serial.py`.

## API (las rutas del primer avance se mantienen)
| Método y ruta | Uso |
|---|---|
| POST /lecturas | El puente envía `{id_vitrina, temperatura, ventilador}` o `{id_vitrina, error:"sensor"}`; responde `{estado, ventilador, led, salida, sensor_ok, intervalo, modo}` |
| GET /hardware | Mapa de pines del Arduino y protocolo serie (JSON) |
| GET /salud | Prueba de conectividad del puente |
| GET /lecturas?fecha&desde&hasta&despues_de | Historial por fecha y hora |
| DELETE /lecturas | Eliminar historial |
| GET /estado | Estado completo: lectura, semáforo, conexión, configuración |
| PUT /vitrina | Guardar configuración (valida igual que el formulario) |
| POST /ventilador | `{modo}` y/o `{encendido}` (solo en modo manual) |
| GET /tipos | Tipos de producto y rango sugerido |
| GET /alertas?estado=todas/pendientes/reconocidas | Lista de alertas |
| GET /alertas/resumen | Alertas hoy, pendientes, tiempo fuera de rango |
| POST /alertas/<id>/reconocer | Reconocer alerta |

### Protocolo USB serie

| Dirección | Línea | Significado |
|---|---|---|
| Arduino → PC | `L,4.25,1,1` | Temperatura, ventilador, sensor OK |
| Arduino → PC | `E,0` | Sensor desconectado, ventilador apagado |
| PC → Arduino | `V,1` / `V,0` | Encender / apagar ventilador |
| PC → Arduino | `I,30` | Intervalo de lectura en segundos |

## Decisiones por confirmar con el equipo
- Placa activa: **Arduino UNO R3** a 5 V; el DS18B20 se alimenta a 5 V y el
  MOSFET debe ser **logic-level** (IRLZ44N / IRL540N).
- El UNO no tiene WiFi: la conexión es por USB con `puente_serial.py`.
- Si no hay MOSFET ni relé: `TIPO_SALIDA 2` (demostración, sin control real).
- Tiempo máximo antes de pedir revisión manual: `TIEMPO_MAX_RECUPERACION_MIN = 15` en `app.py` (el documento lo deja "por definir").
- "Cerca del límite" (amarillo): a menos de `MARGEN_AMARILLO = 0.5` °C del mínimo o máximo.
- Eliminar historial borra las lecturas, no las alertas.
- Lecturas de -127 °C o 85 °C (valores de falla del DS18B20) se tratan como sensor desconectado.
- Un mínimo/máximo válido es 0–10 / 2–12 °C; máximos > 8 °C piden confirmación.
