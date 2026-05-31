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
//OTA update:
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <AsyncElegantOTA.h>
#include <FastLED.h>

// Replace the next variables with your SSID/Password combination
const char* ssid = "dlink";
const char* password = ".MoNitor2?";

// Add your MQTT Broker IP address, example:
const char* mqtt_server = "192.168.0.136"; //!!! mqqt server

//light
#define NUM_LEDS 47 //!!!
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

  pinMode(ledPin, OUTPUT);

  //SETUP 
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
  ///!!! tohle neni odzkouseny:
  server.on("/ON", HTTP_GET, [](AsyncWebServerRequest* request) {
      Serial.println("http lighston:");
      Lights(true);
      AsyncWebServerResponse* response = request->beginResponse_P(200, "text/html; charset=utf-8", "on");
      request->send(response);
  });
  ///!!! tohle neni odzkouseny:
  server.on("/OFF", HTTP_GET, [](AsyncWebServerRequest* request) {
      Serial.println("http lighstoff:");
      Lights(false);
      AsyncWebServerResponse* response = request->beginResponse_P(200, "text/html; charset=utf-8", "off");
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

  //!!!esp32/output - nastaveni mqqt topicu, zpráva je jako plain string - lighston nebo lighstoff
  if (String(topic) == "esp32/output") {
    Serial.print("Changing output to ");
    if(messageTemp == "lighston"){
      Serial.println("lighston:");
      Lights(true);
    }
    else if(messageTemp == "lighstoff"){
      Serial.println("lighstoff:");
      Lights(false);
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
    if (!client.connected()) {
    reconnect();
  }
  client.loop();

}

void Lights(bool onoff) {

    if (onoff) {
      // Set all LEDs to blue
      Serial.println("Lights on"); 
      for (int i = 0; i < NUM_LEDS; i++) {
          leds[i] = CRGB::Blue; //!!!jednoduche nastaveni barev
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