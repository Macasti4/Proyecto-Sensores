// Bobina A (puente H 1)
const int A_IN1 = 2;
const int A_IN2 = 3;

// Bobina B (puente H 2)
const int B_IN1 = 7;
const int B_IN2 = 12;

// Stepper
const int PASOS_VUELTA = 200;

int pasoMotor = 0;     // Cuenta real de pasos: 0 a 199
int faseStepper = 0;   // Fase eléctrica: 0 a 3

String datosSensores = "";

void setup() {

  Serial.begin(9600);    // Hacia la PC / Monitor Serial
  Serial1.begin(9600);   // Recibe datos del otro Arduino

  pinMode(A_IN1, OUTPUT);
  pinMode(A_IN2, OUTPUT);
  pinMode(B_IN1, OUTPUT);
  pinMode(B_IN2, OUTPUT);

  apagarTodo();
}

void apagarTodo() {
  digitalWrite(A_IN1, LOW);
  digitalWrite(A_IN2, LOW);
  digitalWrite(B_IN1, LOW);
  digitalWrite(B_IN2, LOW);
}

void setBobinaA(int sentido) {
  if (sentido > 0) {
    digitalWrite(A_IN1, HIGH);
    digitalWrite(A_IN2, LOW);
  } else {
    digitalWrite(A_IN1, LOW);
    digitalWrite(A_IN2, HIGH);
  }
}

void setBobinaB(int sentido) {
  if (sentido > 0) {
    digitalWrite(B_IN1, HIGH);
    digitalWrite(B_IN2, LOW);
  } else {
    digitalWrite(B_IN1, LOW);
    digitalWrite(B_IN2, HIGH);
  }
}

void ejecutarPaso(int fase) {

  switch (fase) {

    case 0:
      setBobinaA(1);
      setBobinaB(1);
      break;

    case 1:
      setBobinaA(1);
      setBobinaB(-1);
      break;

    case 2:
      setBobinaA(-1);
      setBobinaB(-1);
      break;

    case 3:
      setBobinaA(-1);
      setBobinaB(1);
      break;
  }
}

void moverUnPasoAdelante() {
  ejecutarPaso(faseStepper);

  faseStepper++;

  if (faseStepper > 3) {
    faseStepper = 0;
  }

  pasoMotor++;

  if (pasoMotor >= PASOS_VUELTA) {
    pasoMotor = 0;
  }
}

void loop() {

  if (Serial1.available()) {
    char c = Serial1.read();

    if (c == '\n') {
      datosSensores.trim();

      if (datosSensores.length() > 0) {

        Serial.print(pasoMotor);
        Serial.print(",");
        Serial.println(datosSensores);

        moverUnPasoAdelante();

        delay(200);
      }

      datosSensores = "";
    } 
    else {
      datosSensores += c;
    }
  }
}