#include <HCSR04.h>
#include <Wire.h>
#include <VL53L0X.h>

VL53L0X sensor;

#define LONG_RANGE
#define HIGH_ACCURACY

UltraSonicDistanceSensor distanceSensor(10, 9);
int pinSensorSharp = A0;

void setupVL53L0X(){
  Wire.begin();
  sensor.setTimeout(500);

  if (!sensor.init()) {
    Serial1.println("Error: no se detecto el VL53L0X. Revisa el cableado SDA/SCL.");
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
  return 1.023*distancia_ultrasonico-0.7744;
  }

float medicionVL53L0X() {
  if (sensor.timeoutOccurred()) { Serial1.print(" TIMEOUT"); }
  float medicion_vl53 = sensor.readRangeSingleMillimeters()*0.1;
  return medicion_vl53*0.9078947368;

}

float medicionSHARP() {
  int lectura = analogRead(pinSensorSharp);
  float voltaje = lectura * (5.0 / 1023.0);
  float distancia_Sharp = 33.555 * pow(voltaje, -1.649);
  return 8.8707*exp(0.0319*distancia_Sharp);
}

void setup() {
  Serial1.begin(9600);
  setupVL53L0X();
}

void loop() {
  float medicionSHARP_ = medicionSHARP();
  float medicionVL53L0X_ = medicionVL53L0X();
  float medicionUltrasonico_ = medicionUltrasonico();

  // Envía el primer valor como texto (ej: "23.45")
  Serial1.print(medicionSHARP_);
  Serial1.print(",");
  
  // Envía el segundo valor
  Serial1.print(medicionVL53L0X_);
  Serial1.print(",");
  
  // Envía el tercer valor y agrega un salto de línea al final
  Serial1.println(medicionUltrasonico_);
}