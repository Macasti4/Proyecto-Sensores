// Bobina A puente H 1
const int A_IN1 = 5;
const int A_IN2 = 2;

// Bobina B puente H 2
const int B_IN1 = 11;
const int B_IN2 = 12;

// Stepper
const int PASOS_VUELTA = 200;

int pasoMotor = 0;
int faseStepper = 0;

String datosSensores = "";

void setup() {
  Serial.begin(9600);     // Hacia la PC / GUI
  Serial1.begin(9600);    // Recibe datos del Arduino de sensores

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

  if (faseStepper >= 4) {
    faseStepper = 0;
  }

  pasoMotor++;

  if (pasoMotor >= PASOS_VUELTA) {
    pasoMotor = 0;
  }
}

void loop() {
  while (Serial1.available()) {
    char c = Serial1.read();

    if (c == '\n') {
      datosSensores.trim();

      if (datosSensores.length() > 0) {
        // Formato hacia la GUI:
        // pasoMotor,US,IR,LASER
        Serial.print(pasoMotor);
        Serial.print(",");
        Serial.println(datosSensores);

        moverUnPasoAdelante();
      }

      datosSensores = "";
    } else {
      datosSensores += c;
    }
  }
}