int sensorPin = A0;
float voltaje;
float distancia;

void setup() {
  Serial.begin(9600);
}

void loop() {
  int lectura = analogRead(sensorPin);
  voltaje = lectura * (5.0 / 1023.0);

  distancia = 33.555 * pow(voltaje, -1.649);

 // Serial.print(""Distancia: "");
 Serial.println(distancia);
  //Serial.println("" cm"");

    //Serial.print(""Voltaje: "");
  Serial.println(voltaje);
  //Serial.println("" V"");

  delay(1000);
}
