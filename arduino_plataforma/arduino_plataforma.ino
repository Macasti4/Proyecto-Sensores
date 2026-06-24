#include <HCSR04.h>
#include <Wire.h>
#include <VL53L0X.h>

VL53L0X sensor;

#define LONG_RANGE
#define HIGH_ACCURACY

UltraSonicDistanceSensor distanceSensor(10, 9);
int pinSensorSharp = A0;

void setupVL53L0X() {
  Wire.begin();
  sensor.setTimeout(500);

  if (!sensor.init()) {
    Serial.println("Error: no se detecto el VL53L0X. Revisa el cableado SDA/SCL.");
    while (1) {}
  }

#if defined LONG_RANGE
  sensor.setSignalRateLimit(0.1);
  sensor.setVcselPulsePeriod(VL53L0X::VcselPeriodPreRange, 18);
  sensor.setVcselPulsePeriod(VL53L0X::VcselPeriodFinalRange, 14);
#endif

#if defined HIGH_SPEED
  sensor.setMeasurementTimingBudget(20000);
#elif defined HIGH_ACCURACY
  sensor.setMeasurementTimingBudget(100000);
#endif
}

float medicionUltrasonico() {
  float distancia_ultrasonico = distanceSensor.measureDistanceCm();

  if (distancia_ultrasonico < 0) {
    return 0;
  }

  return 1.023 * distancia_ultrasonico - 0.7744;
}

float medicionVL53L0X() {
  float medicion_vl53 = sensor.readRangeSingleMillimeters() * 0.1;

  if (sensor.timeoutOccurred()) {
    return 0;
  }

  return medicion_vl53;
}

float medicionSHARP() {
  int lectura = analogRead(pinSensorSharp);
  float voltaje = lectura * (5.0 / 1023.0);

  if (voltaje <= 0.05) {
    return 0;
  }

  float distancia_Sharp = 33.555 * pow(voltaje, -1.649);
  return 8.8707 * exp(0.0319 * distancia_Sharp);
}

void setup() {
  Serial.begin(9600);     // Monitor serial para depuración
  Serial1.begin(9600);    // Comunicación hacia el Arduino del stepper

  setupVL53L0X();
}

void loop() {
  delay(160);

  float d_us = medicionUltrasonico();
  float d_ir = medicionSHARP();
  float d_laser = medicionVL53L0X();

  float d_us_1 = medicionUltrasonico();
  float d_ir_1 = medicionSHARP();
  float d_laser_1 = medicionVL53L0X();

  d_us = (d_us + d_us_1) / 2.0;
  d_ir = (d_ir + d_ir_1) / 2.0;
  d_laser = (d_laser + d_laser_1) / 2.0;

  // Orden:
  // US, IR, LASER
  Serial1.print(d_us);
  Serial1.print(",");

  Serial1.print(d_ir);
  Serial1.print(",");

  Serial1.println(d_laser);

  //Serial.print("US: ");
  //Serial.print(d_us);
  //Serial.print(" | IR: ");
  //Serial.print(d_ir);
  //Serial.print(" | LASER: ");
  //Serial.println(d_laser);
}