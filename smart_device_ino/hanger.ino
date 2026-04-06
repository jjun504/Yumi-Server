#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>  // Include servo library

#define SERVO_PIN_1 13   // Servo 1, front side
#define SERVO_PIN_2 12   // Servo 2, opposite side

const char *ssid = "OPPO Reno12 5G";
const char *password = "z63ri8fz";

String mqtt_ClientID = "smart_assistant_87";

// Define your topics to subscribe / publish
const char* sub_topic = "smart187/yumi_esp32s_main_room_hanger/control";
const char* pub_topic = "smart187/yumi_esp32s_main_room_hanger/ack";
const char* pub_init_topic = "smart187/yumi_esp32s_main_room_hanger/is_back";
 
// EMQX broker parameters
const char *mqtt_server = "broker.emqx.io";
const char *mqtt_userName = "smart_assistant";
const char *mqtt_password = "alivetoA+";

WiFiClient espClient;
PubSubClient client(espClient);

Servo servo1;  // Front servo
Servo servo2;  // Opposite servo

void setup_wifi() {
    delay(10);
    Serial.println();
    Serial.print("Connecting to ");
    Serial.println(ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    randomSeed(micros());

    Serial.println("");
    Serial.println("WiFi connected");
    Serial.println("IP address: ");
    Serial.println(WiFi.localIP());
}

void moveServosSmooth(int angle1, int angle2) {
    static int current1 = 90;
    static int current2 = 90;

    while (current1 != angle1 || current2 != angle2) {
        if (current1 < angle1) current1++;
        else if (current1 > angle1) current1--;

        if (current2 < angle2) current2++;
        else if (current2 > angle2) current2--;

        servo1.write(current1);
        servo2.write(current2);

        delay(90);  // Control speed, higher value means slower movement
    }
}


void callback(char *topic, byte *payload, unsigned int length) {
    Serial.print("Message arrived [");
    Serial.print(topic);
    Serial.print("] ");
    for (int i = 0; i < length; i++) {
        Serial.print((char)payload[i]);
    }
    Serial.println();

    payload[length] = '\0';  // Important
    String message = (char *)payload;

    if (strcmp(topic, sub_topic) == 0) {
        if (message == "True") {
            moveServosSmooth(40, 140);  // GPIO13 = 40°, GPIO12 = 140°
            client.publish(pub_topic, "Servos moved: ON");
        }
        else if (message == "False") {
            moveServosSmooth(15, 165);  // GPIO13 = 15°, GPIO12 = 165°
            client.publish(pub_topic, "Servos moved: OFF");
        }
    }
}

void reconnect() {
    while (!client.connected()) {
        Serial.println("Attempting EMQX MQTT connection...");
        String clientId = mqtt_ClientID + String(random(0xffff), HEX);  // Avoid ID conflicts
        if (client.connect(clientId.c_str(), mqtt_userName, mqtt_password)) {
            Serial.print("Connected with Client ID: ");
            Serial.println(clientId);
            client.publish(pub_init_topic, "Hi, I'm online!");
            client.subscribe(sub_topic);
        } else {
            Serial.print("failed, rc=");
            Serial.print(client.state());
            Serial.println(" try again in 5 seconds");
            delay(5000);
        }
    }
}

void setup() {
    Serial.begin(115200);
    setup_wifi();
    client.setServer(mqtt_server, 1883);
    client.setCallback(callback);

    // Initialize PWM period
    servo1.setPeriodHertz(50);
    servo2.setPeriodHertz(50);

    // Wait a bit before attaching servos (to stabilize voltage)
    delay(1000);

    // Attach servos
    servo1.attach(SERVO_PIN_1, 500, 2400);
    servo2.attach(SERVO_PIN_2, 500, 2400);

    // Set default buffer angle (e.g., 90 degrees)
    servo1.write(40);
    servo2.write(140);

    // Wait for servos to slowly move to target angle
    delay(1000);
}


void loop() {
    if (!client.connected()) {
        reconnect();
    }
    client.loop();
}
