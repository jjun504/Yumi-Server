/*
 Basic ESP8266 MQTT example
 This sketch demonstrates the capabilities of the pubsub library in combination
 with the ESP8266 board/library.
 It connects to an MQTT server then:
  - publishes "hello world" to the topic "outTopic" every two seconds
  - subscribes to the topic "inTopic", printing out any messages
    it receives. NB - it assumes the received payloads are strings not binary
  - If the first character of the topic "inTopic" is an 1, switch ON the ESP Led,
    else switch it off
 It will reconnect to the server if the connection is lost using a blocking
 reconnect function. See the 'mqtt_reconnect_nonblocking' example for how to
 achieve the same result without blocking the main loop.
 To install the ESP8266 board, (using Arduino 1.6.4+):
  - Add the following 3rd party board manager under "File ->; Preferences ->; Additional Boards Manager URLs":
       http://arduino.esp8266.com/stable/package_esp8266com_index.json
  - Open the "Tools ->; Board ->; Board Manager" and click install for the ESP8266"
  - Select your ESP8266 in "Tools ->; Board"
*/
 
#include <ESP8266WiFi.h>;
#include <PubSubClient.h>;
#include <EasyButton.h>;
#define LED 2        //built-in LED on ESP32
#define LED2 14        //built-in LED on ESP32
 
// Update these with values suitable for your network.
const char *ssid = "Green Apples";
const char *password = "GreenApple3249";
 
// Define your client ID on EMQX
String mqtt_ClientID = "smart_assistant_87";

// Define your topics to subscribe / publish
const char* sub_topic = "smart187/yumi_esp32s_main_room_light/control";
const char* pub_topic = "smart187/yumi_esp32s_main_room_light/ack";
const char* pub_init_topic = "smart187/yumi_esp32s_main_room_light/is_back";

// Define topics for LED2 (GPIO 14)
const char* sub_topic_led2 = "smart187/yumi_esp32s_main_room_light2/control";
const char* pub_topic_led2 = "smart187/yumi_esp32s_main_room_light2/ack";
const char* pub_init_topic_led2 = "smart187/yumi_esp32s_main_room_light2/is_back";
 
// EMQX broker parameters
const char *mqtt_server = "broker.emqx.io";
const char *mqtt_userName = "smart_assistant";
const char *mqtt_password = "alivetoA+";
 
WiFiClient espClient;
PubSubClient client(espClient);
unsigned long lastMsg = 0;
#define MSG_BUFFER_SIZE (50)
char msg[MSG_BUFFER_SIZE];
int value = 0;
 
void setup_wifi()
{
    delay(10);
    // We start by connecting to a WiFi network
    Serial.println();
    Serial.print("Connecting to ");
    Serial.println(ssid);
 
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);
 
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
 
    randomSeed(micros());
 
    Serial.println("");
    Serial.println("WiFi connected");
    Serial.println("IP address: ");
    Serial.println(WiFi.localIP());
}
 
void callback(char *topic, byte *payload, unsigned int length)
{
    Serial.print("Message arrived [");
    Serial.print(topic);
    Serial.print("] ");
    for (int i = 0; i < length; i++)
    {
        Serial.print((char)payload[i]);
    }
    Serial.println();
 
    payload[length] = '\0';
    String message = (char *)payload;
    
    // Control for LED (GPIO 2)
    if (strcmp(topic, sub_topic) == 0)
    {
        if (message == "False")
        {
            digitalWrite(LED, LOW); //Turn off
            client.publish(pub_topic, "LED off");
        }
        if (message == "True")
        {
            digitalWrite(LED, HIGH); //Turn on
            client.publish(pub_topic, "LED on");
        }
        if (message == "flash")
        {
            digitalWrite(LED, LOW); //LED flashing 2 times
            delay(200);
            digitalWrite(LED, HIGH); 
            delay(200);
            digitalWrite(LED, LOW); 
            delay(200);
            digitalWrite(LED, HIGH); 
            delay(200);
            digitalWrite(LED, LOW); 
            client.publish(pub_topic, "LED flashed 2 times");
        }        
    }
    
    // Control for LED2 (GPIO 14)
    if (strcmp(topic, sub_topic_led2) == 0)
    {
        if (message == "False")
        {
            digitalWrite(LED2, LOW); //Turn off
            client.publish(pub_topic_led2, "LED2 off");
        }
        if (message == "True")
        {
            digitalWrite(LED2, HIGH); //Turn on
            client.publish(pub_topic_led2, "LED2 on");
        }
        if (message == "flash")
        {
            digitalWrite(LED2, LOW); //LED2 flashing 2 times
            delay(200);
            digitalWrite(LED2, HIGH); 
            delay(200);
            digitalWrite(LED2, LOW); 
            delay(200);
            digitalWrite(LED2, HIGH); 
            delay(200);
            digitalWrite(LED2, LOW); 
            client.publish(pub_topic_led2, "LED2 flashed 2 times");
        }
        if (message == "blink")
        {
            // LED2 continuous blinking 5 times
            for(int i = 0; i < 5; i++) {
                digitalWrite(LED2, HIGH);
                delay(100);
                digitalWrite(LED2, LOW);
                delay(100);
            }
            client.publish(pub_topic_led2, "LED2 blinked 5 times");
        }        
    }
 
    /* Switch on the LED if an 1 was received as first character
    // if ((char)payload[0] == '1')
    // {
    //     digitalWrite(BUILTIN_LED, LOW); // Turn the LED on (Note that LOW is the voltage level
    //                                     // but actually the LED is on; this is because
    //                                     // it is active low on the ESP-01)
    // }
    // else
    // {
    //     digitalWrite(BUILTIN_LED, HIGH); // Turn the LED off by making the voltage HIGH
    // } */
}
 
void reconnect()
{
    // Loop until we're reconnected
    while (!client.connected())
    {
 
        Serial.println("Attempting EMQX MQTT connection...");
        // Create a random client ID
        String clientId = mqtt_ClientID + String(random(0xffff), HEX);
        // Attempt to connect
        if (client.connect(clientId.c_str(), mqtt_userName, mqtt_password))
        {
            Serial.print(" connected with Client ID: ");
            Serial.println(mqtt_ClientID);
            // Once connected, publish an announcement...
            client.publish(pub_init_topic, "Hi, I'm online!");
            client.publish(pub_init_topic_led2, "Hi, LED2 is online!");
            // ... and resubscribe
            client.subscribe(sub_topic);
            client.subscribe(sub_topic_led2);
        }
        else
        {
            Serial.print("failed, rc=");
            Serial.print(client.state());
            Serial.println(" try again in 5 seconds");
            // Wait 5 seconds before retrying
            delay(5000);
        }
    }
}
 
void setup()
{
    pinMode(LED, OUTPUT); // Initialize the LED pin as an output
    pinMode(LED2, OUTPUT); // Initialize the LED2 pin as an output
    digitalWrite(LED, LOW); //default ESP32 LOW is turn off
    digitalWrite(LED2, LOW); //default LED2 LOW is turn off
 
    Serial.begin(115200);
    setup_wifi();
    client.setServer(mqtt_server, 1883);
    client.setCallback(callback);
}
 
void loop()
{
 
    if (!client.connected())
    {
        reconnect();
    }
    client.loop();
 
    /* unsigned long now = millis();
    // if (now - lastMsg >; 2000)
    // {
    //     lastMsg = now;
    //     ++value;
    //     snprintf(msg, MSG_BUFFER_SIZE, "hello world #%ld", value);
    //     Serial.print("Publish message: ");
    //     Serial.println(msg);
    //     client.publish("stonez56/esp32s_button_pushed", msg);
    // } */
}