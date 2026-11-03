// arduino_uno.ino - Monitor de Vitrina (Arduino UNO R3)
//
// Lee un DS18B20, controla un ventilador de 12 V por MOSFET (o relé) y envía
// las lecturas por USB serie al PC, donde puente_serial.py las publica en el
// backend Flask. El backend responde con la orden del ventilador y el intervalo.
//
// Conexiones (una sola protoboard):
//   DS18B20 : VCC -> 5 V, GND -> GND, DATA -> D2
//             Resistencia de 4.7 kOhm entre DATA y 5 V (pull-up obligatorio).
//             Bornera de 3 pines: 1 = 5V, 2 = DATA (D2), 3 = GND.
//   LED rojo: D4 -> resistencia 330 Ohm -> ánodo LED -> cátodo -> GND.
//   Ventilador 12 V:
//             - MOSFET canal N logic-level (IRLZ44N / IRL540N):
//               D3 -> 220 Ohm -> gate; 10 kOhm entre gate y GND;
//               source -> GND; drain -> negro del ventilador;
//               rojo del ventilador -> +12 V.
//               Diodo 1N4007 en paralelo con el ventilador:
//               cátodo a +12 V, ánodo al drain.
//             - Módulo relé: IN -> D3, VCC -> 5 V, GND -> GND;
//               COM -> +12 V, NO -> rojo del ventilador.
//             - Sin MOSFET ni relé: ventilador directo a 12 V y el LED solo
//               indica la orden (modo demostración).
//   IMPORTANTE: un pin del Arduino no puede alimentar el ventilador de 12 V.
//               Une el GND de la fuente de 12 V con el GND del Arduino.
//               Alimenta el Arduino por USB, no con los 12 V.
//
// Protocolo por USB serie (115200 baudios):
//   Arduino -> PC : L,<temperatura>,<ventilador>,<sensor_ok>
//                   E,<ventilador>                 (sensor desconectado)
//   PC -> Arduino : V,<0|1>                        (orden del ventilador)
//                   I,<segundos>                   (intervalo de lectura)
//
// Librerías necesarias en Arduino IDE:
//   - OneWire (Paul Stoffregen)
//   - DallasTemperature (Miles Burton)
//
// Placa: Arduino Uno. Puerto: el que aparezca al conectar el USB.

#include <OneWire.h>
#include <DallasTemperature.h>

// ---------------- Configuración ----------------
#define PIN_SENSOR      2     // D2, DATA del DS18B20
#define PIN_VENTILADOR  3     // D3, gate del MOSFET o IN del relé
#define PIN_LED         4     // D4, LED rojo de estado

// 0 = MOSFET (activo en alto), 1 = relé (activo en bajo), 2 = solo LED
#define TIPO_SALIDA     0

#define BAUDIOS         115200
#define INTERVALO_INICIAL_S 30
#define INTERVALO_MIN_S 10
#define INTERVALO_MAX_S 60

// Regla local de respaldo (si el PC/backend no responde)
#define LOCAL_MAX       6.0
#define LOCAL_HISTERESIS 1.0

OneWire oneWire(PIN_SENSOR);
DallasTemperature sensor(&oneWire);

unsigned long intervaloMs = (unsigned long)INTERVALO_INICIAL_S * 1000UL;
unsigned long ultimaLectura = 0;
unsigned long ultimaOrden = 0;
bool ventilador = false;
bool ordenRemota = false;

// ---------------- Prototipos ----------------
void aplicarLed(bool encendido);
void aplicarVentilador(bool encendido);
void atenderSerial();
void leerYEnviar();

// ---------------- Actuadores ----------------
void aplicarLed(bool encendido) {
  digitalWrite(PIN_LED, encendido ? HIGH : LOW);
}

void aplicarVentilador(bool encendido) {
  ventilador = encendido;

  if (TIPO_SALIDA == 2) {          // solo LED: no se conmuta el ventilador
    aplicarLed(encendido);
    return;
  }

  bool nivel = encendido;
  if (TIPO_SALIDA == 1) {          // relé activo en bajo
    nivel = !nivel;
  }
  digitalWrite(PIN_VENTILADOR, nivel ? HIGH : LOW);
  aplicarLed(encendido);
}

// ---------------- Comunicación serie ----------------
void atenderSerial() {
  while (Serial.available() > 0) {
    String linea = Serial.readStringUntil('\n');
    linea.trim();

    if (linea.startsWith("V,")) {
      bool encender = linea.substring(2).toInt() != 0;
      aplicarVentilador(encender);
      ordenRemota = true;
      ultimaOrden = millis();
    } else if (linea.startsWith("I,")) {
      long segundos = linea.substring(2).toInt();
      if (segundos < INTERVALO_MIN_S) segundos = INTERVALO_MIN_S;
      if (segundos > INTERVALO_MAX_S) segundos = INTERVALO_MAX_S;
      intervaloMs = (unsigned long)segundos * 1000UL;
    }
  }
}

// ---------------- Lectura y envío ----------------
void leerYEnviar() {
  sensor.requestTemperatures();

  // Espera no bloqueante de 750 ms (conversión a 12 bits). Mientras tanto se
  // atienden las órdenes que llegan del puente serial.
  unsigned long inicio = millis();
  while (millis() - inicio < 750UL) {
    atenderSerial();
    delay(10);
  }

  float t = sensor.getTempCByIndex(0);
  bool ok = (t > -55.0 && t < 125.0 && t != 85.0 && t != -127.0);

  if (ok) {
    Serial.print("L,");
    Serial.print(t, 2);
    Serial.print(",");
    Serial.print(ventilador ? 1 : 0);
    Serial.print(",1");
    Serial.println();
  } else {
    Serial.print("E,");
    Serial.println(ventilador ? 1 : 0);
  }

  // Si el backend no ha enviado una orden reciente, se usa la regla local.
  // Así el ventilador sigue protegiendo el producto si se cae el PC.
  unsigned long timeout = 3UL * intervaloMs + 5000UL;
  if (!ordenRemota || (millis() - ultimaOrden > timeout)) {
    if (ok) {
      if (t > LOCAL_MAX) {
        aplicarVentilador(true);
      } else if (t <= LOCAL_MAX - LOCAL_HISTERESIS) {
        aplicarVentilador(false);
      }
    }
    ordenRemota = false;
  }
}

// ---------------- Programa principal ----------------
void setup() {
  Serial.begin(BAUDIOS);
  Serial.setTimeout(30);

  pinMode(PIN_VENTILADOR, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  aplicarVentilador(false);
  aplicarLed(false);

  sensor.begin();
  sensor.setResolution(12);

  Serial.println("READY,Arduino UNO R3");

  // Fuerza una primera lectura inmediata.
  ultimaLectura = millis() - intervaloMs;
}

void loop() {
  atenderSerial();

  if (millis() - ultimaLectura >= intervaloMs) {
    ultimaLectura = millis();
    leerYEnviar();
  }
}
