/***************************************************************************
  This is a library for the BMP280 humidity, temperature & pressure sensor

  Designed specifically to work with the Adafruit BMP280 Breakout
  ----> http://www.adafruit.com/products/2651

  These sensors use I2C or SPI to communicate, 2 or 4 pins are required
  to interface.

  Adafruit invests time and resources providing this open source code,
  please support Adafruit andopen-source hardware by purchasing products
  from Adafruit!

  Written by Limor Fried & Kevin Townsend for Adafruit Industries.
  BSD license, all text above must be included in any redistribution
 ***************************************************************************/

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
//#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
//OTA update:
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <AsyncElegantOTA.h>
#include <FastLED.h>

Adafruit_BMP280 bmp; 

//DHT SENSOR:
#include "DHT.h"
#define pinDHT 13
#define typDHT11 DHT11
DHT temperatureSensor(pinDHT, typDHT11);

//LIGHT SENSOR:
const int pResistor = 34;

// Replace the next variables with your SSID/Password combination
const char* ssid = "dlink";
const char* password = ".MoNitor2?";

// Add your MQTT Broker IP address, example:
//const char* mqtt_server = "192.168.1.144";
const char* mqtt_server = "192.168.0.136";

//light
#define NUM_LEDS 47
#define DATA_PIN 5
// Define the array of leds
CRGB leds[NUM_LEDS];
// Array of indices of the LEDs that should blink red
int blinkingLEDs[] = {1, 3, 5, 7, 9}; // Change these to the indices of the LEDs you want to blink
int numBlinkingLEDs = sizeof(blinkingLEDs) / sizeof(blinkingLEDs[0]);

WiFiClient espClient;
PubSubClient client(espClient);
long lastMsg = 0;
char msg[50];
int value = 0;

float temperature = 0;
float humidity = 0;
float pressure = 0;
float temperatureDHT = 0;
// LED Pin
const int ledPin = 4;

AsyncWebServer server(80);

void setup() {
  Serial.begin(115200);

  setup_wifi();

  Serial.println(F("BMP280 Forced Mode Test."));
  int i2cReport [20];
  Scanner(i2cReport);
  temperatureSensor.begin(); // initialize the DHT sensor

  //if (!bmp.begin(BMP280_ADDRESS_ALT, BMP280_CHIPID)) {
  if (!bmp.begin(0x76)) {
    Serial.println(F("Could not find a valid BMP280 sensor, check wiring or "
                      "try a different address!"));
    while (1) delay(10);
  }
    /* Default settings from datasheet. */
  bmp.setSampling(Adafruit_BMP280::MODE_FORCED,     /* Operating Mode. */
                  Adafruit_BMP280::SAMPLING_X2,     /* Temp. oversampling */
                  Adafruit_BMP280::SAMPLING_X16,    /* Pressure oversampling */
                  Adafruit_BMP280::FILTER_X16,      /* Filtering. */
                  Adafruit_BMP280::STANDBY_MS_500); /* Standby time. */

  pinMode(ledPin, OUTPUT);

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);

 //String responseBasic = "Hi! I am ESP32 on "+String(WiFi.localIP());
  server.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
      Serial.print("Hi! I am ESP32-Meteostanice ");
      AsyncWebServerResponse* response = request->beginResponse_P(200, "text/html; charset=utf-8", "Hi! I am ESP32-Meteostanice-v1");
      request->send(response);
  });

  server.on("/IP", HTTP_GET, [](AsyncWebServerRequest* request) {
      IPAddress ip = WiFi.localIP();
      Serial.println(ip);
      AsyncWebServerResponse* response = request->beginResponse_P(200, "text/html; charset=utf-8", WiFi.localIP().toString().c_str());
      request->send(response);
  });

  server.on("/ID", HTTP_GET, [](AsyncWebServerRequest* request) {
      String id = getID();
      Serial.println(id);
      AsyncWebServerResponse* response = request->beginResponse_P(200, "text/html; charset=utf-8", id.c_str());
      request->send(response);
  });

  AsyncElegantOTA.begin(&server);    // Start ElegantOTA
  server.begin();

  FastLED.addLeds<WS2812B, DATA_PIN, GRB>(leds, NUM_LEDS);  // GRB ordering is typical

}

void setup_wifi() {
  delay(10);
  // We start by connecting to a WiFi network
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* message, unsigned int length) {
  Serial.print("Message arrived on topic: ");
  Serial.print(topic);
  Serial.print(". Message: ");
  String messageTemp;
  
  for (int i = 0; i < length; i++) {
    Serial.print((char)message[i]);
    messageTemp += (char)message[i];
  }
  Serial.println();

  // Feel free to add more if statements to control more GPIOs with MQTT

  // If a message is received on the topic esp32/output, you check if the message is either "on" or "off". 
  // Changes the output state according to the message
  if (String(topic) == "esp32/output") {
    Serial.print("Changing output to ");
    if(messageTemp == "on"){
      Serial.println("on");
      digitalWrite(ledPin, HIGH);
    }
    else if(messageTemp == "off"){
      Serial.println("off");
      digitalWrite(ledPin, LOW);
    }
    else if(messageTemp == "measurenow"){
      Serial.println("measurenow");
      Measurement();
    }
    else if(messageTemp == "lighston"){
      Serial.println("lighston:");
      Lights(true);
    }
    else if(messageTemp == "lighstoff"){
      Serial.println("lighstoff:");
      Lights(false);
    }
    else if(messageTemp == "lighstblinking"){
      Serial.println("measurenow");
      Blinking();
    }
  }
}

void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Attempt to connect
    if (client.connect("ESP8266Client")) {
      Serial.println("connected");
      // Subscribe
      client.subscribe("esp32/output");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
  }
}

void loop() {
//Serial.print("Loop");
    if (!client.connected()) {
    reconnect();
  }
  client.loop();



  long now = millis();

// Serial.println("lastMsg");
// Serial.println(lastMsg);
 
// Serial.println(now);

  //kazdych 15 minut
  //TODO co configu..
  if (now - lastMsg > 1000*60*5) {
    Serial.println("loop");
    lastMsg = now;
    Measurement();
  }

}

void Lights(bool onoff) {

    if (onoff) {
      // Set all LEDs to blue
      Serial.println("Lights on"); 
      for (int i = 0; i < NUM_LEDS; i++) {
          leds[i] = CRGB::Blue;
      }
      FastLED.show();
    }
    else {
      Serial.println("Lights off"); 
      for (int i = 0; i < NUM_LEDS; i++) {
          leds[i] = CRGB::Black;
      }
      FastLED.show();
    }
}

//not supported like this!
void Blinking() {
      // Set all LEDs to blue
    for (int i = 0; i < NUM_LEDS; i++) {
        leds[i] = CRGB::Blue;
    }

    // Make specific LEDs blink red
    for (int i = 0; i < numBlinkingLEDs; i++) {
        leds[blinkingLEDs[i]] = CRGB::Red; // Set the LED to red
    }

    FastLED.show();
    delay(500);  // Pause for half a second

    // Turn off the blinking LEDs (set them back to blue)
    for (int i = 0; i < numBlinkingLEDs; i++) {
        leds[blinkingLEDs[i]] = CRGB::Blue; // Set the LED back to blue
    }

    FastLED.show();
    delay(500);  // Pause for half a second
}

void Measurement() {
      if (bmp.takeForcedMeasurement()) {
    temperature = bmp.readTemperature();  
    Serial.println(temperature); 
    // Uncomment the next line to set temperature in Fahrenheit 
    // (and comment the previous temperature line)
    //temperature = 1.8 * bmp.readTemperature() + 32; // Temperature in Fahrenheit
    
    // Convert the value to a char array
    char tempString[8];
    dtostrf(temperature, 1, 2, tempString);
    Serial.print("Temperature: ");
    Serial.println(tempString);
    client.publish("esp32/temperature", tempString);

    pressure = bmp.readPressure();
    Serial.println(pressure);
    //Convert the value to a char array
    char pressureString[16];
    dtostrf(pressure, 1, 2, pressureString);
    Serial.print("Pressure: ");
    Serial.println(pressureString);
    client.publish("esp32/pressure", pressureString);
    Serial.println("client.publish pressure");
    }
    else {
      Serial.println("problem");
    }
    Serial.println("call getHuminidy");
    humidity = getHuminidy();
    //Convert the value to a char array
    char humString[8];
    dtostrf(humidity, 1, 2, humString);
    Serial.print("Humidity: ");
    Serial.println(humString);
    client.publish("esp32/humidity", humString);

    temperatureDHT= getTemperatureDHT();
    char temperatureDHTString[8];
    dtostrf(temperatureDHT, 1, 2, temperatureDHTString);
    Serial.print("TemperatureDHT: ");
    Serial.println(temperatureDHTString);
    client.publish("esp32/temperatureDHT", temperatureDHTString);

}

float getHuminidy() {
  Serial.println("getHuminidy");
  float _vlhkost = 0;
  _vlhkost = temperatureSensor.readHumidity();
  Serial.println("after getHuminidy");
  if (isnan(_vlhkost)) {

    Serial.println("Chyba pri cteni vlhkosti z DHT senzoru!");
  }
  else {
    Serial.println("Vlhkost: " + String(_vlhkost) + " %");
  }
  return _vlhkost;
}

float getTemperatureDHT() {
  //Serial.println("DHT readTemperature");
  float _vnitrniTeplota = 0;
  _vnitrniTeplota = temperatureSensor.readTemperature();

  if (isnan(_vnitrniTeplota)) {

    Serial.println("Chyba pri cteni teploty z DHT senzoru!");
  }
  else {
    Serial.println("DHT teplota:  " + String(_vnitrniTeplota) + ".");
  }

  return _vnitrniTeplota;
}

int getLightIntensity() {

  int lightInt = analogRead(pResistor);
  Serial.println("LightIntensity:" + String(lightInt));
  return lightInt;
}

String getID(){
    String id = "";
    #if defined(ESP8266)
        id = String(ESP.getChipId());
    #elif defined(ESP32)
        id = String((uint32_t)ESP.getEfuseMac(), HEX);
    #endif
    id.toUpperCase();
    return id;
}

void Scanner(int * i2cReport ) {

  Serial.println();
  Serial.println("I2C scanner. Scanning ...");
  byte count = 0;

  Wire.begin();
  for (byte i = 8; i < 120; i++) {
    Wire.beginTransmission(i);        // Begin I2C transmission Address (i)
    if (Wire.endTransmission() == 0)  // Receive 0 = success (ACK response)
    {
      Serial.print("Found address: ");
      Serial.print(i, DEC);
      Serial.print(" (0x");
      Serial.print(i, HEX);  // PCF8574 7 bit address
      Serial.println(")");
      //TODO: i2cReport
      i2cReport[count]= i;
      count++;
    }
  }
  Serial.print("Found ");
  Serial.print(count, DEC);  // numbers of devices
  Serial.println(" device(s).");
}
