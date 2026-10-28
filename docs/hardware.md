# Hardware real — ESP32 + DS18B20 + ventilador 12 V

Este documento adapta el proyecto a los componentes disponibles y a **una sola
protoboard**. El backend no cambia su lógica de control: el ESP32 sigue enviando
la temperatura a `POST /lecturas` y el servidor responde si el ventilador debe
encenderse. Lo que cambia es el **mapa de pines** y la forma de conmutar el
ventilador de 12 V.

## 1. Advertencia importante

Un GPIO del ESP32 entrega como máximo unos **12 mA** (40 mA absolutos) y 3.3 V.
**No puede alimentar ni conmutar un ventilador de 12 V directamente.** Si se
conecta el ventilador a un GPIO, el ESP32 se reinicia o se daña.

Para encenderlo y apagarlo se necesita **un interruptor electrónico**:

| Opción | Componentes | Cuándo usarla |
|---|---|---|
| **MOSFET canal N** (recomendado) | IRLZ44N o IRL540N, resistencia 220 Ω, resistencia 10 kΩ, diodo 1N4007 | Silencioso, rápido, sin desgaste mecánico |
| **Módulo relé** | Relé de 5 V con optoacoplador | Si ya lo tienen o prefieren aislamiento galvánico |
| **Solo LED** | Ninguno adicional | Demostración: el ventilador queda directo a 12 V y el LED solo indica la orden |

> Con los componentes listados (bornera, protoboard, DS18B20, jumpers, fuente
> 12 V, LED rojo y una resistencia) **no es posible conmutar el ventilador**.
> Hace falta el MOSFET (o el relé) y, como mínimo, el diodo de protección.
> Si no se consigue, usar `MODO_SALIDA = "solo_led"` en el firmware: el sistema
> mide y registra, pero el ventilador no se controla.

### Materiales y cantidades

| Material | Cant. | Para qué |
|---|---|---|
| ESP32 DevKit V1 | 1 | Control y WiFi |
| Protoboard | 1 | Montaje |
| DS18B20 (sonda 3 hilos) | 1 | Medir temperatura |
| Bornera 3 pines | 1 | Conectar el DS18B20 |
| Jumpers | ~12 | Conexiones |
| Fuente 12 V DC | 1 | Alimentar el ventilador |
| Ventilador 12 V | 1 | Enfriamiento |
| LED rojo | 1 | Indicador de enfriamiento |
| Resistencia **4.7 kΩ** | 1 | Pull-up del DS18B20 (**obligatoria**) |
| Resistencia **330 Ω** | 1 | Limitar corriente del LED |
| Resistencia **220 Ω** | 1 | Gate del MOSFET |
| Resistencia **10 kΩ** | 1 | Gate–source (evita encendidos falsos) |
| MOSFET IRLZ44N / IRL540N | 1 | Conmutar el ventilador |
| Diodo 1N4007 | 1 | Protección del MOSFET |

> **Ojo con la resistencia única:** el DS18B20 necesita 4.7 kΩ entre DATA y
> 3.3 V; sin ella el sensor no aparece en el bus. El LED necesita 330 Ω y el
> MOSFET 220 Ω + 10 kΩ. Si solo hay una resistencia, no alcanza para el montaje
> completo: prioriza la de 4.7 kΩ para el sensor y usa `solo_led` hasta
> conseguir las demás.

## 2. Mapa de pines (una sola protoboard)

Se eligieron **GPIO 18, 19 y 21** porque están juntos en el lado derecho del
DevKit V1, no son pines de arranque (*strapping*) y no se usan para WiFi, para
la memoria flash ni para el puerto serie USB. Así el cableado cabe en una sola
protoboard y no se cruza con los pines de alimentación.

Evitar: **0, 1, 2, 3, 5, 6–11, 12, 15, 20, 34–39** (arranque, flash, UART0 o
solo entrada).

| Componente | Terminal | Pin ESP32 | Notas |
|---|---|---|---|
| **DS18B20** | VCC (rojo) | **3V3** | Bornera, pin 1 |
| | DATA (amarillo) | **GPIO 18** | Bornera, pin 2 |
| | GND (negro) | **GND** | Bornera, pin 3 |
| **Pull-up DS18B20** | 4.7 kΩ | entre **3V3** y **GPIO 18** | Obligatoria |
| **LED rojo** | Ánodo | **GPIO 21** | A través de 330 Ω |
| | Cátodo | **GND** | |
| **MOSFET IRLZ44N** | Gate (G) | **GPIO 19** | A través de 220 Ω |
| | Gate–Source | **10 kΩ a GND** | Evita encendidos falsos |
| | Source (S) | **GND común** | |
| | Drain (D) | **Negro del ventilador** | |
| **Ventilador 12 V** | Rojo (+) | **+12 V** | Fuente de módem |
| | Negro (–) | **Drain del MOSFET** | |
| **Diodo 1N4007** | Cátodo (raya) | **+12 V** | En paralelo con el ventilador |
| | Ánodo | **Drain / negro del ventilador** | Protege el MOSFET |
| **Fuente 12 V** | Rojo (+) | **+12 V** del ventilador | Verificar polaridad |
| | Negro (–) | **GND común** | Unir con GND del ESP32 |
| **ESP32** | Alimentación | **USB 5 V** | No conectar los 12 V al ESP32 |

### Alternativa con módulo relé

| Relé | Conexión |
|---|---|
| `IN` | **GPIO 19** |
| `VCC` | **5 V** (VIN del ESP32) |
| `GND` | **GND común** |
| `COM` | **+12 V** de la fuente |
| `NO` | **Rojo del ventilador** |
| Negro del ventilador | **GND común** |

En el firmware usar `MODO_SALIDA = "rele"` (muchos módulos son activos en bajo).

## 3. Esquema

![Esquema de conexiones](esquema.svg)

Versión en texto:

```
ESP32                  Bornera 3 pines             DS18B20
3V3    ───────────────  pin 1 (3V3)  ─────────────  rojo
GPIO18 ───────────────  pin 2 (DATA) ─────────────  amarillo
GND    ───────────────  pin 3 (GND)  ─────────────  negro
                        4.7 kΩ entre pin 1 y pin 2

GPIO21 ── 330 Ω ── LED rojo ── GND

GPIO19 ── 220 Ω ── G  MOSFET N  D ── negro del ventilador
                       |         S ── GND
                      10 kΩ
                       |
                      GND

+12 V ──────────────── rojo del ventilador
+12 V ── cátodo [1N4007] ánodo ── negro del ventilador
negro de la fuente 12 V ─────── GND común con el ESP32
```

## 4. Distribución en la única protoboard

El ESP32 va **fuera** de la protoboard (es demasiado ancho); se conecta con
jumpers. La protoboard se divide en tres zonas para no mezclar los 12 V con las
señales de 3.3 V:

| Zona | Contenido | Recomendación |
|---|---|---|
| **A — izquierda** | Bornera de 3 pines, resistencia 4.7 kΩ, LED + 330 Ω | Mantener el sensor lejos del MOSFET |
| **B — centro** | MOSFET, 220 Ω de gate, 10 kΩ gate–source | Cerca del ventilador |
| **C — derecha** | Diodo 1N4007, salida al ventilador, entrada 12 V | Cables de 12 V cortos y cubiertos |
| **Riel inferior** | **GND común** | Unir GND del ESP32 y negro de la fuente |
| **Riel superior** | Solo **3.3 V** | **No** poner 12 V en este riel |

Pasos sugeridos:

1. Con el ESP32 desconectado, montar la bornera y el pull-up de 4.7 kΩ.
2. Montar el LED con su resistencia de 330 Ω.
3. Montar el MOSFET, el divisor de gate (220 Ω + 10 kΩ) y el diodo.
4. Conectar primero **GND común**; después 3.3 V; al final los 12 V.
5. Revisar con multímetro que no haya continuidad entre +12 V y 3.3 V/GND.
6. Alimentar el ESP32 por USB y el ventilador con la fuente de 12 V.

## 5. Firmware

En `firmware/main.py` ajustar:

```python
WIFI_SSID = "TU_RED_WIFI"
WIFI_CLAVE = "TU_CLAVE"
URL_BACKEND = "http://IP_DEL_PC:5000/lecturas"
ID_VITRINA = 1

PIN_SENSOR = 18
PIN_VENTILADOR = 19
PIN_LED = 21

MODO_SALIDA = "mosfet"   # "mosfet", "rele" o "solo_led"
```

- `"mosfet"`: GPIO 19 en alto enciende el ventilador.
- `"rele"`: GPIO 19 en bajo enciende el relé.
- `"solo_led"`: no se conmuta el ventilador; el LED refleja la orden del backend.

El LED siempre se enciende cuando el backend ordena enfriar, aunque el modo sea
`solo_led`. El firmware acepta la respuesta nueva (`salida.ventilador`) y la
anterior (`ventilador`), así que sigue funcionando con versiones viejas del
backend.

Si el ESP32 no trae `urequests`, instalarlo desde el REPL con
`mip.install("urequests")` o copiar `urequests.py` a la placa. Los módulos
`onewire` y `ds18x20` vienen incluidos en el firmware estándar de MicroPython
para ESP32.

## 6. Backend adaptado

Se agregaron dos rutas y campos nuevos, sin romper la API anterior:

| Ruta | Uso |
|---|---|
| `GET /hardware` | Devuelve el mapa de pines y las notas de cableado en JSON |
| `GET /salud` | Prueba de conectividad para el ESP32 (sin tocar la base de datos) |

La respuesta de `POST /lecturas` ahora incluye:

```json
{
  "estado": "FUERA_RANGO_ALTO",
  "ventilador": true,
  "led": true,
  "salida": { "ventilador": true, "led": true },
  "sensor_ok": true,
  "intervalo": 30,
  "modo": "auto"
}
```

`led` es un alias de `ventilador`: el LED rojo indica que la orden de
enfriamiento está activa. No se modificó la base de datos; el historial sigue
guardando el campo `ventilador`.

## 7. Pruebas antes de conectar todo

### 7.1 Fuente de 12 V

Con multímetro, medir la salida del cable del módem:

- Debe dar aproximadamente **12 V DC**.
- Identificar **rojo = positivo** y **negro = negativo**.
- Si el cable es de corriente alterna (AC), **no usarlo**.

### 7.2 DS18B20 solo

En el REPL de MicroPython (Thonny o `mpremote`):

```python
import machine, onewire, ds18x20, time
ds = ds18x20.DS18X20(onewire.OneWire(machine.Pin(18)))
print("ROMs:", ds.scan())          # debe mostrar al menos una dirección
ds.convert_temp()
time.sleep_ms(750)
print("T =", ds.read_temp(ds.scan()[0]), "C")
```

Si `scan()` devuelve `[]`: falta el pull-up de 4.7 kΩ, los cables están
cambiados o el sensor no recibe 3.3 V.

### 7.3 LED y MOSFET

```python
import machine
led = machine.Pin(21, machine.Pin.OUT)
led.value(1)      # LED encendido
led.value(0)      # LED apagado

gate = machine.Pin(19, machine.Pin.OUT)
gate.value(1)     # el ventilador debe girar
gate.value(0)     # el ventilador debe detenerse
```

### 7.4 Backend

```bash
curl http://IP_DEL_PC:5000/salud
curl http://IP_DEL_PC:5000/hardware
```

Simular una lectura alta:

```bash
curl -X POST http://IP_DEL_PC:5000/lecturas ^
  -H "Content-Type: application/json" ^
  -d "{\"id_vitrina\":1,\"temperatura\":9,\"ventilador\":false}"
```

La respuesta debe traer `"ventilador": true` y `"led": true`; el ventilador
debe encenderse. Luego enviar `temperatura: 4` y comprobar que se apaga.

## 8. Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `scan()` vacío | Falta pull-up, cables invertidos | 4.7 kΩ entre DATA y 3.3 V; revisar rojo/amarillo/negro |
| Lectura 85 °C o −127 °C | Sensor sin alimentación o lectura inválida | Revisar 3.3 V, GND y contacto en la bornera |
| LED enciende pero el ventilador no | MOSFET mal cableado o sin GND común | Gate a GPIO 19, source a GND, drain al negro del ventilador |
| Ventilador siempre encendido | Gate flotante, drain/source invertidos o relé activo en bajo | Poner 10 kΩ gate–source; revisar pines; usar `MODO_SALIDA = "rele"` |
| El ESP32 se reinicia al arrancar el ventilador | 12 V conectado al ESP32 o falta diodo | Alimentar por USB, GND común y 1N4007 en paralelo con el ventilador |
| La interfaz dice "sin conexión" | IP incorrecta, firewall o WiFi distinto | Probar `/salud` desde el navegador; misma red; abrir puerto 5000 |
| El ventilador gira al revés | Polaridad del ventilador | Invertir rojo/negro del ventilador (no de la fuente) |

## 9. Seguridad

- No conectar **12 V** a los pines **3V3, 5V, GPIO** del ESP32.
- Unir siempre el **GND** de la fuente de 12 V con el **GND** del ESP32.
- El diodo **1N4007** no es opcional: sin él, el motor genera picos que pueden
  destruir el MOSFET o reiniciar el ESP32.
- No dejar cables pelados de 12 V sobre la protoboard; usar terminales o
  cubrir las uniones.
- Si se usa relé, preferir módulo con optoacoplador y no alimentar la bobina
  desde un GPIO.
